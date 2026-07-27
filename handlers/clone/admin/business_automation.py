"""Business Automation UI and MTProto account connection inside clone-bot Admin Panel."""

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from handlers.common.editor_engine import (
    build_editor_keyboard,
    editor_header,
    editor_media_prompt,
    editor_menu_keyboard,
    editor_text_prompt,
    parse_editor_buttons,
    url_buttons_header,
)
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
from database.business_automation import (
    create_business_reply_template,
    delete_business_reply_template,
    get_business_auto_reply,
    get_business_reply_template,
    get_business_welcome,
    list_business_reply_templates,
    update_business_auto_reply,
    update_business_reply_template,
    update_business_welcome,
)
from utils.crypto import decrypt_secret, encrypt_secret
from services.business_automation_runtime import business_automation_runtime

logger = logging.getLogger(__name__)


def _kb(rows):
    return InlineKeyboardMarkup(rows)


def _buttons_count(rows):
    return sum(len(row) for row in (rows or []))


def _home_keyboard(connected: int, enabled: bool):
    return _kb([
        [InlineKeyboardButton("🔗 Connect Telegram Account", callback_data="ba_connect")],
        [InlineKeyboardButton(f"📱 Connected Accounts ({connected})", callback_data="ba_accounts")],
        [InlineKeyboardButton("👋 Welcome Message", callback_data="ba_welcome")],
        [
            InlineKeyboardButton("💬 Auto Reply", callback_data="ba_auto"),
            InlineKeyboardButton("📝 Reply Templates", callback_data="ba_templates"),
        ],
        [InlineKeyboardButton("⚙️ Settings", callback_data="ba_settings")],
        [InlineKeyboardButton("📊 Statistics", callback_data="ba_stats")],
        [InlineKeyboardButton("⬅ Admin Panel", callback_data="a_home")],
    ])


async def _home(owner: int):
    settings = await get_seller_settings(owner)
    connected = await count_business_accounts(owner)
    enabled = bool(settings.get("business_automation_enabled"))
    text = (
        "💼 Business Automation\n\n"
        f"Status: {'🟢 Enabled' if enabled else '🔴 Disabled'}\n"
        f"Connected Accounts: {connected}\n\n"
        "All connected Telegram accounts use one shared configuration:\n"
        "• Welcome message and media\n"
        "• URL buttons\n"
        "• Auto replies\n"
        "• Reply templates\n"
        "• Settings and statistics"
    )
    return text, _home_keyboard(connected, enabled)


async def _editor_state(owner: int) -> tuple[dict, dict, list[dict]]:
    welcome = await get_business_welcome(owner)
    auto_reply = await get_business_auto_reply(owner)
    templates = await list_business_reply_templates(owner)
    return welcome, auto_reply, templates


def _welcome_text(item):
    return editor_header(
        "👋 Business Welcome Message",
        item,
        variables="{NAME} {ID} {USERNAME} {MENTION} {DATE} {TIME}",
    )


def _welcome_keyboard(item):
    return editor_menu_keyboard(
        "ba_welcome", item, back_callback="ba_home", allow_toggle=True
    )


def _auto_text(item):
    return editor_header(
        "💬 Business Auto Reply",
        item,
        variables="{NAME} {ID} {USERNAME} {MENTION} {DATE} {TIME}",
    )


def _auto_keyboard(item):
    return editor_menu_keyboard(
        "ba_auto", item, back_callback="ba_home", allow_toggle=True
    )


def _templates_keyboard(templates):
    rows = [
        [InlineKeyboardButton(
            f"📝 {item.get('name') or item.get('shortcut') or 'Template'}",
            callback_data=f"ba_tpl_open_{item.get('template_id')}",
        )]
        for item in templates
    ]
    rows.extend([
        [InlineKeyboardButton("➕ Add Reply Template", callback_data="ba_tpl_add")],
        [InlineKeyboardButton("⬅ Business Automation", callback_data="ba_home")],
    ])
    return _kb(rows)


def _template_text(item):
    summary = editor_header(
        "📝 Business Reply Template",
        {**item, "enabled": True},
        variables="{NAME} {ID} {USERNAME} {MENTION} {DATE} {TIME}",
    )
    return (
        f"{summary}\n\n"
        f"Template Name: {item.get('name') or '-'}\n"
        f"Shortcut: {item.get('shortcut') or '-'}"
    )


