"""Feature callback handler extracted from the legacy clone callback router."""

from handlers.common.clone_context import *
from handlers.common.editor_engine import build_editor_keyboard
from database.business_automation import get_business_welcome


def _business_connection_id(message):
    return getattr(message, "business_connection_id", None)


def _business_media(item: dict) -> list[dict]:
    media = list(item.get("media") or [])
    if not media and item.get("media_file_id"):
        media = [{"type": item.get("media_type") or "document", "file_id": item.get("media_file_id")}]
    return [m for m in media if m.get("file_id")][:10]


async def _send_business_welcome(update, context, owner: int, business_connection_id: str):
    """Return feature navigation to the configured Business welcome, not /start."""
    item = await get_business_welcome(owner)
    text = str(item.get("text") or "Welcome!")
    markup = build_editor_keyboard(item.get("buttons") or [])
    chat_id = update.effective_chat.id
    media = _business_media(item)

    if not media:
        await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=markup,
            business_connection_id=business_connection_id,
        )
        return

    for index, entry in enumerate(media):
        kind = str(entry.get("type") or "document")
        file_id = str(entry.get("file_id") or "")
        last = index == len(media) - 1
        kwargs = {
            "chat_id": chat_id,
            "business_connection_id": business_connection_id,
            "caption": text if last else None,
            "reply_markup": markup if last else None,
        }
        if kind == "photo":
            await context.bot.send_photo(photo=file_id, **kwargs)
        elif kind == "video":
            await context.bot.send_video(video=file_id, **kwargs)
        elif kind == "animation":
            await context.bot.send_animation(animation=file_id, **kwargs)
        else:
            await context.bot.send_document(document=file_id, **kwargs)


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
