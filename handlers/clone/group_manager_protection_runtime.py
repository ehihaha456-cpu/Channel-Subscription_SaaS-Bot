from __future__ import annotations

import re
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

from telegram import ChatPermissions, Update
from telegram.ext import ContextTypes

from database.group_manager_protection import get_protection, increment_warn, clear_warn

FLOOD = defaultdict(lambda: deque(maxlen=50))
URL_RE = re.compile(r"(?i)(?:https?://|www\.|t\.me/|telegram\.me/|telegram\.dog/|@[A-Za-z0-9_]{5,})")

async def _is_admin(bot, chat_id, user_id):
    try:
        member=await bot.get_chat_member(chat_id,user_id)
        return member.status in {"administrator","creator"}
    except Exception:
        return False

async def _delete(message):
    try:
        await message.delete()
    except Exception:
        pass

async def _punish(bot, owner, chat_id, user, action, *, warn_cfg, reason, reply_to=None):
    action=str(action or "off")
    if action=="off":
        return
    if action=="warn":
        count=await increment_warn(owner,chat_id,user.id)
        max_warns=int(warn_cfg.get("max_warns",3) or 3)
        warning_text = f"⚠️ {user.mention_html()} warned: {reason}\nWarns: {count}/{max_warns}"
        try:
            kwargs={"chat_id":chat_id,"text":warning_text,"parse_mode":"HTML"}
            if reply_to:
                kwargs["reply_to_message_id"]=reply_to
            await bot.send_message(**kwargs)
        except Exception:
            # If the flood message was deleted first, Telegram can reject a reply
            # to that deleted message. Send the warning normally instead.
            try:
                await bot.send_message(chat_id=chat_id,text=warning_text,parse_mode="HTML")
            except Exception:
                pass
        if count < max_warns:
            return
        action=str(warn_cfg.get("action") or "mute")
        await clear_warn(owner,chat_id,user.id)

    try:
        if action=="kick":
            await bot.ban_chat_member(chat_id,user.id)
            await bot.unban_chat_member(chat_id,user.id,only_if_banned=True)
        elif action=="ban":
            await bot.ban_chat_member(chat_id,user.id)
        elif action=="mute":
            minutes=int(warn_cfg.get("mute_minutes",30) or 30)
            until=datetime.now(timezone.utc)+timedelta(minutes=max(1,minutes))
            await bot.restrict_chat_member(chat_id,user.id,permissions=ChatPermissions(can_send_messages=False),until_date=until)
    except Exception:
        pass

def _forward_type(m):
    origin=getattr(m,"forward_origin",None)
    if not origin:
        return None
    name=origin.__class__.__name__.casefold()
    if "channel" in name: return "channels"
    if "chat" in name: return "groups"
    if "user" in name: return "users"
    return "bots" if "bot" in name else "users"

async def group_manager_protection_message(update:Update, context:ContextTypes.DEFAULT_TYPE):
    m=update.effective_message
    if not m or not m.from_user or m.from_user.is_bot or m.chat.type not in {"group","supergroup"}:
        return
    owner=int(context.application.bot_data.get("seller_owner_id") or 0)
    if not owner:
        return

    sender_is_admin = await _is_admin(context.bot,m.chat.id,m.from_user.id)
    p=await get_protection(owner,m.chat.id)
    warns=p.get("warns") or {}
    text=(m.text or m.caption or "")
    low=" ".join(text.casefold().split())

    # Anti-flood
    # Only normal group members are checked. Group admins, seller/bot admins,
    # and anonymous group-admin messages are ignored.
    flood=p.get("anti_flood") or {}
    action=flood.get("action","off")
    if action!="off" and not sender_is_admin:
        limit=max(2,int(flood.get("messages",5) or 5))
        seconds=max(1,int(flood.get("seconds",3) or 3))
        key=(owner,m.chat.id,m.from_user.id)
        now=time.monotonic()
        dq=FLOOD[key]
        dq.append((now,m.message_id))
        while dq and now-dq[0][0] > seconds:
            dq.popleft()

        if len(dq)>=limit:
            burst=list(dq)
            dq.clear()

            deleted=bool(flood.get("delete",True))
            if deleted:
                # Delete the whole detected burst, not only the last message.
                for _,message_id in burst:
                    try:
                        await context.bot.delete_message(chat_id=m.chat.id,message_id=message_id)
                    except Exception:
                        pass

            await _punish(
                context.bot,owner,m.chat.id,m.from_user,action,
                warn_cfg=warns,reason="Anti-flood",
                reply_to=None if deleted else m.message_id,
            )
            return

    # Keep group admins exempt from the remaining anti-spam/banned-word rules.
    if sender_is_admin:
        return

    # Banned words/phrases
    bw=p.get("banned_words") or {}
    if bw.get("action","off")!="off" and low:
        hit=next((w for w in bw.get("words") or [] if w and re.search(r"(?<!\w)"+re.escape(w)+r"(?!\w)",low,re.I)),None)
        if hit:
            if bw.get("delete",True): await _delete(m)
            await _punish(context.bot,owner,m.chat.id,m.from_user,bw.get("action"),warn_cfg=warns,reason=f"Banned word: {hit}",reply_to=m.message_id)
            return

    spam=p.get("anti_spam") or {}

    # Forwarding
    fw=spam.get("forwarding") or {}
    ftype=_forward_type(m)
    if ftype and fw.get(ftype) and fw.get("action","off")!="off":
        if fw.get("delete",False): await _delete(m)
        await _punish(context.bot,owner,m.chat.id,m.from_user,fw.get("action"),warn_cfg=warns,reason="Forwarded message",reply_to=m.message_id)
        return

    # Telegram Links
    tg=spam.get("telegram_links") or {}
    if tg.get("action","off")!="off" and text:
        is_tg=bool(re.search(r"(?i)(?:https?://)?(?:t\.me|telegram\.me|telegram\.dog)/",text))
        if tg.get("username_antispam") and re.search(r"(?<!\w)@[A-Za-z0-9_]{5,}",text):
            is_tg=True
        if tg.get("bots_antispam") and re.search(r"(?i)(?:t\.me/|@)[A-Za-z0-9_]*bot\b",text):
            is_tg=True
        if is_tg:
            if tg.get("delete",False): await _delete(m)
            await _punish(context.bot,owner,m.chat.id,m.from_user,tg.get("action"),warn_cfg=warns,reason="Telegram link",reply_to=m.message_id)
            return

    # Total links
    total=spam.get("total_links") or {}
    if total.get("action","off")!="off" and text and URL_RE.search(text):
        if total.get("delete",False): await _delete(m)
        await _punish(context.bot,owner,m.chat.id,m.from_user,total.get("action"),warn_cfg=warns,reason="Link",reply_to=m.message_id)
        return