def _template_keyboard(item):
    tid = str(item.get("template_id"))
    rows = [
        [InlineKeyboardButton("✏️ Name & Shortcut", callback_data=f"ba_tpl_meta_{tid}")],
    ]
    common = editor_menu_keyboard(
        f"ba_tpl_{tid}",
        {**item, "enabled": True},
        back_callback="ba_templates",
        allow_toggle=False,
        delete_callback=f"ba_tpl_delete_{tid}",
    )
    rows.extend(common.inline_keyboard)
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
    return build_editor_keyboard(rows)


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
    await client.connect()
    sent = await client.send_code_request(phone)
    context.user_data["ba_auth"] = {"step": "code", "phone": phone, "phone_code_hash": sent.phone_code_hash, "client": client}


async def _finish_auth(context, owner, code=None, password=None):
    auth = context.user_data.get("ba_auth") or {}
    client = auth.get("client")
    if not client:
        raise RuntimeError("Login session expired")
    if password is not None:
        await client.sign_in(password=password)
    else:
        await client.sign_in(phone=auth["phone"], code=code, phone_code_hash=auth["phone_code_hash"])
    me = await client.get_me()
    encrypted = encrypt_secret(StringSession.save(client.session))
    record = await save_business_account_session(owner, int(me.id), encrypted_session=encrypted, phone=auth.get("phone", ""), username=getattr(me, "username", "") or "", first_name=getattr(me, "first_name", "") or "")
    await client.disconnect()
    await business_automation_runtime.start_account(owner, int(me.id), record=record)
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
        rows = []
        if not accounts:
            lines.append("No account is connected yet.")
        for i, x in enumerate(accounts, 1):
            account_id = int(x["account_user_id"])
            name = x.get("first_name") or x.get("username") or account_id
            username = f"@{x.get('username')}" if x.get("username") else "No username"
            lines.append(
                f"{i}. {name}\n{username}\n"
                f"Status: {x.get('connection_status', 'connected').title()}"
            )
            rows.append([
                InlineKeyboardButton(
                    f"🔌 Disconnect {x.get('username') or x.get('first_name') or account_id}",
                    callback_data=f"ba_disconnect_{account_id}",
                )
            ])
        rows.append([InlineKeyboardButton("⬅ Business Automation", callback_data="ba_home")])
        await q.edit_message_text("\n\n".join(lines), reply_markup=_kb(rows)); return True
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
        await business_automation_runtime.stop_account(owner, account_id)
        removed = await disconnect_business_account(owner, account_id)
        await q.answer("Account disconnected." if removed else "Account not found.", show_alert=not removed)
        text, markup = await _home(owner); await q.edit_message_text(text, reply_markup=markup); return True

    s = await get_seller_settings(owner)
    welcome, auto_reply, templates = await _editor_state(owner)

    if action == "ba_welcome":
        await q.edit_message_text(_welcome_text(welcome), reply_markup=_welcome_keyboard(welcome)); return True
    if action == "ba_welcome_toggle":
        welcome = await update_business_welcome(owner, enabled=not welcome.get("enabled", True))
        await q.edit_message_text(_welcome_text(welcome), reply_markup=_welcome_keyboard(welcome)); return True
    if action == "ba_welcome_text":
        context.user_data["ba_editor"] = {"field": "welcome_text"}
        await q.edit_message_text(editor_text_prompt("Business Welcome Text", variables="{NAME} {ID} {USERNAME} {MENTION} {DATE} {TIME}")); return True
    if action == "ba_welcome_media":
        context.user_data["ba_editor"] = {"field": "welcome_media"}
        await q.edit_message_text(editor_media_prompt("Business Welcome Media")); return True
    if action == "ba_welcome_buttons":
        context.user_data["ba_editor"] = {"field": "welcome_buttons"}
        await q.edit_message_text(url_buttons_header() + "\n\nSend /cancel to stop."); return True
    if action == "ba_welcome_rmtext":
        welcome = await update_business_welcome(owner, text="")
        await q.edit_message_text(_welcome_text(welcome), reply_markup=_welcome_keyboard(welcome)); return True
    if action == "ba_welcome_rmmedia":
        welcome = await update_business_welcome(owner, media_type="", media_file_id="")
        await q.edit_message_text(_welcome_text(welcome), reply_markup=_welcome_keyboard(welcome)); return True
    if action == "ba_welcome_rmbuttons":
        welcome = await update_business_welcome(owner, buttons=[])
        await q.edit_message_text(_welcome_text(welcome), reply_markup=_welcome_keyboard(welcome)); return True
    if action == "ba_welcome_preview":
        await _send_preview(q.message, welcome.get("text"), welcome.get("media_type"), welcome.get("media_file_id"), welcome.get("buttons")); await q.answer("Preview sent."); return True

    if action == "ba_auto":
        await q.edit_message_text(_auto_text(auto_reply), reply_markup=_auto_keyboard(auto_reply)); return True
    if action == "ba_auto_toggle":
        auto_reply = await update_business_auto_reply(owner, enabled=not auto_reply.get("enabled", True))
        await q.edit_message_text(_auto_text(auto_reply), reply_markup=_auto_keyboard(auto_reply)); return True
    if action == "ba_auto_text":
        context.user_data["ba_editor"] = {"field": "auto_text"}
        await q.edit_message_text(editor_text_prompt("Business Auto Reply Text", variables="{NAME} {ID} {USERNAME} {MENTION} {DATE} {TIME}")); return True
    if action == "ba_auto_media":
        context.user_data["ba_editor"] = {"field": "auto_media"}
        await q.edit_message_text(editor_media_prompt("Business Auto Reply Media")); return True
    if action == "ba_auto_buttons":
        context.user_data["ba_editor"] = {"field": "auto_buttons"}
        await q.edit_message_text(url_buttons_header() + "\n\nSend /cancel to stop."); return True
    if action == "ba_auto_rmtext":
        auto_reply = await update_business_auto_reply(owner, text="")
        await q.edit_message_text(_auto_text(auto_reply), reply_markup=_auto_keyboard(auto_reply)); return True
    if action == "ba_auto_rmmedia":
        auto_reply = await update_business_auto_reply(owner, media_type="", media_file_id="")
        await q.edit_message_text(_auto_text(auto_reply), reply_markup=_auto_keyboard(auto_reply)); return True
    if action == "ba_auto_rmbuttons":
        auto_reply = await update_business_auto_reply(owner, buttons=[])
        await q.edit_message_text(_auto_text(auto_reply), reply_markup=_auto_keyboard(auto_reply)); return True
    if action == "ba_auto_preview":
        await _send_preview(q.message, auto_reply.get("text"), auto_reply.get("media_type"), auto_reply.get("media_file_id"), auto_reply.get("buttons")); await q.answer("Preview sent."); return True

    if action == "ba_templates":
        await q.edit_message_text(
            "📝 Business Reply Templates\n\nCreate a shortcut, then use the same common editor to add text, media, URL/username buttons, or Clone Bot feature buttons.",
            reply_markup=_templates_keyboard(templates),
        ); return True
    if action == "ba_tpl_add":
        context.user_data["ba_editor"] = {"field": "template_add"}
        await q.edit_message_text("➕ New Reply Template\n\nSend: Shortcut | Template Name\nExample: /payment | Payment Details\n\nSend /cancel to stop."); return True

    if action.startswith("ba_tpl_"):
        suffix = action[len("ba_tpl_"):]
        op = ""; tid = ""
        for candidate in ("delete", "open", "meta"):
            prefix = candidate + "_"
            if suffix.startswith(prefix): op = candidate; tid = suffix[len(prefix):]; break
        if not op:
            # Common editor callbacks are ba_tpl_<id>_<operation>.
            for candidate in ("preview", "rmtext", "rmmedia", "rmbuttons", "text", "media", "buttons"):
                marker = "_" + candidate
                if suffix.endswith(marker): tid = suffix[:-len(marker)]; op = candidate; break
        item = await get_business_reply_template(owner, tid) if tid else None
        if not item:
            await q.answer("Template not found.", show_alert=True); return True
        if op == "open":
            await q.edit_message_text(_template_text(item), reply_markup=_template_keyboard(item)); return True
        if op == "meta":
            context.user_data["ba_editor"] = {"field": "template_meta", "template_id": tid}
            await q.edit_message_text("✏️ Edit Template\n\nSend: Shortcut | Template Name\n\nSend /cancel to stop."); return True
        if op == "text":
            context.user_data["ba_editor"] = {"field": "template_text", "template_id": tid}
            await q.edit_message_text(editor_text_prompt("Reply Template Text", variables="{NAME} {ID} {USERNAME} {MENTION} {DATE} {TIME}")); return True
        if op == "media":
            context.user_data["ba_editor"] = {"field": "template_media", "template_id": tid}
            await q.edit_message_text(editor_media_prompt("Reply Template Media")); return True
        if op == "buttons":
            context.user_data["ba_editor"] = {"field": "template_buttons", "template_id": tid}
            await q.edit_message_text(url_buttons_header() + "\n\nSend /cancel to stop."); return True
        if op == "rmtext": item = await update_business_reply_template(owner, tid, text="")
        elif op == "rmmedia": item = await update_business_reply_template(owner, tid, media_type="", media_file_id="")
        elif op == "rmbuttons": item = await update_business_reply_template(owner, tid, buttons=[])
        elif op == "delete":
            await delete_business_reply_template(owner, tid)
            templates = await list_business_reply_templates(owner)
            await q.edit_message_text("✅ Reply template deleted.", reply_markup=_templates_keyboard(templates)); return True
        elif op == "preview":
            await _send_preview(q.message, item.get("text") or item.get("name"), item.get("media_type"), item.get("media_file_id"), item.get("buttons")); await q.answer("Preview sent."); return True
        if item:
            await q.edit_message_text(_template_text(item), reply_markup=_template_keyboard(item)); return True

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
                await _send_code(context,text)
                await update.effective_message.reply_text(
                    "✅ Login code sent by Telegram.\n\n"
                    "⚠️ Do not send the code as 5 digits together because Telegram may invalidate a login code shared directly in a chat.\n\n"
                    "Send it with spaces, for example: 1 2 3 4 5\n"
                    "or with a hyphen: 12-345"
                )
                return True
            if step == "code":
                # Telegram can invalidate a login code when the exact digits are shared in a Telegram chat.
                # Require separators, then remove them locally before MTProto verification.
                digits = "".join(ch for ch in text if ch.isdigit())
                has_separator = any(not ch.isdigit() for ch in text)
                if not has_separator or len(digits) < 5:
                    await update.effective_message.reply_text(
                        "⚠️ Do not send the code as plain digits.\n\n"
                        "Send it with spaces, for example: 1 2 3 4 5\n"
                        "or with a hyphen: 12-345\n\n"
                        "If you already sent the plain code, request a new code first because Telegram may have invalidated it."
                    )
                    return True
                try:
                    await _finish_auth(context,owner,code=digits)
                except SessionPasswordNeededError:
                    auth["step"]="password"
                    context.user_data["ba_auth"]=auth
                    await update.effective_message.reply_text("🔐 Two-step verification is enabled. Send your Telegram password.")
                    return True
                await update.effective_message.reply_text("✅ Telegram account connected successfully.",reply_markup=_kb([[InlineKeyboardButton("💼 Business Automation",callback_data="ba_home")]]))
                return True
            if step == "password":
                await _finish_auth(context,owner,password=text); await update.effective_message.reply_text("✅ Telegram account connected successfully.",reply_markup=_kb([[InlineKeyboardButton("💼 Business Automation",callback_data="ba_home")]])); return True
        except PhoneCodeExpiredError:
            context.user_data["ba_auth"] = {"step": "phone"}
            await update.effective_message.reply_text(
                "❌ Telegram invalidated or expired this code.\n\n"
                "Send your phone number again, then enter the new code with spaces, for example: 1 2 3 4 5."
            )
            return True
        except (PhoneNumberInvalidError,PhoneCodeInvalidError,PasswordHashInvalidError) as exc:
            await update.effective_message.reply_text(f"❌ Telegram login failed: {type(exc).__name__}. Please try again.")
            return True
        except Exception:
            logger.exception("Business account login failed owner=%s",owner); await update.effective_message.reply_text("❌ Telegram account could not be connected. Please try again."); return True

    editor = context.user_data.get("ba_editor")
    if not editor:
        return False
    if text.lower() == "/cancel":
        context.user_data.pop("ba_editor", None)
        await update.effective_message.reply_text(
            "Editing cancelled.",
            reply_markup=_kb([[InlineKeyboardButton("💼 Business Automation", callback_data="ba_home")]]),
        )
        return True

    field = str(editor.get("field") or "")
    template_id = str(editor.get("template_id") or "")
    try:
        if field == "welcome_text":
            await update_business_welcome(owner, text=text)
        elif field == "auto_text":
            await update_business_auto_reply(owner, text=text)
        elif field == "welcome_buttons":
            await update_business_welcome(owner, buttons=parse_editor_buttons(text))
        elif field == "auto_buttons":
            await update_business_auto_reply(owner, buttons=parse_editor_buttons(text))
        elif field == "template_buttons":
            await update_business_reply_template(owner, template_id, buttons=parse_editor_buttons(text))
        elif field == "template_add":
            if "|" not in text:
                raise ValueError("Use: Shortcut | Template Name")
            shortcut, name = [part.strip() for part in text.split("|", 1)]
            if not shortcut or not name:
                raise ValueError("Shortcut and template name are required")
            await create_business_reply_template(owner, shortcut, name)
        elif field == "template_meta":
            if "|" not in text:
                raise ValueError("Use: Shortcut | Template Name")
            shortcut, name = [part.strip() for part in text.split("|", 1)]
            if not shortcut or not name:
                raise ValueError("Shortcut and template name are required")
            await update_business_reply_template(owner, template_id, shortcut=shortcut[:64], name=name[:80])
        elif field == "template_text":
            await update_business_reply_template(owner, template_id, text=text)
        elif field == "delay":
            value = int(text)
            if not 0 <= value <= 300:
                raise ValueError("Reply delay must be 0-300 seconds")
            await set_seller_setting(owner, "business_reply_delay_seconds", value)
        elif field == "working_hours":
            parts = [part.strip() for part in text.split("|")]
            if len(parts) != 3:
                raise ValueError("Use: HH:MM | HH:MM | Timezone")
            datetime.strptime(parts[0], "%H:%M")
            datetime.strptime(parts[1], "%H:%M")
            ZoneInfo(parts[2])
            await set_seller_setting(owner, "business_working_hours_start", parts[0])
            await set_seller_setting(owner, "business_working_hours_end", parts[1])
            await set_seller_setting(owner, "business_working_hours_timezone", parts[2])
        else:
            return False
    except (ValueError, TypeError) as exc:
        await update.effective_message.reply_text(f"❌ {exc}")
        return True

    context.user_data.pop("ba_editor", None)
    await update.effective_message.reply_text(
        "✅ Business Automation editor updated.",
        reply_markup=_kb([[InlineKeyboardButton("💼 Business Automation", callback_data="ba_home")]]),
    )
    return True


