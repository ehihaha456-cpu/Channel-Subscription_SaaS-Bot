import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from database.forced_join import list_required, get_required, toggle_required, remove_required, update_invite, save_pending_request, list_pending_requests, remove_pending_request
from database.seller_data import get_channels

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
            logger.exception(
                "Automatic approval failed access=%s user=%s",
                access_chat_id, user_id
            )
        return

    # Store the pending private-channel request. From this point the bot
    # watches ChatMember updates in the required chats and approves the
    # original request automatically as soon as all requirements are joined.
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
        if link:
            rows.append([
                InlineKeyboardButton(
                    f"🔗 Join {str(item.get('title') or 'Required Group/Channel')[:35]}",
                    url=link,
                )
            ])

    text=(
        "🔐 Join Required\n\n"
        "To access this private channel, first join the required "
        "group/channel(s) below.\n\n"
        "✅ After you join all required group/channel(s), your original "
        "access request will be approved automatically.\n\n"
        "You do not need to press any verification button."
    )

    try:
        await context.bot.send_message(
            chat_id=user_id,
            text=text,
            reply_markup=_kb(rows) if rows else None,
        )
    except Exception:
        logger.exception(
            "Forced Join DM failed owner=%s user=%s access=%s",
            owner, user_id, access_chat_id
        )


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

async def forced_join_page(q, context):
    owner=int(context.application.bot_data.get("seller_owner_id") or 0)
    items=await list_required(owner)
    rows=[]
    for x in items:
        mark="🟢" if x.get("enabled",True) else "🔴"
        rows.append([InlineKeyboardButton(
            f"{mark} {str(x.get('title') or 'Group/Channel')[:32]}",
            callback_data=f"fj_toggle:{int(x['chat_id'])}"
        )])
    rows.append([InlineKeyboardButton("⬅ Back",callback_data="gm_group")])
    await q.edit_message_text(
        "🔗 Forced Join\n\n"
        "Select the groups/channels users must join before their private-channel request is approved.",
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
