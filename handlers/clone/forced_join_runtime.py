import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from handlers.common.editor_engine import parse_editor_buttons, build_editor_keyboard, editor_text_prompt, editor_media_prompt
from database.forced_join import list_required, get_required, toggle_required, remove_required, update_invite, save_pending_request, list_pending_requests, remove_pending_request
from database.seller_data import get_channels
from database.forced_join import get_forced_join_editor, set_forced_join_editor

logger=logging.getLogger(__name__)

def _kb(rows):
    return InlineKeyboardMarkup(rows)

async def _required_status(bot, user_id, required):
    for item in required:
        if not item.get("enabled", True):
            continue
        try:
            member=await bot.get_chat_member(int(item["chat_id"]), int(user_id))
            if member.status in {"left","kicked"}:
                return False, item
        except Exception:
            # If the bot cannot verify a required chat, fail closed.
            return False, item
    return True, None


async def _send_forced_join_approval_message(bot, owner, user_id):
    item=await get_forced_join_editor(owner)
    if not item:
        return
    text=item.get("text") or ""
    media=item.get("media") or []
    buttons=item.get("buttons") or []
    markup=build_editor_keyboard(buttons)
    try:
        if not media:
            if text or markup:
                await bot.send_message(chat_id=user_id, text=text or " ", reply_markup=markup)
            return
        for idx,entry in enumerate(media):
            fid=entry.get("file_id")
            typ=entry.get("type")
            caption=text if idx == 0 else None
            if typ=="photo":
                await bot.send_photo(chat_id=user_id, photo=fid, caption=caption, reply_markup=markup if idx==0 else None)
            elif typ=="video":
                await bot.send_video(chat_id=user_id, video=fid, caption=caption, reply_markup=markup if idx==0 else None)
            elif typ=="document":
                await bot.send_document(chat_id=user_id, document=fid, caption=caption, reply_markup=markup if idx==0 else None)
    except Exception:
        logger.exception("Forced Join approval editor message failed owner=%s user=%s", owner, user_id)

async def forced_join_request(update, context):
    req=update.chat_join_request
    if not req:
        return

    owner=int(context.application.bot_data.get("seller_owner_id") or 0)
    if not owner:
        return

    access_chat_id=int(req.chat.id)
    user_id=int(req.user_chat_id)

    required=[
        x for x in await list_required(owner)
        if x.get("enabled", True)
        and int(x.get("chat_id", 0) or 0) != access_chat_id
    ]

    if not required:
        try:
            await context.bot.approve_chat_join_request(access_chat_id, user_id)
        except Exception:
            logger.exception("Automatic approval failed access=%s user=%s", access_chat_id, user_id)
        return

    # Check all required chats immediately. If the user is already a member
    # everywhere, approve without sending a Forced Join message.
    ok, missing=await _required_status(context.bot, user_id, required)
    if ok:
        try:
            await context.bot.approve_chat_join_request(access_chat_id, user_id)
            await remove_pending_request(owner, user_id, access_chat_id)
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=(
                        "✅ All required groups/channels are joined.\n"
                        "Your access request has been approved."
                    ),
                )
            except Exception:
                pass
        except Exception:
            logger.exception("Automatic approval failed access=%s user=%s", access_chat_id, user_id)
        return

    # Save the original request so later ChatMember updates can approve it
    # automatically after every required chat has been joined.
    await save_pending_request(owner, user_id, access_chat_id)

    rows=[]
    for item in required:
        link=str(item.get("invite_link") or "").strip()
        if not link:
            try:
                invite=await context.bot.create_chat_invite_link(
                    int(item["chat_id"]), name="Forced Join", member_limit=0
                )
                link=invite.invite_link
                await update_invite(owner, int(item["chat_id"]), link)
            except Exception:
                logger.exception(
                    "Could not create Forced Join invite owner=%s chat=%s",
                    owner, item.get("chat_id")
                )

        # Per-item status: already joined = disabled/info button;
        # missing = clickable Join button.
        try:
            member=await context.bot.get_chat_member(int(item["chat_id"]), user_id)
            status=str(getattr(member, "status", "") or "")
            joined=status in {"creator", "administrator", "member"} or (
                status == "restricted" and bool(getattr(member, "is_member", False))
            )
        except Exception:
            joined=False

        title=str(item.get("title") or "Required Group/Channel")[:35]
        if joined:
            rows.append([
                InlineKeyboardButton(f"📎 Joined {title} ✅", callback_data="fj_info:joined")
            ])
        elif link:
            rows.append([
                InlineKeyboardButton(f"📎 Join {title} ❌", url=link)
            ])
        else:
            rows.append([
                InlineKeyboardButton(f"📎 Join {title} ❌", callback_data="fj_info:missing")
            ])

    text=(
        "🔐 Join Required\n\n"
        "To access this private channel, first join the required "
        "group/channel(s) below.\n\n"
        "After all required groups/channels are joined, your original "
        "access request will be approved automatically."
    )

    try:
        await context.bot.send_message(
            chat_id=user_id,
            text=text,
            reply_markup=_kb(rows) if rows else None,
        )
    except Exception:
        logger.exception("Forced Join DM failed owner=%s user=%s access=%s", owner, user_id, access_chat_id)

