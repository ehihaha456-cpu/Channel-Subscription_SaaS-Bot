"""Business Automation UI and MTProto account connection inside clone-bot Admin Panel."""

import logging
from datetime import datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telethon import TelegramClient
from telethon.errors import (
    PasswordHashInvalidError,
    PhoneCodeExpiredError,
    PhoneCodeInvalidError,
    PhoneNumberInvalidError,
    SessionPasswordNeededError,
)
from telethon.sessions import StringSession

from config import TELEGRAM_API_HASH, TELEGRAM_API_ID
from database.seller_data import (
    business_automation_stats,
    count_business_accounts,
    disconnect_business_account,
    get_business_account,
    get_business_accounts,
    get_seller_settings,
    save_business_account_session,
    set_seller_setting,
)
from utils.crypto import decrypt_secret, encrypt_secret

logger = logging.getLogger(__name__)


def _mask_phone(phone):
    value = str(phone or "")
    if len(value) <= 4:
        return "****"
    return f"***{value[-4:]}"


def _mask_hash(value):
    value = str(value or "")
    if not value:
        return "missing"
    return f"{value[:4]}...{value[-4:]}" if len(value) > 8 else "present"


def _kb(rows):
    return InlineKeyboardMarkup(rows)


def _buttons_count(rows):
    return sum(len(row) for row in (rows or []))


def _templates(settings):
    return [dict(x) for x in (settings.get("business_reply_templates") or []) if isinstance(x, dict)]


def _template(settings, template_id):
    return next((x for x in _templates(settings) if str(x.get("id")) == str(template_id)), None)


def _home_keyboard(connected, enabled):
    rows = [
        [InlineKeyboardButton("🔗 Connect Telegram Account", callback_data="ba_connect")],
        [InlineKeyboardButton(f"📱 Connected Accounts ({connected})", callback_data="ba_accounts")],
        [InlineKeyboardButton("👋 Welcome Message", callback_data="ba_welcome")],
        [InlineKeyboardButton("💬 Auto Reply & Reply Templates", callback_data="ba_replies")],
        [InlineKeyboardButton("⚙️ Settings", callback_data="ba_settings")],
        [InlineKeyboardButton("📊 Statistics", callback_data="ba_stats")],
    ]
    if connected:
        rows.append([InlineKeyboardButton("🔌 Disconnect Account", callback_data="ba_disconnect")])
    rows.append([InlineKeyboardButton("⬅ Admin Panel", callback_data="a_home")])
    return _kb(rows)


async def _home(owner):
    settings = await get_seller_settings(owner)
    connected = await count_business_accounts(owner)
    enabled = bool(settings.get("business_automation_enabled"))
    text = (
        "💼 Business Automation\n\n"
        f"Status: {'🟢 Enabled' if enabled else '🔴 Disabled'}\n"
        f"Connected Accounts: {connected}\n\n"
        "All connected Telegram accounts use one shared configuration:\n"
        "• Welcome message and media\n• URL buttons\n• Auto replies\n"
        "• Reply templates\n• Settings and statistics"
    )
    return text, _home_keyboard(connected, enabled)


def _welcome_text(s):
    return (
        "👋 Business Welcome Message\n\n"
        f"Status: {'Enabled' if s.get('business_welcome_enabled', True) else 'Disabled'}\n"
        f"Text: {'Added' if s.get('business_welcome_message') else 'Not added'}\n"
        f"Media: {'Added' if s.get('business_welcome_media_file_id') else 'Not added'}\n"
        f"URL Buttons: {_buttons_count(s.get('business_welcome_buttons'))}"
    )


def _welcome_keyboard(s):
    rows = [
        [InlineKeyboardButton("Disable Welcome" if s.get("business_welcome_enabled", True) else "Enable Welcome", callback_data="ba_welcome_toggle")],
        [InlineKeyboardButton("✏️ Set Welcome Text", callback_data="ba_welcome_text")],
        [InlineKeyboardButton("🖼 Set Welcome Media", callback_data="ba_welcome_media")],
    ]
    if s.get("business_welcome_media_file_id"):
        rows.append([InlineKeyboardButton("🗑 Remove Media", callback_data="ba_welcome_media_remove")])
    rows += [
        [InlineKeyboardButton("➕ Add URL Button", callback_data="ba_welcome_button")],
        [InlineKeyboardButton(f"🗑 Clear URL Buttons ({_buttons_count(s.get('business_welcome_buttons'))})", callback_data="ba_welcome_buttons_clear")],
        [InlineKeyboardButton("👁 Preview", callback_data="ba_welcome_preview")],
        [InlineKeyboardButton("⬅ Business Automation", callback_data="ba_home")],
    ]
    return _kb(rows)


