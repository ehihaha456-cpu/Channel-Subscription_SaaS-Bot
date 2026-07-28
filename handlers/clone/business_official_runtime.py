"""Official Telegram Business automation for clone bots.

This handles Bot API ``business_connection`` and ``business_message`` updates.
Normal MTProto account automation remains in ``services.business_automation_runtime``.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from database.business_automation import get_business_auto_reply, get_business_welcome
from database.business_official import (
    get_official_business_connection,
    increment_official_business_stat,
    save_official_business_connection,
)
from database.seller_bots import get_bot_by_data_owner_id
from database.seller_data import claim_business_welcome, get_seller_settings

logger = logging.getLogger(__name__)


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
        logger.exception("Invalid official Business Automation working-hours settings")
        return True


async def _inline_markup(owner_id: int, rows) -> InlineKeyboardMarkup | None:
    result: list[list[InlineKeyboardButton]] = []
    bot_record = None
    for row in rows or []:
        clean: list[InlineKeyboardButton] = []
        for item in row or []:
            text = str(item.get("text") or "Open")[:64]
            value = str(item.get("value") or item.get("url") or "").strip()
            item_type = str(item.get("type") or ("url" if item.get("url") else ""))
            if item_type == "callback" and value:
                clean.append(InlineKeyboardButton(text, callback_data=value[:64]))
            elif item_type == "url" and value:
                clean.append(InlineKeyboardButton(text, url=value))
            elif value:
                # Older editor records may omit the type. Preserve clone feature
                # callbacks and treat web links as URL buttons.
                if value.startswith(("http://", "https://", "tg://")):
                    clean.append(InlineKeyboardButton(text, url=value))
                elif value.startswith("c_"):
                    clean.append(InlineKeyboardButton(text, callback_data=value[:64]))
                else:
                    if bot_record is None:
                        bot_record = await get_bot_by_data_owner_id(int(owner_id))
                    username = str((bot_record or {}).get("bot_username") or "").lstrip("@")
                    if username:
                        clean.append(InlineKeyboardButton(text, url=f"https://t.me/{username}?start={value}"))
        if clean:
            result.append(clean)
    return InlineKeyboardMarkup(result) if result else None


async def _send_configured_message(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    chat_id: int,
    business_connection_id: str,
    owner_id: int,
    text: str,
    media_type: str,
    media_file_id: str,
    button_rows,
) -> None:
    markup = await _inline_markup(owner_id, button_rows)
    common = {
        "chat_id": int(chat_id),
        "business_connection_id": str(business_connection_id),
        "reply_markup": markup,
    }
    kind = str(media_type or "").lower()
    if media_file_id:
        if kind == "photo":
            await context.bot.send_photo(photo=media_file_id, caption=text or None, **common)
            return
        if kind == "video":
            await context.bot.send_video(video=media_file_id, caption=text or None, **common)
            return
        if kind == "animation":
            await context.bot.send_animation(animation=media_file_id, caption=text or None, **common)
            return
        await context.bot.send_document(document=media_file_id, caption=text or None, **common)
        return
    await context.bot.send_message(text=text or "Welcome!", **common)


async def handle_business_connection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    connection = update.business_connection
    if connection is None:
        return
    owner_id = int(context.application.bot_data.get("seller_owner_id") or 0)
    if not owner_id:
        return
    await save_official_business_connection(owner_id, connection)
    logger.info(
        "Official business connection updated owner=%s connection=%s enabled=%s user=%s",
        owner_id,
        connection.id,
        connection.is_enabled,
        getattr(connection.user, "id", None),
    )


async def handle_business_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.business_message
    if message is None or not message.business_connection_id:
        return
    if message.chat.type != "private":
        return

    owner_id = int(context.application.bot_data.get("seller_owner_id") or 0)
    if not owner_id:
        return
    connection_id = str(message.business_connection_id)

    try:
        connection_doc = await get_official_business_connection(owner_id, connection_id)
        if not connection_doc:
            connection = await context.bot.get_business_connection(connection_id)
            connection_doc = await save_official_business_connection(owner_id, connection)
        if not connection_doc.get("enabled", True) or not connection_doc.get("can_reply", True):
            return

        business_user_id = int(connection_doc.get("business_user_id") or 0)
        sender = message.from_user
        sender_id = int(getattr(sender, "id", 0) or 0)
        # Ignore messages sent by the connected business owner or by bots.
        if not sender_id or sender_id == business_user_id or bool(getattr(sender, "is_bot", False)):
            return

        settings = await get_seller_settings(owner_id)
        if not settings.get("business_automation_enabled"):
            return
        if not _inside_working_hours(settings):
            return

        welcome = await get_business_welcome(owner_id)
        auto_reply = await get_business_auto_reply(owner_id)
        first_contact = await claim_business_welcome(
            owner_id,
            business_user_id or owner_id,
            sender_id,
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
                await _send_configured_message(
                    context,
                    chat_id=message.chat_id,
                    business_connection_id=connection_id,
                    owner_id=owner_id,
                    text=text,
                    media_type=str(welcome.get("media_type") or ""),
                    media_file_id=media_file_id,
                    button_rows=welcome.get("buttons") or [],
                )
                await increment_official_business_stat(owner_id, connection_id, "welcome_sent")
                welcome_sent = True

        if not welcome_sent and auto_reply.get("enabled", True):
            text = str(auto_reply.get("text") or "").strip()
            media_file_id = str(auto_reply.get("media_file_id") or "")
            if text or media_file_id:
                await _send_configured_message(
                    context,
                    chat_id=message.chat_id,
                    business_connection_id=connection_id,
                    owner_id=owner_id,
                    text=text,
                    media_type=str(auto_reply.get("media_type") or ""),
                    media_file_id=media_file_id,
                    button_rows=auto_reply.get("buttons") or [],
                )
                await increment_official_business_stat(owner_id, connection_id, "auto_replies_sent")
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception(
            "Official Business Automation message failed owner=%s connection=%s chat=%s",
            owner_id,
            connection_id,
            getattr(message, "chat_id", None),
        )
