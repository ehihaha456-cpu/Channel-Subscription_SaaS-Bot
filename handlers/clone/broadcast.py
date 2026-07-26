"""Focused clone-bot feature mixin; behavior preserved from services.bot_manager."""

from services.bot_manager_shared import *


class CloneBroadcastMixin:
    async def broadcast_message_handler(self,update:Update,context:ContextTypes.DEFAULT_TYPE):
        owner=self.owner(context)

        if update.effective_user.id!=owner:
            return

        if context.user_data.get("wait_scheduled_broadcast"):
            raw=(update.effective_message.text or update.effective_message.caption or "").strip()
            lines=raw.splitlines()
            try:
                run_local=datetime.strptime(lines[0].strip(),"%Y-%m-%d %H:%M")
                settings=await get_seller_settings(owner)
                zone=ZoneInfo(settings.get("timezone","Asia/Kolkata"))
                run_at=run_local.replace(tzinfo=zone).astimezone(timezone.utc)
                if run_at<=datetime.now(timezone.utc): raise ValueError("past")
            except Exception:
                await update.effective_message.reply_text("❌ First line must be a future time: YYYY-MM-DD HH:MM")
                return
            job=await save_scheduled_broadcast(owner,run_at,update.effective_chat.id,update.effective_message.message_id)
            context.application.job_queue.run_once(self.scheduled_broadcast_job,when=run_at,data=job,name=f"scheduled_{job['job_id']}")
            context.user_data.clear(); await update.effective_message.reply_text(f"✅ Broadcast scheduled for {run_local:%d-%m-%Y %I:%M %p}",reply_markup=self.admin_menu())
            raise ApplicationHandlerStop

        if not context.user_data.get("wait_broadcast"):
            return

        from database.seller_data import c, USERS

        users=await c(USERS).find(
            {"owner_id":owner},
            {"user_id":1},
        ).to_list(length=None)

        success=0
        failed=0

        for user in users:
            user_id=user.get("user_id")
            if not user_id or user_id==owner:
                continue

            try:
                await context.bot.copy_message(
                    chat_id=user_id,
                    from_chat_id=update.effective_chat.id,
                    message_id=update.effective_message.message_id,
                )
                success+=1
            except Exception:
                failed+=1

        context.user_data.clear()

        await update.effective_message.reply_text(
            "✅ Broadcast completed\n\n"
            f"Success: {success}\n"
            f"Failed: {failed}",
            reply_markup=self.admin_menu(),
        )

        raise ApplicationHandlerStop

    async def restore_scheduled_broadcasts(
        self,
        application: Application,
        owner_id: int,
    ):
        """
        Restore database-backed broadcasts after a clone-bot restart.

        JobQueue entries are memory-only, so pending database jobs must be
        registered again whenever the clone bot starts.
        """
        jobs = await pending_scheduled_broadcasts(owner_id)
        now = datetime.now(timezone.utc)

        for job in jobs:
            run_at = job.get("run_at") or now
            if run_at.tzinfo is None:
                run_at = run_at.replace(tzinfo=timezone.utc)

            existing = application.job_queue.get_jobs_by_name(
                f"scheduled_{job['job_id']}"
            )
            if existing:
                continue

            application.job_queue.run_once(
                self.scheduled_broadcast_job,
                when=max(run_at, now),
                data=job,
                name=f"scheduled_{job['job_id']}",
            )

        if jobs:
            logger.info(
                "Restored scheduled broadcasts owner_id=%s count=%s",
                owner_id,
                len(jobs),
            )

    async def scheduled_broadcast_job(
        self,
        context: ContextTypes.DEFAULT_TYPE,
    ):
        job = context.job.data
        job_id = job["job_id"]
        owner = int(job["owner_id"])

        claimed = await claim_scheduled_broadcast(job_id)
        if not claimed:
            logger.info(
                "Scheduled broadcast skipped because it was already claimed "
                "job_id=%s owner_id=%s",
                job_id,
                owner,
            )
            return

        try:
            from database.seller_data import c, USERS

            users = await c(USERS).find(
                {"owner_id": owner},
                {"user_id": 1},
            ).to_list(length=None)

            success = failed = 0

            for user in users:
                if await broadcast_cancel_requested(job_id):
                    logger.info(
                        "Scheduled broadcast cancellation observed "
                        "job_id=%s owner_id=%s",
                        job_id,
                        owner,
                    )
                    break

                uid = user.get("user_id")
                if not uid or uid == owner:
                    continue

                try:
                    await context.bot.copy_message(
                        uid,
                        job["from_chat_id"],
                        job["message_id"],
                    )
                    success += 1
                except Exception as exc:
                    failed += 1
                    await save_failed_delivery(
                        owner,
                        uid,
                        "scheduled_broadcast",
                        {"job_id": job_id},
                        str(exc),
                    )

                await asyncio.sleep(0.05)

            await set_scheduled_status(
                job_id,
                "completed",
                {"success": success, "failed": failed},
            )

            try:
                await context.bot.send_message(
                    owner,
                    "✅ Scheduled broadcast completed\n"
                    f"Success: {success}\n"
                    f"Failed: {failed}",
                )
            except Exception:
                logger.exception(
                    "Scheduled broadcast completion notice failed "
                    "job_id=%s owner_id=%s",
                    job_id,
                    owner,
                )
        except Exception as exc:
            logger.exception(
                "Scheduled broadcast execution failed "
                "job_id=%s owner_id=%s",
                job_id,
                owner,
            )
            await release_scheduled_broadcast(job_id, str(exc))