def _auto_text(s):
    return (
        "💬 Business Auto Reply\n\n"
        f"Status: {'Enabled' if s.get('business_auto_reply_enabled', True) else 'Disabled'}\n"
        f"Text: {'Added' if s.get('business_auto_reply_message') else 'Not added'}\n"
        f"Media: {'Added' if s.get('business_auto_reply_media_file_id') else 'Not added'}\n"
        f"URL Buttons: {_buttons_count(s.get('business_auto_reply_buttons'))}\n"
        f"Reply Delay: {int(s.get('business_reply_delay_seconds', 0) or 0)} seconds"
    )


def _auto_keyboard(s):
    rows = [
        [InlineKeyboardButton("Disable Auto Reply" if s.get("business_auto_reply_enabled", True) else "Enable Auto Reply", callback_data="ba_auto_toggle")],
        [InlineKeyboardButton("✏️ Set Reply Text", callback_data="ba_auto_text")],
        [InlineKeyboardButton("🖼 Set Reply Media", callback_data="ba_auto_media")],
    ]
    if s.get("business_auto_reply_media_file_id"):
        rows.append([InlineKeyboardButton("🗑 Remove Media", callback_data="ba_auto_media_remove")])
    rows += [
        [InlineKeyboardButton("➕ Add URL Button", callback_data="ba_auto_button")],
        [InlineKeyboardButton(f"🗑 Clear URL Buttons ({_buttons_count(s.get('business_auto_reply_buttons'))})", callback_data="ba_auto_buttons_clear")],
        [InlineKeyboardButton("⏱ Set Reply Delay", callback_data="ba_delay")],
        [InlineKeyboardButton("👁 Preview", callback_data="ba_auto_preview")],
        [InlineKeyboardButton("⬅ Auto Reply & Templates", callback_data="ba_replies")],
    ]
    return _kb(rows)


def _replies_keyboard(s):
    return _kb([
        [InlineKeyboardButton(f"💬 Auto Reply ({'On' if s.get('business_auto_reply_enabled', True) else 'Off'})", callback_data="ba_auto")],
        [InlineKeyboardButton(f"📝 Reply Templates ({len(_templates(s))})", callback_data="ba_templates")],
        [InlineKeyboardButton("Disable Templates" if s.get("business_templates_enabled", True) else "Enable Templates", callback_data="ba_templates_toggle")],
        [InlineKeyboardButton("⬅ Business Automation", callback_data="ba_home")],
    ])


def _templates_keyboard(s):
    rows = [[InlineKeyboardButton(f"📝 {x.get('name') or x.get('shortcut') or 'Template'}", callback_data=f"ba_tpl_open_{x.get('id')}")] for x in _templates(s)]
    rows += [[InlineKeyboardButton("➕ Add Reply Template", callback_data="ba_tpl_add")], [InlineKeyboardButton("⬅ Auto Reply & Templates", callback_data="ba_replies")]]
    return _kb(rows)


def _template_text(t):
    return (
        "📝 Reply Template\n\n"
        f"Name: {t.get('name') or '-'}\nShortcut: {t.get('shortcut') or '-'}\n"
        f"Text: {'Added' if t.get('text') else 'Not added'}\n"
        f"Media: {'Added' if t.get('media_file_id') else 'Not added'}\n"
        f"URL Buttons: {_buttons_count(t.get('buttons'))}"
    )


