from __future__ import annotations

import asyncio
import logging
import re
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

from telegram import ChatPermissions, Update
from telegram.ext import ContextTypes

from config import ADMIN_IDS
from database.group_manager_protection import get_protection, increment_warn, clear_warn
from database.staff import active_staff

logger = logging.getLogger(__name__)
FLOOD = defaultdict(lambda: deque(maxlen=50))
ADMIN_CACHE = {}
STAFF_CACHE = {}
BOT_PERMISSION_CACHE = {}
URL_RE = re.compile(r"(?i)(?:https?://|www\.|t\.me/|telegram\.me/|telegram\.dog/|@[A-Za-z0-9_]{5,})")

async def _is_chat_admin(bot, chat_id, user_id):
    key=(int(chat_id),int(user_id))
    now=time.monotonic()
    cached=ADMIN_CACHE.get(key)
    if cached and now-cached[0] < 20:
        return cached[1]
    try:
        member=await bot.get_chat_member(chat_id,user_id)
        value=member.status in {"administrator","creator"}
    except Exception:
        value=False
    ADMIN_CACHE[key]=(now,value)
    return value

async def _bot_can_moderate(bot, chat_id):
    """Check bot permissions once per chat; moderation actions require admin rights."""
    key=int(chat_id); now=time.monotonic()
    cached=BOT_PERMISSION_CACHE.get(key)
    if cached and now-cached[0] < 30:
        return cached[1]
    try:
        me=await bot.get_me()
        member=await bot.get_chat_member(chat_id, me.id)
        ok=member.status in {"administrator", "creator"}
        if ok and member.status == "administrator":
            # can_delete_messages is not exposed on every PTB member shape;
            # deletion failures are still handled independently below.
            ok=True
    except Exception:
        ok=False
    BOT_PERMISSION_CACHE[key]=(now,ok)
    return ok


async def _delete_ids(bot, chat_id, ids):
    if not ids:
        return 0
    unique=list(dict.fromkeys(int(x) for x in ids))
    results=await asyncio.gather(*(
        bot.delete_message(chat_id=chat_id,message_id=mid) for mid in unique
    ), return_exceptions=True)
    failed=[(mid,err) for mid,err in zip(unique,results) if isinstance(err,Exception)]
    if failed:
        logger.warning("Anti-flood deletion failed chat=%s count=%s first_error=%s", chat_id, len(failed), failed[0][1])
    return len(unique)-len(failed)


