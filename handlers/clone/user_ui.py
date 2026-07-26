"""Focused clone-bot feature mixin; behavior preserved from services.bot_manager."""

from handlers.common.clone_context import *


class CloneUserUIMixin:
    @staticmethod
    def format_dt(value, timezone_name="Asia/Kolkata", fmt="%d-%m-%Y %I:%M:%S %p %Z"):
        if not value:
            return "-"
        try:
            if value.tzinfo is None:
                value = value.replace(tzinfo=timezone.utc)
            try:
                zone = ZoneInfo(timezone_name or "Asia/Kolkata")
            except (ZoneInfoNotFoundError, ValueError, TypeError):
                zone = ZoneInfo("Asia/Kolkata")
            return value.astimezone(zone).strftime(fmt)
        except Exception:
            return str(value)

    async def seller_timezone(self, owner_id:int) -> str:
        settings = await get_seller_settings(int(owner_id)) or {}
        timezone_name = str(settings.get("timezone") or "Asia/Kolkata")
        try:
            ZoneInfo(timezone_name)
            return timezone_name
        except (ZoneInfoNotFoundError, ValueError):
            return "Asia/Kolkata"

    async def user_details_text(self,owner,user_id):
        user=await get_user(owner,int(user_id))
        sub=await get_subscription(owner,int(user_id))

        if not user:
            return None,None,None

        timezone_name = await self.seller_timezone(owner)
        username=f"@{user.get('username')}" if user.get("username") else "Not set"
        name=" ".join(
            value for value in [user.get("first_name"),user.get("last_name")]
            if value
        ) or "Unknown"

        now=datetime.now(timezone.utc)
        expiry=(sub or {}).get("expiry_date")
        if expiry and expiry.tzinfo is None:
            expiry=expiry.replace(tzinfo=timezone.utc)
        active=bool(sub and sub.get("active") and expiry and expiry>now)
        if sub and expiry:
            sub["expiry_date"]=expiry

        text=(
            "👤 User Details\n\n"
            f"🆔 ID: {user.get('user_id')}\n"
            f"👤 Name: {name}\n"
            f"📝 Username: {username}\n"
            f"🚫 Banned: {'Yes' if user.get('banned') else 'No'}\n"
            f"📋 Reason: {user.get('ban_reason') or '-'}\n"
            f"📅 Joined: {self.format_dt(user.get('joined_at'), timezone_name)}\n\n"
            f"💎 Plan: {(sub or {}).get('plan') or 'No Plan'}\n"
            f"📅 Expiry: {self.format_dt((sub or {}).get('expiry_date'), timezone_name)}\n"
            f"📌 Status: {'Active' if active else 'No Subscription'}"
        )
        return text,user,sub

    async def show_user_details(self,q,owner,user_id):
        text,user,sub=await self.user_details_text(owner,user_id)

        if not user:
            await q.edit_message_text(
                "❌ User not found.",
                reply_markup=self.back("a_users"),
            )
            return

        banned=bool(user.get("banned"))
        keyboard=InlineKeyboardMarkup([
            [InlineKeyboardButton("🎁 Give Subscription",callback_data=f"a_user_give_{user_id}")],
            [InlineKeyboardButton("⌛ Extend Subscription",callback_data=f"a_user_extend_{user_id}")],
            [InlineKeyboardButton("❌ Remove Subscription",callback_data=f"a_user_remove_{user_id}")],
            [InlineKeyboardButton(
                "✅ Unban User" if banned else "🚫 Ban User",
                callback_data=f"a_user_unban_{user_id}" if banned else f"a_user_ban_{user_id}",
            )],
            [InlineKeyboardButton("⬅ Back",callback_data="a_users")],
        ])

        await q.edit_message_text(text,reply_markup=keyboard)

    async def show_admin_plan_selector(self,q,owner,user_id,mode):
        plans=await get_plans(owner,True)

        if not plans:
            await q.edit_message_text(
                "❌ No active plans available.",
                reply_markup=self.back(f"a_user_view_{user_id}"),
            )
            return

        title="🎁 Choose plan to give" if mode=="give" else "⌛ Choose plan duration to extend"
        kb=[]

        for plan in plans:
            kb.append([InlineKeyboardButton(
                f"{plan['name']} — {plan['duration_text']} — ₹{plan['price']:g}",
                callback_data=f"a_user_apply_{mode}_{user_id}_{plan['plan_id']}",
            )])

        kb.append([InlineKeyboardButton("⬅ Back",callback_data=f"a_user_view_{user_id}")])
        await q.edit_message_text(title,reply_markup=InlineKeyboardMarkup(kb))

    async def payment_details_caption(
        self,
        owner,
        payment,
        status=None,
        processed_by=None,
    ):
        user=await get_user(owner,int(payment["user_id"])) or {}

        name=" ".join(
            value for value in [
                user.get("first_name"),
                user.get("last_name"),
            ] if value
        ) or "Unknown"

        username=(
            f"@{user.get('username')}"
            if user.get("username")
            else "Not set"
        )

        created=payment.get("created_at")
        created_text=self.format_dt(created)
        current_status=status or payment.get("status","pending")

        status_icon={
            "pending":"🟡",
            "approved":"✅",
            "rejected":"❌",
        }.get(current_status,"ℹ️")

        lines=[
            f"{status_icon} Payment {current_status.title()}",
            "",
            f"🧾 Payment ID: {payment.get('payment_id')}",
            f"🆔 User ID: {payment.get('user_id')}",
            f"👤 Name: {name}",
            f"📝 Username: {username}",
            f"📦 Plan: {payment.get('plan')}",
            f"⏳ Duration: {payment.get('duration_text') or '-'}",
            f"💰 Amount: ₹{payment.get('amount',0):g}",
            f"📅 Submitted: {created_text}",
            f"📌 Status: {current_status.title()}",
        ]

        if processed_by:
            lines.extend([
                f"👮 Processed By: {processed_by}",
                f"🕒 Processed At: {self.format_dt(datetime.now(timezone.utc))}",
            ])

        return "\n".join(lines)

