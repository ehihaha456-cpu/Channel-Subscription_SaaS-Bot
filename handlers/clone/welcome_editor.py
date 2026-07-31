"""Focused clone-bot feature mixin; behavior preserved from services.bot_manager."""

from handlers.common.clone_context import *
from handlers.common.editor_engine import build_editor_keyboard, parse_editor_buttons
from utils.branding import append_branding


class CloneWelcomeEditorMixin:
    @staticmethod
    def welcome_menu():
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("📄 Text",callback_data="a_welcome_text")],
            [InlineKeyboardButton("🖼 Media",callback_data="a_welcome_media")],
            [InlineKeyboardButton("🔗 URL Buttons",callback_data="a_welcome_buttons")],
            [InlineKeyboardButton("👀 Full Preview",callback_data="a_welcome_preview")],
            [InlineKeyboardButton("⬅ Back",callback_data="a_settings")],
        ])

    @staticmethod
    def welcome_text_menu(has_text=False):
        rows=[]
        if has_text:
            rows.append([InlineKeyboardButton("🗑 Remove Text",callback_data="a_welcome_remove_text")])
        rows.append([InlineKeyboardButton("⬅ Back",callback_data="a_welcome")])
        return InlineKeyboardMarkup(rows)

    @staticmethod
    def welcome_media_menu(has_media=False):
        rows=[]
        if has_media:
            rows.append([InlineKeyboardButton("🗑 Remove Media",callback_data="a_welcome_remove_media")])
        rows.append([InlineKeyboardButton("⬅ Back",callback_data="a_welcome")])
        return InlineKeyboardMarkup(rows)

    @staticmethod
    def welcome_buttons_menu(has_buttons=False):
        rows=[]
        if has_buttons:
            rows.append([InlineKeyboardButton("🚫 Remove Keyboard",callback_data="a_welcome_remove_buttons")])
        rows.append([InlineKeyboardButton("⬅ Back",callback_data="a_welcome")])
        return InlineKeyboardMarkup(rows)

    @staticmethod
    def welcome_quick_menu():
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("📋 Plans",callback_data="a_wq_plans"),InlineKeyboardButton("💳 Buy",callback_data="a_wq_buy")],
            [InlineKeyboardButton("👤 My Profile",callback_data="a_wq_profile"),InlineKeyboardButton("🔄 Renew",callback_data="a_wq_renew")],
            [InlineKeyboardButton("🎁 Referral",callback_data="a_wq_referral"),InlineKeyboardButton("🔓 Referral Unlock",callback_data="a_wq_referral_unlock")],
            [InlineKeyboardButton("📞 Support",callback_data="a_wq_support"),InlineKeyboardButton("🏠 Main Menu",callback_data="a_wq_home")],
            [InlineKeyboardButton("⬅ Back",callback_data="a_welcome_buttons")],
        ])

    @staticmethod
    def personalize(text,user,bot_name="Subscription Bot"):
        from datetime import datetime as _datetime
        now=_datetime.now()
        values={
            "{ID}":str(user.id),
            "{NAME}":user.first_name or "",
            "{SURNAME}":user.last_name or "",
            "{NAMESURNAME}":" ".join(x for x in [user.first_name,user.last_name] if x),
            "{USERNAME}":("@"+user.username) if user.username else "",
            "{LANG}":user.language_code or "",
            "{DATE}":now.strftime("%d-%m-%Y"),
            "{TIME}":now.strftime("%I:%M %p"),
            "{WEEKDAY}":now.strftime("%A"),
            "{MENTION}":user.mention_html(),
            "{BOTNAME}":bot_name,
        }
        result=text or ""
        for key,value in values.items(): result=result.replace(key,value)
        return result

    @staticmethod
    def parse_welcome_buttons(text):
        return parse_editor_buttons(text)

    @staticmethod
    def build_welcome_keyboard(rows):
        return build_editor_keyboard(rows)

    async def send_welcome(self,message,context,settings,user):
        # Seller ka editable welcome text optional hai. Agar seller text remove
        # kare, tab bhi default welcome title aur permanent SaaS branding dikhegi.
        seller_text=(settings.get("welcome_message") or "").strip()
        if seller_text:
            welcome_text=self.personalize(
                seller_text,
                user,
                settings.get("bot_name","Subscription Bot"),
            )
        else:
            welcome_text="👋 WELCOME TO OUR SUBSCRIPTION BOT"

        # Platform branding is controlled only from the Owner Dashboard.
        text=await append_branding(welcome_text)

        # Seller ke welcome buttons fully removable hain. Empty list ka matlab
        # welcome message ke niche koi button nahi dikhana.
        keyboard=self.build_welcome_keyboard(
            settings.get("welcome_buttons") or []
        )
        media_type=settings.get("welcome_media_type")
        file_id=settings.get("welcome_media_file_id")

        async def send(parse_mode="HTML"):
            kwargs={"reply_markup":keyboard}
            if parse_mode:
                kwargs["parse_mode"]=parse_mode
            if file_id and media_type=="photo":
                return await message.reply_photo(file_id,caption=text,**kwargs)
            if file_id and media_type=="video":
                return await message.reply_video(file_id,caption=text,**kwargs)
            if file_id and media_type=="animation":
                return await message.reply_animation(file_id,caption=text,**kwargs)
            if file_id and media_type=="document":
                return await message.reply_document(file_id,caption=text,**kwargs)
            return await message.reply_text(
                text,
                disable_web_page_preview=True,
                **kwargs,
            )

        try:
            return await send("HTML")
        except BadRequest as exc:
            logger.warning("Welcome HTML/media send failed; retrying plain text: %s",exc)
            try:
                return await send(None)
            except BadRequest:
                # If an old/invalid Telegram file_id is stored, remove media and send text.
                if file_id:
                    await set_seller_setting(self.owner(context),"welcome_media_type","")
                    await set_seller_setting(self.owner(context),"welcome_media_file_id","")
                    settings["welcome_media_type"]=""
                    settings["welcome_media_file_id"]=""
                    return await message.reply_text(
                        text,
                        reply_markup=keyboard,
                        disable_web_page_preview=True,
                    )
                raise

