import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto, InputMediaVideo, InputMediaDocument
from handlers.common.editor_engine import build_editor_keyboard, editor_header, editor_menu_keyboard, editor_text_prompt, editor_media_prompt, business_url_buttons_header, parse_editor_buttons
from handlers.common.feature_navigation import register_feature_origin
from database.seller_data import get_channels
from database.seller_bots import get_bot_by_data_owner_id
from database.group_manager import get_group, update_welcome, list_auto_replies, save_auto_reply, list_templates, save_template, get_moderation, set_moderation_value, reset_moderation, get_auto_reply, get_template

logger=logging.getLogger(__name__)
def kb(rows): return InlineKeyboardMarkup(rows)
def selected(context): return int(context.user_data.get('gm_group_id') or 0)

async def groups_home(q,owner):
    groups=[x for x in await get_channels(owner) if int(x.get('chat_id',0))<0]
    rows=[[InlineKeyboardButton(f"👥 {str(x.get('title') or 'Group')[:35]}",callback_data=f"gm_select_{x['chat_id']}")] for x in groups]
    rows.append([InlineKeyboardButton('⬅ Admin Panel',callback_data='a_home')])
    await q.edit_message_text('🛡 GROUP MANAGER\n\nSelect a connected group. Settings and messages are saved separately for each selected group.',reply_markup=kb(rows))

async def group_home(q,context,owner):
    gid=selected(context); groups=await get_channels(owner); ch=next((x for x in groups if int(x.get('chat_id',0))==gid),None)
    if not ch: return await groups_home(q,owner)
    await get_group(owner,gid,ch.get('title') or 'Group')
    text=f"🛡 GROUP MANAGER\n\n👥 Group: {ch.get('title') or 'Group'}\n🆔 ID: {gid}\n🟢 Bot: Connected\n\nAll settings below apply only to this group."
    rows=[[InlineKeyboardButton('👋 Welcome Message',callback_data='gm_welcome')],[InlineKeyboardButton('💬 Auto Reply',callback_data='gm_auto'),InlineKeyboardButton('📝 Reply Templates',callback_data='gm_templates')],[InlineKeyboardButton('🗑 Message Moderation',callback_data='gm_mod')],[InlineKeyboardButton('⬅ Groups',callback_data='gm_home')]]
    await q.edit_message_text(text,reply_markup=kb(rows))

def welcome_text(item): return '👋 Group Welcome Message\n\nSent when a new member joins the selected group.\n\n'+editor_header('Current Setup',item,variables='{NAME} {ID} {USERNAME} {MENTION} {GROUP}')

def welcome_menu(item):
    base=editor_menu_keyboard('gm_welcome',item,back_callback='gm_group',allow_toggle=True)
    rows=[list(row) for row in base.inline_keyboard]
    delete_last='✅' if item.get('delete_last_welcome',False) else '❌'
    # Keep Back as the final row and place this group-specific option above it.
    rows.insert(-1,[InlineKeyboardButton(f'🗑 Delete Last Welcome: {delete_last}',callback_data='gm_welcome_delete_last')])
    return InlineKeyboardMarkup(rows)

async def preview(q,context,owner,item,title='Preview'):
    botrec=await get_bot_by_data_owner_id(owner) or {}; username=(botrec.get('bot_username') or '').lstrip('@')
    markup=build_editor_keyboard(item.get('buttons'),clone_username=username)
    text=item.get('text') or f'{title}: no text added.'; media=item.get('media') or []
    if not media:
        m=await q.message.reply_text(text,reply_markup=markup); register_feature_origin(m,text=text,markup=markup); return
    e=media[0]; typ=e.get('type'); fid=e.get('file_id')
    if typ=='photo': m=await q.message.reply_photo(fid,caption=text,reply_markup=markup)
    elif typ=='video': m=await q.message.reply_video(fid,caption=text,reply_markup=markup)
    else: m=await q.message.reply_document(fid,caption=text,reply_markup=markup)
    register_feature_origin(m,text=text,markup=markup)

