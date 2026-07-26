"""Focused clone-bot feature mixin; behavior preserved from services.bot_manager."""

from services.bot_manager_shared import *


class CloneHelpMixin:
    async def help_command(self,update:Update,context:ContextTypes.DEFAULT_TYPE):
        owner=self.owner(context)
        is_owner=update.effective_user.id==owner

        user_text=(
            "📚 Clone Bot Help Center\n\n"
            "👤 User Commands\n"
            "/start — Open the welcome menu\n"
            "/help — Open this help guide\n"
            "/version — Check deployed runtime version\n\n"
            "📋 Plans & Purchase\n"
            "Open Plans or Buy Plan, select a plan, complete payment and upload the payment screenshot when manual payment is enabled.\n\n"
            "🔄 Renew Plan\n"
            "Renew before or after expiry using the available renewal options.\n\n"
            "👤 My Profile\n"
            "View your Telegram ID, active plan, start date, expiry, remaining time and referral details.\n\n"
            "🎁 Referral\n"
            "Share your referral link. Reward days are added according to the seller's referral settings after a valid approved payment.\n\n"
            "📞 Live Support\n"
            "Send your message or supported media through the Support button. The seller's reply will return inside this bot.\n\n"
            "⏰ Expiry\n"
            "Expired access is removed automatically. Use Renew Plan to continue."
        )

        if not is_owner:
            await update.effective_message.reply_text(user_text)
            return

        admin_text=(
            user_text
            + "\n\n━━━━━━━━━━━━━━━━━━━━\n"
            "🛠 Seller Admin Help & Commands\n\n"
            "/admin — Open the Admin Panel\n"
            "/connectgroup — Connect a private subscription group\n"
            "/connectsupport — Connect the Live Support forum group\n\n"
            "🚀 Quick Setup\n"
            "1. Create plans\n"
            "2. Connect channel/group\n"
            "3. Configure payments\n"
            "4. Edit and preview welcome message\n"
            "5. Test purchase, approval and invite delivery\n\n"
            "📦 Manage Plans\n"
            "Add, edit, enable, disable or delete user plans. Example input: Premium | 30d | 199\n\n"
            "📂 Channels / Groups\n"
            "Add the bot as admin with Invite Users and Ban Users permissions. For private groups, send /connectgroup inside the group or use: -1001234567890 | Group Name\n\n"
            "💳 Payments\n"
            "Set UPI ID, UPI name and QR, or configure an available automatic gateway. Review Pending Payments and Payment History.\n\n"
            "👥 User Management\n"
            "Search users, give/extend/remove subscriptions, and ban/unban accounts.\n\n"
            "💬 Welcome Editor\n"
            "Edit text, media and buttons, then use Preview. Test every custom feature and URL button.\n\n"
            "🎫 Live Support\n"
            "Connect a forum group using /connectsupport. Manage Reply Templates and Template Auto Remove from Live Support settings.\n\n"
            "📢 Broadcast\n"
            "Send now or schedule for later. Review results and retry failed deliveries when necessary.\n\n"
            "🧪 Quick Troubleshooting\n"
            "• No reply: check runtime logs and token status\n"
            "• Group issue: recheck admin permissions\n"
            "• No invite: verify Invite Users permission\n"
            "• Support issue: enable forum topics and reconnect\n"
            "• Payment issue: verify UPI/QR or gateway credentials"
        )
        await update.effective_message.reply_text(admin_text)

