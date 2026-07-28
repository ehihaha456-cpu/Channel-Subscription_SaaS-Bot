"""MTProto runtime for connected seller Telegram accounts.

Each active account gets one Telethon client and an incoming private-message
listener. The listener reads the seller's shared Business Automation settings
and sends the configured welcome/auto-reply messages.
"""

from __future__ import annotations

import asyncio
import io
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from telegram import Bot
from telethon import Button, TelegramClient, events
from telethon.sessions import StringSession

from config import TELEGRAM_API_HASH, TELEGRAM_API_ID
from database.seller_bots import get_bot_by_data_owner_id
from database.business_automation import (
    get_business_auto_reply,
    list_business_auto_replies,
    get_business_welcome,
    list_business_reply_templates,
)
from database.seller_data import (
    claim_business_welcome,
    get_business_accounts,
    get_seller_settings,
    increment_business_account_stat,
)
from utils.crypto import decrypt_secret

logger = logging.getLogger(__name__)


class BusinessAutomationRuntime:
    def __init__(self) -> None:
        self._clients: dict[tuple[int, int], TelegramClient] = {}
        self._locks: dict[tuple[int, int], asyncio.Lock] = {}

    def _lock(self, key: tuple[int, int]) -> asyncio.Lock:
        lock = self._locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[key] = lock
        return lock

    @staticmethod
    def _ready() -> bool:
        return bool(TELEGRAM_API_ID and TELEGRAM_API_HASH)

    async def start_all(self) -> int:
        if not self._ready():
            logger.warning("Business Automation runtime disabled: Telegram API credentials missing")
            return 0
        # Query all active accounts across all sellers.
        from database.seller_data import get_all_active_business_accounts

        records = await get_all_active_business_accounts()
        started = 0
        for record in records:
            try:
                if await self.start_account(int(record["owner_id"]), int(record["account_user_id"]), record=record):
                    started += 1
            except Exception:
                logger.exception(
                    "Business Automation account restore failed owner=%s account=%s",
                    record.get("owner_id"),
                    record.get("account_user_id"),
                )
        logger.info("Business Automation runtimes started=%s/%s", started, len(records))
        return started

    async def start_account(self, owner_id: int, account_user_id: int, *, record: dict | None = None) -> bool:
        key = (int(owner_id), int(account_user_id))
        async with self._lock(key):
            existing = self._clients.get(key)
            if existing and existing.is_connected():
                return True

            if record is None:
                records = await get_business_accounts(owner_id)
                record = next((r for r in records if int(r.get("account_user_id", 0)) == int(account_user_id)), None)
            if not record or not record.get("active") or not record.get("encrypted_session"):
                return False

            session = decrypt_secret(record["encrypted_session"])
            client = TelegramClient(StringSession(session), int(TELEGRAM_API_ID), TELEGRAM_API_HASH)
            await client.connect()
            if not await client.is_user_authorized():
                await client.disconnect()
                logger.warning("Business Automation session unauthorized owner=%s account=%s", owner_id, account_user_id)
                return False

            async def incoming_handler(event):
                await self._handle_incoming(owner_id, account_user_id, client, event)

            async def outgoing_handler(event):
                await self._handle_outgoing(owner_id, account_user_id, client, event)

            client.add_event_handler(incoming_handler, events.NewMessage(incoming=True))
            client.add_event_handler(outgoing_handler, events.NewMessage(outgoing=True))
            self._clients[key] = client
            logger.info("Business Automation listener active owner=%s account=%s", owner_id, account_user_id)
            return True

    async def stop_account(self, owner_id: int, account_user_id: int) -> None:
        key = (int(owner_id), int(account_user_id))
        async with self._lock(key):
            client = self._clients.pop(key, None)
            if client:
                try:
                    await client.disconnect()
                except Exception:
                    logger.exception("Business Automation client disconnect failed owner=%s account=%s", *key)

    async def shutdown(self) -> None:
        keys = list(self._clients)
        for owner_id, account_user_id in keys:
            await self.stop_account(owner_id, account_user_id)

    @staticmethod
    def _inside_working_hours(settings: dict) -> bool:
        if not settings.get("business_working_hours_enabled"):
            return True
        try:
            zone = ZoneInfo(settings.get("business_working_hours_timezone") or "Asia/Kolkata")
            now = datetime.now(zone).strftime("%H:%M")
            start = str(settings.get("business_working_hours_start") or "00:00")
            end = str(settings.get("business_working_hours_end") or "23:59")
            if start <= end:
                return start <= now <= end
            return now >= start or now <= end
        except Exception:
            logger.exception("Invalid Business Automation working-hours settings")
            return True

    async def _telethon_buttons(self, owner_id: int, rows) -> list[list[Button]] | None:
        result = []
        bot_record = None
        for row in rows or []:
            clean = []
            for item in row or []:
                value = str(item.get("value") or item.get("url") or "").strip()
                item_type = str(item.get("type") or ("url" if item.get("url") else ""))
                if item_type == "callback":
                    # User accounts cannot send bot callback buttons. Convert shared
                    # feature buttons into a Clone Bot deep link.
                    if bot_record is None:
                        bot_record = await get_bot_by_data_owner_id(int(owner_id))
                    username = str((bot_record or {}).get("bot_username") or "").lstrip("@")
                    feature = value.removeprefix("c_")
                    if username:
                        value = f"https://t.me/{username}?start={feature}"
                        item_type = "url"
                if item_type == "url" and value:
                    clean.append(Button.url(str(item.get("text") or "Open")[:64], value))
            if clean:
                result.append(clean)
        return result or None

    async def _download_clone_media(self, owner_id: int, file_id: str, media_type: str = "") -> io.BytesIO | None:
        try:
            bot_record = await get_bot_by_data_owner_id(int(owner_id))
            if not bot_record:
                return None
            encrypted_token = bot_record.get("bot_token_encrypted")
            if not encrypted_token:
                return None
            token = decrypt_secret(encrypted_token)
            async with Bot(token=token) as bot:
                tg_file = await bot.get_file(file_id)
                data = await tg_file.download_as_bytearray()
            stream = io.BytesIO(bytes(data))
            extension = {
                "photo": ".jpg",
                "video": ".mp4",
                "animation": ".gif",
                "document": ".bin",
            }.get(str(media_type or "").lower(), ".bin")
            stream.name = f"business_media{extension}"
            return stream
        except Exception:
            logger.exception("Business Automation media download failed owner=%s", owner_id)
            return None

    async def _send_configured_message(
        self,
        client: TelegramClient,
        peer_id: int,
        owner_id: int,
        *,
        text: str,
        media_type: str,
        media_file_id: str,
        button_rows,
    ) -> None:
        buttons = await self._telethon_buttons(owner_id, button_rows)
        if media_file_id:
            media = await self._download_clone_media(owner_id, media_file_id, media_type)
            if media is not None:
                await client.send_file(
                    peer_id,
                    media,
                    caption=text or "",
                    buttons=buttons,
                    force_document=str(media_type or "").lower() == "document",
                )
                return
        await client.send_message(peer_id, text or "Welcome!", buttons=buttons)

    async def _handle_incoming(self, owner_id: int, account_user_id: int, client: TelegramClient, event) -> None:
        try:
            if not event.is_private or event.out:
                return
            sender = await event.get_sender()
            peer_id = int(event.sender_id or 0)
            if not peer_id or peer_id == int(account_user_id) or getattr(sender, "bot", False):
                return

            settings = await get_seller_settings(owner_id)
            welcome = await get_business_welcome(owner_id)
            auto_replies = await list_business_auto_replies(owner_id)
            if not settings.get("business_automation_enabled"):
                return
            if not self._inside_working_hours(settings):
                return

            first_contact = await claim_business_welcome(
                owner_id,
                account_user_id,
                peer_id,
                welcome_once=bool(settings.get("business_welcome_once", True)),
            )

            delay = max(0, min(int(settings.get("business_reply_delay_seconds", 0) or 0), 300))
            if delay:
                await asyncio.sleep(delay)

            welcome_sent = False
            if welcome.get("enabled", True) and first_contact:
                text = str(welcome.get("text") or "").strip()
                media_file_id = str(welcome.get("media_file_id") or "")
                if text or media_file_id:
                    await self._send_configured_message(
                        client,
                        peer_id,
                        owner_id,
                        text=text,
                        media_type=str(welcome.get("media_type") or ""),
                        media_file_id=media_file_id,
                        button_rows=welcome.get("buttons") or [],
                    )
                    await increment_business_account_stat(owner_id, account_user_id, "welcome_sent")
                    welcome_sent = True

            # Keyword replies run after the first welcome. Exact matching avoids
            # accidental replies when a keyword appears inside an unrelated sentence.
            if not welcome_sent:
                incoming_text = " ".join(str(getattr(event, "raw_text", "") or "").strip().lower().split())
                match = next((x for x in auto_replies if x.get("enabled", True) and incoming_text == str(x.get("keyword") or "").strip().lower()), None)
                if match:
                    text = str(match.get("text") or "").strip()
                    media_file_id = str(match.get("media_file_id") or "")
                    if text or media_file_id:
                        await self._send_configured_message(
                            client, peer_id, owner_id,
                            text=text,
                            media_type=str(match.get("media_type") or ""),
                            media_file_id=media_file_id,
                            button_rows=match.get("buttons") or [],
                        )
                        await increment_business_account_stat(owner_id, account_user_id, "auto_replies_sent")
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception(
                "Business Automation incoming message failed owner=%s account=%s peer=%s",
                owner_id,
                account_user_id,
                getattr(event, "sender_id", None),
            )

    async def _handle_outgoing(self, owner_id: int, account_user_id: int, client: TelegramClient, event) -> None:
        """Replace seller shortcuts such as /payment with the saved template."""
        try:
            if not event.is_private:
                return
            raw = str(getattr(event, "raw_text", "") or "").strip()
            if not raw.startswith("/"):
                return
            templates = await list_business_reply_templates(owner_id)
            item = next((x for x in templates if raw.lower() == str(x.get("shortcut") or "").strip().lower()), None)
            if not item:
                return
            peer_id = int(event.chat_id or 0)
            if not peer_id:
                return
            try:
                await event.delete()
            except Exception:
                logger.exception("Business template shortcut delete failed owner=%s", owner_id)
            await self._send_configured_message(
                client, peer_id, owner_id,
                text=str(item.get("text") or item.get("name") or ""),
                media_type=str(item.get("media_type") or ""),
                media_file_id=str(item.get("media_file_id") or ""),
                button_rows=item.get("buttons") or [],
            )
            await increment_business_account_stat(owner_id, account_user_id, "templates_used")
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Business Automation outgoing template failed owner=%s account=%s", owner_id, account_user_id)



business_automation_runtime = BusinessAutomationRuntime()
