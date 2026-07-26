"""Feature callback handler extracted from the legacy clone callback router."""

from handlers.common.clone_context import *


async def handle(self, update, context, q, owner, action):
    back_keyboard = self.back('c_home')
    if action.startswith('c_select_'):
        plan = await get_plan(owner, action.replace('c_select_', ''))
        if not plan:
            await q.answer('Plan not found', show_alert=True)
            return True
        context.user_data['selected_child_plan'] = plan
        s = await get_seller_settings(owner)
        gateway_cfg = await get_gateway_config('seller', owner, decrypt=True)
        gateways = gateway_cfg.get('gateways') or {}
        enabled = [g for g in SUPPORTED_GATEWAYS if (gateways.get(g) or {}).get('enabled')]
        default_gateway = str(gateway_cfg.get('default_gateway') or '')
        if default_gateway in enabled:
            enabled.remove(default_gateway)
            enabled.insert(0, default_gateway)
        manual_enabled = bool(gateway_cfg.get('manual_enabled', True))
        rows = []
        text = ''
        if enabled:
            gateway = enabled[0]
            tx = await create_gateway_transaction(scope='seller', owner_id=owner, payer_user_id=q.from_user.id, gateway=gateway, amount=float(plan['price']), currency='INR', purpose='child_subscription', reference_id=plan['plan_id'], metadata={'plan_id': plan['plan_id'], 'plan_name': plan['name'], 'description': f"{plan['name']} subscription"})
            try:
                checkout = await create_checkout(tx)
                text = f"💳 {gateway.title()} Payment\n\nPlan: {plan['name']}\nAmount: ₹{plan['price']:g}\nTransaction: {tx['transaction_id']}\n\nPayment successful hone ke baad plan automatically activate hoga."
                rows.append([InlineKeyboardButton('💳 Pay Now', url=checkout.get('checkout_url'))])
            except GatewayError as exc:
                text = f'❌ Gateway error: {exc}'
        if manual_enabled:
            manual_text = f"Plan: {plan['name']}\nAmount: {s.get('currency', 'INR')} {plan['price']:g}\nDuration: {plan['duration_text']}\n\nUPI Name: {s.get('upi_name') or 'Not Set'}\nUPI ID: {s.get('upi_id') or 'Not Set'}\n\nPay and upload your payment screenshot."
            text = f'{text}\n\n{manual_text}' if text else f'💳 Payment\n\n{manual_text}'
            rows.append([InlineKeyboardButton('📤 Upload Payment Screenshot', callback_data='c_upload')])
        if not enabled and (not manual_enabled):
            text = '⚠️ No payment method is currently available. Please contact support.'
        rows.append([InlineKeyboardButton('⬅ Back', callback_data='c_buy')])
        kb = InlineKeyboardMarkup(rows)
        if s.get('upi_qr_file_id') and manual_enabled:
            try:
                await q.message.delete()
            except TelegramError:
                pass
            await context.bot.send_photo(q.message.chat_id, s['upi_qr_file_id'], caption=text, reply_markup=kb)
        else:
            await self.safe_query_message(q, text, kb)
        return True
    if action.startswith('c_pg_'):
        try:
            _, _, gateway, plan_id = action.split('_', 3)
        except ValueError:
            await q.answer('Invalid payment option', show_alert=True)
            return True
        plan = await get_plan(owner, plan_id)
        if not plan:
            await q.answer('Plan not found', show_alert=True)
            return True
        tx = await create_gateway_transaction(scope='seller', owner_id=owner, payer_user_id=q.from_user.id, gateway=gateway, amount=float(plan['price']), currency='INR', purpose='child_subscription', reference_id=plan_id, metadata={'plan_id': plan_id, 'plan_name': plan['name'], 'description': f"{plan['name']} subscription"})
        try:
            checkout = await create_checkout(tx)
        except GatewayError as exc:
            await self.safe_query_message(q, f'❌ Gateway error: {exc}', back_keyboard)
            return True
        await self.safe_query_message(q, f"💳 {gateway.title()} Secure Payment\n\nPlan: {plan['name']}\nAmount: ₹{plan['price']:g}\nTransaction: {tx['transaction_id']}\n\nPayment verify hote hi subscription automatically activate hogi.", InlineKeyboardMarkup([[InlineKeyboardButton('💳 Pay Now', url=checkout.get('checkout_url'))], [InlineKeyboardButton('⬅ Back', callback_data='c_buy')]]))
        return True
    if action == 'c_upload':
        context.user_data['waiting_child_screenshot'] = True
        await q.message.reply_text('📷 Upload your payment screenshot.', reply_markup=back_keyboard)
        return True
    return False
