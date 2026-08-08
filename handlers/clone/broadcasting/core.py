"""Clone-bot seller broadcast editor and delivery engine."""

from handlers.common.clone_context import *
from handlers.common.editor_engine import build_editor_keyboard, parse_editor_buttons
from handlers.common.feature_navigation import register_feature_origin
from database.broadcast import get_seller_broadcast_draft, update_seller_broadcast_draft
from telegram import InputMediaPhoto, InputMediaVideo, InputMediaDocument


class CloneBroadcastMixin:
    @staticmethod
    def _broadcast_variables(text, user):
        now = datetime.now(timezone.utc)
        username = str(user.get("username") or "")
        mention = f"@{username}" if username else str(user.get("name") or user.get("first_name") or "User")
        values = {
            "{NAME}": str(user.get("name") or user.get("first_name") or "User"),
            "{ID}": str(user.get("user_id") or ""),
            "{USERNAME}": f"@{username}" if username else "Not Set",
            "{MENTION}": mention,
            "{DATE}": now.strftime("%d %b %Y"),
            "{TIME}": now.strftime("%I:%M %p UTC"),
        }
        result = str(text or "")
        for key, value in values.items():
            result = result.replace(key, value)
        return result

    @staticmethod
    def _input_media(item, caption=None):
        media_type = str(item.get("type") or item.get("media_type") or "")
        file_id = str(item.get("file_id") or item.get("media_file_id") or "")
        if media_type == "photo":
            return InputMediaPhoto(file_id, caption=caption)
        if media_type == "video":
            return InputMediaVideo(file_id, caption=caption)
        if media_type == "document":
            return InputMediaDocument(file_id, caption=caption)
        return None

    async def _send_seller_broadcast_item(self, bot, chat_id, item, user):
        text = self._broadcast_variables(item.get("text"), user)
        buttons = build_editor_keyboard(item.get("buttons"))
        media = list(item.get("media") or [])
        if not media and item.get("media_file_id"):
            media = [{"type": item.get("media_type"), "file_id": item.get("media_file_id")}]

        if not media:
            sent = await bot.send_message(chat_id, text or "Broadcast", reply_markup=buttons)
            register_feature_origin(sent, text=text or "Broadcast", markup=buttons)
            return

        if len(media) == 1:
            media_type = str(media[0].get("type") or "")
            file_id = str(media[0].get("file_id") or "")
            kwargs = {"chat_id": chat_id, "caption": text or None, "reply_markup": buttons}
            if media_type == "photo":
                sent = await bot.send_photo(photo=file_id, **kwargs)
            elif media_type == "video":
                sent = await bot.send_video(video=file_id, **kwargs)
            elif media_type == "document":
                sent = await bot.send_document(document=file_id, **kwargs)
            elif media_type == "animation":
                sent = await bot.send_animation(animation=file_id, **kwargs)
            else:
                raise ValueError("Unsupported broadcast media")
            register_feature_origin(sent, text=text, markup=buttons)
            return

        album = []
        for index, media_item in enumerate(media[:10]):
            built = self._input_media(media_item, text if index == 0 and text else None)
            if built:
                album.append(built)
        if not album:
            raise ValueError("No valid album media")
        await bot.send_media_group(chat_id=chat_id, media=album)
        if buttons:
            sent = await bot.send_message(chat_id, "Choose an option:", reply_markup=buttons)
            register_feature_origin(sent, text="Choose an option:", markup=buttons)

    async def send_seller_broadcast_preview(self, message, item):
        owner = int(message.chat_id)
        user = {"user_id": owner, "name": "Preview User", "username": "preview_user"}
        await self._send_seller_broadcast_item(message.get_bot(), owner, item, user)

    async def send_seller_broadcast(self, owner, context, item):
        from database.seller_data import c, USERS

        total = success = failed = 0
        cursor = c(USERS).find({"owner_id": int(owner)}, {"user_id": 1, "name": 1, "first_name": 1, "username": 1})
        async for user in cursor:
            user_id = user.get("user_id")
            if not user_id or int(user_id) == int(owner):
                continue
            total += 1
            try:
                await self._send_seller_broadcast_item(context.bot, int(user_id), item, user)
                success += 1
            except Exception as exc:
                failed += 1
                logger.warning("Seller broadcast failed owner=%s user=%s error=%s", owner, user_id, exc)
            await asyncio.sleep(0.04)
        return {"total": total, "success": success, "failed": failed}

    async def broadcast_message_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        owner = self.owner(context)
        if update.effective_user.id != owner:
            return

        scheduled_editor = context.user_data.get("scheduled_broadcast_editor") or {}
        scheduled_field = str(scheduled_editor.get("field") or "")
        if scheduled_field:
            from handlers.clone.admin.broadcast_coupons import (
                _scheduled_editor_text, _scheduled_editor_keyboard,
                _scheduled_settings_text, _scheduled_settings_keyboard,
            )

            async def edit_scheduled_menu(text, markup):
                chat_id = scheduled_editor.get("menu_chat_id")
                message_id = scheduled_editor.get("menu_message_id")
                if chat_id and message_id:
                    try:
                        await context.bot.edit_message_text(
                            chat_id=int(chat_id), message_id=int(message_id),
                            text=text, reply_markup=markup,
                        )
                        try:
                            await update.effective_message.delete()
                        except Exception:
                            pass
                        return
                    except Exception:
                        logger.exception("Scheduled broadcast menu edit failed owner=%s", owner)
                await update.effective_message.reply_text(text, reply_markup=markup)

            raw = (update.effective_message.text or update.effective_message.caption or "").strip()
            if scheduled_field == "name":
                if not raw:
                    await update.effective_message.reply_text("❌ Send a broadcast name.")
                    raise ApplicationHandlerStop
                item = await create_scheduled_campaign(owner, raw)
                context.user_data.pop("scheduled_broadcast_editor", None)
                await edit_scheduled_menu(_scheduled_editor_text(item), _scheduled_editor_keyboard(item))
                raise ApplicationHandlerStop

            job_id = str(scheduled_editor.get("job_id") or "")
            item = await get_scheduled_campaign(owner, job_id)
            if not item:
                context.user_data.pop("scheduled_broadcast_editor", None)
                await update.effective_message.reply_text("❌ Scheduled broadcast not found.")
                raise ApplicationHandlerStop

            if scheduled_field == "text":
                if not raw:
                    await update.effective_message.reply_text("❌ Send text.")
                    raise ApplicationHandlerStop
                item = await update_scheduled_campaign(owner, job_id, text=raw)
                context.user_data.pop("scheduled_broadcast_editor", None)
                await edit_scheduled_menu(_scheduled_editor_text(item), _scheduled_editor_keyboard(item))
                raise ApplicationHandlerStop

            if scheduled_field == "buttons":
                try:
                    buttons = parse_editor_buttons(raw)
                except ValueError as exc:
                    await update.effective_message.reply_text(f"❌ {exc}")
                    raise ApplicationHandlerStop
                item = await update_scheduled_campaign(owner, job_id, buttons=buttons)
                context.user_data.pop("scheduled_broadcast_editor", None)
                await edit_scheduled_menu(_scheduled_editor_text(item), _scheduled_editor_keyboard(item))
                raise ApplicationHandlerStop

            if scheduled_field == "schedule":
                try:
                    parsed = datetime.strptime(raw, "%d %b %Y %I:%M %p")
                    if parsed <= datetime.now():
                        raise ValueError("past")
                    display = parsed.strftime("%d %b %Y • %I:%M %p")
                except Exception:
                    await update.effective_message.reply_text(
                        "❌ Use: 02 Sep 2026 06:50 PM\nThe date/time must be in the future."
                    )
                    raise ApplicationHandlerStop
                item = await update_scheduled_campaign(owner, job_id, schedule_at=display, status="active")
                context.user_data.pop("scheduled_broadcast_editor", None)
                await edit_scheduled_menu(_scheduled_settings_text(item), _scheduled_settings_keyboard(item))
                raise ApplicationHandlerStop

            if scheduled_field == "repeat":
                import re
                match = re.fullmatch(r"([1-9]\d*)([smhdSMHD])", raw)
                if not match:
                    await update.effective_message.reply_text("❌ Use formats like 6s, 7m, 8h or 9d.")
                    raise ApplicationHandlerStop
                interval = f"{match.group(1)}{match.group(2).lower()}"
                item = await update_scheduled_campaign(owner, job_id, repeat_interval=interval, status="active")
                context.user_data.pop("scheduled_broadcast_editor", None)
                await edit_scheduled_menu(_scheduled_settings_text(item), _scheduled_settings_keyboard(item))
                raise ApplicationHandlerStop

            if scheduled_field == "media":
                msg = update.effective_message
                media_type = ""
                file_id = ""
                if msg.photo:
                    media_type, file_id = "photo", msg.photo[-1].file_id
                elif msg.video:
                    media_type, file_id = "video", msg.video.file_id
                elif msg.document:
                    media_type, file_id = "document", msg.document.file_id
                elif msg.animation:
                    media_type, file_id = "animation", msg.animation.file_id
                if not file_id:
                    await msg.reply_text("❌ Send a photo, video, GIF or document.")
                    raise ApplicationHandlerStop

                async def save_scheduled_media(items):
                    ordered = sorted(items[:10], key=lambda x: int(x.get("message_id") or 0))
                    clean = [{"type": x["type"], "file_id": x["file_id"]} for x in ordered]
                    first = clean[0]
                    saved = await update_scheduled_campaign(
                        owner, job_id, media=clean, media_type=first["type"], media_file_id=first["file_id"]
                    )
                    context.user_data.pop("scheduled_broadcast_editor", None)
                    context.user_data.pop("scheduled_media_batch", None)
                    await edit_scheduled_menu(_scheduled_editor_text(saved), _scheduled_editor_keyboard(saved))

                entry = {"type": media_type, "file_id": file_id, "message_id": msg.message_id}
                group_id = str(msg.media_group_id or "")
                if not group_id:
                    await save_scheduled_media([entry])
                    raise ApplicationHandlerStop
                batch = context.user_data.get("scheduled_media_batch")
                if not batch or batch.get("group_id") != group_id:
                    batch = {"group_id": group_id, "items": [], "generation": 0}
                    context.user_data["scheduled_media_batch"] = batch
                if len(batch["items"]) < 10:
                    batch["items"].append(entry)
                batch["generation"] += 1
                generation = batch["generation"]

                async def finalize_scheduled_album():
                    await asyncio.sleep(1.2)
                    current = context.user_data.get("scheduled_media_batch") or {}
                    if current.get("group_id") != group_id or current.get("generation") != generation:
                        return
                    await save_scheduled_media(list(current.get("items") or []))

                context.application.create_task(finalize_scheduled_album())
                raise ApplicationHandlerStop

        editor = context.user_data.get("seller_broadcast_editor") or {}
        field = str(editor.get("field") or "")
        if field in {"text", "buttons"}:
            raw = (update.effective_message.text or update.effective_message.caption or "").strip()
            if not raw:
                await update.effective_message.reply_text("❌ Send text.")
                raise ApplicationHandlerStop
            try:
                if field == "text":
                    item = await update_seller_broadcast_draft(owner, text=raw)
                else:
                    item = await update_seller_broadcast_draft(owner, buttons=parse_editor_buttons(raw))
            except ValueError as exc:
                await update.effective_message.reply_text(f"❌ {exc}")
                raise ApplicationHandlerStop
            context.user_data.pop("seller_broadcast_editor", None)
            from handlers.clone.admin.broadcast_coupons import _broadcast_text, _broadcast_keyboard
            await update.effective_message.reply_text(_broadcast_text(item), reply_markup=_broadcast_keyboard(item))
            raise ApplicationHandlerStop

        if field == "media":
            msg = update.effective_message
            media_type = ""
            file_id = ""
            if msg.photo:
                media_type, file_id = "photo", msg.photo[-1].file_id
            elif msg.video:
                media_type, file_id = "video", msg.video.file_id
            elif msg.document:
                media_type, file_id = "document", msg.document.file_id
            elif msg.animation:
                media_type, file_id = "animation", msg.animation.file_id
            if not file_id:
                await msg.reply_text("❌ Send a photo, video, GIF or document.")
                raise ApplicationHandlerStop

            async def save_items(items):
                ordered = sorted(items[:10], key=lambda x: int(x.get("message_id") or 0))
                clean = [{"type": x["type"], "file_id": x["file_id"]} for x in ordered]
                first = clean[0]
                item = await update_seller_broadcast_draft(
                    owner,
                    media=clean,
                    media_type=first["type"],
                    media_file_id=first["file_id"],
                )
                context.user_data.pop("seller_broadcast_editor", None)
                context.user_data.pop("seller_broadcast_media_batch", None)
                from handlers.clone.admin.broadcast_coupons import _broadcast_text, _broadcast_keyboard
                await msg.reply_text(_broadcast_text(item), reply_markup=_broadcast_keyboard(item))

            entry = {"type": media_type, "file_id": file_id, "message_id": msg.message_id}
            group_id = str(msg.media_group_id or "")
            if not group_id:
                await save_items([entry])
                raise ApplicationHandlerStop

            batch = context.user_data.get("seller_broadcast_media_batch")
            if not batch or batch.get("group_id") != group_id:
                batch = {"group_id": group_id, "items": [], "generation": 0}
                context.user_data["seller_broadcast_media_batch"] = batch
            if len(batch["items"]) < 10:
                batch["items"].append(entry)
            batch["generation"] += 1
            generation = batch["generation"]

            async def finalize_album():
                await asyncio.sleep(1.2)
                current = context.user_data.get("seller_broadcast_media_batch") or {}
                if current.get("group_id") != group_id or current.get("generation") != generation:
                    return
                await save_items(list(current.get("items") or []))

            context.application.create_task(finalize_album())
            raise ApplicationHandlerStop

        if context.user_data.get("wait_scheduled_broadcast"):
            raw = (update.effective_message.text or update.effective_message.caption or "").strip()
            lines = raw.splitlines()
            try:
                run_local = datetime.strptime(lines[0].strip(), "%Y-%m-%d %H:%M")
                settings = await get_seller_settings(owner)
                zone = ZoneInfo(settings.get("timezone", "Asia/Kolkata"))
                run_at = run_local.replace(tzinfo=zone).astimezone(timezone.utc)
                if run_at <= datetime.now(timezone.utc):
                    raise ValueError("past")
            except Exception:
                await update.effective_message.reply_text("❌ First line must be a future time: YYYY-MM-DD HH:MM")
                return
            job = await save_scheduled_broadcast(owner, run_at, update.effective_chat.id, update.effective_message.message_id)
            context.application.job_queue.run_once(self.scheduled_broadcast_job, when=run_at, data=job, name=f"scheduled_{job['job_id']}")
            context.user_data.clear()
            await update.effective_message.reply_text(f"✅ Broadcast scheduled for {run_local:%d-%m-%Y %I:%M %p}", reply_markup=self.admin_menu())
            raise ApplicationHandlerStop

    async def restore_scheduled_broadcasts(self, application: Application, owner_id: int):
        jobs = await pending_scheduled_broadcasts(owner_id)
        now = datetime.now(timezone.utc)
        for job in jobs:
            run_at = job.get("run_at") or now
            if run_at.tzinfo is None:
                run_at = run_at.replace(tzinfo=timezone.utc)
            existing = application.job_queue.get_jobs_by_name(f"scheduled_{job['job_id']}")
            if existing:
                continue
            application.job_queue.run_once(self.scheduled_broadcast_job, when=max(run_at, now), data=job, name=f"scheduled_{job['job_id']}")
        if jobs:
            logger.info("Restored scheduled broadcasts owner_id=%s count=%s", owner_id, len(jobs))

    async def scheduled_broadcast_job(self, context: ContextTypes.DEFAULT_TYPE):
        job = context.job.data
        job_id = job["job_id"]
        owner = int(job["owner_id"])
        claimed = await claim_scheduled_broadcast(job_id)
        if not claimed:
            return
        try:
            from database.seller_data import c, USERS
            users = c(USERS).find({"owner_id": owner}, {"user_id": 1})
            success = failed = 0
            async for user in users:
                if await broadcast_cancel_requested(job_id):
                    break
                uid = user.get("user_id")
                if not uid or uid == owner:
                    continue
                try:
                    await context.bot.copy_message(uid, job["from_chat_id"], job["message_id"])
                    success += 1
                except Exception as exc:
                    failed += 1
                    await save_failed_delivery(owner, uid, "scheduled_broadcast", {"job_id": job_id}, str(exc))
                await asyncio.sleep(0.05)
            await set_scheduled_status(job_id, "completed", {"success": success, "failed": failed})
            try:
                await context.bot.send_message(owner, f"✅ Scheduled broadcast completed\nSuccess: {success}\nFailed: {failed}")
            except Exception:
                logger.exception("Scheduled broadcast completion notice failed job_id=%s owner_id=%s", job_id, owner)
        except Exception as exc:
            logger.exception("Scheduled broadcast execution failed job_id=%s owner_id=%s", job_id, owner)
            await release_scheduled_broadcast(job_id, str(exc))
