"""Focused clone-bot feature mixin; behavior preserved from services.bot_manager."""

from services.bot_manager_shared import *


class CloneCommonUtilsMixin:
    @staticmethod
    def parse_duration(value:str)->int:
        value=value.strip().lower(); n=int(value[:-1]); unit=value[-1]
        if n<=0: raise ValueError("Duration must be positive")
        if unit=="m": return n
        if unit=="h": return n*60
        if unit=="d": return n*1440
        raise ValueError("Use m, h or d")

    @classmethod
    def parse_plan(cls,text:str):
        p=[x.strip() for x in text.split("|")]
        if len(p)!=3: raise ValueError("Use: Plan Name | Duration | Price")
        return p[0],p[1].lower(),cls.parse_duration(p[1]),float(p[2])

    def owner(self,context): return int(context.application.bot_data["seller_owner_id"])

    def seller_account(self,context): return int(context.application.bot_data.get("seller_account_id", self.owner(context)))

    async def staff_record(self, update, context):
        uid = int(update.effective_user.id)
        if uid == self.seller_account(context):
            return {"role": "seller", "status": "active", "permissions": ["*"]}
        return await active_staff(self.owner(context), uid)

    async def auth(self,update,context):
        return bool(await self.staff_record(update, context))

    async def safe_query_message(self,q,text,reply_markup=None):
        """Edit text messages; reply with a new message when the button is on media."""
        try:
            return await q.edit_message_text(
                text,
                reply_markup=reply_markup,
                disable_web_page_preview=True,
            )
        except BadRequest as exc:
            error=str(exc).lower()
            if (
                "there is no text in the message to edit" in error
                or "message can't be edited" in error
                or "message is not modified" in error
            ):
                if "message is not modified" in error:
                    return None
                return await q.message.reply_text(
                    text,
                    reply_markup=reply_markup,
                    disable_web_page_preview=True,
                )
            raise

