"""Focused clone-bot feature mixin; behavior preserved from services.bot_manager."""

from handlers.common.clone_context import *


class CloneSupportCoreMixin:
    _support_topic_locks = {}

    def _support_datetime(value):
        if not value:
            return "-"
        if value.tzinfo is None:
            value=value.replace(tzinfo=timezone.utc)
        return SellerBotManager.format_dt(value)

    async def support_user_details_text(self,owner,user):
        record=await get_user(owner,user.id) or {}
        sub=await get_subscription(owner,user.id) or {}
        expiry=sub.get("expiry_date")
        if expiry and expiry.tzinfo is None:
            expiry=expiry.replace(tzinfo=timezone.utc)
        active=bool(sub.get("active") and expiry and expiry>datetime.now(timezone.utc))
        full_name=html.escape(user.full_name or str(user.id))
        username=("@"+html.escape(user.username)) if user.username else "Not set"
        mention=f'<a href="tg://user?id={user.id}">{full_name}</a>'
        return (
            "🆕 <b>New Support User</b>\n\n"
            f"👤 Name: {full_name}\n"
            f"📝 Username: {username}\n"
            f"🆔 User ID: <code>{user.id}</code>\n"
            f"🔗 Mention: {mention}\n"
            f"🌐 Language: {html.escape(user.language_code or 'Unknown')}\n"
            f"📅 Joined: {self._support_datetime(record.get('joined_at'))}\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "💎 <b>Subscription</b>\n"
            f"Plan: {html.escape(str(sub.get('plan') or 'No Plan'))}\n"
            f"Status: {'✅ Active' if active else '❌ Inactive'}\n"
            f"Expiry: {self._support_datetime(expiry)}\n\n"
            "User ke Telegram profile par jane ke liye mention ya button use karo."
        )

    @staticmethod
    def support_topic_keyboard(user_id,blocked=False):
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("👤 Open Telegram Profile",url=f"tg://user?id={int(user_id)}")],
            [InlineKeyboardButton("📋 View User Details",callback_data=f"support_profile_{int(user_id)}")],
            [InlineKeyboardButton(
                "✅ Unblock Support" if blocked else "🚫 Block Support",
                callback_data=(f"support_unblock_{int(user_id)}" if blocked else f"support_block_{int(user_id)}"),
            )],
            [InlineKeyboardButton("🆔 Show User ID",callback_data=f"support_id_{int(user_id)}")],
        ])

    async def ensure_support_topic(self,context,owner,user,support):
        """Return one permanent support topic for a user.

        Telegram can deliver several updates from the same user almost at once
        (albums, retries, or duplicate webhook deliveries).  Without a per-user
        lock, every update can create its own forum topic before MongoDB is
        updated.  The lock keeps topic creation idempotent inside the clone-bot
        runtime.
        """
        group_id=int(support["support_group_id"])
        lock_key=(int(owner),int(user.id),group_id)
        lock=self._support_topic_locks.setdefault(lock_key,asyncio.Lock())
        async with lock:
            topic=await get_support_topic(owner,user.id)
            if (
                topic
                and int(topic.get("support_group_id",0))==group_id
                and topic.get("message_thread_id")
            ):
                return topic

            # A record from an older support group must never be reused.
            if topic:
                await delete_support_topic(owner,user.id)

            topic_name=f"👤 {user.first_name or 'User'} | {user.id}"[:128]
            forum_topic=await context.bot.create_forum_topic(group_id,name=topic_name)
            topic=await save_support_topic(
                owner,user.id,group_id,forum_topic.message_thread_id,topic_name,
            )
            blocked=await is_support_blocked(owner,user.id)
            await context.bot.send_message(
                chat_id=group_id,
                message_thread_id=forum_topic.message_thread_id,
                text=await self.support_user_details_text(owner,user),
                parse_mode="HTML",
                reply_markup=self.support_topic_keyboard(user.id,blocked),
                disable_web_page_preview=True,
            )
            return topic

    async def support_template_values(self,owner,user):
        sub=await get_subscription(owner,user.id) or {}
        expiry=sub.get("expiry_date")
        values={
            "{NAME}":user.full_name or str(user.id),
            "{ID}":str(user.id),
            "{USERNAME}":("@"+user.username) if user.username else "",
            "{PLAN}":str(sub.get("plan") or "No Plan"),
            "{EXPIRY}":self._support_datetime(expiry),
        }
        return values

    async def send_support_template(self,context,owner,target_user_id,template,user_obj=None):
        if not template:
            raise ValueError("Template not found")
        if user_obj is None:
            record=await get_user(owner,target_user_id) or {}
            class UserView:
                id=int(target_user_id)
                full_name=" ".join(x for x in [record.get("first_name"),record.get("last_name")] if x) or str(target_user_id)
                username=record.get("username")
            user_obj=UserView()
        text=template.get("text") or ""
        for key,value in (await self.support_template_values(owner,user_obj)).items():
            text=text.replace(key,value)
        keyboard=self.build_welcome_keyboard(template.get("buttons") or [])
        file_id=template.get("media_file_id")
        media_type=template.get("media_type")
        kwargs={"chat_id":int(target_user_id),"reply_markup":keyboard}
        if file_id and media_type=="photo": sent=await context.bot.send_photo(photo=file_id,caption=text or None,**kwargs)
        elif file_id and media_type=="video": sent=await context.bot.send_video(video=file_id,caption=text or None,**kwargs)
        elif file_id and media_type=="animation": sent=await context.bot.send_animation(animation=file_id,caption=text or None,**kwargs)
        elif file_id and media_type=="document": sent=await context.bot.send_document(document=file_id,caption=text or None,**kwargs)
        else: sent=await context.bot.send_message(text=text or "(Empty template)",disable_web_page_preview=True,**kwargs)
        auto_delete_seconds=_template_auto_delete_seconds(template)
        if auto_delete_seconds > 0:
            asyncio.create_task(self._delete_template_message_later(context.bot,sent.chat_id,sent.message_id,auto_delete_seconds))
        return sent

    @staticmethod
    async def _delete_template_message_later(bot,chat_id,message_id,delay_seconds):
        try:
            await asyncio.sleep(max(1,int(delay_seconds)))
            await bot.delete_message(chat_id=chat_id,message_id=message_id)
        except asyncio.CancelledError:
            raise
        except TelegramError as exc:
            logger.warning("Template auto-remove failed chat=%s message=%s: %s",chat_id,message_id,exc)
        except Exception:
            logger.exception("Unexpected template auto-remove failure chat=%s message=%s",chat_id,message_id)

