"""Official Telegram Business automation for clone bots.

This handles Bot API ``business_connection`` and ``business_message`` updates.
Normal MTProto account automation remains in ``services.business_automation_runtime``.
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime
from zoneinfo import ZoneInfo

from telegram import (
    InlineKeyboardButton, InlineKeyboardMarkup, InputMediaDocument, InputMediaPhoto,
    InputMediaVideo, Update,
)
from telegram.ext import ContextTypes

from database.business_automation import get_business_welcome, list_business_auto_replies, list_business_reply_templates, upsert_business_recipient
from database.business_official import (
    get_official_business_connection,
    increment_official_business_stat,
    save_official_business_connection,
)
from database.seller_bots import get_bot_by_data_owner_id
from database.seller_data import claim_business_welcome, get_seller_settings, reset_business_welcome

logger = logging.getLogger(__name__)


def _keyword_in_message(keyword: str, message: str) -> bool:
    keyword = " ".join(str(keyword or "").casefold().split())
    message = " ".join(str(message or "").casefold().split())
    if not keyword or not message:
        return False
    if re.fullmatch(r"[\w]+", keyword, flags=re.UNICODE):
        return re.search(rf"(?<!\w){re.escape(keyword)}(?!\w)", message, flags=re.UNICODE) is not None
    return keyword in message



def _variable_values(user) -> dict[str, str]:
    zone = ZoneInfo("Asia/Kolkata")
    now = datetime.now(zone)
    first = str(getattr(user, "first_name", "") or "")
    last = str(getattr(user, "last_name", "") or "")
    name = " ".join(x for x in (first, last) if x).strip() or str(getattr(user, "username", "") or "User")
    username_raw = str(getattr(user, "username", "") or "").lstrip("@")
    username = f"@{username_raw}" if username_raw else ""
    user_id = str(getattr(user, "id", "") or "")
    mention = f"tg://user?id={user_id}" if user_id else ""
    return {
        "{NAME}": name, "{FIRSTNAME}": first, "{SURNAME}": last,
        "{NAMESURNAME}": name, "{ID}": user_id, "{USERNAME}": username,
        "{MENTION}": mention, "{DATE}": now.strftime("%d %b %Y"),
        "{TIME}": now.strftime("%I:%M %p"), "{WEEKDAY}": now.strftime("%A"),
    }


def _render_variables(value: str, user) -> str:
    rendered = str(value or "")
    for token, replacement in _variable_values(user).items():
        rendered = rendered.replace(token, replacement)
    return rendered


def _render_button_rows(rows, user):
    result = []
    for row in rows or []:
        clean = []
        for item in row or []:
            copy = dict(item)
            copy["text"] = _render_variables(copy.get("text") or "", user)
            if "value" in copy:
                copy["value"] = _render_variables(copy.get("value") or "", user)
            if "url" in copy:
                copy["url"] = _render_variables(copy.get("url") or "", user)
            clean.append(copy)
        if clean:
            result.append(clean)
    return result

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
    media_type: str = "",
    media_file_id: str = "",
    media_items=None,
    button_rows=None,
    user=None,
) -> None:
    """Send saved media as one Telegram album, followed by text/buttons.

    Telegram media groups do not support inline keyboards. Therefore, when
    multiple media items are configured, the complete album is sent first and
    the configured text/buttons are sent as one message immediately after it.
    """
    rendered_text = _render_variables(text, user) if user is not None else str(text or "")
    rendered_rows = _render_button_rows(button_rows or [], user) if user is not None else (button_rows or [])
    markup = await _inline_markup(owner_id, rendered_rows)
    items = list(media_items or [])
    if not items and media_file_id:
        items = [{"type": media_type or "document", "file_id": media_file_id}]
    items = [m for m in items if m.get("file_id")][:10]

    common = {
        "chat_id": int(chat_id),
        "business_connection_id": str(business_connection_id),
    }

    if len(items) > 1:
        album = []
        for item in items:
            kind = str(item.get("type") or "document").lower()
            file_id = str(item.get("file_id") or "")
            if kind == "photo":
                album.append(InputMediaPhoto(media=file_id))
            elif kind == "video":
                album.append(InputMediaVideo(media=file_id))
            else:
                # Telegram albums support photos, videos, audio, and documents.
                # GIF/animation is stored as a document inside mixed albums.
                album.append(InputMediaDocument(media=file_id))
        await context.bot.send_media_group(media=album, **common)
        if rendered_text or markup:
            await context.bot.send_message(
                text=rendered_text or "Choose an option below.",
                reply_markup=markup,
                **common,
            )
        return

    if len(items) == 1:
        item = items[0]
        kind = str(item.get("type") or "document").lower()
        file_id = str(item.get("file_id") or "")
        single_common = {**common, "caption": rendered_text or None, "reply_markup": markup}
        if kind == "photo":
            await context.bot.send_photo(photo=file_id, **single_common)
        elif kind == "video":
            await context.bot.send_video(video=file_id, **single_common)
        elif kind == "animation":
            await context.bot.send_animation(animation=file_id, **single_common)
        else:
            await context.bot.send_document(document=file_id, **single_common)
        return

    await context.bot.send_message(
        text=rendered_text or "Welcome!",
        reply_markup=markup,
        **common,
    )


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
        if not sender_id or bool(getattr(sender, "is_bot", False)):
            return

        # A seller sends a template keyword alone; replace that message with the
        # configured reply template. These updates must never enter Live Support.
        if sender_id == business_user_id:
            raw = str(message.text or message.caption or "").strip()
            if raw and not any(ch.isspace() for ch in raw):
                templates = await list_business_reply_templates(owner_id)
                template = next((x for x in templates if raw.casefold() == str(x.get("shortcut") or "").strip().casefold()), None)
                if template:
                    try:
                        await context.bot.delete_business_messages(connection_id, [message.message_id])
                    except Exception:
                        logger.debug("Could not delete official business template keyword", exc_info=True)
                    await _send_configured_message(
                        context, chat_id=message.chat_id, business_connection_id=connection_id,
                        owner_id=owner_id, text=str(template.get("text") or template.get("name") or ""),
                        media_type=str(template.get("media_type") or ""), media_file_id=str(template.get("media_file_id") or ""),
                        media_items=template.get("media") or [], button_rows=template.get("buttons") or [],
                        user=message.chat,
                    )
                    await increment_official_business_stat(owner_id, connection_id, "templates_used")
            return

        await upsert_business_recipient(owner_id, connection_id, message.chat_id, sender)

        settings = await get_seller_settings(owner_id)
        if not settings.get("business_automation_enabled"):
            return
        if not _inside_working_hours(settings):
            return

        welcome = await get_business_welcome(owner_id)
        auto_replies = await list_business_auto_replies(owner_id)
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
            media_items = list(welcome.get("media") or [])
            if text or media_file_id or media_items:
                await _send_configured_message(
                    context,
                    chat_id=message.chat_id,
                    business_connection_id=connection_id,
                    owner_id=owner_id,
                    text=text,
                    media_type=str(welcome.get("media_type") or ""),
                    media_file_id=media_file_id,
                    media_items=media_items,
                    button_rows=welcome.get("buttons") or [],
                    user=sender,
                )
                await increment_official_business_stat(owner_id, connection_id, "welcome_sent")
                welcome_sent = True

        if not welcome_sent:
            incoming_text = str(message.text or message.caption or "").strip()
            match = next((x for x in auto_replies if x.get("enabled", True) and _keyword_in_message(str(x.get("keyword") or ""), incoming_text)), None)
            if match:
                text = str(match.get("text") or "").strip()
                media_file_id = str(match.get("media_file_id") or "")
                media_items = list(match.get("media") or [])
                if text or media_file_id or media_items:
                    await _send_configured_message(
                        context, chat_id=message.chat_id, business_connection_id=connection_id,
                        owner_id=owner_id, text=text,
                        media_type=str(match.get("media_type") or ""), media_file_id=media_file_id,
                        media_items=media_items, button_rows=match.get("buttons") or [],
                        user=sender,
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


async def handle_deleted_business_messages(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    deleted = update.deleted_business_messages
    if deleted is None:
        return
    owner_id = int(context.application.bot_data.get("seller_owner_id") or 0)
    if not owner_id:
        return
    connection_id = str(deleted.business_connection_id or "")
    if not connection_id:
        return
    try:
        connection_doc = await get_official_business_connection(owner_id, connection_id)
        if not connection_doc:
            connection = await context.bot.get_business_connection(connection_id)
            connection_doc = await save_official_business_connection(owner_id, connection)
        business_user_id = int(connection_doc.get("business_user_id") or owner_id)
        await reset_business_welcome(owner_id, business_user_id, int(deleted.chat.id))
    except Exception:
        logger.exception("Could not reset Business welcome after deleted messages owner=%s", owner_id)


async def send_official_business_broadcast(context, owner_id: int, item: dict, recipients: list[dict]) -> tuple[int, int]:
    sent = failed = 0
    for recipient in recipients:
        try:
            class Recipient:
                pass
            user = Recipient()
            user.id = int(recipient.get("chat_id") or 0)
            user.first_name = str(recipient.get("first_name") or "")
            user.last_name = str(recipient.get("last_name") or "")
            user.username = str(recipient.get("username") or "")
            await _send_configured_message(
                context,
                chat_id=int(recipient["chat_id"]),
                business_connection_id=str(recipient["connection_id"]),
                owner_id=int(owner_id),
                text=str(item.get("text") or ""),
                media_type=str(item.get("media_type") or ""),
                media_file_id=str(item.get("media_file_id") or ""),
                media_items=item.get("media") or [],
                button_rows=item.get("buttons") or [],
                user=user,
            )
            sent += 1
            await asyncio.sleep(0.05)
        except Exception:
            failed += 1
            logger.exception("Business broadcast failed owner=%s chat=%s", owner_id, recipient.get("chat_id"))
    return sent, failed
