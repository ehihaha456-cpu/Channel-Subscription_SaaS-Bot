"""Feature callback handler extracted from the legacy clone callback router."""

from handlers.common.clone_context import *
from handlers.common.editor_engine import url_buttons_header


async def handle(self, update, context, q, owner, staff, a, role):
    if a == 'a_welcome':
        s = await ensure_seller_defaults(owner, (await get_bot_by_data_owner_id(owner) or {}).get('bot_name', 'Subscription Bot'))
        text = (
            "👋 Group Welcome Message\n\n"
            "Sent when a new member joins the selected group.\n\n"
            "Current Setup\n\n"
            "Status: 🟢 Enabled\n"
            f"📝 Text: {'✅ Added' if s.get('welcome_message') else '❌ Not added'}\n"
            f"🖼 Media: {'1/10' if s.get('welcome_media_file_id') else '❌ Not added'}\n"
            f"🔗 Buttons: {sum((len(r) for r in s.get('welcome_buttons') or []))}\n\n"
            "Use the options below to add, replace, preview, or remove each part."
        )
        await q.edit_message_text(text, reply_markup=self.welcome_menu())
        return True
    if a == 'a_welcome_text':
        s = await get_seller_settings(owner)
        context.user_data.clear()
        context.user_data['wait_welcome_text'] = True
        await q.edit_message_text(
            '📝 Group Welcome Message\n\n'
            'Seller, send now the message you want to set!\n\n'
            'You can use HTML and:\n'
            '• {ID} = user ID\n'
            '• {NAME} = first name\n'
            '• {SURNAME} = surname\n'
            '• {NAMESURNAME} = full name\n'
            '• {LANG} = user language\n'
            '• {DATE} = current date\n'
            '• {TIME} = current time\n'
            '• {WEEKDAY} = week day\n'
            '• {MENTION} = link to the user profile\n'
            '• {USERNAME} = username\n'
            '• {RULES} = group rules/description',
            reply_markup=self.welcome_text_menu(bool(s.get('welcome_message')))
        )
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
        s = await get_seller_settings(owner)
        current = (s.get('welcome_message') or '').strip()
        if not current:
            await q.edit_message_text('📝 Welcome text is not set.', reply_markup=self.welcome_text_menu(False))
        else:
            await q.edit_message_text(f'📝 Current Welcome Text\n\n{current}', reply_markup=self.welcome_text_menu(True))
        return True
    if a == 'a_welcome_see_media':
        s = await get_seller_settings(owner)
        media_type = s.get('welcome_media_type')
        file_id = s.get('welcome_media_file_id')
        if not media_type or not file_id:
            await q.edit_message_text('🖼 Welcome media is not set.', reply_markup=self.welcome_media_menu(False))
            return True
        try:
            if media_type == 'photo':
                await q.message.reply_photo(file_id, caption='🖼 Current Welcome Media')
            elif media_type == 'video':
                await q.message.reply_video(file_id, caption='🖼 Current Welcome Media')
            elif media_type == 'animation':
                await q.message.reply_animation(file_id, caption='🖼 Current Welcome Media')
            elif media_type == 'document':
                await q.message.reply_document(file_id, caption='🖼 Current Welcome Media')
            else:
                await q.message.reply_text('🖼 Unsupported welcome media type.')
        except Exception as exc:
            logger.exception('Welcome media preview failed: %s', exc)
            await q.message.reply_text('❌ Unable to preview the saved welcome media.')
        await q.message.reply_text('⬅ Return to Welcome Message', reply_markup=self.welcome_menu())
        return True
    if a == 'a_welcome_see_buttons':
        s = await get_seller_settings(owner)
        rows = s.get('welcome_buttons') or []
        if not rows:
            await q.edit_message_text('No buttons set.', reply_markup=self.welcome_buttons_menu())
            return True
        lines = ['🔗 Current Buttons\n']
        kb = []
        for row_index, row in enumerate(rows):
            names = []
            for button_index, item in enumerate(row):
                name = item.get('text', 'Button')
                names.append(name)
                kb.append([InlineKeyboardButton(f'🗑 Delete: {name[:28]}', callback_data=f'a_welcome_delbtn_{row_index}_{button_index}')])
            lines.append(f'Row {row_index + 1}: ' + ' | '.join(names))
        kb.append([InlineKeyboardButton('➕ Add More', callback_data='a_welcome_buttons')])
        kb.append([InlineKeyboardButton('⬅ Back', callback_data='a_welcome_buttons')])
        await q.edit_message_text('\n'.join(lines), reply_markup=InlineKeyboardMarkup(kb))
        return True
    if a.startswith('a_welcome_delbtn_'):
        try:
            position = a.replace('a_welcome_delbtn_', '')
            row_index, button_index = [int(value) for value in position.split('_', 1)]
            s = await get_seller_settings(owner)
            rows = s.get('welcome_buttons') or []
            if row_index >= len(rows) or button_index >= len(rows[row_index]):
                raise IndexError
            deleted_name = rows[row_index][button_index].get('text', 'Button')
            del rows[row_index][button_index]
            if not rows[row_index]:
                del rows[row_index]
            await set_seller_setting(owner, 'welcome_buttons', rows)
            await q.edit_message_text(f'✅ {deleted_name} button deleted.', reply_markup=self.welcome_buttons_menu())
        except (ValueError, IndexError):
            await q.edit_message_text('❌ Button not found. Open Current Buttons again.', reply_markup=self.welcome_buttons_menu())
        return True
    if a == 'a_welcome_remove_text':
        await set_seller_setting(owner, 'welcome_message', '')
        await q.edit_message_text('✅ Welcome text removed.', reply_markup=self.welcome_text_menu(False))
        return True
    if a == 'a_welcome_remove_media':
        await set_seller_setting(owner, 'welcome_media_type', '')
        await set_seller_setting(owner, 'welcome_media_file_id', '')
        await q.edit_message_text('✅ Welcome media removed.', reply_markup=self.welcome_media_menu(False))
        return True
    if a == 'a_welcome_remove_buttons':
        await set_seller_setting(owner, 'welcome_buttons', [])
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