def _template_keyboard(t):
    tid = str(t.get("id"))
    rows = [
        [InlineKeyboardButton("✏️ Edit Name & Shortcut", callback_data=f"ba_tpl_meta_{tid}")],
        [InlineKeyboardButton("✏️ Set Template Text", callback_data=f"ba_tpl_text_{tid}")],
        [InlineKeyboardButton("🖼 Set Template Media", callback_data=f"ba_tpl_media_{tid}")],
    ]
    if t.get("media_file_id"):
        rows.append([InlineKeyboardButton("🗑 Remove Media", callback_data=f"ba_tpl_media_remove_{tid}")])
    rows += [
        [InlineKeyboardButton("➕ Add URL Button", callback_data=f"ba_tpl_button_{tid}")],
        [InlineKeyboardButton(f"🗑 Clear URL Buttons ({_buttons_count(t.get('buttons'))})", callback_data=f"ba_tpl_buttons_clear_{tid}")],
        [InlineKeyboardButton("👁 Preview", callback_data=f"ba_tpl_preview_{tid}")],
        [InlineKeyboardButton("🗑 Delete Template", callback_data=f"ba_tpl_delete_{tid}")],
        [InlineKeyboardButton("⬅ Reply Templates", callback_data="ba_templates")],
    ]
    return _kb(rows)


def _settings_text(s):
    return (
        "⚙️ Business Automation Settings\n\n"
        f"Automation: {'Enabled' if s.get('business_automation_enabled') else 'Disabled'}\n"
        f"Welcome Once: {'Enabled' if s.get('business_welcome_once', True) else 'Disabled'}\n"
        f"Ignore Own Messages: {'Enabled' if s.get('business_ignore_outgoing', True) else 'Disabled'}\n"
        f"Anti-loop: {'Enabled' if s.get('business_anti_loop', True) else 'Disabled'}\n"
        f"Flood Protection: {'Enabled' if s.get('business_flood_protection', True) else 'Disabled'}\n"
        f"Working Hours: {'Enabled' if s.get('business_working_hours_enabled') else 'Disabled'}\n"
        f"Reply Delay: {int(s.get('business_reply_delay_seconds', 0) or 0)} seconds"
    )


def _settings_keyboard(s):
    return _kb([
        [InlineKeyboardButton("Disable Automation" if s.get("business_automation_enabled") else "Enable Automation", callback_data="ba_setting_automation")],
        [InlineKeyboardButton("Disable Welcome Once" if s.get("business_welcome_once", True) else "Enable Welcome Once", callback_data="ba_setting_once")],
        [InlineKeyboardButton("Allow Own Messages" if s.get("business_ignore_outgoing", True) else "Ignore Own Messages", callback_data="ba_setting_outgoing")],
        [InlineKeyboardButton("Disable Anti-loop" if s.get("business_anti_loop", True) else "Enable Anti-loop", callback_data="ba_setting_loop")],
        [InlineKeyboardButton("Disable Flood Protection" if s.get("business_flood_protection", True) else "Enable Flood Protection", callback_data="ba_setting_flood")],
        [InlineKeyboardButton("Disable Working Hours" if s.get("business_working_hours_enabled") else "Enable Working Hours", callback_data="ba_setting_hours_toggle")],
        [InlineKeyboardButton("🕒 Set Working Hours", callback_data="ba_setting_hours")],
        [InlineKeyboardButton("⏱ Set Reply Delay", callback_data="ba_setting_delay")],
        [InlineKeyboardButton("⬅ Business Automation", callback_data="ba_home")],
    ])


def _preview_markup(rows):
    clean = [[InlineKeyboardButton(str(b.get("text") or "Open"), url=str(b.get("url"))) for b in row if b.get("url")] for row in (rows or [])]
    clean = [row for row in clean if row]
    return _kb(clean) if clean else None


async def _send_preview(message, text, media_type, file_id, buttons):
    markup = _preview_markup(buttons)
    text = text or "Preview message"
    if media_type == "photo" and file_id:
        await message.reply_photo(file_id, caption=text, reply_markup=markup)
    elif media_type == "video" and file_id:
        await message.reply_video(file_id, caption=text, reply_markup=markup)
    else:
        await message.reply_text(text, reply_markup=markup)


def _mtproto_ready():
    return bool(TELEGRAM_API_ID and TELEGRAM_API_HASH)


