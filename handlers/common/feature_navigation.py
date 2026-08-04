"""Return feature-button navigation to the message that opened it."""
from __future__ import annotations

from collections import OrderedDict
from typing import Any

from telegram.error import TelegramError

_MAX = 5000
_ORIGINS: OrderedDict[tuple[int, int], dict[str, Any]] = OrderedDict()


def _message_key(message) -> tuple[int, int] | None:
    """Return a stable key for normal and Telegram Business messages."""
    if message is None:
        return None
    message_id = getattr(message, "message_id", None)
    chat_id = getattr(message, "chat_id", None)
    if chat_id is None:
        chat = getattr(message, "chat", None)
        chat_id = getattr(chat, "id", None)
    if message_id is None or chat_id is None:
        return None
    try:
        return int(chat_id), int(message_id)
    except (TypeError, ValueError):
        return None


def register_feature_origin(message, *, text: str = "", markup=None) -> None:
    key = _message_key(message)
    if key is None:
        return
    _ORIGINS[key] = {"text": str(text or ""), "markup": markup}
    _ORIGINS.move_to_end(key)
    while len(_ORIGINS) > _MAX:
        _ORIGINS.popitem(last=False)


def capture_feature_origin(query, context) -> bool:
    message = getattr(query, "message", None)
    if message is None:
        return False
    key = _message_key(message)
    if key is None:
        return False
    origin = _ORIGINS.get(key)
    if not origin:
        # Business Automation messages can be created by a different bot
        # application instance, so the in-memory registry may not contain the
        # message. Capture the currently displayed message directly instead.
        text = str(getattr(message, "caption", None) or getattr(message, "text", None) or "")
        markup = getattr(message, "reply_markup", None)
        if not text and markup is None:
            return False
        origin = {"text": text, "markup": markup}

    # Persist the origin by message ID as well as in PTB context. Telegram
    # Business callbacks can be handled by a different Application instance,
    # where user_data may not be the same dictionary. The process-wide message
    # registry keeps Back navigation tied to the exact broadcast message.
    _ORIGINS[key] = {"text": str(origin.get("text") or ""), "markup": origin.get("markup")}
    _ORIGINS.move_to_end(key)
    while len(_ORIGINS) > _MAX:
        _ORIGINS.popitem(last=False)

    payload = {**_ORIGINS[key], "chat_id": key[0], "message_id": key[1]}
    try:
        context.user_data["clone_feature_origin"] = payload
        try:
            context.chat_data["clone_feature_origin"] = payload
        except Exception:
            pass
        return True
    except Exception:
        # Origin tracking must never stop the actual feature button action.
        return False


def feature_back_callback(context) -> str:
    try:
        if context.user_data.get("clone_feature_origin"):
            return "c_return_origin"
    except Exception:
        pass
    try:
        if context.chat_data.get("clone_feature_origin"):
            return "c_return_origin"
    except Exception:
        pass
    return "c_home"


async def restore_feature_origin(query, context) -> bool:
    origin = None
    try:
        origin = context.user_data.pop("clone_feature_origin", None)
    except Exception:
        pass
    if not origin:
        try:
            origin = context.chat_data.pop("clone_feature_origin", None)
        except Exception:
            pass
    if not origin:
        key = _message_key(getattr(query, "message", None))
        if key is not None:
            origin = _ORIGINS.get(key)
    if not origin:
        return False
    text = str(origin.get("text") or "")
    markup = origin.get("markup")
    try:
        if getattr(query.message, "caption", None) is not None or getattr(query.message, "photo", None) or getattr(query.message, "video", None) or getattr(query.message, "document", None) or getattr(query.message, "animation", None):
            await query.edit_message_caption(caption=text or None, reply_markup=markup)
        else:
            await query.edit_message_text(text=text or "Choose an option below.", reply_markup=markup)
        register_feature_origin(query.message, text=text, markup=markup)
        return True
    except TelegramError as exc:
        # Treat an already-restored message as success. Falling back to c_home
        # here would create the normal Clone Bot welcome message.
        if "message is not modified" in str(exc).casefold():
            register_feature_origin(query.message, text=text, markup=markup)
            return True
        return False
