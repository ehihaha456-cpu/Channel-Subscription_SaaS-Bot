"""Focused clone-bot feature mixin; behavior preserved from services.bot_manager."""

from handlers.common.clone_context import *


class ClonePaymentDeliveryMixin:
    async def notify_automatic_payment_success(self, owner_id:int, user_id:int, details:dict):
        """Notify the seller and payment-authorized staff through the same clone bot."""
        owner_id = int(owner_id)
        user_id = int(user_id)
        running = self.get_running(owner_id)
        if not running:
            record = await get_bot_by_data_owner_id(owner_id)
            started = await self.start_bot(int(record["bot_id"])) if record else False
            running = self.get_running(owner_id) if started else None
        if not running:
            return {"sent": 0, "failed": 0, "error": "Clone bot is not running"}

        bot = running.application.bot
        timezone_name = await self.seller_timezone(owner_id)
        seller_account_id = int(
            running.application.bot_data.get("seller_account_id", owner_id)
        )

        try:
            user_chat = await bot.get_chat(user_id)
            full_name = getattr(user_chat, "full_name", None) or str(details.get("full_name") or "Unknown")
            username = getattr(user_chat, "username", None) or details.get("username")
        except TelegramError:
            full_name = str(details.get("full_name") or "Unknown")
            username = details.get("username")

        def _format_dt(value):
            return self.format_dt(value, timezone_name, "%d %b %Y, %I:%M %p %Z")

        safe_name = html.escape(full_name)
        safe_username = html.escape(f"@{username}" if username else "Not Set")
        mention = f'<a href="tg://user?id={user_id}">{safe_name}</a>'
        amount = float(details.get("amount") or 0)
        gateway = str(details.get("gateway") or "-").title()

        text = (
            "💰 <b>Automatic Payment Successful</b>\n\n"
            "A subscriber payment has been verified automatically.\n\n"
            "👤 <b>User Details</b>\n"
            f"• Name: {safe_name}\n"
            f"• Username: {safe_username}\n"
            f"• Mention: {mention}\n"
            f"• User ID: <code>{user_id}</code>\n\n"
            "📦 <b>Subscription Details</b>\n"
            f"• Plan: {html.escape(str(details.get('plan_name') or 'Subscription'))}\n"
            f"• Duration: {html.escape(str(details.get('duration') or '-'))}\n"
            f"• Amount: ₹{amount:g}\n"
            f"• Payment Gateway: {html.escape(gateway)}\n"
            f"• Payment Date: {_format_dt(details.get('payment_date'))}\n"
            f"• Expiry Date: {_format_dt(details.get('expiry_date'))}\n\n"
            "🧾 <b>Payment Details</b>\n"
            f"• Transaction ID: <code>{html.escape(str(details.get('transaction_id') or '-'))}</code>\n"
            f"• Invoice: <code>{html.escape(str(details.get('invoice_no') or '-'))}</code>\n"
            "• Status: ✅ Paid & Activated\n\n"
            "✅ The user's subscription has been activated automatically."
        )

        recipients = {seller_account_id}
        try:
            for staff in await list_staff(owner_id):
                if staff.get("status") != "active":
                    continue
                permissions = staff.get("permissions") or []
                if "*" in permissions or "payments" in permissions:
                    recipients.add(int(staff["user_id"]))
        except Exception:
            logger.exception("Failed to load payment notification staff owner=%s", owner_id)

        sent = 0
        failed = 0
        for recipient_id in recipients:
            try:
                await bot.send_message(
                    chat_id=recipient_id,
                    text=text,
                    parse_mode="HTML",
                    disable_web_page_preview=True,
                )
                sent += 1
            except TelegramError as exc:
                failed += 1
                logger.warning(
                    "Automatic payment notification failed owner=%s recipient=%s user=%s: %s",
                    owner_id, recipient_id, user_id, exc,
                )

        return {"sent": sent, "failed": failed, "error": ""}

    async def deliver_subscription_access(self, owner_id:int, user_id:int, success_details:dict|None=None):
        """Send fresh invite links only for chats the user has not joined yet.

        When ``success_details`` is supplied by an automatic gateway payment,
        the access message also includes the user and subscription receipt
        details. Manual/admin delivery keeps the existing compact message.
        """
        running=self.get_running(int(owner_id))
        if not running:
            record=await get_bot_by_data_owner_id(int(owner_id))
            started=await self.start_bot(int(record["bot_id"])) if record else False
            running=self.get_running(int(owner_id)) if started else None
        if not running:
            return {"sent":0,"already_member":0,"failed":0,"error":"Clone bot is not running"}

        bot=running.application.bot
        timezone_name = await self.seller_timezone(int(owner_id))
        connected_channels=await get_channels(int(owner_id))
        if not connected_channels:
            return {"sent":0,"already_member":0,"failed":0,"error":"No channel/group is connected to this clone bot"}

        # Existing channel documents default to enabled so current sellers keep
        # their previous behaviour until they explicitly disable a destination.
        channels=[
            channel for channel in connected_channels
            if channel.get("auto_invite_enabled",True) is not False
        ]
        if not channels:
            return {
                "sent":0,
                "already_member":0,
                "failed":0,
                "error":"Automatic invite delivery is disabled for every connected channel/group",
            }

        links=[]
        already_member=0
        failed=0

        for ch in channels:
            chat_id=int(ch["chat_id"])
            try:
                member=await bot.get_chat_member(chat_id,int(user_id))
                status=getattr(member,"status","")
                is_member=getattr(member,"is_member",None)
                if status in {"creator","administrator","member"} or (status=="restricted" and is_member is not False):
                    # Keep membership information for delivery statistics, but do
                    # not skip link creation. Every successful new payment gets a
                    # fresh private invite link, even when the user is already in
                    # the connected channel/group.
                    already_member+=1
                if status=="kicked":
                    try:
                        await bot.unban_chat_member(chat_id,int(user_id),only_if_banned=True)
                    except TelegramError:
                        pass
            except BadRequest:
                pass
            except TelegramError as exc:
                logger.warning("Membership check failed owner=%s chat=%s user=%s: %s",owner_id,chat_id,user_id,exc)

            try:
                invite=await bot.create_chat_invite_link(
                    chat_id=chat_id,
                    member_limit=1,
                    name=f"Subscription access {user_id}",
                )
                await save_invite(owner_id, user_id, chat_id, invite.invite_link)
                links.append(f"📢 {ch.get('title','Premium Channel/Group')}\n{invite.invite_link}")
            except TelegramError as exc:
                failed+=1
                logger.warning("Invite creation failed owner=%s chat=%s user=%s: %s",owner_id,chat_id,user_id,exc)

        if links:
            try:
                if success_details:
                    try:
                        chat = await bot.get_chat(int(user_id))
                        full_name = getattr(chat, "full_name", None) or "Unknown"
                        username = getattr(chat, "username", None)
                    except TelegramError:
                        full_name = str(success_details.get("full_name") or "Unknown")
                        username = success_details.get("username")

                    username_text = f"@{username}" if username else "Not Set"

                    def _format_dt(value):
                        return self.format_dt(value, timezone_name, "%d %b %Y, %I:%M %p %Z")

                    was_already_active = bool(success_details.get("was_already_active"))
                    if was_already_active:
                        subscription_note = (
                            "ℹ️ Your subscription was already active.\n"
                            "Your new purchase has been added to your existing subscription.\n\n"
                            f"📅 Previous Expiry: {_format_dt(success_details.get('previous_expiry'))}\n"
                            f"📅 New Expiry: {_format_dt(success_details.get('expiry_date'))}\n\n"
                            "🔗 A fresh private invite link has been generated for you."
                        )
                    else:
                        subscription_note = (
                            f"⏳ Expiry Date: {_format_dt(success_details.get('expiry_date'))}\n\n"
                            "🔗 Your fresh private invite link has been generated."
                        )

                    text = (
                        "✅ Payment verified automatically\n"
                        "━━━━━━━━━━━━━━━━━━━━━━\n"
                        f"👤 Name: {full_name}\n"
                        f"🆔 Username: {username_text}\n"
                        f"📦 Purchased Plan: {success_details.get('plan_name') or 'Subscription'}\n"
                        f"💰 Amount: ₹{float(success_details.get('amount') or 0):g}\n"
                        f"💳 Gateway: {str(success_details.get('gateway') or '').title() or '-'}\n"
                        f"🧾 Transaction ID: {success_details.get('transaction_id') or '-'}\n"
                        f"📅 Payment Date: {_format_dt(success_details.get('payment_date'))}\n"
                        f"⌛ Added Duration: {success_details.get('duration') or '-'}\n"
                        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
                        f"{subscription_note}\n\n"
                        "Join using your private invite link(s):\n\n"
                        + "\n\n".join(links)
                    )
                else:
                    text = (
                        "✅ Your subscription has been updated.\n\n"
                        "Use the fresh invite link(s) below to join the channel/group(s) you have not joined yet:\n\n"
                        + "\n\n".join(links)
                    )

                await bot.send_message(
                    chat_id=int(user_id),
                    text=text,
                    disable_web_page_preview=True,
                )
            except TelegramError as exc:
                return {"sent":0,"already_member":already_member,"failed":failed+len(links),"error":str(exc)}

        error = ""
        if not links and already_member == 0:
            error = "Invite link could not be created for any connected channel/group"
        elif failed and not links:
            error = "Invite link creation failed for all connected channel/groups"
        return {"sent":len(links),"already_member":already_member,"failed":failed,"error":error}

