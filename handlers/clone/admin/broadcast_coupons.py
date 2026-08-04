"""Feature callback handler extracted from the legacy clone callback router."""

from handlers.common.clone_context import *
from handlers.common.editor_engine import editor_header, editor_menu_keyboard, editor_media_prompt, editor_text_prompt, url_buttons_header
from database.broadcast import get_seller_broadcast_draft, update_seller_broadcast_draft


def _broadcast_text(item):
    return (
        "📣 Seller Broadcast\n\n"
        "Create one complete broadcast with text, up to 10 media files and URL/feature buttons.\n\n"
        + editor_header(
            "Current Setup",
            {**item, "enabled": True},
            variables="{NAME} {ID} {USERNAME} {MENTION} {DATE} {TIME}",
        )
    )


def _broadcast_keyboard(item):
    base = editor_menu_keyboard(
        "a_bc",
        {**item, "enabled": True},
        back_callback="a_home",
        allow_toggle=False,
    )
    rows = list(base.inline_keyboard)
    rows.insert(-1, [InlineKeyboardButton("📤 Send Broadcast", callback_data="a_bc_send")])
    return InlineKeyboardMarkup(rows)


def _input_keyboard(back_callback, remove_callback=None, remove_label="Remove"):
    rows = []
    if remove_callback:
        rows.append([InlineKeyboardButton(f"🗑 {remove_label}", callback_data=remove_callback)])
    rows.append([InlineKeyboardButton("⬅ Back", callback_data=back_callback)])
    return InlineKeyboardMarkup(rows)


async def handle(self, update, context, q, owner, staff, a, role):
    if a == 'a_broadcast_schedule':
        context.user_data.clear()
        context.user_data['wait_scheduled_broadcast'] = True
        await q.edit_message_text('🗓 Send a message with first line in this format:\nYYYY-MM-DD HH:MM\n\nWrite the broadcast text after the first line. Time uses your configured timezone.', reply_markup=self.back())
        return True
    if a == 'a_coupons':
        coupons = await list_coupons(owner)
        lines = ['🎟 Coupon System\n', 'Create: CODE | percent/fixed | VALUE | USAGE_LIMIT']
        for cpn in coupons[:20]:
            lines.append(f"• {cpn['code']} — {cpn['value']:g} {cpn['discount_type']} — {cpn['used_count']}/{cpn['usage_limit']}")
        context.user_data.clear()
        context.user_data['wait_coupon_create'] = True
        await q.edit_message_text('\n'.join(lines), reply_markup=self.back())
        return True

    if a == 'a_broadcast':
        context.user_data.pop('seller_broadcast_editor', None)
        context.user_data.pop('seller_broadcast_media_batch', None)
        item = await get_seller_broadcast_draft(owner)
        await q.edit_message_text(_broadcast_text(item), reply_markup=_broadcast_keyboard(item))
        return True
    if a == 'a_bc_text':
        item = await get_seller_broadcast_draft(owner)
        context.user_data['seller_broadcast_editor'] = {'field': 'text'}
        await q.edit_message_text(
            editor_text_prompt('Seller Broadcast Text', variables='{NAME} {ID} {USERNAME} {MENTION} {DATE} {TIME}'),
            reply_markup=_input_keyboard('a_broadcast', 'a_bc_rmtext' if item.get('text') else None, 'Remove Text'),
        )
        return True
    if a == 'a_bc_media':
        item = await get_seller_broadcast_draft(owner)
        context.user_data['seller_broadcast_editor'] = {'field': 'media'}
        await q.edit_message_text(
            editor_media_prompt('Seller Broadcast Media'),
            reply_markup=_input_keyboard('a_broadcast', 'a_bc_rmmedia' if (item.get('media') or item.get('media_file_id')) else None, 'Remove Media'),
        )
        return True
    if a == 'a_bc_buttons':
        item = await get_seller_broadcast_draft(owner)
        context.user_data['seller_broadcast_editor'] = {'field': 'buttons'}
        await q.edit_message_text(
            url_buttons_header(),
            reply_markup=_input_keyboard('a_broadcast', 'a_bc_rmbuttons' if item.get('buttons') else None, 'Remove Buttons'),
        )
        return True
    if a == 'a_bc_rmtext':
        item = await update_seller_broadcast_draft(owner, text='')
        await q.edit_message_text(_broadcast_text(item), reply_markup=_broadcast_keyboard(item))
        return True
    if a == 'a_bc_rmmedia':
        item = await update_seller_broadcast_draft(owner, media=[], media_type='', media_file_id='')
        await q.edit_message_text(_broadcast_text(item), reply_markup=_broadcast_keyboard(item))
        return True
    if a == 'a_bc_rmbuttons':
        item = await update_seller_broadcast_draft(owner, buttons=[])
        await q.edit_message_text(_broadcast_text(item), reply_markup=_broadcast_keyboard(item))
        return True
    if a == 'a_bc_preview':
        item = await get_seller_broadcast_draft(owner)
        await self.send_seller_broadcast_preview(q.message, item)
        await q.answer('Preview sent.')
        return True
    if a == 'a_bc_send':
        item = await get_seller_broadcast_draft(owner)
        if not (item.get('text') or item.get('media') or item.get('media_file_id')):
            await q.answer('Add text or media first.', show_alert=True)
            return True
        await q.answer('Broadcast started.')
        await q.message.reply_text(
            '📤 Broadcast is running in the background.\n\nYou can continue using the bot.',
            reply_markup=_broadcast_keyboard(item),
        )
        context.application.create_task(
            self.run_seller_broadcast_background(owner, context, item),
            name=f"seller_broadcast_{owner}",
        )
        return True
    return False
