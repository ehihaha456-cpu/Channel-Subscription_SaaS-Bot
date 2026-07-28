"""Business Automation UI and MTProto account connection inside clone-bot Admin Panel."""

import asyncio
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto, InputMediaVideo, InputMediaAnimation, InputMediaDocument
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
        "Connect Telegram accounts and automatically reply to customers.\n\n"
        f"Status: {'🟢 Enabled' if enabled else '🔴 Disabled'}\n"
        f"Connected Accounts: {connected}\n\n"
        "Use the buttons below to connect accounts and manage the shared "
        "Welcome Message, Auto Reply, Reply Templates, Settings, and Statistics."
    )
    return text, _home_keyboard(connected, enabled)


async def _editor_state(owner: int) -> tuple[dict, dict, list[dict]]:
    welcome = await get_business_welcome(owner)
    auto_reply = await get_business_auto_reply(owner)
    templates = await list_business_reply_templates(owner)
    return welcome, auto_reply, templates


def _welcome_text(item):
    return (
        "👋 Welcome Message\n\n"
        "This message is sent automatically when a customer messages a connected account for the first time. "
        "Add text, media, URL buttons, or Clone Bot feature buttons, then use Preview before enabling it.\n\n"
        + editor_header(
            "Current Setup",
            item,
            variables="{NAME} {ID} {USERNAME} {MENTION} {DATE} {TIME}",
        )
    )


def _welcome_keyboard(item):
    return editor_menu_keyboard(
        "ba_welcome", item, back_callback="ba_home", allow_toggle=True
    )


