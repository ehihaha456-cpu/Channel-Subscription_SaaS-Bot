"""Feature callback handler extracted from the legacy clone callback router."""

from handlers.common.clone_context import *
from handlers.common.editor_engine import url_buttons_header


async def handle(self, update, context, q, owner, staff, a, role):
    if a == 'a_live_support':
        support = await get_live_support_settings(owner)
        blocked = await count_support_blocks(owner)
        await q.edit_message_text(self.live_support_text(support, blocked), reply_markup=self.live_support_menu(support))
        return True
    if a == 'a_live_support_toggle':
        support = await get_live_support_settings(owner)
        updated = await update_live_support_settings(owner, enabled=not bool(support.get('enabled')))
        blocked = await count_support_blocks(owner)
        await q.edit_message_text(self.live_support_text(updated, blocked), reply_markup=self.live_support_menu(updated))
        return True
    if a in {'a_live_support_mode_private', 'a_live_support_mode_topic'}:
        mode = 'private' if a.endswith('private') else 'topic'
        updated = await update_live_support_settings(owner, mode=mode)
        blocked = await count_support_blocks(owner)
        await q.edit_message_text(self.live_support_text(updated, blocked), reply_markup=self.live_support_menu(updated))
        return True
    if a == 'a_live_support_group_info':
        support = await get_live_support_settings(owner)
        await q.edit_message_text(f"📌 Support Group\n\nName: {support.get('support_group_title') or 'Not connected'}\nChat ID: {support.get('support_group_id') or '-'}\n\nGroup badalne ke liye naye forum group me /connectsupport bhejo.", reply_markup=self.back('a_live_support'))
        return True
    if a == 'a_live_support_blocks':
        blocked = await count_support_blocks(owner)
        await q.edit_message_text(f'🚫 Support-blocked users: {blocked}\n\nUser ke support topic ke first details message se Block/Unblock kiya ja sakta hai.', reply_markup=self.back('a_live_support'))
        return True
    if a == 'a_support_auto_replies':
        items = await list_support_auto_replies(owner)
        await q.edit_message_text('🤖 Live Support Auto Reply\n\nSet a keyword, then configure its text, media and URL buttons. When a user message contains that keyword, the saved reply is sent automatically.', reply_markup=self.support_auto_replies_menu(items))
        return True
    if a == 'a_support_ar_add':
        context.user_data.clear()
        context.user_data['wait_support_ar_keyword'] = True
        await q.edit_message_text('🔑 Send the keyword or phrase for this auto reply.\n\nExample: payment', reply_markup=self.back('a_support_auto_replies'))
        return True
    if a.startswith('a_support_ar_view_'):
        keyword = a.replace('a_support_ar_view_', '')
        item = await get_support_auto_reply(owner, keyword)
        if not item:
            await q.edit_message_text('❌ Auto reply not found', reply_markup=self.back('a_support_auto_replies'))
            return True
        count = sum((len(row) for row in item.get('buttons') or []))
        await q.edit_message_text(f"🤖 Auto Reply\n\n🔑 Keyword: {keyword}\n📄 Text: {('✅' if item.get('text') else '❌')}\n🖼 Media: {('✅' if item.get('media_file_id') else '❌')}\n🔗 URL Buttons: {count}", reply_markup=self.support_auto_reply_edit_menu(keyword))
        return True
    if a.startswith('a_support_ar_text_'):
        keyword = a.replace('a_support_ar_text_', '')
        item = await get_support_auto_reply(owner, keyword) or {}
        context.user_data.clear()
        context.user_data['wait_support_ar_text'] = keyword
        await q.edit_message_text('📄 Send the auto-reply text.\n\nHTML and variables are supported: {NAME} {ID} {USERNAME} {PLAN} {EXPIRY}', reply_markup=self.support_auto_reply_text_menu(keyword, bool(item.get('text'))))
        return True
    if a.startswith('a_support_ar_media_'):
        keyword = a.replace('a_support_ar_media_', '')
        item = await get_support_auto_reply(owner, keyword) or {}
        context.user_data.clear()
        context.user_data['wait_support_ar_media'] = keyword
        await q.edit_message_text('🖼 Send a photo, video, GIF or document.', reply_markup=self.support_auto_reply_media_menu(keyword, bool(item.get('media_file_id'))))
        return True
    if a.startswith('a_support_ar_buttons_'):
        keyword = a.replace('a_support_ar_buttons_', '')
        item = await get_support_auto_reply(owner, keyword) or {}
        context.user_data.clear()
        context.user_data['wait_support_ar_buttons'] = keyword
        await q.edit_message_text(url_buttons_header(), reply_markup=self.support_auto_reply_buttons_menu(keyword, bool(item.get('buttons'))))
        return True
    if a.startswith('a_support_ar_rmtext_'):
        keyword = a.replace('a_support_ar_rmtext_', '')
        await save_support_auto_reply(owner, keyword, text='')
        await q.edit_message_text('✅ Text removed', reply_markup=self.support_auto_reply_text_menu(keyword, False))
        return True
    if a.startswith('a_support_ar_rmmedia_'):
        keyword = a.replace('a_support_ar_rmmedia_', '')
        await save_support_auto_reply(owner, keyword, media_type='', media_file_id='')
        await q.edit_message_text('✅ Media removed', reply_markup=self.support_auto_reply_media_menu(keyword, False))
        return True
    if a.startswith('a_support_ar_rmbuttons_'):
        keyword = a.replace('a_support_ar_rmbuttons_', '')
        await save_support_auto_reply(owner, keyword, buttons=[])
        await q.edit_message_text('✅ Keyboard removed', reply_markup=self.support_auto_reply_buttons_menu(keyword, False))
        return True
    if a.startswith('a_support_ar_delete_'):
        keyword = a.replace('a_support_ar_delete_', '')
        await delete_support_auto_reply(owner, keyword)
        await q.edit_message_text('✅ Auto reply deleted', reply_markup=self.support_auto_replies_menu(await list_support_auto_replies(owner)))
        return True
    if a.startswith('a_support_ar_preview_'):
        keyword = a.replace('a_support_ar_preview_', '')
        item = await get_support_auto_reply(owner, keyword)
        if item:
            await self.send_support_template(context, owner, q.from_user.id, item, q.from_user)
        await q.answer('Preview sent', show_alert=True)
        return True
    if a == 'a_support_templates':
        templates = await list_support_templates(owner)
        text = '⚡ Live Support Reply Templates\n\nTopic/private support me saved command bhejo, jaise /payment. Bot saved text, media aur buttons user ko reply ke roop me bhejega.\n\nVariables: {NAME} {ID} {USERNAME} {PLAN} {EXPIRY}'
        await q.edit_message_text(text, reply_markup=self.support_templates_menu(templates))
        return True
    if a == 'a_support_tpl_add':
        context.user_data.clear()
        context.user_data['wait_support_tpl_command'] = True
        await q.edit_message_text('Command name bhejo. Example: payment\n\nSlash mat lagao. Sirf letters, numbers aur underscore.', reply_markup=self.back('a_support_templates'))
        return True
    if a.startswith('a_support_tpl_view_'):
        command = a.replace('a_support_tpl_view_', '')
        tpl = await get_support_template(owner, command)
        if not tpl:
            await q.edit_message_text('❌ Template not found', reply_markup=self.back('a_support_templates'))
            return True
        count = sum((len(row) for row in tpl.get('buttons') or []))
        auto_delete = _format_auto_delete(_template_auto_delete_seconds(tpl))
        await q.edit_message_text(f"⚡ /{command}\n\n📝 Text: {('✅' if tpl.get('text') else '❌')}\n🖼 Media: {('✅' if tpl.get('media_file_id') else '❌')}\n🔗 Buttons: {count}\n⏱ Auto Remove: {auto_delete}", reply_markup=self.support_template_edit_menu(command))
        return True
    if a.startswith('a_support_tpl_text_'):
        command = a.replace('a_support_tpl_text_', '')
        tpl = await get_support_template(owner, command) or {}
        context.user_data.clear()
        context.user_data['wait_support_tpl_text'] = command
        await q.edit_message_text('📄 Send the template reply text.\n\nHTML and variables are supported: {NAME} {ID} {USERNAME} {PLAN} {EXPIRY}', reply_markup=self.support_template_text_menu(command, bool(tpl.get('text'))))
        return True
    if a.startswith('a_support_tpl_media_'):
        command = a.replace('a_support_tpl_media_', '')
        tpl = await get_support_template(owner, command) or {}
        context.user_data.clear()
        context.user_data['wait_support_tpl_media'] = command
        await q.edit_message_text('🖼 Send a photo, video, GIF or document.', reply_markup=self.support_template_media_menu(command, bool(tpl.get('media_file_id'))))
        return True
    if a.startswith('a_support_tpl_buttons_'):
        command = a.replace('a_support_tpl_buttons_', '')
        tpl = await get_support_template(owner, command) or {}
        context.user_data.clear()
        context.user_data['wait_support_tpl_buttons'] = command
        await q.edit_message_text(url_buttons_header(), reply_markup=self.support_template_buttons_menu(command, bool(tpl.get('buttons'))))
        return True
    if a.startswith('a_support_tpl_autodel_'):
        command = a.replace('a_support_tpl_autodel_', '')
        tpl = await get_support_template(owner, command)
        if not tpl:
            await q.edit_message_text('❌ Template not found', reply_markup=self.back('a_support_templates'))
            return True
        current = _template_auto_delete_seconds(tpl)
        await q.edit_message_text(f'⏱ Template Auto Remove — /{command}\n\nCurrent: {_format_auto_delete(current)}\n\nBot ka template reply selected time ke baad automatically remove hoga.', reply_markup=self.support_template_auto_delete_menu(command, current))
        return True
    if a.startswith('a_tpl_ad_custom_'):
        command = a.replace('a_tpl_ad_custom_', '')
        context.user_data.clear()
        context.user_data['wait_support_tpl_auto_delete'] = command
        await q.edit_message_text('⌨️ Custom auto-remove duration bhejo.\n\nExamples:\n30s = 30 seconds\n2m = 2 minutes\n1h = 1 hour\n6h = 6 hours\n1d = 1 day\noff = disable\n\nMaximum: 7 days', reply_markup=self.back(f'a_support_tpl_autodel_{command}'))
        return True
    if a.startswith('a_tpl_ad_'):
        payload = a.replace('a_tpl_ad_', '', 1)
        seconds_text, command = payload.split('_', 1)
        seconds = int(seconds_text)
        await save_support_template(owner, command, auto_delete_seconds=seconds)
        await q.edit_message_text(f'✅ Template Auto Remove updated\n\n/{command}: {_format_auto_delete(seconds)}', reply_markup=self.support_template_auto_delete_menu(command, seconds))
        return True
    if a.startswith('a_support_tpl_rmtext_'):
        command = a.replace('a_support_tpl_rmtext_', '')
        await save_support_template(owner, command, text='')
        await q.edit_message_text('✅ Text removed', reply_markup=self.support_template_text_menu(command, False))
        return True
    if a.startswith('a_support_tpl_rmmedia_'):
        command = a.replace('a_support_tpl_rmmedia_', '')
        await save_support_template(owner, command, media_type='', media_file_id='')
        await q.edit_message_text('✅ Media removed', reply_markup=self.support_template_media_menu(command, False))
        return True
    if a.startswith('a_support_tpl_rmbuttons_'):
        command = a.replace('a_support_tpl_rmbuttons_', '')
        await save_support_template(owner, command, buttons=[])
        await q.edit_message_text('✅ Keyboard removed', reply_markup=self.support_template_buttons_menu(command, False))
        return True
    if a.startswith('a_support_tpl_delete_'):
        command = a.replace('a_support_tpl_delete_', '')
        await delete_support_template(owner, command)
        await q.edit_message_text(f'✅ /{command} deleted', reply_markup=self.support_templates_menu(await list_support_templates(owner)))
        return True
    if a.startswith('a_support_tpl_preview_'):
        command = a.replace('a_support_tpl_preview_', '')
        tpl = await get_support_template(owner, command)
        await self.send_support_template(context, owner, q.from_user.id, tpl, q.from_user)
        await q.answer('Preview sent', show_alert=True)
        return True
    return False