async def forced_join_auto_approve(update, context):
    """Approve pending private-channel requests after required membership changes."""
    cm=update.chat_member
    if not cm:
        return

    new=cm.new_chat_member
    status=str(getattr(new, "status", "") or "")
    is_member=bool(getattr(new, "is_member", False))
    if status in {"left", "kicked"} or (status == "restricted" and not is_member):
        return

    owner=int(context.application.bot_data.get("seller_owner_id") or 0)
    user_id=int(getattr(new.user, "id", 0) or 0)
    if not owner or not user_id:
        return

    required=[
        x for x in await list_required(owner)
        if x.get("enabled", True)
    ]
    if not required:
        return

    pending=await list_pending_requests(owner, user_id)
    if not pending:
        return

    # Check every required chat. This makes approval independent of which
    # required group/channel generated the latest ChatMember update.
    ok, missing=await _required_status(context.bot, user_id, required)
    if not ok:
        return

    for request in pending:
        access_chat_id=int(request.get("access_chat_id", 0) or 0)
        if not access_chat_id:
            continue
        try:
            await context.bot.approve_chat_join_request(access_chat_id, user_id)
            await remove_pending_request(owner, user_id, access_chat_id)
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=(
                        "✅ All required groups/channels are joined.\n\n"
                        "Your private-channel access request has been "
                        "approved automatically."
                    ),
                )
            except Exception:
                pass
        except Exception:
            logger.exception(
                "Forced Join automatic approval failed access=%s user=%s",
                access_chat_id, user_id
            )

async def forced_join_info_callback(update, context):
    q=update.callback_query
    if not q:
        return
    if (q.data or "")=="fj_forced_groups":
        await forced_join_groups_page(q, context)
        return
    if (q.data or "")=="fj_editor":
        await forced_join_message_editor(q, context)
        return
    if (q.data or "").startswith("fj_info:"):
        if q.data.endswith(":joined"):
            await q.answer("✅ You have already joined this required group/channel.")
        else:
            await q.answer("Please use the Join button for this required group/channel.")

async def forced_join_message_editor(q, context):
    owner=int(context.application.bot_data.get("seller_owner_id") or 0)
    item=await get_forced_join_editor(owner)
    text=item.get("text") or ""
    media=item.get("media") or []
    buttons=item.get("buttons") or []
    rows=[
        [InlineKeyboardButton("📝 Text",callback_data="fj_editor_text"),
         InlineKeyboardButton("🖼 Media",callback_data="fj_editor_media")],
        [InlineKeyboardButton("🔗 Buttons",callback_data="fj_editor_buttons"),
         InlineKeyboardButton("👀 Preview",callback_data="fj_editor_preview")],
        [InlineKeyboardButton("⬅ Back",callback_data="gm_forced_join")],
    ]
    await q.edit_message_text(
        "📝 Forced Join Approval Message\n\n"
        "This editor message is sent after all required groups/channels are "
        "joined and the private access request is approved.\n\n"
        f"📄 Text: {'✅ Added' if text else '❌ Not added'}\n"
        f"🖼 Media: {len(media)}/10" if media else
        "📝 Forced Join Approval Message\n\n"
        "This editor message is sent after all required groups/channels are "
        "joined and the private access request is approved.\n\n"
        f"📄 Text: {'✅ Added' if text else '❌ Not added'}\n"
        "🖼 Media: ❌ Not added",
        reply_markup=_kb(rows),
    )

