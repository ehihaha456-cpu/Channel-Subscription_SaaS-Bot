"""Focused clone-bot feature mixin; behavior preserved from services.bot_manager."""

from services.bot_manager_shared import *


class CloneLiveSupportUIMixin:
    @staticmethod
    def live_support_menu(settings):
        enabled=bool(settings.get("enabled"))
        mode=settings.get("mode","topic")
        group_title=settings.get("support_group_title") or "Not connected"
        return InlineKeyboardMarkup([
            [InlineKeyboardButton(
                "🔴 Turn Support OFF" if enabled else "🟢 Turn Support ON",
                callback_data="a_live_support_toggle",
            )],
            [InlineKeyboardButton(
                ("✅ " if mode=="private" else "")+"💬 Normal Private Reply",
                callback_data="a_live_support_mode_private",
            )],
            [InlineKeyboardButton(
                ("✅ " if mode=="topic" else "")+"🧵 Topic Mode",
                callback_data="a_live_support_mode_topic",
            )],
            [InlineKeyboardButton(f"📌 Group: {group_title[:28]}",callback_data="a_live_support_group_info")],
            [InlineKeyboardButton("🤖 Auto Reply",callback_data="a_support_auto_replies")],
            [InlineKeyboardButton("⚡ Reply Templates",callback_data="a_support_templates")],
            [InlineKeyboardButton("🚫 Blocked Users Count",callback_data="a_live_support_blocks")],
            [InlineKeyboardButton("⬅ Back",callback_data="a_home")],
        ])

    @staticmethod
    def live_support_text(settings, blocked_count):
        mode_name="Topic Mode" if settings.get("mode","topic")=="topic" else "Normal Private Reply"
        group_name=settings.get("support_group_title") or "Not connected"
        return (
            "💬 Live Support Settings\n\n"
            f"Status: {'🟢 ON' if settings.get('enabled') else '🔴 OFF'}\n"
            f"Reply Mode: {mode_name}\n"
            f"Support Group: {group_name}\n"
            f"Blocked Users: {blocked_count}\n\n"
            "Topic Mode me har user ke liye ek permanent topic banta hai. "
            "Messages auto-delete nahi honge.\n\n"
            "Connect Support Group\n\n"
            "1. Private supergroup banao.\n"
            "2. Topics ON karo.\n"
            "3. Clone Bot ko Admin banao.\n"
            "4. Manage Topics permission ON rakho.\n"
            "5. Usi group me /connectsupport bhejo.\n\n"
            "Connect hone ke baad har user ka alag topic automatically banega."
        )

    @staticmethod
    def support_templates_menu(templates):
        rows=[[InlineKeyboardButton("➕ Add Command",callback_data="a_support_tpl_add")]]
        for item in templates:
            command=item.get("command","")
            duration=_format_auto_delete(_template_auto_delete_seconds(item))
            icon="🔴" if duration=="Off" else "🟢"
            rows.append([InlineKeyboardButton(f"/{command}   {icon} {duration}",callback_data=f"a_support_tpl_view_{command}")])
        rows.append([InlineKeyboardButton("⬅ Back",callback_data="a_live_support")])
        return InlineKeyboardMarkup(rows)

    @staticmethod
    def support_auto_replies_menu(items):
        rows=[[InlineKeyboardButton("➕ Add Auto Reply",callback_data="a_support_ar_add")]]
        for item in items:
            keyword=item.get("keyword","")
            rows.append([InlineKeyboardButton(f"🔑 {keyword[:42]}",callback_data=f"a_support_ar_view_{keyword}")])
        rows.append([InlineKeyboardButton("⬅ Back",callback_data="a_live_support")])
        return InlineKeyboardMarkup(rows)

    @staticmethod
    def support_auto_reply_edit_menu(keyword):
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("📄 Text",callback_data=f"a_support_ar_text_{keyword}")],
            [InlineKeyboardButton("🖼 Media",callback_data=f"a_support_ar_media_{keyword}")],
            [InlineKeyboardButton("🔗 URL Buttons",callback_data=f"a_support_ar_buttons_{keyword}")],
            [InlineKeyboardButton("👀 Full Preview",callback_data=f"a_support_ar_preview_{keyword}")],
            [InlineKeyboardButton("🗑 Delete Auto Reply",callback_data=f"a_support_ar_delete_{keyword}")],
            [InlineKeyboardButton("⬅ Back",callback_data="a_support_auto_replies")],
        ])

    @staticmethod
    def support_auto_reply_text_menu(keyword, has_text=False):
        rows=[]
        if has_text:
            rows.append([InlineKeyboardButton("🗑 Remove Text",callback_data=f"a_support_ar_rmtext_{keyword}")])
        rows.append([InlineKeyboardButton("⬅ Back",callback_data=f"a_support_ar_view_{keyword}")])
        return InlineKeyboardMarkup(rows)

    @staticmethod
    def support_auto_reply_media_menu(keyword, has_media=False):
        rows=[]
        if has_media:
            rows.append([InlineKeyboardButton("🗑 Remove Media",callback_data=f"a_support_ar_rmmedia_{keyword}")])
        rows.append([InlineKeyboardButton("⬅ Back",callback_data=f"a_support_ar_view_{keyword}")])
        return InlineKeyboardMarkup(rows)

    @staticmethod
    def support_auto_reply_buttons_menu(keyword, has_buttons=False):
        rows=[]
        if has_buttons:
            rows.append([InlineKeyboardButton("🚫 Remove Keyboard",callback_data=f"a_support_ar_rmbuttons_{keyword}")])
        rows.append([InlineKeyboardButton("⬅ Back",callback_data=f"a_support_ar_view_{keyword}")])
        return InlineKeyboardMarkup(rows)

    @staticmethod
    def support_template_edit_menu(command):
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("📄 Text",callback_data=f"a_support_tpl_text_{command}")],
            [InlineKeyboardButton("🖼 Media",callback_data=f"a_support_tpl_media_{command}")],
            [InlineKeyboardButton("🔗 URL Buttons",callback_data=f"a_support_tpl_buttons_{command}")],
            [InlineKeyboardButton("👀 Full Preview",callback_data=f"a_support_tpl_preview_{command}")],
            [InlineKeyboardButton("⏱ Template Auto Remove",callback_data=f"a_support_tpl_autodel_{command}")],
            [InlineKeyboardButton("🗑 Delete Command",callback_data=f"a_support_tpl_delete_{command}")],
            [InlineKeyboardButton("⬅ Back",callback_data="a_support_templates")],
        ])

    @staticmethod
    def support_template_text_menu(command, has_text=False):
        rows=[]
        if has_text:
            rows.append([InlineKeyboardButton("🗑 Remove Text",callback_data=f"a_support_tpl_rmtext_{command}")])
        rows.append([InlineKeyboardButton("⬅ Back",callback_data=f"a_support_tpl_view_{command}")])
        return InlineKeyboardMarkup(rows)

    @staticmethod
    def support_template_media_menu(command, has_media=False):
        rows=[]
        if has_media:
            rows.append([InlineKeyboardButton("🗑 Remove Media",callback_data=f"a_support_tpl_rmmedia_{command}")])
        rows.append([InlineKeyboardButton("⬅ Back",callback_data=f"a_support_tpl_view_{command}")])
        return InlineKeyboardMarkup(rows)

    @staticmethod
    def support_template_buttons_menu(command, has_buttons=False):
        rows=[]
        if has_buttons:
            rows.append([InlineKeyboardButton("🚫 Remove Keyboard",callback_data=f"a_support_tpl_rmbuttons_{command}")])
        rows.append([InlineKeyboardButton("⬅ Back",callback_data=f"a_support_tpl_view_{command}")])
        return InlineKeyboardMarkup(rows)

    @staticmethod
    def support_template_auto_delete_menu(command, current_seconds=0):
        current=_format_auto_delete(current_seconds)
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Off",callback_data=f"a_tpl_ad_0_{command}"),InlineKeyboardButton("30 Seconds",callback_data=f"a_tpl_ad_30_{command}")],
            [InlineKeyboardButton("1 Minute",callback_data=f"a_tpl_ad_60_{command}"),InlineKeyboardButton("5 Minutes",callback_data=f"a_tpl_ad_300_{command}")],
            [InlineKeyboardButton("10 Minutes",callback_data=f"a_tpl_ad_600_{command}"),InlineKeyboardButton("30 Minutes",callback_data=f"a_tpl_ad_1800_{command}")],
            [InlineKeyboardButton("1 Hour",callback_data=f"a_tpl_ad_3600_{command}"),InlineKeyboardButton("⌨️ Custom",callback_data=f"a_tpl_ad_custom_{command}")],
            [InlineKeyboardButton(f"Current: {current}",callback_data="noop")],
            [InlineKeyboardButton("⬅ Back",callback_data=f"a_support_tpl_view_{command}")],
        ])

