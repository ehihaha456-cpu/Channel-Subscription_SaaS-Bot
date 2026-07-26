"""Clone-bot end-user callback router."""

from handlers.common.clone_context import *
from handlers.clone.user import navigation, payments, profile, referral, support

_USER_HANDLERS = (navigation, payments, profile, referral, support)

class CloneUserCallbacksMixin:
    async def child_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        q = update.callback_query
        await q.answer()
        owner = self.owner(context)
        action = q.data
        for handler in _USER_HANDLERS:
            if await handler.handle(self, update, context, q, owner, action):
                return
        await q.answer("Button action not found", show_alert=True)