async def _punish(bot, owner, chat_id, user, action, *, warn_cfg, reason, reply_to=None, duration_seconds=None):
    action=str(action or "off").lower()
    if action=="off":
        return

    if action=="warn":
        try:
            count=await increment_warn(owner,chat_id,user.id,expires_seconds=duration_seconds)
        except TypeError:
            count=await increment_warn(owner,chat_id,user.id)
        except Exception:
            logger.exception("Anti-flood warning counter failed chat=%s user=%s",chat_id,user.id)
            count=1
        max_warns=int(warn_cfg.get("max_warns",3) or 3)
        warning_text=f"⚠️ {user.mention_html()} warned: {reason}\nWarns: {count}/{max_warns}"
        try:
            kwargs={"chat_id":chat_id,"text":warning_text,"parse_mode":"HTML"}
            if reply_to:
                kwargs["reply_to_message_id"]=reply_to
            await bot.send_message(**kwargs)
        except Exception:
            try:
                await bot.send_message(chat_id=chat_id,text=warning_text,parse_mode="HTML")
            except Exception:
                logger.exception("Anti-flood warning message failed chat=%s user=%s",chat_id,user.id)
        if count < max_warns:
            return
        action=str(warn_cfg.get("action") or "mute").lower()
        duration_seconds=int(warn_cfg.get("mute_minutes",30) or 30)*60
        try:
            await clear_warn(owner,chat_id,user.id)
        except Exception:
            pass

    if action not in {"kick","mute","ban"}:
        return

    seconds=int(duration_seconds or 0)
    until=datetime.now(timezone.utc)+timedelta(seconds=max(30,seconds or 1800))
    try:
        if action=="kick":
            await bot.ban_chat_member(chat_id,user.id)
            await bot.unban_chat_member(chat_id,user.id,only_if_banned=True)
        elif action=="ban":
            await bot.ban_chat_member(chat_id,user.id,until_date=until)
        elif action=="mute":
            await bot.restrict_chat_member(
                chat_id,user.id,
                permissions=ChatPermissions(can_send_messages=False),
                until_date=until,
            )
    except Exception:
        logger.exception("Anti-flood punishment failed action=%s chat=%s user=%s",action,chat_id,user.id)


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
    chat=update.effective_chat
    user=update.effective_user
    if not m or not chat or not user or user.is_bot or chat.type not in {"group","supergroup"}:
        return

    owner=int(context.application.bot_data.get("seller_owner_id") or 0)
    if not owner:
        return

    # Anonymous group-admin messages have sender_chat set to the group itself.
    anonymous_admin=bool(getattr(m,"sender_chat",None) and int(getattr(m.sender_chat,"id",0) or 0)==int(chat.id))
    if anonymous_admin:
        return

    # Group admins, bot/global admins and seller staff are exempt from Anti-Flood.
    if await _is_chat_admin(context.bot,chat.id,user.id):
        return
    bot_admin=int(user.id)==owner or int(user.id) in {int(x) for x in (ADMIN_IDS or [])}
    if not bot_admin:
        cache_key=(owner,int(user.id)); now=time.monotonic(); cached=STAFF_CACHE.get(cache_key)
        if cached and now-cached[0] < 30:
            bot_admin=cached[1]
        else:
            try:
                bot_admin=bool(await active_staff(owner,user.id))
            except Exception:
                bot_admin=False
            STAFF_CACHE[cache_key]=(now,bot_admin)
    if bot_admin:
        return

    p=await get_protection(owner,chat.id)
    warns=p.get("warns") or {}
    flood=p.get("anti_flood") or {}
    action=str(flood.get("action","off") or "off").strip().lower()

    # Flood detection is intentionally done before all other group protections.
    # This means /commands are counted even if Delete Commands stops their later handlers.
    if action in {"warn","kick","mute","ban"}:
        try:
            limit=max(2,int(flood.get("messages",5) or 5))
            seconds=max(1,int(flood.get("seconds",3) or 3))
        except (TypeError,ValueError):
            limit,seconds=5,3

        key=(owner,int(chat.id),int(user.id))
        now=time.monotonic()
        dq=FLOOD[key]
        cutoff=now-seconds
        while dq and dq[0][0] < cutoff:
            dq.popleft()
        dq.append((now,int(m.message_id)))

        if len(dq) >= limit:
            burst=[mid for _,mid in dq]
            dq.clear()
            logger.info(
                "ANTI_FLOOD_TRIGGER owner=%s chat=%s user=%s messages=%s window=%ss action=%s delete=%s",
                owner, chat.id, user.id, len(burst), seconds, action, bool(flood.get("delete",True))
            )
            if flood.get("delete",True):
                await _delete_ids(context.bot,chat.id,burst)
            duration_key={"warn":"warn_duration_seconds","mute":"mute_duration_seconds","ban":"ban_duration_seconds"}.get(action)
            duration_seconds=int(flood.get(duration_key,0) or 0) if duration_key else 0
            await _punish(
                context.bot,owner,chat.id,user,action,
                warn_cfg=warns,reason="Anti-flood",
                reply_to=None if flood.get("delete",True) else m.message_id,
                duration_seconds=duration_seconds,
            )
            return

    # Existing protections remain user-only below this point.
    text=(m.text or m.caption or "")
    low=" ".join(text.casefold().split())
    bw=p.get("banned_words") or {}
    if bw.get("action","off")!="off" and low:
        hit=next((w for w in bw.get("words") or [] if w and re.search(r"(?<!\w)"+re.escape(w)+r"(?!\w)",low,re.I)),None)
        if hit:
            if bw.get("delete",True):
                await _delete_ids(context.bot,chat.id,[m.message_id])
            await _punish(context.bot,owner,chat.id,user,bw.get("action"),warn_cfg=warns,reason=f"Banned word: {hit}",reply_to=m.message_id)
            return

    spam=p.get("anti_spam") or {}
    fw=spam.get("forwarding") or {}
    ftype=_forward_type(m)
    if ftype and fw.get(ftype) and fw.get("action","off")!="off":
        if fw.get("delete",False): await _delete_ids(context.bot,chat.id,[m.message_id])
        await _punish(context.bot,owner,chat.id,user,fw.get("action"),warn_cfg=warns,reason="Forwarded message",reply_to=m.message_id)
        return

    tg=spam.get("telegram_links") or {}
    if tg.get("action","off")!="off" and text:
        is_tg=bool(re.search(r"(?i)(?:https?://)?(?:t\.me|telegram\.me|telegram\.dog)/",text))
        if tg.get("username_antispam") and re.search(r"(?<!\w)@[A-Za-z0-9_]{5,}",text): is_tg=True
        if tg.get("bots_antispam") and re.search(r"(?i)(?:t\.me/|@)[A-Za-z0-9_]*bot\b",text): is_tg=True
        if is_tg:
            if tg.get("delete",False): await _delete_ids(context.bot,chat.id,[m.message_id])
            await _punish(context.bot,owner,chat.id,user,tg.get("action"),warn_cfg=warns,reason="Telegram link",reply_to=m.message_id)
            return

    total=spam.get("total_links") or {}
    if total.get("action","off")!="off" and text and URL_RE.search(text):
        if total.get("delete",False): await _delete_ids(context.bot,chat.id,[m.message_id])
        await _punish(context.bot,owner,chat.id,user,total.get("action"),warn_cfg=warns,reason="Link",reply_to=m.message_id)
        return