def _auto_text(item):
    return (
        "💬 Auto Reply\n\n"
        "This reply is sent automatically when a customer messages after the Welcome Message has already been sent. "
        "Add text, media, links, or feature buttons and use Preview to check the result.\n\n"
        + editor_header(
            "Current Setup",
            item,
            variables="{NAME} {ID} {USERNAME} {MENTION} {DATE} {TIME}",
        )
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
        "⚙️ Business Automation Settings\n\nControl how automation works for every connected account. These settings are shared across all accounts.\n\n"
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


def _media_items(item):
    media = list(item.get("media") or [])
    if not media and item.get("media_file_id"):
        media = [{"type": item.get("media_type") or "document", "file_id": item.get("media_file_id")}]
    return [m for m in media if m.get("file_id")][:10]


async def _send_preview(message, item):
    markup = _preview_markup(item.get("buttons") or [])
    text = str(item.get("text") or "Preview message")
    media = _media_items(item)
    if not media:
        await message.reply_text(text, reply_markup=markup)
        return

    if len(media) == 1:
        m = media[0]
        kind, file_id = str(m.get("type") or "document"), str(m.get("file_id") or "")
        if kind == "photo":
            await message.reply_photo(file_id, caption=text, reply_markup=markup)
        elif kind == "video":
            await message.reply_video(file_id, caption=text, reply_markup=markup)
        elif kind == "animation":
            await message.reply_animation(file_id, caption=text, reply_markup=markup)
        else:
            await message.reply_document(file_id, caption=text, reply_markup=markup)
        return

    album = []
    for m in media:
        kind = str(m.get("type") or "document").lower()
        file_id = str(m.get("file_id") or "")
        if kind == "photo":
            album.append(InputMediaPhoto(media=file_id))
        elif kind == "video":
            album.append(InputMediaVideo(media=file_id))
        else:
            album.append(InputMediaDocument(media=file_id))
    await message.reply_media_group(media=album)
    if text or markup:
        await message.reply_text(text or "Choose an option below.", reply_markup=markup)


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
        lines = [
            "📱 Connected Accounts",
            "",
            "View all connected Telegram accounts here.",
            "Tap Disconnect only when you want to remove an account and stop its automation.",
            "",
        ]
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
        text = (
            "🔗 Connect Telegram Account\n\n"
            "Choose which type of Telegram account you want to connect.\n\n"
            "👤 Normal Telegram Account\n"
            "• Free to use\n"
            "• Connect with phone number, Telegram login code, and 2-step password when enabled\n"
            "• Supports Welcome Message, media, Auto Reply, and Reply Templates\n"
            "• Real inline callback buttons are not supported\n\n"
            "💼 Telegram Business Account\n"
            "• Telegram Business/Premium is required\n"
            "• Supports official Business integration and real inline buttons"
        )
        await q.edit_message_text(text, reply_markup=_kb([
            [InlineKeyboardButton("👤 Normal Account", callback_data="ba_connect_normal")],
            [InlineKeyboardButton("💼 Business Account", callback_data="ba_connect_official")],
            [InlineKeyboardButton("⬅ Business Automation", callback_data="ba_home")],
        ])); return True
    if action == "ba_connect_normal":
        if not _mtproto_ready():
            await q.edit_message_text("⚠️ Telegram API credentials are not configured by the platform owner.", reply_markup=_kb([[InlineKeyboardButton("⬅ Business Automation", callback_data="ba_home")]])); return True
        context.user_data["ba_auth"] = {"step": "phone"}
        await q.edit_message_text(
            "👤 Connect Normal Telegram Account\n\n"
            "Send the phone number with country code.\n"
            "Example: +919876543210\n\n"
            "Telegram will send a login code. Send /cancel to stop."
        ); return True
    if action == "ba_connect_official":
        await q.edit_message_text(
            "💼 Connect Telegram Business Account\n\n"
            "Telegram Business/Premium must be active on the account.\n\n"
            "Open Telegram Settings → Telegram Business → Chatbots, then connect this Clone Bot. "
            "After Telegram confirms the connection, return here.\n\n"
            "Normal accounts can still use Welcome Message, Auto Reply, and Reply Templates without Premium.",
            reply_markup=_kb([[InlineKeyboardButton("⬅ Connect Account", callback_data="ba_connect")]])
        ); return True
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

    # Load only the data needed by the selected section.  Previously all three
    # editor collections were loaded for Settings and Statistics too, so one
    # editor-storage error made every Business Automation button appear dead.
    s = await get_seller_settings(owner)

    if action.startswith("ba_welcome"):
        welcome = await get_business_welcome(owner)
    else:
        welcome = None
    if action.startswith("ba_auto"):
        auto_reply = await get_business_auto_reply(owner)
    else:
        auto_reply = None
    if action == "ba_templates" or action.startswith("ba_tpl_"):
        templates = await list_business_reply_templates(owner)
    else:
        templates = []

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
        welcome = await update_business_welcome(owner, media_type="", media_file_id="", media=[])
        await q.edit_message_text(_welcome_text(welcome), reply_markup=_welcome_keyboard(welcome)); return True
    if action == "ba_welcome_rmbuttons":
        welcome = await update_business_welcome(owner, buttons=[])
        await q.edit_message_text(_welcome_text(welcome), reply_markup=_welcome_keyboard(welcome)); return True
    if action == "ba_welcome_preview":
        await _send_preview(q.message, welcome); await q.answer("Preview sent."); return True

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
        auto_reply = await update_business_auto_reply(owner, media_type="", media_file_id="", media=[])
        await q.edit_message_text(_auto_text(auto_reply), reply_markup=_auto_keyboard(auto_reply)); return True
    if action == "ba_auto_rmbuttons":
        auto_reply = await update_business_auto_reply(owner, buttons=[])
        await q.edit_message_text(_auto_text(auto_reply), reply_markup=_auto_keyboard(auto_reply)); return True
    if action == "ba_auto_preview":
        await _send_preview(q.message, auto_reply); await q.answer("Preview sent."); return True

    if action == "ba_templates":
        await q.edit_message_text(
            "📝 Reply Templates\n\nCreate saved replies that can be sent quickly with a shortcut. Each template can include text, media, URL buttons, or Clone Bot feature buttons.\n\nExample: /plans | Available Plans",
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
        elif op == "rmmedia": item = await update_business_reply_template(owner, tid, media_type="", media_file_id="", media=[])
        elif op == "rmbuttons": item = await update_business_reply_template(owner, tid, buttons=[])
        elif op == "delete":
            await delete_business_reply_template(owner, tid)
            templates = await list_business_reply_templates(owner)
            await q.edit_message_text("✅ Reply template deleted.", reply_markup=_templates_keyboard(templates)); return True
        elif op == "preview":
            await _send_preview(q.message, item); await q.answer("Preview sent."); return True
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


async def _save_media_selection(owner: int, field: str, template_id: str, media: list[dict]):
    """Replace the editor media with one Telegram message/album."""
    media = [item for item in media if item.get("file_id")][:10]
    if not media:
        return
    legacy = media[0]
    payload = {
        "media": media,
        "media_type": legacy["type"],
        "media_file_id": legacy["file_id"],
    }
    if field == "welcome_media":
        await update_business_welcome(owner, **payload)
    elif field == "auto_media":
        await update_business_auto_reply(owner, **payload)
    else:
        await update_business_reply_template(owner, template_id, **payload)


async def _finish_media_album(context, key):
    """Wait briefly for every update in one Telegram media group, then save once."""
    await asyncio.sleep(1.2)
    bucket = context.application.bot_data.get("ba_media_albums", {}).pop(key, None)
    if not bucket:
        return
    items = sorted(bucket["items"], key=lambda item: item["message_id"])
    media = [{"type": item["type"], "file_id": item["file_id"]} for item in items[:10]]
    await _save_media_selection(bucket["owner"], bucket["field"], bucket["template_id"], media)

    editor = context.user_data.get("ba_editor") or {}
    if (
        str(editor.get("field") or "") == bucket["field"]
        and str(editor.get("template_id") or "") == bucket["template_id"]
    ):
        context.user_data.pop("ba_editor", None)

    extra = max(0, len(items) - 10)
    note = f"\n⚠️ {extra} extra file(s) were ignored." if extra else ""
    await bucket["message"].reply_text(
        f"✅ {len(media)} media file(s) saved together.{note}",
        reply_markup=_kb([[InlineKeyboardButton("💼 Business Automation", callback_data="ba_home")]]),
    )


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
    if field == "template_media" and not await get_business_reply_template(owner, template_id):
        await msg.reply_text("❌ Reply template not found.")
        return True

    # A single Telegram media message replaces the old selection immediately.
    # An album arrives as several updates sharing one media_group_id, so collect
    # them briefly and save the whole album automatically—no /done command.
    media_group_id = str(msg.media_group_id or "")
    if not media_group_id:
        await _save_media_selection(
            owner,
            field,
            template_id,
            [{"type": media_type, "file_id": file_id}],
        )
        context.user_data.pop("ba_editor", None)
        await msg.reply_text(
            "✅ Media saved.",
            reply_markup=_kb([[InlineKeyboardButton("💼 Business Automation", callback_data="ba_home")]]),
        )
        return True

    albums = context.application.bot_data.setdefault("ba_media_albums", {})
    key = (int(owner), int(msg.chat_id), media_group_id, field, template_id)
    bucket = albums.setdefault(
        key,
        {
            "owner": int(owner),
            "field": field,
            "template_id": template_id,
            "items": [],
            "message": msg,
            "task": None,
        },
    )
    bucket["items"].append(
        {
            "message_id": int(msg.message_id),
            "type": media_type,
            "file_id": file_id,
        }
    )
    bucket["message"] = msg

    old_task = bucket.get("task")
    if old_task and not old_task.done():
        old_task.cancel()
    bucket["task"] = context.application.create_task(
        _finish_media_album(context, key),
        name=f"ba-media-album-{media_group_id}",
    )
    return True
