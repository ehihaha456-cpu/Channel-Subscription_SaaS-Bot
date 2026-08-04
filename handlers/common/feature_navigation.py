"""Return feature-button navigation to the message that opened it."""
from __future__ import annotations

from collections import OrderedDict
from typing import Any

from telegram.error import TelegramError

_MAX = 5000
_ORIGINS: OrderedDict[tuple[int, int], dict[str, Any]] = OrderedDict()


def register_feature_origin(message, *, text: str = "", markup=None) -> None:
    if message is None or not getattr(message, "message_id", None) or not getattr(message, "chat_id", None):
        return
    key = (int(message.chat_id), int(message.message_id))
    _ORIGINS[key] = {"text": str(text or ""), "markup": markup}
    _ORIGINS.move_to_end(key)
    while len(_ORIGINS) > _MAX:
        _ORIGINS.popitem(last=False)


def capture_feature_origin(query, context) -> bool:
    message = getattr(query, "message", None)
    if message is None:
        return False
    key = (int(message.chat_id), int(message.message_id))
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
    try:
        context.user_data["clone_feature_origin"] = {**origin, "chat_id": key[0], "message_id": key[1]}
        return True
    except Exception:
        # Origin tracking must never stop the actual feature button action.
        return False


def feature_back_callback(context) -> str:
    return "c_return_origin" if context.user_data.get("clone_feature_origin") else "c_home"


async def restore_feature_origin(query, context) -> bool:
    origin = context.user_data.pop("clone_feature_origin", None)
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