async def _send_code(context, phone):
    client = TelegramClient(StringSession(), int(TELEGRAM_API_ID), TELEGRAM_API_HASH)
    logger.info("BA login: connecting client phone=%s", _mask_phone(phone))
    await client.connect()
    sent = await client.send_code_request(phone)
    context.user_data["ba_auth"] = {
        "step": "code",
        "phone": phone,
        "phone_code_hash": sent.phone_code_hash,
        "client": client,
    }
    logger.info(
        "BA login: code sent phone=%s hash=%s client_connected=%s",
        _mask_phone(phone),
        _mask_hash(sent.phone_code_hash),
        client.is_connected(),
    )


async def _finish_auth(context, owner, code=None, password=None):
    auth = context.user_data.get("ba_auth") or {}
    client = auth.get("client")
    logger.info(
        "BA login: verify start owner=%s step=%s phone=%s hash=%s client_present=%s client_connected=%s password_flow=%s",
        owner,
        auth.get("step"),
        _mask_phone(auth.get("phone")),
        _mask_hash(auth.get("phone_code_hash")),
        bool(client),
        bool(client and client.is_connected()),
        password is not None,
    )
    if not client:
        raise RuntimeError("Login session expired")
    if password is not None:
        await client.sign_in(password=password)
    else:
        await client.sign_in(phone=auth["phone"], code=code, phone_code_hash=auth["phone_code_hash"])
    me = await client.get_me()
    logger.info("BA login: authorization successful owner=%s telegram_user_id=%s", owner, getattr(me, "id", None))
    encrypted = encrypt_secret(StringSession.save(client.session))
    await save_business_account_session(owner, int(me.id), encrypted_session=encrypted, phone=auth.get("phone", ""), username=getattr(me, "username", "") or "", first_name=getattr(me, "first_name", "") or "")
    await client.disconnect()
    context.user_data.pop("ba_auth", None)


async def _logout(record):
    token = record.get("encrypted_session")
    if not token or not _mtproto_ready():
        return
    client = TelegramClient(StringSession(decrypt_secret(token)), int(TELEGRAM_API_ID), TELEGRAM_API_HASH)
    try:
        await client.connect()
        if await client.is_user_authorized():
            await client.log_out()
    finally:
        await client.disconnect()