async def forced_join_editor_callback(update, context):
    q=update.callback_query
    await q.answer()
    a=q.data or ""
    owner=int(context.application.bot_data.get("seller_owner_id") or 0)
    if a=="fj_editor":
        await forced_join_message_editor(q,context); return True
    if a=="fj_editor_text":
        context.user_data["fj_editor_input"]="text"
        await q.edit_message_text(editor_text_prompt("Forced Join Approval Message"))
        return True
    if a=="fj_editor_media":
        context.user_data["fj_editor_input"]="media"
        await q.edit_message_text(editor_media_prompt("Forced Join Approval Message"))
        return True
    if a=="fj_editor_buttons":
        context.user_data["fj_editor_input"]="buttons"
        await q.edit_message_text(
            "🔗 Forced Join Approval Message Buttons\n\n"
            "Send button rows using:\n"
            "Button title - https://t.me/example\n\n"
            "Multiple buttons in one row:\n"
            "Button 1 - https://t.me/a && Button 2 - https://t.me/b"
        )
        return True
    if a=="fj_editor_preview":
        item=await get_forced_join_editor(owner)
        markup=build_editor_keyboard(item.get("buttons") or [])
        text=item.get("text") or "❌ No text added."
        media=item.get("media") or []
        if not media:
            await q.message.reply_text(text,reply_markup=markup)
        else:
            e=media[0]; typ=e.get("type"); fid=e.get("file_id")
            if typ=="photo": await q.message.reply_photo(fid,caption=text,reply_markup=markup)
            elif typ=="video": await q.message.reply_video(fid,caption=text,reply_markup=markup)
            else: await q.message.reply_document(fid,caption=text,reply_markup=markup)
        return True
    return False

async def forced_join_editor_text_input(update, context):
    mode=context.user_data.get("fj_editor_input")
    if mode not in {"text","buttons"}:
        return False
    owner=int(context.application.bot_data.get("seller_owner_id") or 0)
    item=await get_forced_join_editor(owner)
    text=(update.effective_message.text or "").strip()
    if not text:
        await update.effective_message.reply_text("❌ Cannot be empty.")
        return True
    if mode=="text":
        item["text"]=text
    else:
        try:
            item["buttons"]=parse_editor_buttons(text)
        except ValueError as e:
            await update.effective_message.reply_text(f"❌ {e}")
            return True
    await set_forced_join_editor(owner,item)
    context.user_data.pop("fj_editor_input",None)
    await update.effective_message.reply_text(
        "✅ Saved.",
        reply_markup=_kb([[InlineKeyboardButton("⬅ Continue",callback_data="fj_editor")]]),
    )
    return True

async def forced_join_editor_media_input(update, context):
    if context.user_data.get("fj_editor_input")!="media":
        return False
    m=update.effective_message
    entry=None
    if m.photo: entry={"type":"photo","file_id":m.photo[-1].file_id}
    elif m.video: entry={"type":"video","file_id":m.video.file_id}
    elif m.document: entry={"type":"document","file_id":m.document.file_id}
    if not entry:
        return False
    owner=int(context.application.bot_data.get("seller_owner_id") or 0)
    item=await get_forced_join_editor(owner)
    media=item.get("media") or []
    media=[entry]  # replace current approval media
    item["media"]=media
    await set_forced_join_editor(owner,item)
    context.user_data.pop("fj_editor_input",None)
    await m.reply_text(
        "✅ Media saved.",
        reply_markup=_kb([[InlineKeyboardButton("⬅ Continue",callback_data="fj_editor")]]),
    )
    return True

