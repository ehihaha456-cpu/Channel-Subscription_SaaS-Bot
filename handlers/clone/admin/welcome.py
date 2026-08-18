"""Feature callback handler extracted from the legacy clone callback router."""

from handlers.common.clone_context import *


async def handle(self, update, context, q, owner, staff, a, role):
    # Bot Settings -> Welcome Message only: keep the callback acknowledgement
    # instant and reuse the settings already loaded by Bot Settings.
    cached = context.user_data.get('_bot_settings_cache')
    if isinstance(cached, dict):
        s = dict(cached)
    else:
        s = await get_seller_settings(owner)

    if a == 'a_welcome':
        s = await ensure_seller_defaults(owner, (await get_bot_by_data_owner_id(owner) or {}).get('bot_name', 'Subscription Bot'))
        context.user_data['_bot_settings_cache'] = dict(s)
        text = f"💬 Welcome Message\n\n📝 Text: {('✅' if s.get('welcome_message') else '❌')}\n🖼 Media: {('✅' if s.get('welcome_media_file_id') else '❌')}\n🔗 Buttons: {sum((len(r) for r in s.get('welcome_buttons') or []))}"
        await q.edit_message_text(text, reply_markup=self.welcome_menu())
        return True
    if a == 'a_welcome_text':
        s = await get_seller_settings(owner)
        context.user_data.clear()
        context.user_data['wait_welcome_text'] = True
        await q.edit_message_text('📄 Send the welcome message text.\n\nHTML and variables are supported:\n{ID} {NAME} {SURNAME} {NAMESURNAME} {USERNAME} {LANG} {DATE} {TIME} {WEEKDAY} {MENTION} {BOTNAME}', reply_markup=self.welcome_text_menu(bool(s.get('welcome_message'))))
        return True
    if a == 'a_welcome_media':
        s = await get_seller_settings(owner)
        context.user_data.clear()
        context.user_data['wait_welcome_media'] = True
        await q.edit_message_text('🖼 Send a photo, video, GIF or document.\n\nThe same media will appear in Full Preview and on /start.', reply_markup=self.welcome_media_menu(bool(s.get('welcome_media_file_id'))))
        return True
    if a == 'a_welcome_buttons':
        s = await get_seller_settings(owner)
        context.user_data.clear()
        context.user_data['wait_welcome_buttons'] = True
        await q.edit_message_text(url_buttons_header(), reply_markup=self.welcome_buttons_menu(bool(s.get('welcome_buttons'))))
        return True
    if a == 'a_welcome_quick':
        await q.edit_message_text('⚡ Choose a bot button to add', reply_markup=self.welcome_quick_menu())
        return True
    if a.startswith('a_wq_'):
        feature = a.replace('a_wq_', '')
        config = {'plans': ('📋 Plans', 'c_plans'), 'buy': ('💳 Buy', 'c_buy'), 'profile': ('👤 My Profile', 'c_profile'), 'renew': ('🔄 Renew', 'c_renew'), 'referral': ('🎁 Referral', 'c_referral'), 'referral_unlock': ('🔓 Referral Unlock', 'c_referral_unlock'), 'support': ('📞 Support', 'c_support'), 'home': ('🏠 Main Menu', 'c_home')}
        title, callback = config[feature]
        s = await get_seller_settings(owner)
        rows = s.get('welcome_buttons') or []
        already_exists = any((item.get('type') == 'callback' and item.get('value') == callback for row in rows for item in row))
        if already_exists:
            await q.edit_message_text(f'ℹ️ {title} button already exists.', reply_markup=self.welcome_buttons_menu())
            return True
        rows.append([{'text': title, 'type': 'callback', 'value': callback}])
        await set_seller_setting(owner, 'welcome_buttons', rows)
        await q.edit_message_text(f'✅ {title} button added.', reply_markup=self.welcome_buttons_menu())
        return True
    if a == 'a_welcome_manual':
        s = await get_seller_settings(owner)
        context.user_data.clear()
        context.user_data['wait_welcome_buttons'] = True
        await q.edit_message_text(url_buttons_header(), reply_markup=self.welcome_buttons_menu(bool(s.get('welcome_buttons'))))
        return True
    if a == 'a_welcome_see_text':
        value = str(s.get('welcome_message') or '').strip()
        if not value:
            value = '❌ No welcome text configured.'
        await q.edit_message_text('📝 Current Welcome Text\n\n' + value, reply_markup=self.welcome_text_menu(bool(s.get('welcome_message'))))
        return True
    if a == 'a_welcome_see_media':
        media_type = str(s.get('welcome_media_type') or '').strip()
        file_id = str(s.get('welcome_media_file_id') or '').strip()
        if not file_id:
            await q.edit_message_text('🖼 Current Welcome Media\n\n❌ No media configured.', reply_markup=self.welcome_media_menu(False))
            return True
        await q.edit_message_text(f'🖼 Current Welcome Media\n\nType: {media_type or "media"}\nStatus: ✅ Added', reply_markup=self.welcome_media_menu(True))
        return True
    if a == 'a_welcome_see_buttons':
        rows = s.get('welcome_buttons') or []
        if not rows:
            await q.edit_message_text('🔗 Current Buttons\n\n❌ No buttons configured.', reply_markup=self.welcome_buttons_menu(False))
            return True
        lines = ['🔗 Current Buttons', '']
        for row in rows:
            parts = []
            for item in row:
                title = str(item.get('text') or 'Button')
                typ = str(item.get('type') or 'url')
                value = str(item.get('value') or '')
                if typ == 'callback':
                    reverse = {'c_plans':'plans','c_buy':'buy','c_profile':'profile','c_renew':'renew','c_referral':'referral','c_referral_unlock':'referral_unlock','c_support':'support','c_home':'home'}
                    target = 'feature:' + reverse.get(value, value)
                elif typ == 'url':
                    target = value
                elif typ == 'popup':
                    target = 'popup: ' + value
                elif typ == 'alert':
                    target = 'alert: ' + value
                elif typ == 'rules':
                    target = 'rules'
                elif typ == 'share':
                    target = 'share: ' + value
                elif typ == 'copy':
                    target = 'copy: ' + value
                else:
                    target = value
                parts.append(f'{title} - {target}')
            if parts:
                lines.append('\n'.join(parts))
        # See is read-only: no Add More and no Delete buttons.
        await q.edit_message_text('\n'.join(lines), reply_markup=InlineKeyboardMarkup([*(self.build_welcome_keyboard(rows).inline_keyboard if self.build_welcome_keyboard(rows) else []), [InlineKeyboardButton('⬅ Back', callback_data='a_welcome')]]))
        return True

    if a == 'a_welcome_remove_text':
        await set_seller_setting(owner, 'welcome_message', '')
        s['welcome_message'] = ''
        context.user_data['_bot_settings_cache'] = dict(s)
        await q.edit_message_text('✅ Welcome text removed.', reply_markup=self.welcome_text_menu(False))
        return True
    if a == 'a_welcome_remove_media':
        await set_seller_setting(owner, 'welcome_media_type', '')
        await set_seller_setting(owner, 'welcome_media_file_id', '')
        s['welcome_media_file_id'] = ''
        s['welcome_media_type'] = ''
        context.user_data['_bot_settings_cache'] = dict(s)
        await q.edit_message_text('✅ Welcome media removed.', reply_markup=self.welcome_media_menu(False))
        return True
    if a == 'a_welcome_remove_buttons':
        await set_seller_setting(owner, 'welcome_buttons', [])
        s['welcome_buttons'] = []
        context.user_data['_bot_settings_cache'] = dict(s)
        await q.edit_message_text('✅ Welcome keyboard removed.', reply_markup=self.welcome_buttons_menu(False))
        return True
    if a == 'a_welcome_preview':
        s = await ensure_seller_defaults(owner, (await get_bot_by_data_owner_id(owner) or {}).get('bot_name', 'Subscription Bot'))
        try:
            await q.message.reply_text('👀 Preview — users will see the message below:')
            await self.send_welcome(q.message, context, s, q.from_user)
        except Exception as exc:
            logger.exception('Welcome preview failed for owner=%s', owner)
            await q.message.reply_text(f'❌ Preview failed: {str(exc)[:300]}', reply_markup=self.welcome_menu())
        return True
    return False
