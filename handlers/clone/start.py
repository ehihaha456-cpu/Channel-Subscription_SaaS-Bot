"""Focused clone-bot feature mixin; behavior preserved from services.bot_manager."""

from services.bot_manager_shared import *


class CloneStartMixin:
    async def child_start(self,update:Update,context:ContextTypes.DEFAULT_TYPE):
        owner=self.owner(context)

        # Clone-bot seller opens the selected section directly from main-bot deep links.
        staff = await self.staff_record(update, context)
        if staff:
            context.user_data.clear()
            target = context.args[0] if context.args else "admin_panel"
            if target == "admin_payment":
                settings = await get_seller_settings(owner)
                await update.effective_message.reply_text(
                    f"💳 Payment Settings\n\nUPI Name: {settings.get('upi_name') or 'Not Set'}\n"
                    f"UPI ID: {settings.get('upi_id') or 'Not Set'}\n"
                    f"QR: {'Added' if settings.get('upi_qr_file_id') else 'Not Added'}",
                    reply_markup=self.payment_menu(),
                )
            elif target == "admin_settings":
                settings = await get_seller_settings(owner)
                await update.effective_message.reply_text(
                    "⚙️ Bot Settings\n\n"
                    f"Bot Name: {settings.get('bot_name') or '-'}\n"
                    f"Support: {settings.get('support_username') or '-'}\n"
                    f"Currency: {settings.get('currency') or 'INR'}\n"
                    f"Timezone: {settings.get('timezone') or 'Asia/Kolkata'}",
                    reply_markup=self.settings_menu(),
                )
            elif target == "admin_channels":
                await update.effective_message.reply_text("📢 Channels / Groups", reply_markup=self.channels_menu())
            elif target == "admin_stats":
                data = await stats(owner)
                await update.effective_message.reply_text(
                    "📊 Statistics\n\n"
                    f"Users: {data.get('users',0)}\nPlans: {data.get('plans',0)}\n"
                    f"Channels/Groups: {data.get('channels',0)}\n"
                    f"Pending Payments: {data.get('pending',0)}\nRevenue: ₹{data.get('revenue',0):g}",
                    reply_markup=self.admin_menu(),
                )
            elif target == "admin_terms":
                policy = await get_policy(owner)
                parts=[]
                for key in ("terms","privacy","refund","support"):
                    value=(policy or {}).get(key)
                    if value: parts.append(f"{key.title()}:\n{value}")
                await update.effective_message.reply_text(
                    "📜 Terms & Policy\n\n" + ("\n\n".join(parts) if parts else "No policy configured."),
                    reply_markup=self.admin_menu(),
                )
            else:
                await update.effective_message.reply_text(
                    await self.admin_panel_text(owner, update.effective_user),
                    reply_markup=self.admin_menu(),
                    parse_mode="HTML",
                )
            return

        try:
            await upsert_user(owner,update.effective_user)
            user_record=await get_user(owner,update.effective_user.id)

            if user_record and user_record.get("banned"):
                await update.effective_message.reply_text(
                    "🚫 You are banned from using this bot.\n"
                    f"Reason: {user_record.get('ban_reason') or 'Not specified'}"
                )
                return

            if context.args:
                arg=context.args[0]
                if arg.startswith("ref_"):
                    try:
                        referrer_id=int(arg.replace("ref_","",1))
                        await register_referral(owner,referrer_id,update.effective_user.id)
                    except (TypeError,ValueError):
                        pass

            record=await get_bot_by_data_owner_id(owner)
            settings=await ensure_seller_defaults(
                owner,
                (record or {}).get("bot_name","Subscription Bot"),
            )
            await self.send_welcome(
                update.effective_message,
                context,
                settings,
                update.effective_user,
            )
        except Exception as exc:
            logger.exception(
                "Child /start failed owner=%s runtime=%s",
                owner,
                WELCOME_RUNTIME_VERSION,
            )
            await update.effective_message.reply_text(
                "❌ Welcome message could not be sent.\n"
                f"Runtime: {WELCOME_RUNTIME_VERSION}\n"
                f"Error: {str(exc)[:250]}"
            )

