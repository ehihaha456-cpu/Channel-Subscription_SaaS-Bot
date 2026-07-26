"""Focused clone-bot feature mixin; behavior preserved from services.bot_manager."""

from handlers.common.clone_context import *


class CloneMediaHandlersMixin:
    async def welcome_media_handler(self,update:Update,context:ContextTypes.DEFAULT_TYPE):
        owner=self.owner(context)
        if update.effective_user.id!=owner:
            return
        if context.user_data.get("wait_support_ar_media"):
            keyword=context.user_data["wait_support_ar_media"]
            msg=update.effective_message; media_type=""; file_id=""
            if msg.photo: media_type="photo"; file_id=msg.photo[-1].file_id
            elif msg.video: media_type="video"; file_id=msg.video.file_id
            elif msg.animation: media_type="animation"; file_id=msg.animation.file_id
            elif msg.document: media_type="document"; file_id=msg.document.file_id
            if not file_id: await msg.reply_text("❌ Send a photo, video, GIF or document."); return
            await save_support_auto_reply(owner,keyword,media_type=media_type,media_file_id=file_id)
            context.user_data.clear(); await msg.reply_text("✅ Media saved",reply_markup=self.support_auto_reply_edit_menu(keyword))
            raise ApplicationHandlerStop
        if context.user_data.get("wait_support_tpl_media"):
            command=context.user_data["wait_support_tpl_media"]
            msg=update.effective_message; media_type=""; file_id=""
            if msg.photo: media_type="photo"; file_id=msg.photo[-1].file_id
            elif msg.video: media_type="video"; file_id=msg.video.file_id
            elif msg.animation: media_type="animation"; file_id=msg.animation.file_id
            elif msg.document: media_type="document"; file_id=msg.document.file_id
            if not file_id: await msg.reply_text("❌ Photo, video, GIF ya document bhejo."); return
            await save_support_template(owner,command,media_type=media_type,media_file_id=file_id)
            context.user_data.clear(); await msg.reply_text("✅ Template media saved",reply_markup=self.support_template_edit_menu(command))
            raise ApplicationHandlerStop
        if not context.user_data.get("wait_welcome_media"): return
        msg=update.effective_message; media_type=""; file_id=""
        if msg.photo: media_type="photo"; file_id=msg.photo[-1].file_id
        elif msg.video: media_type="video"; file_id=msg.video.file_id
        elif msg.animation: media_type="animation"; file_id=msg.animation.file_id
        elif msg.document: media_type="document"; file_id=msg.document.file_id
        if not file_id: await msg.reply_text("❌ Send photo, video, GIF or document."); return
        await set_seller_setting(owner,"welcome_media_type",media_type)
        await set_seller_setting(owner,"welcome_media_file_id",file_id)
        context.user_data.clear(); await msg.reply_text("✅ Welcome media saved. Use 👀 Full Preview to check it.",reply_markup=self.welcome_media_menu(True))
        raise ApplicationHandlerStop

    async def photo_handler(self,update:Update,context:ContextTypes.DEFAULT_TYPE):
        owner=self.owner(context)

        if update.effective_user.id==owner and context.user_data.get("wait_qr"):
            await set_seller_setting(owner,"upi_qr_file_id",update.effective_message.photo[-1].file_id); context.user_data.clear(); gateway_cfg=await get_gateway_config("seller",owner,decrypt=True); await update.effective_message.reply_text("✅ QR updated",reply_markup=self.manual_payment_menu(bool(gateway_cfg.get("manual_enabled",True)))); return
        if context.user_data.get("waiting_child_screenshot"):
            plan=context.user_data.get("selected_child_plan")
            if not plan: await update.effective_message.reply_text("Select a plan first"); return
            photo=update.effective_message.photo[-1]
            unique=getattr(photo,"file_unique_id","")
            if not await reserve_payment_fingerprint("child",owner,unique,update.effective_user.id):
                context.user_data.clear(); await update.effective_message.reply_text("⚠️ This payment screenshot was already submitted. Send a new genuine payment proof."); return
            p=await create_payment(owner,update.effective_user.id,plan,photo.file_id); context.user_data.clear()
            await audit("child_payment_submitted",update.effective_user.id,owner,{"payment_id":p.get("payment_id")})
            kb=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "✅ Approve",
                        callback_data=f"a_pay_ok_{p['payment_id']}",
                    ),
                    InlineKeyboardButton(
                        "❌ Reject",
                        callback_data=f"a_pay_no_{p['payment_id']}",
                    ),
                ]
            ])

            caption=await self.payment_details_caption(
                owner,
                p,
                status="pending",
            )

            await context.bot.send_photo(
                owner,
                p["screenshot_file_id"],
                caption=caption,
                reply_markup=kb,
            )

            await update.effective_message.reply_text(
                "✅ Payment submitted. Waiting for approval."
            )
            raise ApplicationHandlerStop

    async def forward_handler(self,update:Update,context:ContextTypes.DEFAULT_TYPE):
        owner=self.owner(context)
        if update.effective_user.id!=owner or not context.user_data.get("wait_channel"): return
        m=update.effective_message; chat=getattr(m,"forward_from_chat",None)
        if chat is None:
            origin=getattr(m,"forward_origin",None); chat=getattr(origin,"chat",None)
        if chat is None:
            await m.reply_text(
                "❌ Forward se group detect nahi hua.\n\n"
                "Easy method: child bot ko group me Admin banao, phir group ke andar /connectgroup bhejo."
            )
            return
        await add_channel(owner,chat.id,chat.title or "Unknown",getattr(chat,"type","unknown")); context.user_data.clear(); await m.reply_text("✅ Channel/group added",reply_markup=self.channels_menu())