async def handle(self, update, context, q, owner, staff_record, action, role):
    if not action.startswith("ba_"):
        return False
    if role != "seller":
        await q.answer("Only the seller can manage Business Automation.", show_alert=True)
        return True

    if action == "ba_home":
        text, markup = await _home(owner); await q.edit_message_text(text, reply_markup=markup); return True
    if action == "ba_accounts":
        accounts = await get_business_accounts(owner)
        lines = ["📱 Connected Telegram Accounts", ""]
        if not accounts: lines.append("No account is connected yet.")
        for i, x in enumerate(accounts, 1):
            name = x.get("first_name") or x.get("username") or x.get("account_user_id")
            username = f"@{x.get('username')}" if x.get("username") else "No username"
            lines.append(f"{i}. {name}\n{username}\nStatus: {x.get('connection_status', 'connected').title()}")
        await q.edit_message_text("\n\n".join(lines), reply_markup=_kb([[InlineKeyboardButton("⬅ Business Automation", callback_data="ba_home")]])); return True
    if action == "ba_connect":
        if not _mtproto_ready():
            await q.edit_message_text("⚠️ Telegram API credentials are not configured by the platform owner.", reply_markup=_kb([[InlineKeyboardButton("⬅ Business Automation", callback_data="ba_home")]])); return True
        context.user_data["ba_auth"] = {"step": "phone"}
        await q.edit_message_text("🔗 Connect Telegram Account\n\nSend the phone number with country code.\nExample: +919876543210\n\nSend /cancel to stop."); return True
    if action == "ba_disconnect":
        accounts = await get_business_accounts(owner)
        if not accounts:
            await q.answer("No connected account.", show_alert=True); return True
        rows = [[InlineKeyboardButton(f"Disconnect {x.get('username') or x.get('first_name') or x.get('account_user_id')}", callback_data=f"ba_disconnect_{int(x['account_user_id'])}")] for x in accounts]
        rows.append([InlineKeyboardButton("⬅ Business Automation", callback_data="ba_home")])
        await q.edit_message_text("🔌 Select the Telegram account to disconnect.", reply_markup=_kb(rows)); return True
    if action.startswith("ba_disconnect_"):
        account_id = int(action.rsplit("_", 1)[1]); record = await get_business_account(owner, account_id)
        if record:
            try: await _logout(record)
            except Exception: logger.exception("Remote business logout failed owner=%s account=%s", owner, account_id)
        removed = await disconnect_business_account(owner, account_id)
        await q.answer("Account disconnected." if removed else "Account not found.", show_alert=not removed)
        text, markup = await _home(owner); await q.edit_message_text(text, reply_markup=markup); return True

    s = await get_seller_settings(owner)
    if action == "ba_welcome": await q.edit_message_text(_welcome_text(s), reply_markup=_welcome_keyboard(s)); return True
    if action == "ba_welcome_toggle": await set_seller_setting(owner, "business_welcome_enabled", not s.get("business_welcome_enabled", True)); s=await get_seller_settings(owner); await q.edit_message_text(_welcome_text(s), reply_markup=_welcome_keyboard(s)); return True
    if action in {"ba_welcome_text","ba_welcome_media","ba_welcome_button","ba_auto_text","ba_auto_media","ba_auto_button","ba_delay","ba_tpl_add","ba_setting_hours","ba_setting_delay"}:
        field = {"ba_welcome_text":"welcome_text","ba_welcome_media":"welcome_media","ba_welcome_button":"welcome_button","ba_auto_text":"auto_text","ba_auto_media":"auto_media","ba_auto_button":"auto_button","ba_delay":"delay","ba_tpl_add":"template_add","ba_setting_hours":"working_hours","ba_setting_delay":"delay"}[action]
        context.user_data["ba_editor"] = {"field": field}
        prompt = {"welcome_text":"Send the new welcome text.","welcome_media":"Send one photo or video.","welcome_button":"Send: Button Name | https://example.com","auto_text":"Send the auto reply text.","auto_media":"Send one photo or video.","auto_button":"Send: Button Name | https://example.com","delay":"Send reply delay in seconds (0-300).","template_add":"Send: Shortcut | Template Name","working_hours":"Send: HH:MM | HH:MM | Timezone\nExample: 09:00 | 21:00 | Asia/Kolkata"}[field]
        await q.edit_message_text(prompt + "\n\nSend /cancel to stop."); return True
    if action == "ba_welcome_media_remove": await set_seller_setting(owner,"business_welcome_media_type",""); await set_seller_setting(owner,"business_welcome_media_file_id",""); s=await get_seller_settings(owner); await q.edit_message_text(_welcome_text(s),reply_markup=_welcome_keyboard(s)); return True
    if action == "ba_welcome_buttons_clear": await set_seller_setting(owner,"business_welcome_buttons",[]); s=await get_seller_settings(owner); await q.edit_message_text(_welcome_text(s),reply_markup=_welcome_keyboard(s)); return True
    if action == "ba_welcome_preview": await _send_preview(q.message,s.get("business_welcome_message"),s.get("business_welcome_media_type"),s.get("business_welcome_media_file_id"),s.get("business_welcome_buttons")); await q.answer("Preview sent."); return True

    if action == "ba_replies": await q.edit_message_text("💬 Auto Reply & Reply Templates",reply_markup=_replies_keyboard(s)); return True
    if action == "ba_auto": await q.edit_message_text(_auto_text(s),reply_markup=_auto_keyboard(s)); return True
    if action == "ba_auto_toggle": await set_seller_setting(owner,"business_auto_reply_enabled",not s.get("business_auto_reply_enabled",True)); s=await get_seller_settings(owner); await q.edit_message_text(_auto_text(s),reply_markup=_auto_keyboard(s)); return True
    if action == "ba_auto_media_remove": await set_seller_setting(owner,"business_auto_reply_media_type",""); await set_seller_setting(owner,"business_auto_reply_media_file_id",""); s=await get_seller_settings(owner); await q.edit_message_text(_auto_text(s),reply_markup=_auto_keyboard(s)); return True
    if action == "ba_auto_buttons_clear": await set_seller_setting(owner,"business_auto_reply_buttons",[]); s=await get_seller_settings(owner); await q.edit_message_text(_auto_text(s),reply_markup=_auto_keyboard(s)); return True
    if action == "ba_auto_preview": await _send_preview(q.message,s.get("business_auto_reply_message"),s.get("business_auto_reply_media_type"),s.get("business_auto_reply_media_file_id"),s.get("business_auto_reply_buttons")); await q.answer("Preview sent."); return True
    if action == "ba_templates_toggle": await set_seller_setting(owner,"business_templates_enabled",not s.get("business_templates_enabled",True)); s=await get_seller_settings(owner); await q.edit_message_text("💬 Auto Reply & Reply Templates",reply_markup=_replies_keyboard(s)); return True
    if action == "ba_templates": await q.edit_message_text("📝 Reply Templates",reply_markup=_templates_keyboard(s)); return True

    if action.startswith("ba_tpl_"):
        suffix = action[len("ba_tpl_"):]
        op = ""
        tid = ""
        for candidate in ("media_remove", "buttons_clear", "preview", "delete", "open", "meta", "text", "media", "button"):
            prefix = candidate + "_"
            if suffix.startswith(prefix):
                op = candidate
                tid = suffix[len(prefix):]
                break
        if suffix == "add":
            op = "add"
        if op == "add": return True
        t = _template(s, tid)
        if not t: await q.answer("Template not found.",show_alert=True); return True
        if op == "open": await q.edit_message_text(_template_text(t),reply_markup=_template_keyboard(t)); return True
        if op in {"meta","text","media","button"}:
            context.user_data["ba_editor"]={"field":f"template_{op}","template_id":tid}
            await q.edit_message_text({"meta":"Send: Shortcut | Template Name","text":"Send the template text.","media":"Send one photo or video.","button":"Send: Button Name | https://example.com"}[op]); return True
        templates = _templates(s)
        target = next(x for x in templates if str(x.get("id")) == tid)
        if op == "media_remove": target["media_type"]=""; target["media_file_id"]=""
        elif op == "buttons_clear": target["buttons"]=[]
        elif op == "delete": templates=[x for x in templates if str(x.get("id")) != tid]; await set_seller_setting(owner,"business_reply_templates",templates); s=await get_seller_settings(owner); await q.edit_message_text("✅ Reply template deleted.",reply_markup=_templates_keyboard(s)); return True
        elif op == "preview": await _send_preview(q.message,t.get("text") or t.get("name"),t.get("media_type"),t.get("media_file_id"),t.get("buttons")); await q.answer("Preview sent."); return True
        await set_seller_setting(owner,"business_reply_templates",templates); s=await get_seller_settings(owner); t=_template(s,tid); await q.edit_message_text(_template_text(t),reply_markup=_template_keyboard(t)); return True

    if action == "ba_settings": await q.edit_message_text(_settings_text(s),reply_markup=_settings_keyboard(s)); return True
    toggle_map={"ba_setting_automation":("business_automation_enabled",False),"ba_setting_once":("business_welcome_once",True),"ba_setting_outgoing":("business_ignore_outgoing",True),"ba_setting_loop":("business_anti_loop",True),"ba_setting_flood":("business_flood_protection",True),"ba_setting_hours_toggle":("business_working_hours_enabled",False)}
    if action in toggle_map:
        key,default=toggle_map[action]; await set_seller_setting(owner,key,not s.get(key,default)); s=await get_seller_settings(owner); await q.edit_message_text(_settings_text(s),reply_markup=_settings_keyboard(s)); return True
    if action == "ba_stats":
        st=await business_automation_stats(owner)
        text=("📊 Business Automation Statistics\n\n"f"Connected Accounts: {int(st.get('accounts',0))}\n"f"Conversations: {int(st.get('conversations',0))}\n"f"Welcome Messages Sent: {int(st.get('welcome_sent',0))}\n"f"Auto Replies Sent: {int(st.get('auto_replies_sent',0))}\n"f"Reply Templates Used: {int(st.get('templates_used',0))}\n\n"f"Plans Opened: {int(st.get('plans_opened',0))}\n"f"Renew Opened: {int(st.get('renew_opened',0))}\n"f"Profile Opened: {int(st.get('profile_opened',0))}\n"f"Referral Opened: {int(st.get('referral_opened',0))}")
        await q.edit_message_text(text,reply_markup=_kb([[InlineKeyboardButton("🔄 Refresh",callback_data="ba_stats")],[InlineKeyboardButton("⬅ Business Automation",callback_data="ba_home")]])); return True
    return True


