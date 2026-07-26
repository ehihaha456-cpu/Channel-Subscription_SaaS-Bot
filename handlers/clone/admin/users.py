"""Feature callback handler extracted from the legacy clone callback router."""

from handlers.common.clone_context import *


async def handle(self, update, context, q, owner, staff, a, role):
    if a == 'a_users':
        context.user_data.clear()
        context.user_data['wait_user_search'] = True
        await q.edit_message_text('👥 User Management\n\nSend User ID or @username to search.', reply_markup=self.back('a_home'))
        return True
    if a.startswith('a_user_view_'):
        await self.show_user_details(q, owner, int(a.replace('a_user_view_', '')))
        return True
    if a.startswith('a_user_give_'):
        await self.show_admin_plan_selector(q, owner, int(a.replace('a_user_give_', '')), 'give')
        return True
    if a.startswith('a_user_extend_'):
        await self.show_admin_plan_selector(q, owner, int(a.replace('a_user_extend_', '')), 'extend')
        return True
    if a.startswith('a_user_apply_'):
        parts = a.split('_', 5)
        if len(parts) != 6:
            await q.edit_message_text('❌ Invalid action.')
            return True
        mode = parts[3]
        user_id = int(parts[4])
        plan_id = parts[5]
        plan = await get_plan(owner, plan_id)
        if not plan:
            await q.edit_message_text('❌ Plan not found.', reply_markup=self.back(f'a_user_view_{user_id}'))
            return True
        plan_cfg, _ = await effective_plan(owner)
        active_now = await active_subscriptions(owner)
        already_active = any((int(x.get('user_id')) == user_id for x in active_now))
        sub_limit = int(plan_cfg.get('active_subscriber_limit', 25))
        if not already_active and sub_limit >= 0 and (len(active_now) >= sub_limit):
            await q.edit_message_text(await plan_limit_warning(owner), reply_markup=self.limit_keyboard(f'a_user_view_{user_id}'))
            return True
        await activate_subscription(owner, user_id, plan['name'], plan['duration_minutes'], amount=plan.get('price'), duration_text=plan.get('duration_text'))
        delivery = await self.deliver_subscription_access(owner, user_id)
        try:
            await context.bot.send_message(user_id, f"🎉 Subscription activated/extended by admin.\nPlan: {plan['name']}\nDuration added: {plan['duration_text']}\n\nNew invite links sent: {delivery.get('sent', 0)}\nAlready joined: {delivery.get('already_member', 0)}")
        except Exception:
            pass
        await self.show_user_details(q, owner, user_id)
        return True
    if a.startswith('a_user_remove_'):
        user_id = int(a.replace('a_user_remove_', ''))
        await remove_subscription(owner, user_id)
        try:
            await context.bot.send_message(user_id, '❌ Your subscription was removed by admin.')
        except Exception:
            pass
        await self.show_user_details(q, owner, user_id)
        return True
    if a.startswith('a_user_ban_'):
        user_id = int(a.replace('a_user_ban_', ''))
        context.user_data.clear()
        context.user_data['wait_user_ban_reason'] = user_id
        await q.edit_message_text('🚫 Send ban reason.', reply_markup=self.back(f'a_user_view_{user_id}'))
        return True
    if a.startswith('a_user_unban_'):
        user_id = int(a.replace('a_user_unban_', ''))
        await set_user_ban(owner, user_id, False, '')
        try:
            await context.bot.send_message(user_id, '✅ You have been unbanned.')
        except Exception:
            pass
        await self.show_user_details(q, owner, user_id)
        return True
    if a == 'a_stats':
        s = await stats(owner)
        await q.edit_message_text(f"📊 Statistics\n\nUsers: {s['users']}\nPlans: {s['plans']}\nChannels: {s['channels']}\nPending: {s['pending']}\nRevenue: ₹{s['revenue']:g}", reply_markup=self.admin_menu())
        return True
    return False
