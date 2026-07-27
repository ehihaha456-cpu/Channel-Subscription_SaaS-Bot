"""Feature callback handler extracted from the legacy clone callback router."""

from handlers.common.clone_context import *


async def handle(self, update, context, q, owner, staff, a, role):
    if a == 'a_plans':
        await q.edit_message_text('📦 Plan Management', reply_markup=self.plans_admin_menu())
        return True
    if a == 'a_plan_add':
        plan_cfg, _ = await effective_plan(owner)
        existing = len(await get_plans(owner))
        limit = int(plan_cfg.get('plan_limit', 2))
        if limit >= 0 and existing >= limit:
            await q.edit_message_text(await plan_limit_warning(owner), reply_markup=self.limit_keyboard('a_plans'))
            return True
        context.user_data.clear()
        context.user_data['wait_plan_add'] = True
        await q.edit_message_text('Send: Plan Name | Duration | Price | Stars\nExample: Premium | 30d | 199 | 99', reply_markup=self.back('a_plans'))
        return True
    if a == 'a_plan_list':
        plans = await get_plans(owner)
        lines = ['📋 Plans\n']
        kb = []
        for p in plans:
            lines.append(f"{('✅' if p.get('active') else '⏸')} {p['name']} — {p['duration_text']} — ₹{p['price']:g} — ⭐{int(p.get('stars_price',0) or 0)}")
            kb.append([InlineKeyboardButton(f"✏ {p['name'][:16]}", callback_data=f"a_plan_edit_{p['plan_id']}"), InlineKeyboardButton('🗑', callback_data=f"a_plan_del_{p['plan_id']}")])
            kb.append([InlineKeyboardButton('⏸ Disable' if p.get('active') else '▶ Enable', callback_data=f"a_plan_toggle_{p['plan_id']}")])
        kb.append([InlineKeyboardButton('⬅ Back', callback_data='a_plans')])
        await q.edit_message_text('\n'.join(lines), reply_markup=InlineKeyboardMarkup(kb))
        return True
    if a.startswith('a_plan_edit_'):
        context.user_data.clear()
        context.user_data['wait_plan_edit'] = a.replace('a_plan_edit_', '')
        await q.edit_message_text('Send new: Plan Name | Duration | Price | Stars', reply_markup=self.back('a_plan_list'))
        return True
    if a.startswith('a_plan_del_'):
        await delete_plan(owner, a.replace('a_plan_del_', ''))
        await q.edit_message_text('✅ Plan deleted', reply_markup=self.plans_admin_menu())
        return True
    if a.startswith('a_plan_toggle_'):
        pid = a.replace('a_plan_toggle_', '')
        p = await get_plan(owner, pid)
        await update_plan(owner, pid, active=not bool(p.get('active')))
        await q.edit_message_text('✅ Plan status updated', reply_markup=self.plans_admin_menu())
        return True
    return False
