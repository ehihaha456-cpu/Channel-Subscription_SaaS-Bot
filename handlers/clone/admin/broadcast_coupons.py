"""Feature callback handler extracted from the legacy clone callback router."""

from handlers.common.clone_context import *


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
        context.user_data.clear()
        context.user_data['wait_broadcast'] = True
        await q.edit_message_text('📢 Send any one message to broadcast.\n\nSupported: text, photo with caption, video, document, audio, voice, GIF, sticker and forwarded messages.', reply_markup=self.back())
        return True
    return False