async def handle_text(self, update, context):
    owner = self.owner(context)
    if int(update.effective_user.id) != int(owner):
        return False
    text = (update.effective_message.text or "").strip()
    auth = context.user_data.get("ba_auth")
    if auth:
        if text.lower() == "/cancel":
            client=auth.get("client")
            if client:
                try: await client.disconnect()
                except Exception: pass
            context.user_data.pop("ba_auth",None); await update.effective_message.reply_text("Connection cancelled.",reply_markup=_kb([[InlineKeyboardButton("💼 Business Automation",callback_data="ba_home")]])); return True
        try:
            step=auth.get("step")
            if step == "phone":
                await _send_code(context,text); await update.effective_message.reply_text("✅ Login code sent by Telegram. Send the code here."); return True
            if step == "code":
                try: await _finish_auth(context,owner,code=text.replace(" ",""))
                except SessionPasswordNeededError: auth["step"]="password"; context.user_data["ba_auth"]=auth; await update.effective_message.reply_text("🔐 Two-step verification is enabled. Send your Telegram password."); return True
                await update.effective_message.reply_text("✅ Telegram account connected successfully.",reply_markup=_kb([[InlineKeyboardButton("💼 Business Automation",callback_data="ba_home")]])); return True
            if step == "password":
                await _finish_auth(context,owner,password=text); await update.effective_message.reply_text("✅ Telegram account connected successfully.",reply_markup=_kb([[InlineKeyboardButton("💼 Business Automation",callback_data="ba_home")]])); return True
        except (PhoneNumberInvalidError, PhoneCodeInvalidError, PhoneCodeExpiredError, PasswordHashInvalidError) as exc:
            current = context.user_data.get("ba_auth") or {}
            logger.exception(
                "BA login rejected owner=%s error=%s step=%s phone=%s hash=%s client_present=%s client_connected=%s",
                owner,
                type(exc).__name__,
                current.get("step"),
                _mask_phone(current.get("phone")),
                _mask_hash(current.get("phone_code_hash")),
                bool(current.get("client")),
                bool(current.get("client") and current.get("client").is_connected()),
            )
            await update.effective_message.reply_text(
                f"❌ Telegram login failed: {type(exc).__name__}. Please try again."
            )
            return True
        except Exception as exc:
            current = context.user_data.get("ba_auth") or {}
            logger.exception(
                "BA login unexpected failure owner=%s error=%s step=%s phone=%s hash=%s client_present=%s client_connected=%s",
                owner,
                type(exc).__name__,
                current.get("step"),
                _mask_phone(current.get("phone")),
                _mask_hash(current.get("phone_code_hash")),
                bool(current.get("client")),
                bool(current.get("client") and current.get("client").is_connected()),
            )
            await update.effective_message.reply_text(
                "❌ Telegram account could not be connected. Please try again."
            )
            return True

    editor=context.user_data.get("ba_editor")
    if not editor: return False
    if text.lower()=="/cancel": context.user_data.pop("ba_editor",None); await update.effective_message.reply_text("Editing cancelled.",reply_markup=_kb([[InlineKeyboardButton("💼 Business Automation",callback_data="ba_home")]])); return True
    field=editor.get("field"); tid=str(editor.get("template_id") or "")
    s=await get_seller_settings(owner)
    try:
        if field=="welcome_text": await set_seller_setting(owner,"business_welcome_message",text)
        elif field=="auto_text": await set_seller_setting(owner,"business_auto_reply_message",text)
        elif field in {"welcome_button","auto_button","template_button"}:
            if "|" not in text: raise ValueError("Use: Button Name | https://example.com")
            label,url=[x.strip() for x in text.split("|",1)]
            if not url.lower().startswith(("http://","https://")): raise ValueError("Enter a valid http/https URL")
            if field=="welcome_button": rows=list(s.get("business_welcome_buttons") or []); rows.append([{"text":label[:64],"url":url}]); await set_seller_setting(owner,"business_welcome_buttons",rows)
            elif field=="auto_button": rows=list(s.get("business_auto_reply_buttons") or []); rows.append([{"text":label[:64],"url":url}]); await set_seller_setting(owner,"business_auto_reply_buttons",rows)
            else:
                templates=_templates(s); t=next(x for x in templates if str(x.get("id"))==tid); rows=list(t.get("buttons") or []); rows.append([{"text":label[:64],"url":url}]); t["buttons"]=rows; await set_seller_setting(owner,"business_reply_templates",templates)
        elif field=="delay":
            value=int(text)
            if not 0<=value<=300: raise ValueError("Reply delay must be 0-300 seconds")
            await set_seller_setting(owner,"business_reply_delay_seconds",value)
        elif field=="working_hours":
            parts=[x.strip() for x in text.split("|")]
            if len(parts)!=3: raise ValueError("Use: HH:MM | HH:MM | Timezone")
            datetime.strptime(parts[0],"%H:%M"); datetime.strptime(parts[1],"%H:%M"); ZoneInfo(parts[2])
            await set_seller_setting(owner,"business_working_hours_start",parts[0]); await set_seller_setting(owner,"business_working_hours_end",parts[1]); await set_seller_setting(owner,"business_working_hours_timezone",parts[2])
        elif field=="template_add":
            if "|" not in text: raise ValueError("Use: Shortcut | Template Name")
            shortcut,name=[x.strip() for x in text.split("|",1)]; templates=_templates(s); templates.append({"id":uuid4().hex[:12],"shortcut":shortcut[:64],"name":name[:80],"text":"","media_type":"","media_file_id":"","buttons":[]}); await set_seller_setting(owner,"business_reply_templates",templates)
        elif field in {"template_meta","template_text"}:
            templates=_templates(s); t=next(x for x in templates if str(x.get("id"))==tid)
            if field=="template_meta":
                if "|" not in text: raise ValueError("Use: Shortcut | Template Name")
                t["shortcut"],t["name"]=[x.strip() for x in text.split("|",1)]
            else: t["text"]=text
            await set_seller_setting(owner,"business_reply_templates",templates)
        else: return False
    except (ValueError,KeyError,StopIteration) as exc:
        await update.effective_message.reply_text(f"❌ {exc}"); return True
    context.user_data.pop("ba_editor",None)
    await update.effective_message.reply_text("✅ Business Automation updated.",reply_markup=_kb([[InlineKeyboardButton("💼 Business Automation",callback_data="ba_home")]])); return True