async def handle(self,update,context,q,owner,staff,a,role):
    if not a.startswith('gm_'): return False
    if role!='seller': await q.answer('Only the seller can manage groups.',show_alert=True); return True
    if a=='gm_home': await groups_home(q,owner); return True
    if a.startswith('gm_select_'):
        context.user_data['gm_group_id']=int(a[len('gm_select_'):]); await group_home(q,context,owner); return True
    if a=='gm_group': await group_home(q,context,owner); return True
    gid=selected(context)
    if not gid: await groups_home(q,owner); return True
    doc=await get_group(owner,gid); item=doc.get('welcome') or {}
    if a=='gm_welcome': await q.edit_message_text(welcome_text(item),reply_markup=welcome_menu(item)); return True
    if a=='gm_welcome_toggle': await update_welcome(owner,gid,enabled=not item.get('enabled',False)); doc=await get_group(owner,gid); await q.edit_message_text(welcome_text(doc['welcome']),reply_markup=welcome_menu(doc['welcome'])); return True
    if a=='gm_welcome_delete_last': await update_welcome(owner,gid,delete_last_welcome=not item.get('delete_last_welcome',False)); doc=await get_group(owner,gid); await q.edit_message_text(welcome_text(doc['welcome']),reply_markup=welcome_menu(doc['welcome'])); return True
    if a=='gm_welcome_text': context.user_data['gm_input']='welcome_text'; await q.edit_message_text(editor_text_prompt('Group Welcome Text',variables='{NAME} {ID} {USERNAME} {MENTION} {GROUP}'),reply_markup=kb([[InlineKeyboardButton('⬅ Back',callback_data='gm_welcome')]])); return True
    if a=='gm_welcome_media': context.user_data['gm_input']='welcome_media'; await q.edit_message_text(editor_media_prompt('Group Welcome Media'),reply_markup=kb([[InlineKeyboardButton('⬅ Back',callback_data='gm_welcome')]])); return True
    if a=='gm_welcome_buttons': context.user_data['gm_input']='welcome_buttons'; await q.edit_message_text(business_url_buttons_header(),reply_markup=kb([[InlineKeyboardButton('⬅ Back',callback_data='gm_welcome')]])); return True
    if a=='gm_welcome_preview': await preview(q,context,owner,item,'Group Welcome'); return True
    if a=='gm_auto':
        items=await list_auto_replies(owner,gid); rows=[[InlineKeyboardButton(f"💬 {x.get('keyword','Keyword')}",callback_data=f"gm_ar_{x['id']}")] for x in items]; rows += [[InlineKeyboardButton('➕ Add Keyword',callback_data='gm_ar_add')],[InlineKeyboardButton('⬅ Back',callback_data='gm_group')]]; await q.edit_message_text('💬 Group Auto Reply\n\nKeyword replies are saved only for this selected group.',reply_markup=kb(rows)); return True
    if a=='gm_ar_add': context.user_data['gm_input']='ar_keyword'; await q.edit_message_text('➕ Add Auto Reply\n\nSend a keyword or phrase.',reply_markup=kb([[InlineKeyboardButton('⬅ Back',callback_data='gm_auto')]])); return True
    if a.startswith('gm_ar_') and a not in {'gm_ar_add'}:
        rest=a[len('gm_ar_'):]; parts=rest.rsplit('_',1); rid=parts[0]; action=parts[1] if len(parts)>1 and parts[1] in {'text','media','buttons','preview','toggle'} else 'open'; rid=rest if action=='open' else rid
        ar=await get_auto_reply(owner,gid,rid)
        if not ar: await q.answer('Auto Reply not found.',show_alert=True); return True
        if action=='open': await q.edit_message_text('💬 Group Auto Reply\n\nKeyword: '+ar.get('keyword','')+'\n\n'+editor_header('Current Setup',ar,variables='{NAME} {ID} {USERNAME} {MENTION} {GROUP}'),reply_markup=editor_menu_keyboard(f'gm_ar_{rid}',ar,back_callback='gm_auto',allow_toggle=True)); return True
        if action=='toggle': ar['enabled']=not ar.get('enabled',True); await save_auto_reply(owner,gid,ar); q.data=f'gm_ar_{rid}'; return await handle(self,update,context,q,owner,staff,q.data,role)
        if action in {'text','media','buttons'}: context.user_data['gm_input']=f'ar_{rid}_{action}'; prompt=editor_text_prompt('Group Auto Reply Text',variables='{NAME} {ID} {USERNAME} {MENTION} {GROUP}') if action=='text' else (editor_media_prompt('Group Auto Reply Media') if action=='media' else business_url_buttons_header()); await q.edit_message_text(prompt,reply_markup=kb([[InlineKeyboardButton('⬅ Back',callback_data=f'gm_ar_{rid}')]])); return True
        if action=='preview': await preview(q,context,owner,ar,'Auto Reply'); return True
    if a=='gm_templates':
        items=await list_templates(owner,gid); rows=[[InlineKeyboardButton(f"📝 {x.get('keyword','Template')}",callback_data=f"gm_tpl_{x['id']}")] for x in items]; rows += [[InlineKeyboardButton('➕ Add Reply Template',callback_data='gm_tpl_add')],[InlineKeyboardButton('⬅ Back',callback_data='gm_group')]]; await q.edit_message_text('📝 Group Reply Templates\n\nTemplates are saved only for this selected group.',reply_markup=kb(rows)); return True
    if a=='gm_tpl_add': context.user_data['gm_input']='tpl_keyword'; await q.edit_message_text('➕ Add Reply Template\n\nSend a unique keyword.',reply_markup=kb([[InlineKeyboardButton('⬅ Back',callback_data='gm_templates')]])); return True
    if a.startswith('gm_tpl_') and a not in {'gm_tpl_add'}:
        rest=a[len('gm_tpl_'):]; parts=rest.rsplit('_',1); tid=parts[0]; action=parts[1] if len(parts)>1 and parts[1] in {'text','media','buttons','preview','toggle'} else 'open'; tid=rest if action=='open' else tid
        it=await get_template(owner,gid,tid)
        if not it: await q.answer('Template not found.',show_alert=True); return True
        if action=='open': await q.edit_message_text('📝 Group Reply Template\n\nKeyword: '+it.get('keyword','')+'\n\n'+editor_header('Current Setup',it,variables='{NAME} {ID} {USERNAME} {MENTION} {GROUP}'),reply_markup=editor_menu_keyboard(f'gm_tpl_{tid}',it,back_callback='gm_templates',allow_toggle=True)); return True
        if action=='toggle': it['enabled']=not it.get('enabled',True); await save_template(owner,gid,it); q.data=f'gm_tpl_{tid}'; return await handle(self,update,context,q,owner,staff,q.data,role)
        if action in {'text','media','buttons'}: context.user_data['gm_input']=f'tpl_{tid}_{action}'; prompt=editor_text_prompt('Group Reply Template Text',variables='{NAME} {ID} {USERNAME} {MENTION} {GROUP}') if action=='text' else (editor_media_prompt('Group Reply Template Media') if action=='media' else business_url_buttons_header()); await q.edit_message_text(prompt,reply_markup=kb([[InlineKeyboardButton('⬅ Back',callback_data=f'gm_tpl_{tid}')]])); return True
        if action=='preview': await preview(q,context,owner,it,'Reply Template'); return True
    if a=='gm_mod':
        s=await get_moderation(owner,gid); mark=lambda v:'✅' if v else '❌'; rows=[[InlineKeyboardButton(f"{mark(s.get('enabled',True))} Moderation Master Switch",callback_data='gm_mod_master')],[InlineKeyboardButton('🗑 Delete Commands',callback_data='gm_mod_commands')],[InlineKeyboardButton('🔗 Link Protection',callback_data='gm_mod_links')],[InlineKeyboardButton('📦 Forwarded Media',callback_data='gm_mod_forwarded')],[InlineKeyboardButton('💥 Service Messages',callback_data='gm_mod_service')],[InlineKeyboardButton('🛡 Safety Settings',callback_data='gm_mod_safety')],[InlineKeyboardButton('♻️ Reset Settings',callback_data='gm_mod_reset')],[InlineKeyboardButton('⬅ Back',callback_data='gm_group')]]; await q.edit_message_text('🗑 Message Moderation\n\nThese deletion settings apply only to the selected group.',reply_markup=kb(rows)); return True
    if a=='gm_mod_master': s=await get_moderation(owner,gid); await set_moderation_value(owner,gid,'enabled',not s.get('enabled',True)); q.data='gm_mod'; return await handle(self,update,context,q,owner,staff,'gm_mod',role)
    if a=='gm_mod_reset': await reset_moderation(owner,gid); await q.answer('Group moderation settings reset.',show_alert=True); return await handle(self,update,context,q,owner,staff,'gm_mod',role)
    if a in {'gm_mod_commands','gm_mod_links','gm_mod_forwarded','gm_mod_service','gm_mod_safety'}:
        await q.edit_message_text('This section is now scoped to the selected group. Detailed existing moderation controls are being preserved under Group Manager.',reply_markup=kb([[InlineKeyboardButton('⬅ Back',callback_data='gm_mod')]])); return True
    return True

