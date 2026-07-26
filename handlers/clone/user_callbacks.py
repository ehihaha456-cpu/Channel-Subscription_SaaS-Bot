"""Focused clone-bot feature mixin; behavior preserved from services.bot_manager."""

from handlers.common.clone_context import *


class CloneUserCallbacksMixin:
    async def child_callback(self,update:Update,context:ContextTypes.DEFAULT_TYPE):
        q=update.callback_query
        await q.answer()
        owner=self.owner(context)
        action=q.data
        if action=="seller_current_plan":
            await q.edit_message_text(
                await current_plan_text(owner),
                reply_markup=self.limit_keyboard("a_home"),
            )
            return
        if action=="seller_upgrade_plan":
            cfg=await get_config()
            plans=[p for p in cfg.get("paid_plans",[]) if p.get("active",True)]
            if not plans:
                await q.edit_message_text("No paid seller plans are available right now.", reply_markup=self.back("a_home")); return
            lines=["💎 Upgrade Seller Plan", ""]
            for p in plans:
                lines.append(f"• {p.get('name','Plan')} — ₹{p.get('price',0)} / {p.get('duration_days',30)} days")
            lines += ["", "Contact the SaaS owner to activate a plan."]
            await q.edit_message_text("\n".join(lines), reply_markup=self.back("a_home")); return
        back_keyboard=self.back("c_home")

        if action=="c_home":
            record=await get_bot_by_data_owner_id(owner)
            settings=await ensure_seller_defaults(
                owner,
                (record or {}).get("bot_name","Subscription Bot"),
            )
            await self.send_welcome(
                q.message,
                context,
                settings,
                q.from_user,
            )
            return

        if action=="c_plans":
            await self.show_plans(q,owner,True)
            return

        if action in {"c_buy","c_renew"}:
            await self.show_plans(q,owner,True)
            return

        if action.startswith("c_select_"):
            plan=await get_plan(owner,action.replace("c_select_",""))

            if not plan:
                await q.answer("Plan not found",show_alert=True)
                return

            context.user_data["selected_child_plan"]=plan
            s=await get_seller_settings(owner)

            gateway_cfg=await get_gateway_config("seller", owner, decrypt=True)
            gateways=gateway_cfg.get("gateways") or {}
            enabled=[g for g in SUPPORTED_GATEWAYS if (gateways.get(g) or {}).get("enabled")]
            default_gateway=str(gateway_cfg.get("default_gateway") or "")
            if default_gateway in enabled:
                enabled.remove(default_gateway)
                enabled.insert(0,default_gateway)
            manual_enabled=bool(gateway_cfg.get("manual_enabled",True))
            rows=[]
            text=""

            if enabled:
                gateway=enabled[0]
                tx=await create_gateway_transaction(
                    scope="seller", owner_id=owner, payer_user_id=q.from_user.id,
                    gateway=gateway, amount=float(plan["price"]), currency="INR",
                    purpose="child_subscription", reference_id=plan["plan_id"],
                    metadata={"plan_id":plan["plan_id"],"plan_name":plan["name"],"description":f"{plan['name']} subscription"},
                )
                try:
                    checkout=await create_checkout(tx)
                    text=(
                        f"💳 {gateway.title()} Payment\n\n"
                        f"Plan: {plan['name']}\nAmount: ₹{plan['price']:g}\n"
                        f"Transaction: {tx['transaction_id']}\n\n"
                        "Payment successful hone ke baad plan automatically activate hoga."
                    )
                    rows.append([InlineKeyboardButton("💳 Pay Now",url=checkout.get("checkout_url"))])
                except GatewayError as exc:
                    text=f"❌ Gateway error: {exc}"

            if manual_enabled:
                manual_text=(
                    f"Plan: {plan['name']}\n"
                    f"Amount: {s.get('currency','INR')} {plan['price']:g}\n"
                    f"Duration: {plan['duration_text']}\n\n"
                    f"UPI Name: {s.get('upi_name') or 'Not Set'}\n"
                    f"UPI ID: {s.get('upi_id') or 'Not Set'}\n\n"
                    "Pay and upload your payment screenshot."
                )
                text=f"{text}\n\n{manual_text}" if text else f"💳 Payment\n\n{manual_text}"
                rows.append([InlineKeyboardButton("📤 Upload Payment Screenshot",callback_data="c_upload")])

            if not enabled and not manual_enabled:
                text="⚠️ No payment method is currently available. Please contact support."
            rows.append([InlineKeyboardButton("⬅ Back",callback_data="c_buy")])
            kb=InlineKeyboardMarkup(rows)

            if s.get("upi_qr_file_id") and manual_enabled:
                try:
                    await q.message.delete()
                except TelegramError:
                    pass
                await context.bot.send_photo(q.message.chat_id,s["upi_qr_file_id"],caption=text,reply_markup=kb)
            else:
                await self.safe_query_message(q,text,kb)
            return

        if action.startswith("c_pg_"):
            try:
                _,_,gateway,plan_id=action.split("_",3)
            except ValueError:
                await q.answer("Invalid payment option",show_alert=True); return
            plan=await get_plan(owner,plan_id)
            if not plan:
                await q.answer("Plan not found",show_alert=True); return
            tx=await create_gateway_transaction(
                scope="seller", owner_id=owner, payer_user_id=q.from_user.id,
                gateway=gateway, amount=float(plan["price"]), currency="INR",
                purpose="child_subscription", reference_id=plan_id,
                metadata={"plan_id":plan_id,"plan_name":plan["name"],"description":f"{plan['name']} subscription"},
            )
            try:
                checkout=await create_checkout(tx)
            except GatewayError as exc:
                await self.safe_query_message(q,f"❌ Gateway error: {exc}",back_keyboard); return
            await self.safe_query_message(
                q,
                f"💳 {gateway.title()} Secure Payment\n\nPlan: {plan['name']}\nAmount: ₹{plan['price']:g}\nTransaction: {tx['transaction_id']}\n\nPayment verify hote hi subscription automatically activate hogi.",
                InlineKeyboardMarkup([[InlineKeyboardButton("💳 Pay Now",url=checkout.get("checkout_url"))],[InlineKeyboardButton("⬅ Back",callback_data="c_buy")]]),
            )
            return

        if action=="c_upload":
            context.user_data["waiting_child_screenshot"]=True
            await q.message.reply_text(
                "📷 Upload your payment screenshot.",
                reply_markup=back_keyboard,
            )
            return

        if action=="c_profile":
            try:
                timezone_name = await self.seller_timezone(owner)
                user_record=await get_user(owner,q.from_user.id) or {}
                sub=await get_subscription(owner,q.from_user.id)
                me=await context.bot.get_me()

                def aware_utc(value):
                    if not value:
                        return None
                    if value.tzinfo is None:
                        return value.replace(tzinfo=timezone.utc)
                    return value.astimezone(timezone.utc)

                joined=aware_utc(user_record.get("joined_at"))
                joined_text=(
                    self.format_dt(joined, timezone_name, "%d %b %Y, %I:%M %p %Z")
                    if joined else "Unknown"
                )

                referral_link=(
                    f"https://t.me/{me.username}"
                    f"?start=ref_{q.from_user.id}"
                )

                total_referrals=await count_all_referrals(
                    owner,
                    q.from_user.id,
                )
                successful_referrals=await count_successful_referrals(
                    owner,
                    q.from_user.id,
                )

                username=(
                    f"@{q.from_user.username}"
                    if q.from_user.username else "Not set"
                )
                full_name=" ".join(
                    value for value in [
                        q.from_user.first_name,
                        q.from_user.last_name,
                    ] if value
                ) or "Unknown"

                lines=[
                    "👤 My Profile",
                    "",
                    f"🆔 User ID: {q.from_user.id}",
                    f"👤 Name: {full_name}",
                    f"📝 Username: {username}",
                    f"🌐 Language: {q.from_user.language_code or 'Unknown'}",
                    f"📅 Joined: {joined_text}",
                    f"👥 Total Referrals: {total_referrals}",
                    f"✅ Successful Referrals: {successful_referrals}",
                    "",
                    "🔗 Referral Link:",
                    referral_link,
                    "",
                    "━━━━━━━━━━━━━━━━━━━━",
                    "📋 Subscription Details",
                ]

                now=datetime.now(timezone.utc)
                expiry=aware_utc((sub or {}).get("expiry_date"))
                active=bool(
                    sub
                    and sub.get("active")
                    and expiry
                    and expiry>now
                )

                if active:
                    remaining=expiry-now
                    days=max(remaining.days,0)
                    hours=remaining.seconds//3600
                    minutes=(remaining.seconds%3600)//60

                    start=aware_utc(
                        sub.get("start_date")
                        or sub.get("created_at")
                    )
                    start_text=(
                        self.format_dt(start, timezone_name, "%d %b %Y, %I:%M %p %Z")
                        if start else "Unknown"
                    )
                    expiry_text=self.format_dt(
                        expiry, timezone_name, "%d %b %Y, %I:%M %p %Z"
                    )

                    amount=sub.get("amount")
                    amount_text=(
                        f"₹{amount:g}"
                        if isinstance(amount,(int,float))
                        else str(amount or "—")
                    )

                    lines.extend([
                        "📌 Status: ✅ Active",
                        f"💎 Plan: {sub.get('plan') or 'Unknown'}",
                        f"💰 Amount: {amount_text}",
                        f"⏳ Duration: {sub.get('duration_text') or '—'}",
                        f"📅 Start Date: {start_text}",
                        f"📅 Expiry: {expiry_text}",
                        f"⏱ Time Left: {days}d {hours}h {minutes}m",
                    ])
                else:
                    lines.extend([
                        "📌 Status: ❌ No Active Subscription",
                        f"💎 Last Plan: {(sub or {}).get('plan') or '—'}",
                        f"💰 Amount: {(sub or {}).get('amount') or '—'}",
                        f"⏳ Duration: {(sub or {}).get('duration_text') or '—'}",
                        f"📅 Expiry: {self.format_dt(expiry)}",
                    ])

                await self.safe_query_message(
                    q,
                    "\n".join(lines),
                    back_keyboard,
                )

            except Exception as exc:
                logger.exception(
                    "Profile failed owner=%s user=%s",
                    owner,
                    q.from_user.id,
                )
                await q.message.reply_text(
                    "❌ Profile could not be loaded.\n"
                    f"Error: {str(exc)[:250]}",
                    reply_markup=back_keyboard,
                )
            return

        if action=="c_referral":
            me=await context.bot.get_me()
            settings=await get_seller_settings(owner)
            reward_days=int(settings.get("referral_reward_days",7) or 7)
            total=await count_all_referrals(owner,q.from_user.id)
            successful=await count_successful_referrals(owner,q.from_user.id)
            referral_link=f"https://t.me/{me.username}?start=ref_{q.from_user.id}"
            share_url=(
                "https://t.me/share/url?url="
                + referral_link
                + "&text=Join%20this%20subscription%20bot"
            )

            text=(
                "🎁 Referral Program\n\n"
                f"👥 Total Referrals: {total}\n"
                f"✅ Successful Referrals: {successful}\n"
                f"🎉 Reward: {reward_days} Free Days per successful referral.\n\n"
                "🔗 Your Referral Link:\n"
                f"{referral_link}"
            )

            kb=InlineKeyboardMarkup([
                [InlineKeyboardButton(
                    "📤 Share Referral Link",
                    url=share_url,
                )],
                [InlineKeyboardButton(
                    "⬅ Back",
                    callback_data="c_home",
                )],
            ])

            await self.safe_query_message(q,text,kb)
            return

        if action=="c_referral_unlock":
            settings=await get_seller_settings(owner)
            enabled=bool(settings.get("referral_unlock_enabled",False))
            required=max(1,int(settings.get("referral_unlock_required",3) or 3))
            target_chat_id=settings.get("referral_unlock_target_chat_id")
            target_title=settings.get("referral_unlock_target_title") or "Private Group"
            duration_days=max(1,int(settings.get("referral_unlock_duration_days",30) or 30))
            count_mode=settings.get("referral_unlock_count_mode","subscription")
            counted=(
                await count_all_referrals(owner,q.from_user.id)
                if count_mode == "start"
                else await count_successful_referrals(owner,q.from_user.id)
            )
            progress=min(counted,required)
            me=await context.bot.get_me()
            referral_link=f"https://t.me/{me.username}?start=ref_{q.from_user.id}"
            share_url="https://t.me/share/url?url="+referral_link+"&text=Join%20this%20bot"
            if not enabled or not target_chat_id:
                await self.safe_query_message(
                    q,
                    "🔓 Referral Unlock is not available right now.\n\nPlease contact support.",
                    InlineKeyboardMarkup([[InlineKeyboardButton("⬅ Back",callback_data="c_home")]]),
                )
                return
            if counted < required:
                count_instruction=(
                    f"Invite {required} new user(s) with your referral link.\n\n"
                    if count_mode == "start"
                    else f"Invite {required} user(s) who complete a subscription.\n\n"
                )
                text=(
                    "🔓 Unlock Private Access\n\n"
                    + count_instruction
                    + f"Progress: {progress}/{required}\n\n"
                    "Your unique referral link:\n"
                    f"{referral_link}\n\n"
                    "After the required referrals are completed, open this button again to receive the private invite link."
                )
                kb=InlineKeyboardMarkup([
                    [InlineKeyboardButton("📤 Share Referral Link",url=share_url)],
                    [InlineKeyboardButton("🔄 Check Progress",callback_data="c_referral_unlock")],
                    [InlineKeyboardButton("⬅ Back",callback_data="c_home")],
                ])
                await self.safe_query_message(q,text,kb)
                return
            saved=await get_referral_unlock(owner,q.from_user.id)
            invite_link=(saved or {}).get("invite_link")
            if not invite_link:
                try:
                    invite=await context.bot.create_chat_invite_link(
                        chat_id=int(target_chat_id), member_limit=1,
                        expire_date=datetime.now(timezone.utc)+timedelta(days=duration_days),
                        name=f"Referral unlock {q.from_user.id}",
                    )
                    invite_link=invite.invite_link
                    await save_referral_unlock(owner,q.from_user.id,int(target_chat_id),invite_link,duration_days)
                except Exception:
                    logger.exception("Referral unlock invite failed owner=%s user=%s",owner,q.from_user.id)
                    await self.safe_query_message(
                        q,
                        "❌ The private invite link could not be created.\n\nPlease contact support.",
                        InlineKeyboardMarkup([[InlineKeyboardButton("⬅ Back",callback_data="c_home")]]),
                    )
                    return
            await self.safe_query_message(
                q,
                "🎉 Referral Target Completed!\n\n"
                f"Progress: {counted}/{required}\n"
                f"Destination: {target_title}\n\n"
                "Use your private one-time invite link below.",
                InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔓 Join Now",url=invite_link)],
                    [InlineKeyboardButton("⬅ Back",callback_data="c_home")],
                ]),
            )
            return

        if action=="c_support":
            support=await get_live_support_settings(owner)
            if not support.get("enabled"):
                await self.safe_query_message(
                    q,
                    "🔴 Live support is currently unavailable. Please try again later.",
                    back_keyboard,
                )
                return
            await self.safe_query_message(
                q,
                "💬 Live Support is ON.\n\nSend any text, photo, video, voice, audio, document or sticker here. Your message will stay in the support conversation and will not be auto-deleted.",
                back_keyboard,
            )
            return

        await q.answer(
            "Button action not found",
            show_alert=True,
        )

