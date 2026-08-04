"""Return feature-button navigation to the message that opened it."""
from __future__ import annotations

from collections import OrderedDict
from copy import deepcopy
from typing import Any

from telegram.error import TelegramError

_MAX = 5000
_ORIGINS: OrderedDict[tuple[int, int], dict[str, Any]] = OrderedDict()


def register_feature_origin(message, *, text: str = "", markup=None) -> None:
    if message is None or not getattr(message, "message_id", None) or not getattr(message, "chat_id", None):
        return
    key = (int(message.chat_id), int(message.message_id))
    _ORIGINS[key] = {"text": str(text or ""), "markup": deepcopy(markup)}
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
        return False
    context.user_data["clone_feature_origin"] = {**deepcopy(origin), "chat_id": key[0], "message_id": key[1]}
    return True


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
    except TelegramError:
        return False
