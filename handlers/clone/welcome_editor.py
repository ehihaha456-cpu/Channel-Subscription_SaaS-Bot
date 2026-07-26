"""Focused clone-bot feature mixin; behavior preserved from services.bot_manager."""

from services.bot_manager_shared import *


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
        rows=[]
        for raw_line in text.splitlines():
            raw_line=raw_line.strip()
            if not raw_line: continue
            row=[]
            for item in raw_line.split("&&"):
                item=item.strip()
                if " - " not in item: raise ValueError("Use: Button title - URL")
                title,target=[x.strip() for x in item.split(" - ",1)]
                if not title or not target: raise ValueError("Button title and target required")
                if target.startswith(("http://","https://","tg://")) or target.startswith("t.me/"):
                    if target.startswith("t.me/"):
                        target="https://"+target
                    row.append({"text":title,"type":"url","value":target})
                elif target.startswith("@"):
                    username=target[1:].strip()
                    if not username or len(username)>32 or not all(ch.isalnum() or ch=="_" for ch in username):
                        raise ValueError("Invalid Telegram username. Example: Button title - @username")
                    row.append({"text":title,"type":"url","value":f"https://t.me/{username}"})
                elif target.startswith("feature:"):
                    feature=target.split(":",1)[1].lower()
                    allowed={"plans":"c_plans","buy":"c_buy","profile":"c_profile","renew":"c_renew","referral":"c_referral","referral_unlock":"c_referral_unlock","support":"c_support","home":"c_home"}
                    if feature not in allowed: raise ValueError("Unknown feature button")
                    row.append({"text":title,"type":"callback","value":allowed[feature]})
                else:
                    raise ValueError("Target must be URL, @username, or feature:plans/buy/profile/renew/referral/referral_unlock/support/home")
            if row: rows.append(row)
        if not rows: raise ValueError("No buttons found")
        return rows

    @staticmethod
    def build_welcome_keyboard(rows):
        if not rows: return None
        keyboard=[]
        for row in rows:
            built=[]
            for item in row:
                if item.get("type")=="url": built.append(InlineKeyboardButton(item.get("text","Button"),url=item.get("value")))
                else: built.append(InlineKeyboardButton(item.get("text","Button"),callback_data=item.get("value","c_home")))
            if built: keyboard.append(built)
        return InlineKeyboardMarkup(keyboard) if keyboard else None

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

        # Ye branding seller edit/remove nahi kar sakta. Main bot username
        # Render ke MAIN_BOT_USERNAME environment variable se aata hai.
        creator_line=(
            "\n\n🤖 Powered by "
            f'<a href="https://t.me/{MAIN_BOT_USERNAME}">'
            f"@{MAIN_BOT_USERNAME}</a>"
        )
        text=f"{welcome_text}{creator_line}"

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

