import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from database.forced_join import list_required, get_required, toggle_required, remove_required
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

    required=[x for x in await list_required(owner) if x.get("enabled",True)]
    if not required:
        return

    # The chat where the request was made is the access/private channel.
    access_chat_id=int(req.chat.id)
    user_chat_id=int(req.user_chat_id)

    # Give the user the required channels/groups and a check button.
    rows=[]
    for item in required:
        link=item.get("invite_link") or ""
        if link:
            rows.append([InlineKeyboardButton(
                f"🔗 Join {str(item.get('title') or 'Required Group')[:35]}",
                url=link
            )])
    rows.append([InlineKeyboardButton("✅ I've Joined",callback_data=f"fj_check:{access_chat_id}")])

    text=(
        "🔐 Join Required\n\n"
        "To access this channel, you must first join the required group/channel(s).\n\n"
        "After joining, tap the button below."
    )
    try:
        await context.bot.send_message(
            chat_id=user_chat_id,
            text=text,
            reply_markup=_kb(rows),
        )
    except Exception:
        logger.exception("Forced Join DM failed owner=%s user=%s access=%s",owner,user_chat_id,access_chat_id)

async def forced_join_callback(update, context):
    q=update.callback_query
    if not q:
        return
    await q.answer()
    data=q.data or ""
    if not data.startswith("fj_check:"):
        return
    try:
        access_chat_id=int(data.split(":",1)[1])
    except ValueError:
        await q.answer("Invalid request.",show_alert=True); return

    owner=int(context.application.bot_data.get("seller_owner_id") or 0)
    user=q.from_user
    required=[x for x in await list_required(owner) if x.get("enabled",True)]
    ok, missing=await _required_status(context.bot,user.id,required)
    if not ok:
        name=str((missing or {}).get("title") or "required group/channel")
        await q.answer(f"❌ Please join {name} first.",show_alert=True)
        return

    # Approve the original join request when all requirements are satisfied.
    try:
        await context.bot.approve_chat_join_request(access_chat_id,user.id)
    except Exception as exc:
        logger.exception("Forced Join approval failed access=%s user=%s",access_chat_id,user.id)
        await q.answer("❌ Could not approve the join request yet.",show_alert=True)
        return

    await q.edit_message_text(
        "✅ All required groups/channels are joined.\n\n"
        "Your access request has been approved."
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
        member=await context.bot.get_chat_member(target_id, context.bot.id)
        if getattr(member,"status","") not in {"administrator","creator"}:
            await message.reply_text("❌ Bot must be an administrator in this group/channel.")
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
