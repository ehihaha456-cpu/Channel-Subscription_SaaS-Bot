"""Feature callback handler extracted from the legacy clone callback router."""

from handlers.common.clone_context import *


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
    if action == 'c_home':
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
