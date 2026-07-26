"""Focused clone-bot feature mixin; behavior preserved from services.bot_manager."""

from handlers.common.clone_context import *
from handlers.common.editor_engine import url_buttons_header


class CloneAdminCallbacksMixin:
    async def admin_callback(self,update:Update,context:ContextTypes.DEFAULT_TYPE):
        q=update.callback_query; await q.answer(); owner=self.owner(context)
        staff = await self.staff_record(update, context)
        if not staff:
            await q.edit_message_text("❌ Not authorized")
            return
        a=q.data
        role = staff.get("role", "moderator")
        if role == "moderator":
            allowed_prefixes = ("a_home", "a_users", "a_user_", "a_pending", "a_pay_", "a_live_support", "a_help")
            if not any(a == p or a.startswith(p) for p in allowed_prefixes):
                await q.answer("Moderator permission is not available for this section.", show_alert=True)
                return
        if role != "seller" and a.startswith("a_staff"):
            await q.answer("Only the seller can manage staff.", show_alert=True)
            return
        if a=="a_home":
            context.user_data.clear()
            await q.edit_message_text(
                await self.admin_panel_text(owner, q.from_user),
                reply_markup=self.admin_menu(),
                parse_mode="HTML",
            )
            return
        if a=="a_seller_profile":
            timezone_name = await self.seller_timezone(owner)
            plan,assignment=await effective_plan(owner)
            usage=await stats(owner)
            bot_record=await get_bot_by_data_owner_id(owner) or {}
            expiry=(assignment or {}).get("expiry_date")
            if expiry and getattr(expiry,"tzinfo",None) is None:
                expiry=expiry.replace(tzinfo=timezone.utc)
            now=datetime.now(timezone.utc)
            if expiry and expiry>now:
                remaining=expiry-now
                remaining_text=f"{remaining.days}d {remaining.seconds//3600}h {(remaining.seconds%3600)//60}m"
                status="✅ Active"
            elif str(plan.get("plan_id","free"))=="free":
                remaining_text="No expiry"
                status="🆓 Free Plan"
            else:
                remaining_text="Expired"
                status="❌ Expired"
            def lim(value):
                try:
                    value=int(value)
                    return "Unlimited" if value<0 else f"{value:,}"
                except Exception:
                    return str(value)
            username_text = (
                f"@{q.from_user.username}"
                if q.from_user.username
                else "Not set"
            )
            text = (
                "👤 Seller Profile\n\n"
                f"🆔 Seller ID: {owner}\n"
                f"👤 Name: {q.from_user.full_name or 'Unknown'}\n"
                f"📝 Username: {username_text}"
            )
            text += (
                "\n\n💎 Plan Details\n"
                f"Plan: {plan.get('name','Free')}\n"
                f"Status: {status}\n"
                f"Expiry: {self.format_dt(expiry, timezone_name)}\n"
                f"Remaining: {remaining_text}\n\n"
                "📊 Usage & Limits\n"
                f"🤖 Clone Bots: {1 if bot_record else 0} / {lim(plan.get('bot_limit',1))}\n"
                f"👥 Active Subscribers: {usage.get('active',0)} / {lim(plan.get('active_subscriber_limit',25))}\n"
                f"📢 Channels / Groups: {usage.get('channels',0)} / {lim(plan.get('channel_limit',1))}\n"
                f"📦 Subscription Plans: {usage.get('plans',0)} / {lim(plan.get('plan_limit',2))}\n\n"
                f"👥 Total Users: {usage.get('users',0)}\n"
                f"💳 Pending Payments: {usage.get('pending',0)}\n"
                f"💰 Revenue: ₹{usage.get('revenue',0):g}"
            )
            main_bot_username = os.getenv("MAIN_BOT_USERNAME", "Subscripti0n_Manage_bot").lstrip("@")
            kb=InlineKeyboardMarkup([
                [InlineKeyboardButton(
                    "💎 Buy / Change Plan",
                    url=f"https://t.me/{main_bot_username}?start=sellerplan",
                )],
                [InlineKeyboardButton("⬅ Seller Admin Panel",callback_data="a_home")],
            ])
            await q.edit_message_text(text,reply_markup=kb)
            return
        if a=="a_seller_plan_history":
            await q.edit_message_text(
                "📜 Seller Plan History\n\nOpen the main SaaS bot → Seller Dashboard → Plan History to view complete seller plan records.",
                reply_markup=self.back("a_seller_profile"),
            )
            return
        if a=="a_plans": await q.edit_message_text("📦 Plan Management",reply_markup=self.plans_admin_menu()); return
        if a=="a_plan_add":
            plan_cfg,_=await effective_plan(owner)
            existing=len(await get_plans(owner))
            limit=int(plan_cfg.get("plan_limit",2))
            if limit>=0 and existing>=limit:
                await q.edit_message_text(await plan_limit_warning(owner), reply_markup=self.limit_keyboard("a_plans")); return
            context.user_data.clear(); context.user_data["wait_plan_add"]=True; await q.edit_message_text("Send: Plan Name | Duration | Price\nExample: Premium | 30d | 199",reply_markup=self.back("a_plans")); return
        if a=="a_plan_list":
            plans=await get_plans(owner); lines=["📋 Plans\n"]; kb=[]
            for p in plans:
                lines.append(f"{'✅' if p.get('active') else '⏸'} {p['name']} — {p['duration_text']} — ₹{p['price']:g}")
                kb.append([InlineKeyboardButton(f"✏ {p['name'][:16]}",callback_data=f"a_plan_edit_{p['plan_id']}"),InlineKeyboardButton("🗑",callback_data=f"a_plan_del_{p['plan_id']}")])
                kb.append([InlineKeyboardButton("⏸ Disable" if p.get("active") else "▶ Enable",callback_data=f"a_plan_toggle_{p['plan_id']}")])
            kb.append([InlineKeyboardButton("⬅ Back",callback_data="a_plans")]); await q.edit_message_text("\n".join(lines),reply_markup=InlineKeyboardMarkup(kb)); return
        if a.startswith("a_plan_edit_"): context.user_data.clear(); context.user_data["wait_plan_edit"]=a.replace("a_plan_edit_",""); await q.edit_message_text("Send new: Plan Name | Duration | Price",reply_markup=self.back("a_plan_list")); return
        if a.startswith("a_plan_del_"): await delete_plan(owner,a.replace("a_plan_del_","")); await q.edit_message_text("✅ Plan deleted",reply_markup=self.plans_admin_menu()); return
        if a.startswith("a_plan_toggle_"):
            pid=a.replace("a_plan_toggle_",""); p=await get_plan(owner,pid); await update_plan(owner,pid,active=not bool(p.get("active"))); await q.edit_message_text("✅ Plan status updated",reply_markup=self.plans_admin_menu()); return
        if a=="a_channels": await q.edit_message_text("📢 Channels / Groups",reply_markup=self.channels_menu()); return
        if a=="a_channel_add":
            plan_cfg,_=await effective_plan(owner)
            existing=len(await get_channels(owner))
            limit=int(plan_cfg.get("channel_limit",1))
            if limit>=0 and existing>=limit:
                await q.edit_message_text(await plan_limit_warning(owner), reply_markup=self.limit_keyboard("a_channels")); return
            context.user_data.clear(); context.user_data["wait_channel"]=True; await q.edit_message_text(
                "📢 Connect Channel / Group\n\n"
                "✅ Channel\n"
                "• Child bot ko channel me Admin banao.\n"
                "• Channel se koi bhi message yahan FORWARD karo.\n\n"
                "✅ Private Group (Recommended)\n"
                "1. Child bot ko group me add karo.\n"
                "2. Bot ko Admin banao.\n"
                "3. Invite Users permission ON rakho.\n"
                "4. Usi group ke andar /connectgroup bhejo.\n\n"
                "Bot group automatically detect karke save karega aur invite-link permission test karega.\n\n"
                "🔄 Agar auto detect na ho:\n"
                "• Group se koi message yahan FORWARD karo.\n\n"
                "⚠️ Sirf last option:\n"
                "-100xxxxxxxxxx | Group Name",
                reply_markup=self.back("a_channels"),
            ); return
        if a=="a_channel_list":
            channels=await get_channels(owner)
            lines=[
                "📋 Channels / Groups\n",
                "Choose which connected chats should receive automatic invite links after successful automatic payment verification.\n",
                "✅ Enabled: invite link will be sent\n❌ Disabled: invite link will be skipped",
            ]
            kb=[]
            for ch in channels:
                enabled=ch.get("auto_invite_enabled", True) is not False
                status="✅ Enabled" if enabled else "❌ Disabled"
                title=ch.get("title","Chat")
                lines.append(f"• {title}\n  {ch.get('chat_id')}\n  Auto Invite: {status}")
                kb.append([
                    InlineKeyboardButton(
                        f"{'✅' if enabled else '❌'} {title[:24]}",
                        callback_data=f"a_channel_autoinvite_{ch['chat_id']}",
                    ),
                    InlineKeyboardButton(
                        "🗑 Remove",
                        callback_data=f"a_channel_del_{ch['chat_id']}",
                    ),
                ])
            kb.append([InlineKeyboardButton("⬅ Back",callback_data="a_channels")])
            await q.edit_message_text("\n\n".join(lines),reply_markup=InlineKeyboardMarkup(kb))
            return
        if a.startswith("a_channel_autoinvite_"):
            chat_id=int(a.replace("a_channel_autoinvite_","",1))
            channels=await get_channels(owner)
            channel=next((item for item in channels if int(item.get("chat_id"))==chat_id),None)
            if not channel:
                await q.answer("Channel or group not found.",show_alert=True)
                return
            current=channel.get("auto_invite_enabled",True) is not False
            await set_channel_auto_invite(owner,chat_id,not current)
            channels=await get_channels(owner)
            lines=[
                "📋 Channels / Groups\n",
                "Choose which connected chats should receive automatic invite links after successful automatic payment verification.\n",
                "✅ Enabled: invite link will be sent\n❌ Disabled: invite link will be skipped",
            ]
            kb=[]
            for ch in channels:
                enabled=ch.get("auto_invite_enabled",True) is not False
                status="✅ Enabled" if enabled else "❌ Disabled"
                title=ch.get("title","Chat")
                lines.append(f"• {title}\n  {ch.get('chat_id')}\n  Auto Invite: {status}")
                kb.append([
                    InlineKeyboardButton(
                        f"{'✅' if enabled else '❌'} {title[:24]}",
                        callback_data=f"a_channel_autoinvite_{ch['chat_id']}",
                    ),
                    InlineKeyboardButton(
                        "🗑 Remove",
                        callback_data=f"a_channel_del_{ch['chat_id']}",
                    ),
                ])
            kb.append([InlineKeyboardButton("⬅ Back",callback_data="a_channels")])
            await q.edit_message_text("\n\n".join(lines),reply_markup=InlineKeyboardMarkup(kb))
            return
        if a=="a_channel_resend":
            channels=await get_channels(owner)
            if not channels:
                await q.edit_message_text(
                    "❌ Pehle kam se kam ek channel/group add karo.",
                    reply_markup=self.channels_menu(),
                )
                return
            active_count=len(await active_subscriptions(owner))
            await q.edit_message_text(
                "🔗 Group/Channel Invite Link Resend\n\n"
                f"Active subscribers found: {active_count}\n"
                f"Channels/Groups: {len(channels)}\n\n"
                "Fresh invite links sabhi active subscribers ko bheje jayenge. "
                "Expired users ko message nahi jayega.\n\nContinue?",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("✅ Yes, Resend",callback_data="a_channel_resend_yes")],
                    [InlineKeyboardButton("❌ No",callback_data="a_channels")],
                ]),
            )
            return
        if a=="a_channel_resend_yes":
            await q.edit_message_text("⏳ Invite links resend ho rahe hain...")
            channels=await get_channels(owner)
            subscriptions=await active_subscriptions(owner)
            sent=failed=invite_failed=0
            now=datetime.now(timezone.utc)

            for sub in subscriptions:
                user_id=int(sub["user_id"])
                expiry=sub.get("expiry_date")
                if expiry and expiry.tzinfo is None:
                    expiry=expiry.replace(tzinfo=timezone.utc)
                remaining=expiry-now if expiry else None
                if not remaining or remaining.total_seconds()<=0:
                    continue
                days=remaining.days
                hours=remaining.seconds//3600
                minutes=(remaining.seconds%3600)//60
                link_lines=[]
                for ch in channels:
                    try:
                        invite=await context.bot.create_chat_invite_link(
                            chat_id=ch["chat_id"],
                            member_limit=1,
                        )
                        await save_invite(owner, user_id, ch["chat_id"], invite.invite_link)
                        link_lines.append(
                            f"📢 {ch.get('title','Premium Channel')}\n{invite.invite_link}"
                        )
                    except Exception as exc:
                        invite_failed+=1
                        logger.warning(
                            "Invite create failed owner=%s chat=%s user=%s: %s",
                            owner,ch.get("chat_id"),user_id,exc,
                        )

                if not link_lines:
                    failed+=1
                    continue

                try:
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=(
                            "📢 Channel/Group Invite Links Updated\n\n"
                            "Your subscription is still active.\n\n"
                            f"⏱ Remaining: {days}d {hours}h {minutes}m\n\n"
                            "Join using the fresh invite link(s):\n\n"
                            + "\n\n".join(link_lines)
                        ),
                        disable_web_page_preview=True,
                    )
                    sent+=1
                except Exception as exc:
                    failed+=1
                    await save_failed_delivery(owner,user_id,"invite_resend",{"channels":[c.get("chat_id") for c in channels]},str(exc))
                    logger.warning(
                        "Invite resend failed owner=%s user=%s: %s",
                        owner,user_id,exc,
                    )
                await asyncio.sleep(0.05)

            await q.edit_message_text(
                "✅ Invite Link Resend Completed\n\n"
                f"Active subscribers: {len(subscriptions)}\n"
                f"Successfully sent: {sent}\n"
                f"Failed/blocked users: {failed}\n"
                f"Invite creation failures: {invite_failed}\n\n"
                "Expired users ko message nahi bheja gaya.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔁 Retry Failed Users", callback_data="a_retry_failed")],
                    [InlineKeyboardButton("⬅ Back", callback_data="a_channels")],
                ]),
            )
            return
        if a == "a_retry_failed":
            failed_docs = await get_failed_deliveries(
                owner,
                "invite_resend",
            )
            sent = still_failed = skipped = 0
            channels = await get_channels(owner)

            for item in failed_docs:
                claimed = await claim_failed_delivery(
                    item["_id"],
                    owner,
                    stale_after_seconds=600,
                )
                if not claimed:
                    skipped += 1
                    continue

                uid = int(claimed.get("user_id"))

                try:
                    links = []

                    for ch in channels:
                        invite = await context.bot.create_chat_invite_link(
                            ch["chat_id"],
                            member_limit=1,
                        )
                        await save_invite(
                            owner,
                            uid,
                            ch["chat_id"],
                            invite.invite_link,
                        )
                        links.append(
                            f"{ch.get('title', 'Channel')}: "
                            f"{invite.invite_link}"
                        )

                    await context.bot.send_message(
                        uid,
                        "🔁 Fresh invite link(s):\n\n"
                        + "\n".join(links),
                        disable_web_page_preview=True,
                    )

                    resolved = await resolve_failed_delivery(
                        claimed["_id"]
                    )
                    if resolved:
                        sent += 1
                    else:
                        still_failed += 1
                        logger.warning(
                            "Failed delivery retry sent but could not "
                            "finalize owner_id=%s user_id=%s delivery_id=%s",
                            owner,
                            uid,
                            claimed["_id"],
                        )
                except Exception as exc:
                    still_failed += 1
                    logger.exception(
                        "Failed delivery retry failed owner_id=%s "
                        "user_id=%s delivery_id=%s",
                        owner,
                        uid,
                        claimed["_id"],
                    )
                    try:
                        await release_failed_delivery_claim(
                            claimed["_id"],
                            str(exc),
                        )
                    except Exception:
                        logger.exception(
                            "Failed delivery claim release failed "
                            "owner_id=%s user_id=%s delivery_id=%s",
                            owner,
                            uid,
                            claimed["_id"],
                        )

            await q.edit_message_text(
                "🔁 Retry completed\n\n"
                f"Sent: {sent}\n"
                f"Still failed: {still_failed}\n"
                f"Already processing: {skipped}",
                reply_markup=self.admin_menu(),
            )
            return
        if a.startswith("a_channel_del_"): await remove_channel(owner,int(a.replace("a_channel_del_",""))); await q.edit_message_text("✅ Removed",reply_markup=self.channels_menu()); return
        if a=="a_welcome":
            s=await ensure_seller_defaults(owner,(await get_bot_by_data_owner_id(owner) or {}).get("bot_name","Subscription Bot"))
            text=("💬 Welcome Message\n\n"
                  f"📝 Text: {'✅' if s.get('welcome_message') else '❌'}\n"
                  f"🖼 Media: {'✅' if s.get('welcome_media_file_id') else '❌'}\n"
                  f"🔗 Buttons: {sum(len(r) for r in (s.get('welcome_buttons') or []))}")
            await q.edit_message_text(text,reply_markup=self.welcome_menu()); return
        if a=="a_welcome_text":
            s=await get_seller_settings(owner)
            context.user_data.clear(); context.user_data["wait_welcome_text"]=True
            await q.edit_message_text(
                "📄 Send the welcome message text.\n\n"
                "HTML and variables are supported:\n"
                "{ID} {NAME} {SURNAME} {NAMESURNAME} {USERNAME} {LANG} "
                "{DATE} {TIME} {WEEKDAY} {MENTION} {BOTNAME}",
                reply_markup=self.welcome_text_menu(bool(s.get("welcome_message"))),
            ); return
        if a=="a_welcome_media":
            s=await get_seller_settings(owner)
            context.user_data.clear(); context.user_data["wait_welcome_media"]=True
            await q.edit_message_text(
                "🖼 Send a photo, video, GIF or document.\n\n"
                "The same media will appear in Full Preview and on /start.",
                reply_markup=self.welcome_media_menu(bool(s.get("welcome_media_file_id"))),
            ); return
        if a=="a_welcome_buttons":
            s=await get_seller_settings(owner)
            context.user_data.clear(); context.user_data["wait_welcome_buttons"]=True
            await q.edit_message_text(
                url_buttons_header(),
                reply_markup=self.welcome_buttons_menu(bool(s.get("welcome_buttons"))),
            ); return
        if a=="a_welcome_quick": await q.edit_message_text("⚡ Choose a bot button to add",reply_markup=self.welcome_quick_menu()); return
        if a.startswith("a_wq_"):
            feature=a.replace("a_wq_","")
            config={
                "plans":("📋 Plans","c_plans"),"buy":("💳 Buy","c_buy"),"profile":("👤 My Profile","c_profile"),
                "renew":("🔄 Renew","c_renew"),"referral":("🎁 Referral","c_referral"),"referral_unlock":("🔓 Referral Unlock","c_referral_unlock"),"support":("📞 Support","c_support"),"home":("🏠 Main Menu","c_home")}
            title,callback=config[feature]
            s=await get_seller_settings(owner)
            rows=s.get("welcome_buttons") or []

            already_exists=any(
                item.get("type")=="callback"
                and item.get("value")==callback
                for row in rows
                for item in row
            )

            if already_exists:
                await q.edit_message_text(
                    f"ℹ️ {title} button already exists.",
                    reply_markup=self.welcome_buttons_menu(),
                )
                return

            rows.append([
                {
                    "text":title,
                    "type":"callback",
                    "value":callback,
                }
            ])

            await set_seller_setting(
                owner,
                "welcome_buttons",
                rows,
            )

            await q.edit_message_text(
                f"✅ {title} button added.",
                reply_markup=self.welcome_buttons_menu(),
            )
            return
        if a=="a_welcome_manual":
            s=await get_seller_settings(owner)
            context.user_data.clear(); context.user_data["wait_welcome_buttons"]=True
            await q.edit_message_text(
                url_buttons_header(),
                reply_markup=self.welcome_buttons_menu(bool(s.get("welcome_buttons"))),
            ); return
        if a=="a_welcome_see_buttons":
            s=await get_seller_settings(owner)
            rows=s.get("welcome_buttons") or []

            if not rows:
                await q.edit_message_text(
                    "No buttons set.",
                    reply_markup=self.welcome_buttons_menu(),
                )
                return

            lines=["🔗 Current Buttons\n"]
            kb=[]

            for row_index,row in enumerate(rows):
                names=[]

                for button_index,item in enumerate(row):
                    name=item.get("text","Button")
                    names.append(name)
                    kb.append([
                        InlineKeyboardButton(
                            f"🗑 Delete: {name[:28]}",
                            callback_data=(
                                f"a_welcome_delbtn_"
                                f"{row_index}_{button_index}"
                            ),
                        )
                    ])

                lines.append(
                    f"Row {row_index + 1}: "
                    + " | ".join(names)
                )

            kb.append([
                InlineKeyboardButton(
                    "➕ Add More",
                    callback_data="a_welcome_buttons",
                )
            ])
            kb.append([
                InlineKeyboardButton(
                    "⬅ Back",
                    callback_data="a_welcome_buttons",
                )
            ])

            await q.edit_message_text(
                "\n".join(lines),
                reply_markup=InlineKeyboardMarkup(kb),
            )
            return

        if a.startswith("a_welcome_delbtn_"):
            try:
                position=a.replace(
                    "a_welcome_delbtn_",
                    "",
                )
                row_index,button_index=[
                    int(value)
                    for value in position.split("_",1)
                ]

                s=await get_seller_settings(owner)
                rows=s.get("welcome_buttons") or []

                if row_index>=len(rows) or button_index>=len(rows[row_index]):
                    raise IndexError

                deleted_name=rows[row_index][button_index].get(
                    "text",
                    "Button",
                )

                del rows[row_index][button_index]

                if not rows[row_index]:
                    del rows[row_index]

                await set_seller_setting(
                    owner,
                    "welcome_buttons",
                    rows,
                )

                await q.edit_message_text(
                    f"✅ {deleted_name} button deleted.",
                    reply_markup=self.welcome_buttons_menu(),
                )
            except (ValueError,IndexError):
                await q.edit_message_text(
                    "❌ Button not found. Open Current Buttons again.",
                    reply_markup=self.welcome_buttons_menu(),
                )
            return
        if a=="a_welcome_remove_text": await set_seller_setting(owner,"welcome_message",""); await q.edit_message_text("✅ Welcome text removed.",reply_markup=self.welcome_text_menu(False)); return
        if a=="a_welcome_remove_media":
            await set_seller_setting(owner,"welcome_media_type",""); await set_seller_setting(owner,"welcome_media_file_id","")
            await q.edit_message_text("✅ Welcome media removed.",reply_markup=self.welcome_media_menu(False)); return
        if a=="a_welcome_remove_buttons": await set_seller_setting(owner,"welcome_buttons",[]); await q.edit_message_text("✅ Welcome keyboard removed.",reply_markup=self.welcome_buttons_menu(False)); return
        if a=="a_welcome_preview":
            s=await ensure_seller_defaults(owner,(await get_bot_by_data_owner_id(owner) or {}).get("bot_name","Subscription Bot"))
            try:
                await q.message.reply_text("👀 Preview — users will see the message below:")
                await self.send_welcome(q.message,context,s,q.from_user)
            except Exception as exc:
                logger.exception("Welcome preview failed for owner=%s",owner)
                await q.message.reply_text(f"❌ Preview failed: {str(exc)[:300]}",reply_markup=self.welcome_menu())
            return
        if a=="a_pg_home":
            cfg=await get_gateway_config("seller",owner,decrypt=True)
            gateways=cfg.get("gateways") or {}
            rz=gateways.get("razorpay") or {}
            cf=gateways.get("cashfree") or {}
            lines=[
                "🌐 Automatic Payment Gateways",
                "",
                f"{'✅' if rz.get('enabled') else '❌'} Razorpay: {'Enabled' if rz.get('enabled') else 'Disabled'} | Credentials: {'Added' if rz.get('key_id') and rz.get('key_secret') else 'Not added'}",
                f"{'✅' if cf.get('enabled') else '❌'} Cashfree: {'Enabled' if cf.get('enabled') else 'Disabled'} | Credentials: {'Added' if cf.get('client_id') and cf.get('client_secret') else 'Not added'}",
            ]
            rows=[]
            for gateway in ("razorpay","cashfree"):
                g=gateways.get(gateway,{})
                rows.append([InlineKeyboardButton(
                    f"{'✅' if g.get('enabled') else '❌'} {gateway.title()}",
                    callback_data=f"a_pg_view_{gateway}",
                )])
            rows += [
                [InlineKeyboardButton("📜 Gateway History",callback_data="a_pg_history")],
                [InlineKeyboardButton("⬅ Back",callback_data="a_payment")],
            ]
            await q.edit_message_text("\n".join(lines),reply_markup=InlineKeyboardMarkup(rows)); return
        if a.startswith("a_pg_view_"):
            gateway=a.replace("a_pg_view_",""); cfg=await get_gateway_config("seller",owner,decrypt=True); g=(cfg.get("gateways") or {}).get(gateway,{})
            if gateway=="razorpay":
                await q.edit_message_text(
                    _seller_razorpay_text(g),
                    reply_markup=_seller_razorpay_keyboard(bool(g.get("enabled"))),
                ); return
            details=(
                f"Client ID: {'Added' if g.get('client_id') else 'Not added'}\n"
                f"Client Secret: {'Added' if g.get('client_secret') else 'Not added'}"
            )
            await q.edit_message_text(
                f"💳 Cashfree\n\nStatus: {'Enabled ✅' if g.get('enabled') else 'Disabled ❌'}\n{details}",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("⛔ Disable" if g.get('enabled') else "✅ Enable",callback_data="a_pg_toggle_cashfree")],
                    [InlineKeyboardButton("🔑 Set / Replace Credentials",callback_data="a_pg_creds_cashfree")],
                    [InlineKeyboardButton("✅ Test Connection",callback_data="a_pg_testconn_cashfree")],
                    [InlineKeyboardButton("⬅ Back",callback_data="a_pg_home")],
                ]),
            ); return
        if a.startswith("a_pg_toggle_"):
            gateway=a.replace("a_pg_toggle_",""); cfg=await get_gateway_config("seller",owner,decrypt=True); g=(cfg.get("gateways") or {}).get(gateway,{})
            try:
                await save_gateway_config("seller",owner,gateway,{"enabled":not bool(g.get("enabled")),"mode":"live"})
            except Exception as exc:
                await q.answer(str(exc),show_alert=True); return
            cfg=await get_gateway_config("seller",owner,decrypt=True); g=(cfg.get("gateways") or {}).get(gateway,{})
            if gateway=="razorpay":
                await q.edit_message_text(_seller_razorpay_text(g),reply_markup=_seller_razorpay_keyboard(bool(g.get("enabled")))); return
            details=f"Client ID: {'Added' if g.get('client_id') else 'Not added'}\nClient Secret: {'Added' if g.get('client_secret') else 'Not added'}"
            await q.edit_message_text(
                f"💳 Cashfree\n\nStatus: {'Enabled ✅' if g.get('enabled') else 'Disabled ❌'}\n{details}",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("⛔ Disable" if g.get('enabled') else "✅ Enable",callback_data="a_pg_toggle_cashfree")],
                    [InlineKeyboardButton("🔑 Set / Replace Credentials",callback_data="a_pg_creds_cashfree")],
                    [InlineKeyboardButton("✅ Test Connection",callback_data="a_pg_testconn_cashfree")],
                    [InlineKeyboardButton("⬅ Back",callback_data="a_pg_home")],
                ]),
            ); return

        if a=="a_pg_webhook_secret":
            context.user_data.clear(); context.user_data["wait_pg_webhook_secret"]=True
            await q.edit_message_text(
                "🔐 Set Webhook Secret\n\nSend the same Webhook Secret that you created in Razorpay Dashboard.\n\nRazorpay Key Secret and Webhook Secret are different.",
                reply_markup=self.back("a_pg_view_razorpay"),
            ); return

        if a=="a_pg_webhook_setup":
            # Keep this page plain-text. Telegram Markdown parsing can reject a
            # generated URL containing special characters, making the button
            # appear to do nothing.
            try:
                cfg=await get_gateway_config("seller",owner,decrypt=True)
                g=(cfg.get("gateways") or {}).get("razorpay",{})
                await q.edit_message_text(
                    _seller_webhook_setup_text(owner,g),
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🧪 Test Webhook",callback_data="a_pg_test_webhook")],
                        [InlineKeyboardButton("📖 Setup Guide",callback_data="a_pg_webhook_guide")],
                        [InlineKeyboardButton("⬅ Back",callback_data="a_pg_view_razorpay")],
                    ]),
                )
            except Exception as exc:
                logger.exception("Seller Razorpay webhook setup page failed for owner=%s", owner)
                await q.answer("Webhook Setup could not open. Please try again.", show_alert=True)
            return

        if a=="a_pg_webhook_guide":
            links=await get_official_links(); rows=[]
            if links.get("support"):
                rows.append([InlineKeyboardButton("💬 Contact Support",url=links["support"])])
            rows.append([InlineKeyboardButton("⬅ Back",callback_data="a_pg_webhook_setup")])
            await q.edit_message_text(_seller_webhook_guide_text(),reply_markup=InlineKeyboardMarkup(rows)); return

        if a=="a_pg_test_webhook":
            cfg=await get_gateway_config("seller",owner,decrypt=True); g=(cfg.get("gateways") or {}).get("razorpay",{})
            received=g.get("last_webhook_received_at")
            if received:
                when=received.strftime("%Y-%m-%d %H:%M UTC") if isinstance(received,datetime) else str(received)
                text=f"✅ Test Webhook Received\n\nA valid Razorpay webhook signature was received successfully.\nLast received: {when}"
            else:
                text="🧪 Razorpay Webhook Test\n\nNo valid webhook has been received yet.\n\nSend a test webhook from Razorpay Dashboard or complete a test payment, then tap Check Again."
            await q.edit_message_text(text,reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Check Again",callback_data="a_pg_test_webhook")],
                [InlineKeyboardButton("📖 Setup Guide",callback_data="a_pg_webhook_guide")],
                [InlineKeyboardButton("⬅ Back",callback_data="a_pg_webhook_setup")],
            ])); return

        if a.startswith("a_pg_testconn_"):
            gateway=a.replace("a_pg_testconn_","")
            try:
                await test_gateway_connection("seller",owner,gateway)
                await q.edit_message_text(
                    f"✅ {gateway.title()} connection successful.\n\nAPI access verified.",
                    reply_markup=self.back(f"a_pg_view_{gateway}"),
                )
            except GatewayError as exc:
                await q.edit_message_text(
                    f"❌ {gateway.title()} connection failed.\n\n{exc}",
                    reply_markup=self.back(f"a_pg_view_{gateway}"),
                )
            return
        if a.startswith("a_pg_creds_"):
            gateway=a.replace("a_pg_creds_",""); context.user_data.clear(); context.user_data["wait_pg_credentials"]=gateway
            help_text={"razorpay":"KEY_ID | KEY_SECRET","cashfree":"CLIENT_ID | CLIENT_SECRET"}[gateway]
            await q.edit_message_text(f"Send credentials in one message:\n{help_text}",reply_markup=self.back(f"a_pg_view_{gateway}")); return
        if a=="a_pg_history":
            items=await gateway_history("seller",owner,25); text="📜 Gateway History\n\n"+"\n".join(f"• {x.get('gateway','-').title()} ₹{x.get('amount',0):g} — {x.get('status')}" for x in items)
            await q.edit_message_text(text if items else "📜 No gateway payments yet.",reply_markup=self.back("a_pg_home")); return


        if a=="a_live_support":
            support=await get_live_support_settings(owner)
            blocked=await count_support_blocks(owner)
            await q.edit_message_text(
                self.live_support_text(support,blocked),
                reply_markup=self.live_support_menu(support),
            ); return
        if a=="a_live_support_toggle":
            support=await get_live_support_settings(owner)
            updated=await update_live_support_settings(owner,enabled=not bool(support.get("enabled")))
            blocked=await count_support_blocks(owner)
            await q.edit_message_text(
                self.live_support_text(updated,blocked),
                reply_markup=self.live_support_menu(updated),
            ); return
        if a in {"a_live_support_mode_private","a_live_support_mode_topic"}:
            mode="private" if a.endswith("private") else "topic"
            updated=await update_live_support_settings(owner,mode=mode)
            blocked=await count_support_blocks(owner)
            await q.edit_message_text(
                self.live_support_text(updated,blocked),
                reply_markup=self.live_support_menu(updated),
            ); return
        if a=="a_live_support_group_info":
            support=await get_live_support_settings(owner)
            await q.edit_message_text(
                "📌 Support Group\n\n"
                f"Name: {support.get('support_group_title') or 'Not connected'}\n"
                f"Chat ID: {support.get('support_group_id') or '-'}\n\n"
                "Group badalne ke liye naye forum group me /connectsupport bhejo.",
                reply_markup=self.back("a_live_support"),
            ); return
        if a=="a_live_support_blocks":
            blocked=await count_support_blocks(owner)
            await q.edit_message_text(
                f"🚫 Support-blocked users: {blocked}\n\n"
                "User ke support topic ke first details message se Block/Unblock kiya ja sakta hai.",
                reply_markup=self.back("a_live_support"),
            ); return
        if a=="a_support_auto_replies":
            items=await list_support_auto_replies(owner)
            await q.edit_message_text(
                "🤖 Live Support Auto Reply\n\nSet a keyword, then configure its text, media and URL buttons. When a user message contains that keyword, the saved reply is sent automatically.",
                reply_markup=self.support_auto_replies_menu(items),
            ); return
        if a=="a_support_ar_add":
            context.user_data.clear(); context.user_data["wait_support_ar_keyword"]=True
            await q.edit_message_text(
                "🔑 Send the keyword or phrase for this auto reply.\n\nExample: payment",
                reply_markup=self.back("a_support_auto_replies"),
            ); return
        if a.startswith("a_support_ar_view_"):
            keyword=a.replace("a_support_ar_view_","")
            item=await get_support_auto_reply(owner,keyword)
            if not item:
                await q.edit_message_text("❌ Auto reply not found",reply_markup=self.back("a_support_auto_replies")); return
            count=sum(len(row) for row in (item.get("buttons") or []))
            await q.edit_message_text(
                f"🤖 Auto Reply\n\n🔑 Keyword: {keyword}\n📄 Text: {'✅' if item.get('text') else '❌'}\n🖼 Media: {'✅' if item.get('media_file_id') else '❌'}\n🔗 URL Buttons: {count}",
                reply_markup=self.support_auto_reply_edit_menu(keyword),
            ); return
        if a.startswith("a_support_ar_text_"):
            keyword=a.replace("a_support_ar_text_","")
            item=await get_support_auto_reply(owner,keyword) or {}
            context.user_data.clear(); context.user_data["wait_support_ar_text"]=keyword
            await q.edit_message_text(
                "📄 Send the auto-reply text.\n\nHTML and variables are supported: {NAME} {ID} {USERNAME} {PLAN} {EXPIRY}",
                reply_markup=self.support_auto_reply_text_menu(keyword,bool(item.get("text"))),
            ); return
        if a.startswith("a_support_ar_media_"):
            keyword=a.replace("a_support_ar_media_","")
            item=await get_support_auto_reply(owner,keyword) or {}
            context.user_data.clear(); context.user_data["wait_support_ar_media"]=keyword
            await q.edit_message_text(
                "🖼 Send a photo, video, GIF or document.",
                reply_markup=self.support_auto_reply_media_menu(keyword,bool(item.get("media_file_id"))),
            ); return
        if a.startswith("a_support_ar_buttons_"):
            keyword=a.replace("a_support_ar_buttons_","")
            item=await get_support_auto_reply(owner,keyword) or {}
            context.user_data.clear(); context.user_data["wait_support_ar_buttons"]=keyword
            await q.edit_message_text(
                url_buttons_header(),
                reply_markup=self.support_auto_reply_buttons_menu(keyword,bool(item.get("buttons"))),
            ); return
        if a.startswith("a_support_ar_rmtext_"):
            keyword=a.replace("a_support_ar_rmtext_",""); await save_support_auto_reply(owner,keyword,text="")
            await q.edit_message_text("✅ Text removed",reply_markup=self.support_auto_reply_text_menu(keyword,False)); return
        if a.startswith("a_support_ar_rmmedia_"):
            keyword=a.replace("a_support_ar_rmmedia_",""); await save_support_auto_reply(owner,keyword,media_type="",media_file_id="")
            await q.edit_message_text("✅ Media removed",reply_markup=self.support_auto_reply_media_menu(keyword,False)); return
        if a.startswith("a_support_ar_rmbuttons_"):
            keyword=a.replace("a_support_ar_rmbuttons_",""); await save_support_auto_reply(owner,keyword,buttons=[])
            await q.edit_message_text("✅ Keyboard removed",reply_markup=self.support_auto_reply_buttons_menu(keyword,False)); return
        if a.startswith("a_support_ar_delete_"):
            keyword=a.replace("a_support_ar_delete_",""); await delete_support_auto_reply(owner,keyword)
            await q.edit_message_text("✅ Auto reply deleted",reply_markup=self.support_auto_replies_menu(await list_support_auto_replies(owner))); return
        if a.startswith("a_support_ar_preview_"):
            keyword=a.replace("a_support_ar_preview_",""); item=await get_support_auto_reply(owner,keyword)
            if item:
                await self.send_support_template(context,owner,q.from_user.id,item,q.from_user)
            await q.answer("Preview sent",show_alert=True); return

        if a=="a_support_templates":
            templates=await list_support_templates(owner)
            text="⚡ Live Support Reply Templates\n\nTopic/private support me saved command bhejo, jaise /payment. Bot saved text, media aur buttons user ko reply ke roop me bhejega.\n\nVariables: {NAME} {ID} {USERNAME} {PLAN} {EXPIRY}"
            await q.edit_message_text(text,reply_markup=self.support_templates_menu(templates)); return
        if a=="a_support_tpl_add":
            context.user_data.clear(); context.user_data["wait_support_tpl_command"]=True
            await q.edit_message_text("Command name bhejo. Example: payment\n\nSlash mat lagao. Sirf letters, numbers aur underscore.",reply_markup=self.back("a_support_templates")); return
        if a.startswith("a_support_tpl_view_"):
            command=a.replace("a_support_tpl_view_","")
            tpl=await get_support_template(owner,command)
            if not tpl:
                await q.edit_message_text("❌ Template not found",reply_markup=self.back("a_support_templates")); return
            count=sum(len(row) for row in (tpl.get("buttons") or []))
            auto_delete=_format_auto_delete(_template_auto_delete_seconds(tpl))
            await q.edit_message_text(f"⚡ /{command}\n\n📝 Text: {'✅' if tpl.get('text') else '❌'}\n🖼 Media: {'✅' if tpl.get('media_file_id') else '❌'}\n🔗 Buttons: {count}\n⏱ Auto Remove: {auto_delete}",reply_markup=self.support_template_edit_menu(command)); return
        if a.startswith("a_support_tpl_text_"):
            command=a.replace("a_support_tpl_text_","")
            tpl=await get_support_template(owner,command) or {}
            context.user_data.clear(); context.user_data["wait_support_tpl_text"]=command
            await q.edit_message_text(
                "📄 Send the template reply text.\n\nHTML and variables are supported: {NAME} {ID} {USERNAME} {PLAN} {EXPIRY}",
                reply_markup=self.support_template_text_menu(command,bool(tpl.get("text"))),
            ); return
        if a.startswith("a_support_tpl_media_"):
            command=a.replace("a_support_tpl_media_","")
            tpl=await get_support_template(owner,command) or {}
            context.user_data.clear(); context.user_data["wait_support_tpl_media"]=command
            await q.edit_message_text(
                "🖼 Send a photo, video, GIF or document.",
                reply_markup=self.support_template_media_menu(command,bool(tpl.get("media_file_id"))),
            ); return
        if a.startswith("a_support_tpl_buttons_"):
            command=a.replace("a_support_tpl_buttons_","")
            tpl=await get_support_template(owner,command) or {}
            context.user_data.clear(); context.user_data["wait_support_tpl_buttons"]=command
            await q.edit_message_text(
                url_buttons_header(),
                reply_markup=self.support_template_buttons_menu(command,bool(tpl.get("buttons"))),
            ); return
        if a.startswith("a_support_tpl_autodel_"):
            command=a.replace("a_support_tpl_autodel_","")
            tpl=await get_support_template(owner,command)
            if not tpl:
                await q.edit_message_text("❌ Template not found",reply_markup=self.back("a_support_templates")); return
            current=_template_auto_delete_seconds(tpl)
            await q.edit_message_text(
                f"⏱ Template Auto Remove — /{command}\n\nCurrent: {_format_auto_delete(current)}\n\nBot ka template reply selected time ke baad automatically remove hoga.",
                reply_markup=self.support_template_auto_delete_menu(command,current),
            ); return
        if a.startswith("a_tpl_ad_custom_"):
            command=a.replace("a_tpl_ad_custom_","")
            context.user_data.clear(); context.user_data["wait_support_tpl_auto_delete"]=command
            await q.edit_message_text(
                "⌨️ Custom auto-remove duration bhejo.\n\nExamples:\n30s = 30 seconds\n2m = 2 minutes\n1h = 1 hour\n6h = 6 hours\n1d = 1 day\noff = disable\n\nMaximum: 7 days",
                reply_markup=self.back(f"a_support_tpl_autodel_{command}"),
            ); return
        if a.startswith("a_tpl_ad_"):
            payload=a.replace("a_tpl_ad_", "", 1)
            seconds_text, command=payload.split("_",1)
            seconds=int(seconds_text)
            await save_support_template(owner,command,auto_delete_seconds=seconds)
            await q.edit_message_text(
                f"✅ Template Auto Remove updated\n\n/{command}: {_format_auto_delete(seconds)}",
                reply_markup=self.support_template_auto_delete_menu(command,seconds),
            ); return
        if a.startswith("a_support_tpl_rmtext_"):
            command=a.replace("a_support_tpl_rmtext_",""); await save_support_template(owner,command,text="")
            await q.edit_message_text("✅ Text removed",reply_markup=self.support_template_text_menu(command,False)); return
        if a.startswith("a_support_tpl_rmmedia_"):
            command=a.replace("a_support_tpl_rmmedia_",""); await save_support_template(owner,command,media_type="",media_file_id="")
            await q.edit_message_text("✅ Media removed",reply_markup=self.support_template_media_menu(command,False)); return
        if a.startswith("a_support_tpl_rmbuttons_"):
            command=a.replace("a_support_tpl_rmbuttons_",""); await save_support_template(owner,command,buttons=[])
            await q.edit_message_text("✅ Keyboard removed",reply_markup=self.support_template_buttons_menu(command,False)); return
        if a.startswith("a_support_tpl_delete_"):
            command=a.replace("a_support_tpl_delete_",""); await delete_support_template(owner,command)
            await q.edit_message_text(f"✅ /{command} deleted",reply_markup=self.support_templates_menu(await list_support_templates(owner))); return
        if a.startswith("a_support_tpl_preview_"):
            command=a.replace("a_support_tpl_preview_",""); tpl=await get_support_template(owner,command)
            await self.send_support_template(context,owner,q.from_user.id,tpl,q.from_user)
            await q.answer("Preview sent",show_alert=True); return

        if a.startswith("a_tz_"):
            key = a.replace("a_tz_", "", 1)
            if key == "manual":
                context.user_data.clear()
                context.user_data["wait_timezone"] = True
                settings = await get_seller_settings(owner)
                await q.edit_message_text(
                    timezone_guide(settings.get("timezone") or "Asia/Kolkata")
                    + "\n\nSend the timezone name now.",
                    reply_markup=self.back("a_settings"),
                )
                return
            timezone_name = timezone_from_key(key)
            if not timezone_name:
                await q.answer("Invalid timezone selection.", show_alert=True)
                return
            await set_seller_setting(owner, "timezone", timezone_name)
            context.user_data.clear()
            await q.edit_message_text(
                f"✅ Timezone updated!\n\nTimezone: {timezone_name}",
                reply_markup=self.settings_menu(),
            )
            return

        if a=="a_payment":
            settings=await get_seller_settings(owner)
            gateway_cfg=await get_gateway_config("seller",owner,decrypt=True)
            gateways=gateway_cfg.get("gateways") or {}
            rz=gateways.get("razorpay") or {}
            cf=gateways.get("cashfree") or {}
            manual_enabled=bool(gateway_cfg.get("manual_enabled",True))
            await q.edit_message_text(
                "💳 Payment Settings\n\n"
                f"{'✅' if rz.get('enabled') else '❌'} Razorpay: {'Enabled' if rz.get('enabled') else 'Disabled'} | Credentials: {'Added' if rz.get('key_id') and rz.get('key_secret') else 'Not added'}\n"
                f"{'✅' if cf.get('enabled') else '❌'} Cashfree: {'Enabled' if cf.get('enabled') else 'Disabled'} | Credentials: {'Added' if cf.get('client_id') and cf.get('client_secret') else 'Not added'}\n"
                f"{'✅' if manual_enabled else '❌'} Manual Payment: {'Enabled' if manual_enabled else 'Disabled'}\n\n"
                f"UPI ID: {settings.get('upi_id') or 'Not added'}\n"
                f"UPI Name: {settings.get('upi_name') or 'Not added'}\n"
                f"QR Code: {'Added ✅' if settings.get('upi_qr_file_id') else 'Not added ❌'}",
                reply_markup=self.payment_menu(),
            ); return
        if a=="a_manual_payment":
            settings=await get_seller_settings(owner)
            gateway_cfg=await get_gateway_config("seller",owner,decrypt=True)
            manual_enabled=bool(gateway_cfg.get("manual_enabled",True))
            await q.edit_message_text(
                "💵 Manual Payment\n\n"
                f"UPI ID: {settings.get('upi_id') or 'Not added'}\n"
                f"UPI Name: {settings.get('upi_name') or 'Not added'}\n"
                f"QR Code: {'Added ✅' if settings.get('upi_qr_file_id') else 'Not added ❌'}",
                reply_markup=self.manual_payment_menu(manual_enabled),
            ); return
        if a=="a_manual_toggle":
            gateway_cfg=await get_gateway_config("seller",owner,decrypt=True)
            await set_gateway_preferences("seller",owner,manual_enabled=not gateway_cfg.get("manual_enabled",True))
            settings=await get_seller_settings(owner)
            gateway_cfg=await get_gateway_config("seller",owner,decrypt=True)
            manual_enabled=bool(gateway_cfg.get("manual_enabled",True))
            await q.edit_message_text(
                "💵 Manual Payment\n\n"
                f"UPI ID: {settings.get('upi_id') or 'Not added'}\n"
                f"UPI Name: {settings.get('upi_name') or 'Not added'}\n"
                f"QR Code: {'Added ✅' if settings.get('upi_qr_file_id') else 'Not added ❌'}",
                reply_markup=self.manual_payment_menu(manual_enabled),
            ); return
        if a=="a_remove_qr":
            await set_seller_setting(owner,"upi_qr_file_id","")
            settings=await get_seller_settings(owner)
            gateway_cfg=await get_gateway_config("seller",owner,decrypt=True)
            manual_enabled=bool(gateway_cfg.get("manual_enabled",True))
            await q.edit_message_text(
                "💵 Manual Payment\n\n"
                f"UPI ID: {settings.get('upi_id') or 'Not added'}\n"
                f"UPI Name: {settings.get('upi_name') or 'Not added'}\n"
                "QR Code: Not added ❌",
                reply_markup=self.manual_payment_menu(manual_enabled),
            ); return
        if a=="a_payment_preview":
            settings=await get_seller_settings(owner)
            preview=(
                "💳 Payment Details\n\n"
                f"UPI ID: {settings.get('upi_id') or 'Not Set'}\n"
                f"UPI Name: {settings.get('upi_name') or 'Not Set'}\n"
                f"QR Code: {'Added' if settings.get('upi_qr_file_id') else 'Not Added'}"
            )
            preview_kb=self.back("a_manual_payment")
            if settings.get("upi_qr_file_id"):
                await q.message.reply_photo(settings["upi_qr_file_id"],caption=preview,reply_markup=preview_kb)
            else:
                await q.edit_message_text(preview,reply_markup=preview_kb)
            return
        state={"a_set_upi_id":("wait_upi_id","Send UPI ID","a_manual_payment"),"a_set_upi_name":("wait_upi_name","Send UPI Name","a_manual_payment"),"a_set_bot_name":("wait_bot_name","Send Bot Name","a_settings"),"a_set_support":("wait_support","Send Support Username","a_settings"),"a_set_currency":("wait_currency","Send Currency","a_settings"),"a_set_timezone":("wait_timezone","__TIMEZONE_PICKER__","a_settings"),"a_set_reminder":("wait_reminder","Send Reminder Days","a_settings"),"a_set_referral_days":("wait_referral_days","Send free reward days per successful referral","a_settings")}
        if a in state:
            key,msg,back=state[a]
            context.user_data.clear()
            if a == "a_set_timezone":
                settings = await get_seller_settings(owner)
                await q.edit_message_text(
                    timezone_guide(settings.get("timezone") or "Asia/Kolkata"),
                    reply_markup=timezone_keyboard("a_tz_", "a_settings"),
                )
            else:
                context.user_data[key]=True
                await q.edit_message_text(msg,reply_markup=self.back(back))
            return
        if a=="a_set_qr": context.user_data.clear(); context.user_data["wait_qr"]=True; await q.edit_message_text("Send QR image",reply_markup=self.back("a_manual_payment")); return
        if a=="a_settings":
            s=await get_seller_settings(owner); await q.edit_message_text(f"⚙ Bot Settings\n\nBot Name: {s.get('bot_name')}\nSupport: {s.get('support_username') or 'Not Set'}\nCurrency: {s.get('currency')}\nTimezone: {s.get('timezone')}\nReminder: {s.get('reminder_days')}",reply_markup=self.settings_menu()); return
        if a=="a_pending":
            ps=await pending_payments(owner); lines=["📨 Pending Payments\n"]; kb=[]
            for p in ps:
                lines.append(f"• {p['user_id']} | ₹{p['amount']:g} | {p['plan']}")
                kb.append([InlineKeyboardButton(f"View {p['user_id']}",callback_data=f"a_pay_view_{p['payment_id']}")])
            kb.append([InlineKeyboardButton("⬅ Back",callback_data="a_home")]); await q.edit_message_text("\n".join(lines) if ps else "📨 No pending payments",reply_markup=InlineKeyboardMarkup(kb)); return
        if a.startswith("a_pay_view_"):
            p=await get_payment(owner,a.replace("a_pay_view_",""));
            if not p: await q.edit_message_text("Not found",reply_markup=self.admin_menu()); return
            kb=InlineKeyboardMarkup([[InlineKeyboardButton("✅ Approve",callback_data=f"a_pay_ok_{p['payment_id']}"),InlineKeyboardButton("❌ Reject",callback_data=f"a_pay_no_{p['payment_id']}")],[InlineKeyboardButton("⬅ Back",callback_data="a_pending")]])
            caption=await self.payment_details_caption(
                owner,
                p,
                status=p.get("status","pending"),
            )
            await q.message.reply_photo(
                p["screenshot_file_id"],
                caption=caption,
                reply_markup=kb,
            )
            return
        if a.startswith("a_pay_ok_") or a.startswith("a_pay_no_"):
            approve=a.startswith("a_pay_ok_")
            pid=a.replace(
                "a_pay_ok_" if approve else "a_pay_no_",
                "",
                1,
            )
            p=await get_payment(owner,pid)

            if not p:
                await q.answer(
                    "Payment not found",
                    show_alert=True,
                )
                return

            current_status=p.get("status","pending")

            if current_status in {"approved","rejected"}:
                final_caption=await self.payment_details_caption(
                    owner,
                    p,
                    status=current_status,
                    processed_by=p.get("admin_id"),
                )
                try:
                    await q.edit_message_caption(
                        caption=final_caption,
                        reply_markup=None,
                    )
                except BadRequest:
                    pass
                await q.answer(
                    f"Already {current_status}",
                    show_alert=True,
                )
                return

            if not approve:
                changed=await set_payment_status(
                    owner,
                    pid,
                    "rejected",
                    owner,
                )
                if not changed:
                    await q.answer(
                        "Payment is already being processed",
                        show_alert=True,
                    )
                    return

                await context.bot.send_message(
                    p["user_id"],
                    "❌ Payment rejected",
                )
                rejected_caption=await self.payment_details_caption(
                    owner,
                    p,
                    status="rejected",
                    processed_by=owner,
                )
                await q.edit_message_caption(
                    caption=rejected_caption,
                    reply_markup=None,
                )
                return

            claimed=await claim_payment_for_processing(
                owner,
                pid,
                owner,
            )
            if not claimed:
                latest=await get_payment(owner,pid)
                latest_status=(latest or {}).get("status","unknown")
                await q.answer(
                    f"Payment status: {latest_status}",
                    show_alert=True,
                )
                return

            try:
                plan_cfg,_=await effective_plan(owner)
                active_now=await active_subscriptions(owner)
                already_active=any(int(x.get("user_id"))==int(p["user_id"]) for x in active_now)
                sub_limit=int(plan_cfg.get("active_subscriber_limit",25))
                if not already_active and sub_limit>=0 and len(active_now)>=sub_limit:
                    await release_processing_payment(owner,pid,"seller subscriber limit reached")
                    await q.answer("Seller plan limit reached",show_alert=True)
                    await context.bot.send_message(owner, await plan_limit_warning(owner), reply_markup=self.limit_keyboard("a_pending"))
                    return
                previous_sub=await get_subscription(owner,p["user_id"])
                now=datetime.now(timezone.utc)
                previous_expiry=(previous_sub or {}).get("expiry_date")
                if previous_expiry and previous_expiry.tzinfo is None:
                    previous_expiry=previous_expiry.replace(tzinfo=timezone.utc)
                was_already_active=bool(
                    previous_sub
                    and previous_sub.get("active")
                    and previous_expiry
                    and previous_expiry>now
                )

                manual_fulfillment=await fulfill_subscription_payment(
                    owner,
                    p["user_id"],
                    f"manual:{owner}:{pid}",
                    p["plan"],
                    p["duration_minutes"],
                    amount=p.get("amount"),
                    duration_text=p.get("duration_text"),
                )
                expiry=manual_fulfillment.get("expiry_date")

                referral=await mark_referral_rewarded(
                    owner,
                    p["user_id"],
                    payment_id=pid,
                )
                if referral:
                    settings=await get_seller_settings(owner)
                    reward_days=int(
                        settings.get("referral_reward_days",7) or 0
                    )
                    referrer_id=int(referral["referrer_user_id"])

                    try:
                        if reward_days>0:
                            await activate_subscription(
                                owner,
                                referrer_id,
                                "Referral Reward",
                                reward_days*1440,
                                amount=0,
                                duration_text=f"{reward_days}d",
                            )

                        finalized_reward=await finalize_referral_reward(
                            owner,
                            p["user_id"],
                            payment_id=pid,
                        )
                        if not finalized_reward:
                            raise RuntimeError(
                                "Referral reward finalization was not applied"
                            )

                        if reward_days>0:
                            try:
                                await context.bot.send_message(
                                    referrer_id,
                                    "🎉 Referral Reward Added!\n"
                                    f"You received {reward_days} free day(s).",
                                )
                            except Exception:
                                logger.exception(
                                    "Referral reward notification failed "
                                    "owner=%s referrer=%s payment=%s",
                                    owner,
                                    referrer_id,
                                    pid,
                                )
                    except Exception as exc:
                        await release_referral_reward(
                            owner,
                            p["user_id"],
                            str(exc),
                            payment_id=pid,
                        )
                        logger.exception(
                            "Referral reward processing failed "
                            "owner=%s referred=%s payment=%s",
                            owner,
                            p["user_id"],
                            pid,
                        )

                links=[]
                for ch in await get_channels(owner):
                    try:
                        inv=await context.bot.create_chat_invite_link(
                            ch["chat_id"],
                            member_limit=1,
                        )
                        await save_invite(owner, p["user_id"], ch["chat_id"], inv.invite_link)
                        links.append(
                            f"{ch.get('title')}: {inv.invite_link}"
                        )
                    except Exception as exc:
                        links.append(
                            f"{ch.get('title')}: invite failed ({exc})"
                        )

                finalized=await finalize_processed_payment(
                    owner,
                    pid,
                    "approved",
                    owner,
                )
                if not finalized:
                    raise RuntimeError(
                        "Could not finalize payment status"
                    )

                expiry_text=self.format_dt(expiry)
                invoice=await create_invoice(owner,p["user_id"],p,(await get_seller_settings(owner)).get("bot_name","Seller"))
                await audit("child_payment_approved",owner,owner,{"payment_id":pid,"invoice_no":invoice["invoice_no"]})
                if was_already_active:
                    status_text=(
                        "ℹ️ Your subscription was already active.\n"
                        "Your new payment has been added to your existing subscription.\n\n"
                        f"📅 Previous Expiry: {self.format_dt(previous_expiry)}\n"
                        f"📅 New Expiry: {expiry_text}\n\n"
                        "🔗 A fresh private invite link has been generated for you."
                    )
                else:
                    status_text=(
                        f"📅 Expiry Date: {expiry_text}\n\n"
                        "🔗 Your fresh private invite link has been generated."
                    )

                await context.bot.send_message(
                    p["user_id"],
                    "✅ Payment approved manually\n"
                    "━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"📦 Purchased Plan: {p['plan']}\n"
                    f"💰 Amount: ₹{float(p.get('amount') or 0):g}\n"
                    f"🧾 Payment ID: {pid}\n"
                    f"⌛ Added Duration: {p.get('duration_text') or '-'}\n"
                    f"🧾 Receipt/Invoice: {invoice['invoice_no']}\n"
                    "━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"{status_text}\n\n"
                    "Join using your private invite link(s):\n\n"
                    + "\n\n".join(links),
                    disable_web_page_preview=True,
                )

                approved_caption=await self.payment_details_caption(
                    owner,
                    p,
                    status="approved",
                    processed_by=owner,
                )
                approved_caption+=(
                    "\n"
                    f"📅 New Expiry: {expiry_text}\n"
                    "➕ Remaining validity was preserved and "
                    "the new plan duration was added."
                )

                await q.edit_message_caption(
                    caption=approved_caption,
                    reply_markup=None,
                )

            except Exception as exc:
                logger.exception(
                    "Payment approval failed owner=%s payment=%s",
                    owner,
                    pid,
                )
                await release_processing_payment(
                    owner,
                    pid,
                    str(exc),
                )
                await q.answer(
                    "Approval failed. Payment is still pending; "
                    "you can press Approve again.",
                    show_alert=True,
                )
                try:
                    await q.edit_message_caption(
                        caption=(
                            await self.payment_details_caption(
                                owner,
                                p,
                                status="pending",
                            )
                            + "\n\n⚠️ Last approval attempt failed. "
                            "Payment was kept pending safely."
                        ),
                        reply_markup=InlineKeyboardMarkup([
                            [
                                InlineKeyboardButton(
                                    "✅ Approve",
                                    callback_data=f"a_pay_ok_{pid}",
                                ),
                                InlineKeyboardButton(
                                    "❌ Reject",
                                    callback_data=f"a_pay_no_{pid}",
                                ),
                            ]
                        ]),
                    )
                except Exception:
                    pass
            return

        if a=="a_history":
            ps=await payment_history(owner); text="📜 Payment History\n\n"+"\n".join(f"{'✅' if p['status']=='approved' else '❌'} {p['user_id']} ₹{p['amount']:g} {p['plan']}" for p in ps[:20]); await q.edit_message_text(text,reply_markup=self.back()); return
        if a=="a_broadcast_schedule":
            context.user_data.clear(); context.user_data["wait_scheduled_broadcast"]=True
            await q.edit_message_text("🗓 Send a message with first line in this format:\nYYYY-MM-DD HH:MM\n\nWrite the broadcast text after the first line. Time uses your configured timezone.",reply_markup=self.back()); return
        if a=="a_coupons":
            coupons=await list_coupons(owner)
            lines=["🎟 Coupon System\n", "Create: CODE | percent/fixed | VALUE | USAGE_LIMIT"]
            for cpn in coupons[:20]: lines.append(f"• {cpn['code']} — {cpn['value']:g} {cpn['discount_type']} — {cpn['used_count']}/{cpn['usage_limit']}")
            context.user_data.clear(); context.user_data["wait_coupon_create"]=True
            await q.edit_message_text("\n".join(lines),reply_markup=self.back()); return
        if a=="a_referral_unlock":
            settings=await get_seller_settings(owner)
            channels=await get_channels(owner)
            await q.edit_message_text(
                self.referral_unlock_text(settings),
                reply_markup=self.referral_unlock_menu(settings,channels),
            ); return
        if a=="a_referral_unlock_toggle":
            settings=await get_seller_settings(owner)
            new_value=not bool(settings.get("referral_unlock_enabled",False))
            if new_value and not settings.get("referral_unlock_target_chat_id"):
                await q.answer("Select a destination first.",show_alert=True); return
            await set_seller_setting(owner,"referral_unlock_enabled",new_value)
            settings=await get_seller_settings(owner)
            channels=await get_channels(owner)
            await q.edit_message_text(
                self.referral_unlock_text(settings),
                reply_markup=self.referral_unlock_menu(settings,channels),
            ); return
        if a=="a_referral_unlock_required":
            context.user_data.clear(); context.user_data["wait_referral_unlock_required"]=True
            await q.edit_message_text(
                "👥 Set Required Successful Referrals\n\n"
                "Send a whole number from 1 to 100.\n\n"
                "Example: 3\n\n"
                "Only successful referrals are counted. Opening or sharing the link alone does not increase progress.",
                reply_markup=self.back("a_referral_unlock"),
            ); return
        if a=="a_referral_unlock_count_mode":
            settings=await get_seller_settings(owner)
            current=settings.get("referral_unlock_count_mode","subscription")
            new_mode="start" if current != "start" else "subscription"
            await set_seller_setting(owner,"referral_unlock_count_mode",new_mode)
            settings=await get_seller_settings(owner)
            channels=await get_channels(owner)
            await q.edit_message_text(
                self.referral_unlock_text(settings),
                reply_markup=self.referral_unlock_menu(settings,channels),
            ); return
        if a=="a_referral_unlock_duration":
            context.user_data.clear(); context.user_data["wait_referral_unlock_duration"]=True
            await q.edit_message_text(
                "📅 Set Access Duration\n\n"
                "Send the number of days the unlocked group or channel access should remain active.\n\n"
                "Allowed range: 1 to 3650 days\n"
                "Example: 30",
                reply_markup=self.back("a_referral_unlock"),
            ); return
        if a=="a_referral_unlock_destination":
            channels=await get_channels(owner)
            if not channels:
                await q.edit_message_text(
                    "❌ No connected group or channel found.\n\nConnect a destination first from Channels / Groups, then return here.",
                    reply_markup=self.back("a_referral_unlock"),
                ); return
            await q.edit_message_text(
                "📢 Select Unlock Destination\n\n"
                "Choose the private group or channel whose invite link will be given after the user completes the referral target.\n\n"
                "The clone bot must be an administrator and must have permission to create invite links.",
                reply_markup=self.referral_unlock_channels_menu(channels),
            ); return
        if a.startswith("a_referral_unlock_chat_"):
            chat_id=int(a.replace("a_referral_unlock_chat_","",1))
            channels=await get_channels(owner)
            selected=next((item for item in channels if int(item.get("chat_id"))==chat_id),None)
            if not selected:
                await q.answer("Destination not found.",show_alert=True); return
            await set_seller_setting(owner,"referral_unlock_target_chat_id",chat_id)
            await set_seller_setting(owner,"referral_unlock_target_title",selected.get("title") or str(chat_id))
            settings=await get_seller_settings(owner)
            await q.edit_message_text(
                self.referral_unlock_text(settings),
                reply_markup=self.referral_unlock_menu(settings,channels),
            ); return

        if a=="a_seller_referral":
            data=await seller_referral_stats(owner)
            link=f"https://t.me/{MAIN_BOT_USERNAME}?start=refseller_{owner}"
            await q.edit_message_text(
                "🤝 Seller Referral Program\n\n"
                f"👥 Sellers joined: {data['total']}\n"
                f"🎁 Rewards received: {data['rewarded']}\n\n"
                "Share this link with new sellers:\n"
                f"{link}\n\n"
                "The owner controls reward days and reward plan from Owner Dashboard → Subscription Management.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("📤 Share Referral Link",url=f"https://t.me/share/url?url={link}")],
                    [InlineKeyboardButton("⬅ Back",callback_data="a_home")],
                ]),
                disable_web_page_preview=True,
            ); return
        if a=="a_help":
            await q.edit_message_text(
                "📚 Clone Bot Admin Help Center\n\n"
                "🚀 Quick Start\n"
                "1️⃣ Add subscription plans\n"
                "2️⃣ Connect channel/group\n"
                "3️⃣ Configure UPI/QR or gateway\n"
                "4️⃣ Edit and preview welcome message\n"
                "5️⃣ Test payment, approval and invite link\n\n"
                "🛠 Commands\n"
                "/start — Seller opens Admin Panel; users open Welcome Menu\n"
                "/admin — Open Admin Panel\n"
                "/help — Full user and seller guide\n"
                "/connectgroup — Connect subscription group\n"
                "/connectsupport — Connect Live Support forum group\n"
                "/version — Show deployed runtime version\n\n"
                "📦 Plans — Add, edit, enable, disable or delete plans\n"
                "📂 Channels / Groups — Connect chats and resend links\n"
                "💳 Payments — UPI/QR, gateways, pending proofs and history\n"
                "👥 Users — Give, extend, remove, ban or unban\n"
                "💬 Welcome Editor — Text, media, buttons and preview\n"
                "🎫 Live Support — Topics, templates and auto remove\n"
                "📢 Broadcast — Send now, schedule and retry failed\n"
                "🎟 Coupons — Create and manage discounts\n"
                "🤝 Referral — User and seller referral controls\n"
                "📊 Statistics — Users, payments, plans and revenue\n\n"
                "🧪 Troubleshooting\n"
                "• Group not connecting: make bot admin and use /connectgroup inside it\n"
                "• Invite not sent: enable Invite Users permission\n"
                "• Live Support not working: enable forum topics and reconnect\n"
                "• Payment issue: verify UPI/QR or gateway credentials\n"
                "• Bot not replying: check runtime status and logs",
                reply_markup=self.back("a_home"),
            ); return
        if a=="a_terms":
            parts=[]
            for key in ("terms","privacy","refund","support"):
                policy=await get_policy(key); parts.append(f"{key.title()}:\n{policy.get('text')}")
            await q.edit_message_text("📜 Terms & Policy\n\n"+"\n\n".join(parts),reply_markup=self.admin_menu()); return
        if a=="a_broadcast": context.user_data.clear(); context.user_data["wait_broadcast"]=True; await q.edit_message_text("📢 Send any one message to broadcast.\n\nSupported: text, photo with caption, video, document, audio, voice, GIF, sticker and forwarded messages.",reply_markup=self.back()); return
        if a=="a_staff":
            await q.edit_message_text(
                "👮 Staff Management\n\nPromote trusted people as Admin or Moderator for this clone bot.\n\nAdmin: broad management access\nModerator: users, pending payments and live support",
                reply_markup=self.staff_menu(),
            )
            return
        if a in {"a_staff_add_admin", "a_staff_add_moderator"}:
            context.user_data.clear()
            context.user_data["wait_staff_promote"] = "admin" if a.endswith("admin") else "moderator"
            await q.edit_message_text(
                "Send the Telegram User ID of the person you want to promote.\n\nThe person must start this clone bot once before using staff access.",
                reply_markup=self.back("a_staff"),
            )
            return
        if a=="a_staff_list":
            rows=await list_staff(owner)
            if not rows:
                await q.edit_message_text("📋 Staff List\n\nNo staff members added.", reply_markup=self.back("a_staff"))
                return
            kb=[]
            lines=["📋 Staff List\n"]
            for row in rows:
                uid=int(row["user_id"]); role_name=str(row.get("role","moderator")).title(); status=row.get("status","active")
                label=("@"+row.get("username")) if row.get("username") else (row.get("full_name") or str(uid))
                lines.append(f"• {label} — {role_name} — {status.title()}")
                kb.append([InlineKeyboardButton(f"{role_name}: {label}", callback_data=f"a_staff_view_{uid}")])
            kb.append([InlineKeyboardButton("⬅ Back", callback_data="a_staff")])
            await q.edit_message_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(kb))
            return
        if a.startswith("a_staff_view_"):
            uid=int(a.replace("a_staff_view_", "")); row=await active_staff(owner,uid)
            if not row:
                all_rows=await list_staff(owner); row=next((x for x in all_rows if int(x.get("user_id",0))==uid),None)
            if not row:
                await q.edit_message_text("❌ Staff member not found.", reply_markup=self.back("a_staff_list")); return
            label=("@"+row.get("username")) if row.get("username") else (row.get("full_name") or "Not available")
            text=(f"👮 Staff Details\n\nName: {label}\nUser ID: {uid}\nRole: {str(row.get('role','')).title()}\nStatus: {str(row.get('status','active')).title()}\nTotal Actions: {int(row.get('total_actions',0))}\nLast Action: {row.get('last_action') or 'No activity yet'}")
            await q.edit_message_text(text, reply_markup=self.staff_item_menu(uid,row.get("status")=="suspended"))
            return
        if a.startswith("a_staff_status_"):
            _,_,_,uid,status=a.split("_",4); await set_staff_status(owner,int(uid),status)
            await q.edit_message_text(f"✅ Staff status updated: {status.title()}", reply_markup=self.back("a_staff_list")); return
        if a.startswith("a_staff_remove_"):
            uid=int(a.replace("a_staff_remove_", "")); await remove_staff(owner,uid)
            await q.edit_message_text("✅ Staff member removed.", reply_markup=self.back("a_staff_list")); return

        if a=="a_users":
            context.user_data.clear()
            context.user_data["wait_user_search"]=True
            await q.edit_message_text(
                "👥 User Management\n\nSend User ID or @username to search.",
                reply_markup=self.back("a_home"),
            )
            return

        if a.startswith("a_user_view_"):
            await self.show_user_details(q,owner,int(a.replace("a_user_view_","")))
            return

        if a.startswith("a_user_give_"):
            await self.show_admin_plan_selector(
                q,owner,int(a.replace("a_user_give_","")),"give"
            )
            return

        if a.startswith("a_user_extend_"):
            await self.show_admin_plan_selector(
                q,owner,int(a.replace("a_user_extend_","")),"extend"
            )
            return

        if a.startswith("a_user_apply_"):
            parts=a.split("_",5)
            if len(parts)!=6:
                await q.edit_message_text("❌ Invalid action.")
                return

            mode=parts[3]
            user_id=int(parts[4])
            plan_id=parts[5]
            plan=await get_plan(owner,plan_id)

            if not plan:
                await q.edit_message_text(
                    "❌ Plan not found.",
                    reply_markup=self.back(f"a_user_view_{user_id}"),
                )
                return

            plan_cfg,_=await effective_plan(owner)
            active_now=await active_subscriptions(owner)
            already_active=any(int(x.get("user_id"))==user_id for x in active_now)
            sub_limit=int(plan_cfg.get("active_subscriber_limit",25))
            if not already_active and sub_limit>=0 and len(active_now)>=sub_limit:
                await q.edit_message_text(await plan_limit_warning(owner), reply_markup=self.limit_keyboard(f"a_user_view_{user_id}")); return
            await activate_subscription(
                owner,user_id,plan["name"],plan["duration_minutes"],
                amount=plan.get("price"),
                duration_text=plan.get("duration_text"),
            )

            delivery=await self.deliver_subscription_access(owner,user_id)
            try:
                await context.bot.send_message(
                    user_id,
                    "🎉 Subscription activated/extended by admin.\n"
                    f"Plan: {plan['name']}\n"
                    f"Duration added: {plan['duration_text']}\n\n"
                    f"New invite links sent: {delivery.get('sent',0)}\n"
                    f"Already joined: {delivery.get('already_member',0)}",
                )
            except Exception:
                pass

            await self.show_user_details(q,owner,user_id)
            return

        if a.startswith("a_user_remove_"):
            user_id=int(a.replace("a_user_remove_",""))
            await remove_subscription(owner,user_id)
            try:
                await context.bot.send_message(
                    user_id,
                    "❌ Your subscription was removed by admin.",
                )
            except Exception:
                pass
            await self.show_user_details(q,owner,user_id)
            return

        if a.startswith("a_user_ban_"):
            user_id=int(a.replace("a_user_ban_",""))
            context.user_data.clear()
            context.user_data["wait_user_ban_reason"]=user_id
            await q.edit_message_text(
                "🚫 Send ban reason.",
                reply_markup=self.back(f"a_user_view_{user_id}"),
            )
            return

        if a.startswith("a_user_unban_"):
            user_id=int(a.replace("a_user_unban_",""))
            await set_user_ban(owner,user_id,False,"")
            try:
                await context.bot.send_message(user_id,"✅ You have been unbanned.")
            except Exception:
                pass
            await self.show_user_details(q,owner,user_id)
            return

        if a=="a_stats":
            s=await stats(owner); await q.edit_message_text(f"📊 Statistics\n\nUsers: {s['users']}\nPlans: {s['plans']}\nChannels: {s['channels']}\nPending: {s['pending']}\nRevenue: ₹{s['revenue']:g}",reply_markup=self.admin_menu()); return

