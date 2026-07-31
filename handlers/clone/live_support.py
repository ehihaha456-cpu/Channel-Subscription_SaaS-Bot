"""Focused clone-bot feature mixin; behavior preserved from services.bot_manager."""

from handlers.common.clone_context import *


# One FIFO lock per seller/user pair. Telegram can dispatch several updates
# concurrently; without this lock rapid customer messages can overtake each
# other while the first support topic is being created.
_LIVE_SUPPORT_FIFO_LOCKS = {}


def _live_support_fifo_lock(owner_id: int, user_id: int):
    key = (int(owner_id), int(user_id))
    lock = _LIVE_SUPPORT_FIFO_LOCKS.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _LIVE_SUPPORT_FIFO_LOCKS[key] = lock
    return lock


class CloneLiveSupportMixin:
    @staticmethod
    def _is_closed_support_topic_error(exc):
        text = str(exc or "").lower()
        return any(marker in text for marker in (
            "topic_closed", "topic closed", "message thread is closed",
        ))

    @staticmethod
    def _is_missing_support_topic_error(exc):
        text = str(exc or "").lower()
        return any(marker in text for marker in (
            "message thread not found", "forum topic not found",
        ))

    @classmethod
    def _is_stale_support_topic_error(cls, exc):
        return cls._is_closed_support_topic_error(exc) or cls._is_missing_support_topic_error(exc)

    async def _reopen_support_topic(self, context, topic):
        """Reopen the same permanent topic; never create a second topic for a closed one."""
        try:
            await context.bot.reopen_forum_topic(
                chat_id=int(topic["support_group_id"]),
                message_thread_id=int(topic["message_thread_id"]),
            )
        except BadRequest as exc:
            text = str(exc or "").lower()
            # Already open is a successful state for our purpose.
            if not any(marker in text for marker in ("topic_not_modified", "not modified", "already open")):
                raise

    async def _send_support_message_direct(self, context, topic, message):
        """Send customer content directly into the existing forum topic.

        Telegram occasionally rejects copy_message for the first update after
        an idle period even though normal sends to that same thread work. Using
        the original file_id/content removes that dependency. The MongoDB
        delivery claim in route_live_support_message still guarantees that the
        same source update is completed only once.
        """
        common = {
            "chat_id": int(topic["support_group_id"]),
            "message_thread_id": int(topic["message_thread_id"]),
        }
        caption = message.caption or None

        if message.text:
            return await context.bot.send_message(
                text=message.text,
                entities=message.entities or None,
                **common,
            )
        if message.photo:
            return await context.bot.send_photo(
                photo=message.photo[-1].file_id,
                caption=caption,
                caption_entities=message.caption_entities or None,
                **common,
            )
        if message.video:
            return await context.bot.send_video(
                video=message.video.file_id,
                caption=caption,
                caption_entities=message.caption_entities or None,
                **common,
            )
        if message.animation:
            return await context.bot.send_animation(
                animation=message.animation.file_id,
                caption=caption,
                caption_entities=message.caption_entities or None,
                **common,
            )
        if message.document:
            return await context.bot.send_document(
                document=message.document.file_id,
                caption=caption,
                caption_entities=message.caption_entities or None,
                **common,
            )
        if message.audio:
            return await context.bot.send_audio(
                audio=message.audio.file_id,
                caption=caption,
                caption_entities=message.caption_entities or None,
                **common,
            )
        if message.voice:
            return await context.bot.send_voice(
                voice=message.voice.file_id,
                caption=caption,
                caption_entities=message.caption_entities or None,
                **common,
            )
        if message.video_note:
            return await context.bot.send_video_note(video_note=message.video_note.file_id, **common)
        if message.sticker:
            return await context.bot.send_sticker(sticker=message.sticker.file_id, **common)
        if message.contact:
            return await context.bot.send_contact(
                phone_number=message.contact.phone_number,
                first_name=message.contact.first_name,
                last_name=message.contact.last_name,
                vcard=message.contact.vcard,
                **common,
            )
        if message.location:
            kwargs = {
                "latitude": message.location.latitude,
                "longitude": message.location.longitude,
                **common,
            }
            if message.location.horizontal_accuracy is not None:
                kwargs["horizontal_accuracy"] = message.location.horizontal_accuracy
            if message.location.live_period is not None:
                kwargs["live_period"] = message.location.live_period
            if message.location.heading is not None:
                kwargs["heading"] = message.location.heading
            if message.location.proximity_alert_radius is not None:
                kwargs["proximity_alert_radius"] = message.location.proximity_alert_radius
            return await context.bot.send_location(**kwargs)
        if message.venue:
            return await context.bot.send_venue(
                latitude=message.venue.location.latitude,
                longitude=message.venue.location.longitude,
                title=message.venue.title,
                address=message.venue.address,
                foursquare_id=message.venue.foursquare_id,
                foursquare_type=message.venue.foursquare_type,
                google_place_id=message.venue.google_place_id,
                google_place_type=message.venue.google_place_type,
                **common,
            )
        if message.poll:
            return await context.bot.send_poll(
                question=message.poll.question,
                options=[option.text for option in message.poll.options],
                is_anonymous=message.poll.is_anonymous,
                allows_multiple_answers=message.poll.allows_multiple_answers,
                **common,
            )

        # Rare unsupported service/content types retain Telegram's native copy.
        return await context.bot.copy_message(
            from_chat_id=int(message.chat_id),
            message_id=int(message.message_id),
            **common,
        )

    async def _copy_to_support_topic_reliably(self, context, topic, message):
        """Deliver directly, refreshing/reopening the same topic when needed."""
        last_error = None
        reopened = False
        for attempt in range(10):
            try:
                return await self._send_support_message_direct(context, topic, message)
            except BadRequest as exc:
                last_error = exc
                if self._is_closed_support_topic_error(exc) and not reopened:
                    await self._reopen_support_topic(context, topic)
                    reopened = True
                elif self._is_missing_support_topic_error(exc):
                    # Let the caller reset only a genuinely missing mapping.
                    raise
                elif attempt >= 2:
                    raise
            except (TimedOut, NetworkError, RetryAfter) as exc:
                last_error = exc
            except TelegramError as exc:
                last_error = exc
                if attempt >= 2:
                    raise
            await asyncio.sleep(min(0.45 * (attempt + 1), 3.0))
        if last_error:
            raise last_error
        raise RuntimeError("Live support delivery failed")

    async def _ensure_support_topic_reliably(self, context, owner, user, support):
        """Wait for/create the permanent topic before forwarding the first message."""
        last_error=None
        for attempt in range(6):
            try:
                return await self.ensure_support_topic(context, owner, user, support)
            except (TimedOut, NetworkError, RetryAfter, RuntimeError) as exc:
                last_error=exc
                delay=float(getattr(exc,"retry_after",0) or (0.9*(attempt+1)))
                await asyncio.sleep(min(max(delay,0.5),4.0))
        if last_error:
            raise last_error
        raise RuntimeError("Support topic could not be prepared")

    async def route_live_support_message(self,update:Update,context:ContextTypes.DEFAULT_TYPE):
        message=update.effective_message
        user=update.effective_user
        chat=update.effective_chat
        if not message or not user or user.is_bot or not chat:
            return
        # Telegram Business-account updates belong to Business Automation and
        # must never be copied into Clone Bot Live Support.
        if getattr(update, "business_message", None) is not None or getattr(update, "business_connection", None) is not None:
            return
        owner=self.owner(context)
        support=await get_live_support_settings(owner)

        # Seller reply inside the connected topic group.
        # Restored working direct-delivery flow: no receipt claim/queue layer.
        if (
            support.get("enabled") and support.get("mode")=="topic"
            and support.get("support_group_id")
            and int(chat.id)==int(support["support_group_id"])
            and message.message_thread_id
        ):
            if user.id!=owner:
                return
            topic=await get_topic_by_thread(owner,chat.id,message.message_thread_id)
            if not topic:
                return
            try:
                await context.bot.copy_message(
                    chat_id=int(topic["user_id"]),
                    from_chat_id=chat.id,
                    message_id=message.message_id,
                )
            except TelegramError as exc:
                logger.warning("Support topic reply failed owner=%s user=%s: %s",owner,topic.get("user_id"),exc)
            raise ApplicationHandlerStop

        # Seller reply in normal private mode must be a reply to a copied user message.
        if chat.type=="private" and user.id==owner:
            if support.get("enabled") and support.get("mode")=="private" and message.reply_to_message:
                link=await get_private_message_link(owner,chat.id,message.reply_to_message.message_id)
                if link:
                    await context.bot.copy_message(
                        chat_id=int(link["user_id"]),
                        from_chat_id=chat.id,
                        message_id=message.message_id,
                    )
                    raise ApplicationHandlerStop
            return

        # Users send an actual non-command content message in private chat.
        if chat.type!="private" or user.id==owner:
            return
        has_user_content=bool(
            message.text
            or message.caption
            or message.effective_attachment
            or message.contact
            or message.location
            or message.venue
            or message.poll
        )
        if not has_user_content or not support.get("enabled"):
            return
        special_states={
            "waiting_child_screenshot","wait_qr","wait_welcome_media","wait_broadcast",
            "wait_scheduled_broadcast","wait_channel","wait_plan_add","wait_plan_edit",
            "ba_editor","ba_auth","ba_media_batch",
        }
        if any(context.user_data.get(key) for key in special_states):
            return
        if await is_support_blocked(owner,user.id):
            await message.reply_text("🚫 You cannot contact live support right now.")
            raise ApplicationHandlerStop

        await upsert_user(owner,user)
        auto_reply=None
        if message.text and not message.text.startswith("/"):
            auto_reply=await match_support_auto_reply(owner,message.text)
        mode=support.get("mode","topic")
        if mode == "topic" and not support.get("support_group_id"):
            await message.reply_text("⚠️ Live support group is not connected yet. Please try again later.")
            raise ApplicationHandlerStop

        # Topic creation and forwarding happen inside one FIFO section. A MongoDB
        # receipt additionally prevents two Render workers from forwarding the
        # same Telegram update twice, while failed attempts remain retryable.
        receipt = None
        try:
            async with _live_support_fifo_lock(owner, user.id):
                receipt = await claim_support_delivery(
                    owner,
                    "user_to_support",
                    chat.id,
                    message.message_id,
                    stale_seconds=180,
                )
                if receipt is None:
                    # This exact update is already completed or is currently
                    # being handled by another worker.
                    raise ApplicationHandlerStop
                if mode=="topic":
                    topic=await self._ensure_support_topic_reliably(context,owner,user,support)
                    try:
                        await self._copy_to_support_topic_reliably(
                            context, topic, message,
                        )
                    except BadRequest as exc:
                        if self._is_closed_support_topic_error(exc):
                            await self._reopen_support_topic(context, topic)
                            await self._copy_to_support_topic_reliably(context, topic, message)
                        elif self._is_missing_support_topic_error(exc):
                            logger.warning("Support topic missing owner=%s user=%s: %s",owner,user.id,exc)
                            await reset_support_topic_mapping(owner,user.id,str(exc))
                            topic=await self._ensure_support_topic_reliably(context,owner,user,support)
                            await self._copy_to_support_topic_reliably(context, topic, message)
                        else:
                            raise
                else:
                    await context.bot.send_message(
                        owner,
                        f"💬 Live Support\nUser: {user.full_name}\nID: {user.id}\nReply to the copied message below.",
                    )
                    copied=await context.bot.copy_message(
                        chat_id=owner,
                        from_chat_id=chat.id,
                        message_id=message.message_id,
                    )
                    await save_private_message_link(owner,owner,copied.message_id,user.id)

                await complete_support_delivery(
                    receipt["_id"],
                    target_chat_id=(
                        int(topic["support_group_id"]) if mode == "topic" else int(owner)
                    ),
                    target_message_thread_id=(
                        int(topic["message_thread_id"]) if mode == "topic" else None
                    ),
                )
                receipt = None

                if auto_reply:
                    try:
                        await self.send_support_template(context,owner,user.id,auto_reply,user)
                    except TelegramError as exc:
                        logger.warning("Support auto reply failed owner=%s user=%s: %s",owner,user.id,exc)

                confirmation=await message.reply_text("✅ Message sent to live support.")
                async def _delete_support_confirmation():
                    await asyncio.sleep(3)
                    try:
                        await confirmation.delete()
                    except TelegramError:
                        pass
                asyncio.create_task(_delete_support_confirmation())
        except ApplicationHandlerStop:
            raise
        except TelegramError as exc:
            if receipt is not None:
                await fail_support_delivery(receipt["_id"], str(exc))
            logger.exception("Live support routing failed owner=%s user=%s",owner,user.id)
            await message.reply_text("❌ Message could not be sent to live support. Please try again.")
        except Exception as exc:
            if receipt is not None:
                await fail_support_delivery(receipt["_id"], str(exc))
            logger.exception("Unexpected live support routing failure owner=%s user=%s",owner,user.id)
            await message.reply_text("❌ Message could not be sent to live support. Please try again.")

        return

    async def support_callback(self,update:Update,context:ContextTypes.DEFAULT_TYPE):
        q=update.callback_query
        await q.answer()
        owner=self.owner(context)
        if q.from_user.id!=owner:
            await q.answer("Not authorized",show_alert=True)
            return
        data=q.data
        try:
            user_id=int(data.rsplit("_",1)[-1])
        except ValueError:
            return
        if data.startswith("support_id_"):
            await q.answer(f"User ID: {user_id}",show_alert=True); return
        if data.startswith("support_block_"):
            await set_support_block(owner,user_id,True)
            await q.edit_message_reply_markup(self.support_topic_keyboard(user_id,True)); return
        if data.startswith("support_unblock_"):
            await set_support_block(owner,user_id,False)
            await q.edit_message_reply_markup(self.support_topic_keyboard(user_id,False)); return
        if data.startswith("support_profile_"):
            text,record,sub=await self.user_details_text(owner,user_id)
            if not text:
                await q.answer("User not found",show_alert=True); return
            await context.bot.send_message(
                chat_id=q.message.chat_id,
                message_thread_id=q.message.message_thread_id,
                text=text,
            )
            return

    async def text_handler(self,update:Update,context:ContextTypes.DEFAULT_TYPE):
        owner=self.owner(context); text=update.effective_message.text.strip()
        staff = await self.staff_record(update, context)
        if staff:
            if context.user_data.get("wait_pg_webhook_secret"):
                try:
                    if not text:
                        raise ValueError("Webhook Secret cannot be empty")
                    await save_gateway_config("seller",owner,"razorpay",{"webhook_secret":text,"mode":"live"})
                    context.user_data.clear()
                    cfg=await get_gateway_config("seller",owner,decrypt=True); g=(cfg.get("gateways") or {}).get("razorpay",{})
                    await update.effective_message.reply_text(
                        "✅ Webhook Secret saved securely.",
                        reply_markup=_seller_razorpay_keyboard(bool(g.get("enabled"))),
                    )
                except Exception as exc:
                    await update.effective_message.reply_text(f"❌ {exc}")
                return
            gateway=context.user_data.get("wait_pg_credentials")
            if gateway:
                values=[x.strip() for x in text.split("|")]
                try:
                    if gateway=="razorpay" and len(values)==2:
                        payload={"key_id":values[0],"key_secret":values[1],"mode":"live"}
                    elif gateway=="cashfree" and len(values)==2:
                        payload={"client_id":values[0],"client_secret":values[1]}
                    elif gateway=="phonepe" and len(values)==5:
                        payload={"client_id":values[0],"client_version":values[1],"client_secret":values[2],"webhook_username":values[3],"webhook_password":values[4]}
                    elif gateway=="paytm" and len(values)==3:
                        payload={"mid":values[0],"merchant_key":values[1],"website_name":values[2]}
                    else:
                        raise ValueError("Invalid credential format")
                    await save_gateway_config("seller",owner,gateway,payload)
                    context.user_data.clear()
                    await update.effective_message.reply_text("✅ Gateway credentials saved securely.",reply_markup=self.back(f"a_pg_view_{gateway}"))
                except Exception as exc:
                    await update.effective_message.reply_text(f"❌ {exc}")
                return
            if context.user_data.get("wait_support_ar_keyword"):
                keyword=" ".join(text.strip().lower().split())
                try:
                    await save_support_auto_reply(owner,keyword)
                except Exception as exc:
                    await update.effective_message.reply_text(f"❌ {exc}"); return
                context.user_data.clear()
                await update.effective_message.reply_text(
                    "✅ Auto reply created",
                    reply_markup=self.support_auto_reply_edit_menu(keyword),
                ); return
            if context.user_data.get("wait_support_ar_text"):
                keyword=context.user_data["wait_support_ar_text"]
                await save_support_auto_reply(owner,keyword,text=text); context.user_data.clear()
                await update.effective_message.reply_text("✅ Text saved",reply_markup=self.support_auto_reply_edit_menu(keyword)); return
            if context.user_data.get("wait_support_ar_buttons"):
                keyword=context.user_data["wait_support_ar_buttons"]
                try: rows=self.parse_welcome_buttons(text)
                except Exception as exc: await update.effective_message.reply_text(f"❌ {exc}"); return
                await save_support_auto_reply(owner,keyword,buttons=rows); context.user_data.clear()
                await update.effective_message.reply_text("✅ URL buttons saved",reply_markup=self.support_auto_reply_edit_menu(keyword)); return
            if context.user_data.get("wait_support_tpl_command"):
                command=text.strip().lower().lstrip("/")
                try:
                    await save_support_template(owner,command)
                except Exception as exc:
                    await update.effective_message.reply_text(f"❌ {exc}"); return
                context.user_data.clear(); await update.effective_message.reply_text(f"✅ /{command} created",reply_markup=self.support_template_edit_menu(command)); return
            if context.user_data.get("wait_support_tpl_text"):
                command=context.user_data["wait_support_tpl_text"]
                await save_support_template(owner,command,text=text); context.user_data.clear()
                await update.effective_message.reply_text("✅ Template text saved",reply_markup=self.support_template_edit_menu(command)); return
            if context.user_data.get("wait_support_tpl_buttons"):
                command=context.user_data["wait_support_tpl_buttons"]
                try: rows=self.parse_welcome_buttons(text)
                except Exception as exc: await update.effective_message.reply_text(f"❌ {exc}"); return
                await save_support_template(owner,command,buttons=rows); context.user_data.clear()
                await update.effective_message.reply_text("✅ Template buttons saved",reply_markup=self.support_template_edit_menu(command)); return
            if context.user_data.get("wait_support_tpl_auto_delete"):
                command=context.user_data["wait_support_tpl_auto_delete"]
                try:
                    seconds=_parse_auto_delete_duration(text)
                    await save_support_template(owner,command,auto_delete_seconds=seconds)
                except Exception as exc:
                    await update.effective_message.reply_text(f"❌ {exc}")
                    return
                context.user_data.clear()
                await update.effective_message.reply_text(
                    f"✅ Template Auto Remove updated\n\n/{command}: {_format_auto_delete(seconds)}",
                    reply_markup=self.support_template_edit_menu(command),
                ); return
            if context.user_data.get("wait_coupon_create"):
                try:
                    code,ctype,value,limit=[x.strip() for x in text.split("|",3)]
                    if ctype not in {"percent","fixed"}: raise ValueError("type")
                    await create_coupon(owner,code,ctype,float(value),int(limit))
                    context.user_data.clear(); await update.effective_message.reply_text("✅ Coupon saved",reply_markup=self.admin_menu())
                except Exception:
                    await update.effective_message.reply_text("❌ Use: SAVE20 | percent | 20 | 100")
                return
            if context.user_data.get("wait_plan_add") or context.user_data.get("wait_plan_edit"):
                try:
                    name,dtext,dmins,price,stars=self.parse_plan(text)
                    pid=context.user_data.get("wait_plan_edit")
                    if pid: await update_plan(owner,pid,name=name,duration_text=dtext,duration_minutes=dmins,price=price,stars_price=stars)
                    else: await create_plan(owner,name,dtext,dmins,price,stars)
                    context.user_data.clear(); await update.effective_message.reply_text("✅ Plan saved",reply_markup=self.plans_admin_menu())
                except Exception as exc: await update.effective_message.reply_text(f"❌ {exc}")
                return
            if context.user_data.get("wait_channel"):
                try:
                    cid,name=[x.strip() for x in text.split("|",1)]; await add_channel(owner,int(cid),name,"group")
                    context.user_data.clear(); await update.effective_message.reply_text("✅ Channel/group added",reply_markup=self.channels_menu())
                except Exception: await update.effective_message.reply_text("❌ Use: -1001234567890 | Group Name")
                return
            if context.user_data.get("wait_upi_id") or context.user_data.get("wait_upi_name"):
                key="upi_id" if context.user_data.get("wait_upi_id") else "upi_name"
                await set_seller_setting(owner,key,text)
                context.user_data.clear()
                gateway_cfg=await get_gateway_config("seller",owner,decrypt=True)
                await update.effective_message.reply_text("✅ Updated",reply_markup=self.manual_payment_menu(bool(gateway_cfg.get("manual_enabled",True))))
                return
            mapping=[("wait_bot_name","bot_name",text,self.settings_menu()),("wait_support","support_username",text if text.startswith("@") else "@"+text,self.settings_menu()),("wait_currency","currency",text.upper(),self.settings_menu())]
            for state,key,val,kb in mapping:
                if context.user_data.get(state): await set_seller_setting(owner,key,val); context.user_data.clear(); await update.effective_message.reply_text("✅ Updated",reply_markup=kb); return
            if context.user_data.get("wait_welcome_text"):
                await set_seller_setting(owner,"welcome_message",text); context.user_data.clear()
                await update.effective_message.reply_text("✅ Welcome text saved. Use 👀 Full Preview to check it.",reply_markup=self.welcome_text_menu(True)); return
            if context.user_data.get("wait_welcome_buttons"):
                try: rows=self.parse_welcome_buttons(text)
                except Exception as exc: await update.effective_message.reply_text(f"❌ {exc}"); return
                await set_seller_setting(owner,"welcome_buttons",rows); context.user_data.clear()
                await update.effective_message.reply_text("✅ Welcome buttons saved. Use 👀 Full Preview to check them.",reply_markup=self.welcome_buttons_menu(True)); return
            if context.user_data.get("wait_staff_promote"):
                try:
                    staff_user_id=int(text.strip())
                    if staff_user_id==owner:
                        raise ValueError("Seller is already the owner")
                    user=await get_user(owner,staff_user_id)
                    role=context.user_data["wait_staff_promote"]
                    record=await promote_staff(
                        owner, staff_user_id, role, update.effective_user.id,
                        username=(user or {}).get("username", ""),
                        full_name=(user or {}).get("full_name", ""),
                    )
                    context.user_data.clear()
                    try:
                        await context.bot.send_message(staff_user_id, f"✅ You were promoted as {role.title()} for this clone bot. Send /start to open your staff panel.")
                    except Exception:
                        pass
                    await update.effective_message.reply_text(
                        f"✅ Staff promoted\n\nUser ID: {staff_user_id}\nRole: {role.title()}",
                        reply_markup=self.staff_menu(),
                    )
                except Exception as exc:
                    await update.effective_message.reply_text(f"❌ Could not promote staff: {exc}\n\nSend a numeric Telegram User ID.")
                return

            if context.user_data.get("wait_user_search"):
                query=text.strip()
                user=None

                if query.startswith("@"):
                    user=await get_user_by_username(owner,query)
                else:
                    try:
                        user=await get_user(owner,int(query))
                    except ValueError:
                        user=await get_user_by_username(owner,query)

                if not user:
                    await update.effective_message.reply_text(
                        "❌ User not found. Send a valid User ID or @username.",
                        reply_markup=self.back("a_home"),
                    )
                    return

                context.user_data.clear()

                await self.show_user_details(
                    _MessageQueryAdapter(update.effective_message),
                    owner,
                    int(user["user_id"]),
                )
                return

            if context.user_data.get("wait_user_ban_reason"):
                user_id=int(context.user_data["wait_user_ban_reason"])
                await set_user_ban(owner,user_id,True,text)
                context.user_data.clear()

                try:
                    await context.bot.send_message(
                        user_id,
                        f"🚫 You have been banned.\nReason: {text}",
                    )
                except Exception:
                    pass

                await self.show_user_details(
                    _MessageQueryAdapter(update.effective_message),
                    owner,
                    user_id,
                )
                return

            if context.user_data.get("wait_timezone"):
                try:
                    timezone_name = normalize_timezone(text)
                except Exception:
                    await update.effective_message.reply_text(
                        "❌ Invalid timezone.\n\nUse the exact format, for example:\nAsia/Kolkata\n\nTimezone names are case-sensitive.",
                        reply_markup=timezone_keyboard("a_tz_", "a_settings"),
                    )
                    return
                await set_seller_setting(owner, "timezone", timezone_name)
                context.user_data.clear()
                await update.effective_message.reply_text(
                    f"✅ Timezone updated!\n\nTimezone: {timezone_name}",
                    reply_markup=self.settings_menu(),
                )
                return
            if context.user_data.get("wait_referral_unlock_duration"):
                try:
                    duration_days=int((update.effective_message.text or "").strip())
                except (TypeError,ValueError):
                    duration_days=0
                if duration_days < 1 or duration_days > 3650:
                    await update.effective_message.reply_text("❌ Send a whole number from 1 to 3650.",reply_markup=self.back("a_referral_unlock")); return
                await set_seller_setting(owner,"referral_unlock_duration_days",duration_days)
                context.user_data.clear()
                settings=await get_seller_settings(owner)
                channels=await get_channels(owner)
                await update.effective_message.reply_text(
                    self.referral_unlock_text(settings),
                    reply_markup=self.referral_unlock_menu(settings,channels),
                ); return
            if context.user_data.get("wait_referral_unlock_required"):
                try:
                    required=int((message.text or "").strip())
                    if required < 1 or required > 100:
                        raise ValueError
                except ValueError:
                    await update.effective_message.reply_text("❌ Send a whole number from 1 to 100.",reply_markup=self.back("a_referral_unlock")); return
                await set_seller_setting(owner,"referral_unlock_required",required)
                context.user_data.clear()
                settings=await get_seller_settings(owner)
                channels=await get_channels(owner)
                await update.effective_message.reply_text(
                    self.referral_unlock_text(settings),
                    reply_markup=self.referral_unlock_menu(settings,channels),
                ); return

            if context.user_data.get("wait_referral_days"):
                try:
                    days=int(text)
                    if days < 0 or days > 3650:
                        raise ValueError
                except ValueError:
                    await update.effective_message.reply_text(
                        "❌ Send a number from 0 to 3650."
                    )
                    return

                await set_seller_setting(
                    owner,
                    "referral_reward_days",
                    days,
                )
                context.user_data.clear()
                await update.effective_message.reply_text(
                    f"✅ Referral reward set to {days} day(s).",
                    reply_markup=self.settings_menu(),
                )
                return
            if context.user_data.get("wait_reminder"):
                try: days=int(text)
                except ValueError: await update.effective_message.reply_text("❌ Send number"); return
                await set_seller_setting(owner,"reminder_days",days); context.user_data.clear(); await update.effective_message.reply_text("✅ Updated",reply_markup=self.settings_menu()); return

