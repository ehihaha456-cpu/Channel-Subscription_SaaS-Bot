"""Feature callback handler extracted from the legacy clone callback router."""

from handlers.common.clone_context import *
from handlers.common.editor_engine import build_editor_keyboard
from database.business_automation import get_business_welcome
from handlers.common.clone_context import MAIN_BOT_USERNAME
from utils.branding import append_branding
from telegram import InputMediaDocument, InputMediaPhoto, InputMediaVideo
from datetime import datetime
from zoneinfo import ZoneInfo



def _render_business_variables(value: str, user) -> str:
    now = datetime.now(ZoneInfo("Asia/Kolkata"))
    first = str(getattr(user, "first_name", "") or "")
    last = str(getattr(user, "last_name", "") or "")
    name = " ".join(x for x in (first, last) if x).strip() or str(getattr(user, "username", "") or "User")
    username_raw = str(getattr(user, "username", "") or "").lstrip("@")
    user_id = str(getattr(user, "id", "") or "")
    values = {
        "{NAME}": name, "{FIRSTNAME}": first, "{SURNAME}": last, "{NAMESURNAME}": name,
        "{ID}": user_id, "{USERNAME}": f"@{username_raw}" if username_raw else "",
        "{MENTION}": f"tg://user?id={user_id}" if user_id else "",
        "{DATE}": now.strftime("%d %b %Y"), "{TIME}": now.strftime("%I:%M %p"),
        "{WEEKDAY}": now.strftime("%A"),
    }
    rendered = str(value or "")
    for token, replacement in values.items():
        rendered = rendered.replace(token, replacement)
    return rendered


def _render_business_buttons(rows, user):
    result = []
    for row in rows or []:
        clean = []
        for item in row or []:
            copy = dict(item)
            copy["text"] = _render_business_variables(copy.get("text") or "", user)
            if "value" in copy:
                copy["value"] = _render_business_variables(copy.get("value") or "", user)
            if "url" in copy:
                copy["url"] = _render_business_variables(copy.get("url") or "", user)
            clean.append(copy)
        if clean:
            result.append(clean)
    return result


def _business_connection_id(message):
    return getattr(message, "business_connection_id", None)


def _business_media(item: dict) -> list[dict]:
    media = list(item.get("media") or [])
    if not media and item.get("media_file_id"):
        media = [{"type": item.get("media_type") or "document", "file_id": item.get("media_file_id")}]
    return [m for m in media if m.get("file_id")][:10]


async def _send_business_welcome(update, context, owner: int, business_connection_id: str):
    """Restore the configured Business welcome on the same callback message."""
    item = await get_business_welcome(owner)
    user = update.effective_user
    text = _render_business_variables(str(item.get("text") or "Welcome!"), user)
    text = await append_branding(text)
    markup = build_editor_keyboard(_render_business_buttons(item.get("buttons") or [], user))
    q = update.callback_query
    message = q.message
    has_media = bool(
        getattr(message, "photo", None)
        or getattr(message, "video", None)
        or getattr(message, "animation", None)
        or getattr(message, "document", None)
        or getattr(message, "audio", None)
    )

    try:
        if has_media:
            await q.edit_message_caption(caption=text, reply_markup=markup)
        else:
            await q.edit_message_text(
                text=text,
                reply_markup=markup,
                disable_web_page_preview=True,
            )
    except Exception as exc:
        # Telegram reports this when Back restores content that is already open.
        if "message is not modified" not in str(exc).lower():
            raise


async def handle(self, update, context, q, owner, action):
    back_keyboard = self.back('c_home')
    if action == 'seller_current_plan':
        await q.edit_message_text(await current_plan_text(owner), reply_markup=self.limit_keyboard('a_home'))
        return True
    if action == 'seller_upgrade_plan':
        cfg = await get_config()
        plans = [p for p in cfg.get('paid_plans', []) if p.get('active', True)]
        if not plans:
            await q.edit_message_text('No paid seller plans are available right now.', reply_markup=self.back('a_home'))
            return True
        lines = ['💎 Upgrade Seller Plan', '']
        for p in plans:
            lines.append(f"• {p.get('name', 'Plan')} — ₹{p.get('price', 0)} / {p.get('duration_days', 30)} days")
        lines += ['', 'Contact the SaaS owner to activate a plan.']
        await q.edit_message_text('\n'.join(lines), reply_markup=self.back('a_home'))
        return True
    if action in {'ba_user_home', 'c_home'}:
        business_connection_id = _business_connection_id(q.message)
        if business_connection_id:
            await _send_business_welcome(update, context, owner, business_connection_id)
            return True
        record = await get_bot_by_data_owner_id(owner)
        settings = await ensure_seller_defaults(owner, (record or {}).get('bot_name', 'Subscription Bot'))
        await self.send_welcome(q.message, context, settings, q.from_user)
        return True
    if action == 'c_plans':
        await self.show_plans(q, owner, True)
        return True
    if action in {'c_buy', 'c_renew'}:
        await self.show_plans(q, owner, True)
        return True
    return False