async def handle_media(self, update, context):
    owner = self.owner(context)
    if int(update.effective_user.id) != int(owner):
        return False
    editor = context.user_data.get("ba_editor") or {}
    field = str(editor.get("field") or "")
    if field not in {"welcome_media", "auto_media", "template_media"}:
        return False

    msg = update.effective_message
    media_type = ""
    file_id = ""
    if msg.photo:
        media_type, file_id = "photo", msg.photo[-1].file_id
    elif msg.video:
        media_type, file_id = "video", msg.video.file_id
    elif msg.animation:
        media_type, file_id = "animation", msg.animation.file_id
    elif msg.document:
        media_type, file_id = "document", msg.document.file_id
    if not file_id:
        return False

    template_id = str(editor.get("template_id") or "")
    if field == "welcome_media":
        await update_business_welcome(owner, media_type=media_type, media_file_id=file_id)
    elif field == "auto_media":
        await update_business_auto_reply(owner, media_type=media_type, media_file_id=file_id)
    else:
        item = await update_business_reply_template(
            owner, template_id, media_type=media_type, media_file_id=file_id
        )
        if not item:
            await msg.reply_text("❌ Reply template not found.")
            return True

    context.user_data.pop("ba_editor", None)
    await msg.reply_text(
        "✅ Business Automation media updated.",
        reply_markup=_kb([[InlineKeyboardButton("💼 Business Automation", callback_data="ba_home")]]),
    )
    return True
