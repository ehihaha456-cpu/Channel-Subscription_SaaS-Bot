import re
from telegram import Update
from telegram.ext import ContextTypes
from database.group_manager import get_group
from handlers.common.editor_engine import build_editor_keyboard
from database.seller_data import get_bot_by_data_owner_id


def vars_text(text,user,chat):
    username=f"@{user.username}" if getattr(user,'username',None) else ''
    mention=f'<a href="tg://user?id={user.id}">{user.first_name or "User"}</a>'
    vals={'{NAME}':user.full_name or user.first_name or 'User','{ID}':str(user.id),'{USERNAME}':username,'{MENTION}':mention,'{GROUP}':chat.title or 'Group'}
    for k,v in vals.items(): text=text.replace(k,v)
    return text

async def _send(bot,chat_id,item,text,markup,reply_to=None):
    media=item.get('media') or []; common={'chat_id':chat_id,'parse_mode':'HTML','reply_markup':markup}
    if reply_to: common['reply_to_message_id']=reply_to
    if not media: return await bot.send_message(text=text,**common)
    e=media[0]; typ=e.get('type'); fid=e.get('file_id'); common['caption']=text
    if typ=='photo': return await bot.send_photo(photo=fid,**common)
    if typ=='video': return await bot.send_video(video=fid,**common)
    return await bot.send_document(document=fid,**common)

async def _markup(owner,item):
    rec=await get_bot_by_data_owner_id(owner) or {}; return build_editor_keyboard(item.get('buttons'),clone_username=(rec.get('bot_username') or '').lstrip('@'))

async def group_manager_new_members(update:Update,context:ContextTypes.DEFAULT_TYPE):
    m=update.effective_message
    if not m or m.chat.type not in {'group','supergroup'}: return
    owner=int(context.application.bot_data.get('seller_owner_id') or 0); doc=await get_group(owner,m.chat.id,m.chat.title or 'Group'); item=doc.get('welcome') or {}
    if not item.get('enabled') or not (item.get('text') or item.get('media')): return
    markup=await _markup(owner,item)
    for user in m.new_chat_members or []:
        if user.is_bot: continue
        await _send(context.bot,m.chat.id,item,vars_text(item.get('text') or '',user,m.chat),markup)

async def group_manager_message(update:Update,context:ContextTypes.DEFAULT_TYPE):
    m=update.effective_message
    if not m or m.chat.type not in {'group','supergroup'} or not m.from_user or m.from_user.is_bot: return
    text=(m.text or m.caption or '').strip()
    if not text: return
    owner=int(context.application.bot_data.get('seller_owner_id') or 0); doc=await get_group(owner,m.chat.id,m.chat.title or 'Group')
    low=text.casefold()
    for item in doc.get('auto_replies') or []:
        if item.get('enabled',True) and (item.get('keyword') or '').casefold() in low and (item.get('text') or item.get('media')):
            await _send(context.bot,m.chat.id,item,vars_text(item.get('text') or '',m.from_user,m.chat),await _markup(owner,item),m.message_id); return
    for item in doc.get('templates') or []:
        if item.get('enabled',True) and low==(item.get('keyword') or '').casefold() and (item.get('text') or item.get('media')):
            await _send(context.bot,m.chat.id,item,vars_text(item.get('text') or '',m.from_user,m.chat),await _markup(owner,item),m.message_id); return
