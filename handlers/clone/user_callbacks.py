"""Clone-bot end-user callback router."""

from handlers.common.clone_context import *
from handlers.clone.user import navigation, payments, profile, referral, support
from database.broadcast import get_seller_broadcast_draft

_USER_HANDLERS = (navigation, payments, profile, referral, support)

class CloneUserCallbacksMixin:
    async def child_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        q = update.callback_query
        await q.answer()
        owner = self.owner(context)
        action = q.data
        if action.startswith("bc:"):
            action = action[3:]
            context.user_data["clone_feature_back_target"] = "c_broadcast_home"
            context.user_data["clone_broadcast_origin_item"] = await get_seller_broadcast_draft(owner)
        elif action == "c_home":
            context.user_data.pop("clone_feature_back_target", None)
            context.user_data.pop("clone_broadcast_origin_item", None)
        for handler in _USER_HANDLERS:
            if await handler.handle(self, update, context, q, owner, action):
                return
        await q.answer("Button action not found", show_alert=True)