async def handle_text(self,update,context):
    mode=context.user_data.get('gm_input'); gid=selected(context)
    if not mode or not gid: return False
    owner=self.owner(context)
    if update.effective_user.id!=self.seller_account(context): return False
    text=(update.effective_message.text or '').strip()
    if mode=='welcome_text': await update_welcome(owner,gid,text=text); back='gm_welcome'; msg='✅ Welcome text saved.'
    elif mode=='welcome_buttons':
        try: buttons=parse_editor_buttons(text)
        except ValueError as e: await update.effective_message.reply_text(f'❌ {e}'); return True
        await update_welcome(owner,gid,buttons=buttons); back='gm_welcome'; msg='✅ Buttons saved.'
    elif mode=='ar_keyword': await save_auto_reply(owner,gid,{'keyword':text,'enabled':True,'text':'','media':[],'buttons':[]}); back='gm_auto'; msg='✅ Auto Reply created.'
    elif mode=='tpl_keyword': await save_template(owner,gid,{'keyword':text,'enabled':True,'text':'','media':[],'buttons':[]}); back='gm_templates'; msg='✅ Reply Template created.'
    elif mode.startswith('ar_') or mode.startswith('tpl_'):
        kind,rid,field=mode.split('_',2); item=await (get_auto_reply(owner,gid,rid) if kind=='ar' else get_template(owner,gid,rid))
        if not item: context.user_data.pop('gm_input',None); return True
        if field=='buttons':
            try: item['buttons']=parse_editor_buttons(text)
            except ValueError as e: await update.effective_message.reply_text(f'❌ {e}'); return True
        else: item['text']=text
        if kind=='ar': await save_auto_reply(owner,gid,item); back=f'gm_ar_{rid}'
        else: await save_template(owner,gid,item); back=f'gm_tpl_{rid}'
        msg='✅ Saved.'
    else: return False
    context.user_data.pop('gm_input',None); await update.effective_message.reply_text(msg,reply_markup=kb([[InlineKeyboardButton('⬅ Continue',callback_data=back)]])); return True

async def handle_media(self,update,context):
    mode=context.user_data.get('gm_input') or ''
    if not selected(context) or not (mode=='welcome_media' or mode.endswith('_media')): return False
    m=update.effective_message; entry=None
    if m.photo: entry={'type':'photo','file_id':m.photo[-1].file_id}
    elif m.video: entry={'type':'video','file_id':m.video.file_id}
    elif m.document: entry={'type':'document','file_id':m.document.file_id}
    if not entry: return False
    owner=self.owner(context); gid=selected(context)
    if mode=='welcome_media': await update_welcome(owner,gid,media=[entry]); back='gm_welcome'
    else:
        kind,rid,_=mode.split('_',2); item=await (get_auto_reply(owner,gid,rid) if kind=='ar' else get_template(owner,gid,rid)); item['media']=[entry]
        if kind=='ar': await save_auto_reply(owner,gid,item); back=f'gm_ar_{rid}'
        else: await save_template(owner,gid,item); back=f'gm_tpl_{rid}'
    context.user_data.pop('gm_input',None); await m.reply_text('✅ Media saved.',reply_markup=kb([[InlineKeyboardButton('⬅ Continue',callback_data=back)]])); return True