async def handle_media(self, update, context):
    owner=self.owner(context)
    if int(update.effective_user.id)!=int(owner): return False
    editor=context.user_data.get("ba_editor") or {}; field=editor.get("field")
    if field not in {"welcome_media","auto_media","template_media"}: return False
    msg=update.effective_message; media_type="photo" if msg.photo else "video" if msg.video else ""; file_id=msg.photo[-1].file_id if msg.photo else msg.video.file_id if msg.video else ""
    if not file_id: return False
    if field=="welcome_media": await set_seller_setting(owner,"business_welcome_media_type",media_type); await set_seller_setting(owner,"business_welcome_media_file_id",file_id)
    elif field=="auto_media": await set_seller_setting(owner,"business_auto_reply_media_type",media_type); await set_seller_setting(owner,"business_auto_reply_media_file_id",file_id)
    else:
        tid=str(editor.get("template_id") or ""); s=await get_seller_settings(owner); templates=_templates(s); t=next((x for x in templates if str(x.get("id"))==tid),None)
        if not t: await msg.reply_text("❌ Reply template not found."); return True
        t["media_type"]=media_type; t["media_file_id"]=file_id; await set_seller_setting(owner,"business_reply_templates",templates)
    context.user_data.pop("ba_editor",None); await msg.reply_text("✅ Business Automation media updated.",reply_markup=_kb([[InlineKeyboardButton("💼 Business Automation",callback_data="ba_home")]])); return True