async def forced_join_page(q, context):
    owner=int(context.application.bot_data.get("seller_owner_id") or 0)
    rows=[
        [InlineKeyboardButton("🔗 Forced Group/Channel",callback_data="fj_forced_groups")],
        [InlineKeyboardButton("📝 Approval Message",callback_data="fj_editor")],
        [InlineKeyboardButton("⬅ Back",callback_data="gm_group")],
    ]
    await q.edit_message_text(
        "🔗 Forced Join\n\n"
        "Manage the groups/channels used for Forced Join and the "
        "message sent after automatic approval.",
        reply_markup=_kb(rows)
    )

async def forced_join_groups_page(q, context):
    owner=int(context.application.bot_data.get("seller_owner_id") or 0)
    items=await list_required(owner)
    rows=[]
    for x in items:
        mark="🟢" if x.get("enabled",True) else "🔴"
        rows.append([InlineKeyboardButton(
            f"{mark} {str(x.get('title') or 'Group/Channel')[:32]}",
            callback_data=f"fj_toggle:{int(x['chat_id'])}"
        )])
    rows.append([InlineKeyboardButton("⬅ Back",callback_data="gm_forced_join")])
    await q.edit_message_text(
        "🔗 Forced Group/Channel\n\n"
        "Only groups/channels connected with /connectforcedjoin are shown here.\n\n"
        "How to connect:\n"
        "/connectforcedjoin",
        reply_markup=_kb(rows)
    )


async def forced_join_toggle_callback(update, context):
    q=update.callback_query
    await q.answer()
    try:
        chat_id=int((q.data or "").split(":",1)[1])
    except Exception:
        return
    owner=int(context.application.bot_data.get("seller_owner_id") or 0)
    await toggle_required(owner,chat_id)
    await forced_join_page(q,context)
    return True

async def connect_forced_join_command(self, update, context):
    owner=self.owner(context)
    if not await self.auth(update,context):
        return
    message=update.effective_message
    chat=update.effective_chat
    target_id=chat.id if chat and chat.type in {"group","supergroup","channel"} else 0
    if context.args:
        try: target_id=int(context.args[0])
        except ValueError:
            await message.reply_text("❌ Send a valid chat ID.")
            return
    if not target_id:
        await message.reply_text(
            "❌ Use this command inside the required group/channel, "
            "or send /connectforcedjoin <chat_id> from the bot admin chat."
        )
        return
    try:
        info=await context.bot.get_chat(target_id)

        # /connectgroup subscription chats are deliberately excluded from
        # the Forced Join connection list.
        connected = await get_channels(owner)
        if any(int(x.get("chat_id", 0) or 0) == int(target_id) for x in (connected or [])):
            await message.reply_text(
                "❌ This group/channel is already connected for subscriptions "
                "with /connectgroup.\n\n"
                "Use a separate group/channel for Forced Join."
            )
            return

        member=await context.bot.get_chat_member(target_id, context.bot.id)
        if getattr(member,"status","") not in {"administrator","creator"}:
            await message.reply_text("❌ Bot must be an administrator in this group/channel.")
            return
        if getattr(member,"status","") != "creator" and not getattr(member,"can_invite_users",False):
            await message.reply_text(
                "❌ Bot needs the Invite Users permission in this group/channel."
            )
            return
        invite=await context.bot.create_chat_invite_link(
            target_id,name="Forced Join",member_limit=0
        )
        from database.forced_join import upsert_required
        await upsert_required(owner,target_id,info.title or "Group/Channel",info.type,invite.invite_link)
        await message.reply_text(
            f"✅ Forced Join group/channel connected.\n\n"
            f"Name: {info.title or 'Group/Channel'}\n"
            f"ID: {target_id}\n\n"
            "It is now available in Group Manager → Forced Join."
        )
    except Exception as exc:
        logger.exception("connectforcedjoin failed")
        await message.reply_text(f"❌ Could not connect this group/channel.\n\n{exc}")
