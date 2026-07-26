"""Feature callback handler extracted from the legacy clone callback router."""

from handlers.common.clone_context import *


async def handle(self, update, context, q, owner, staff, a, role):
    if a == 'a_help':
        await q.edit_message_text('📚 Clone Bot Admin Help Center\n\n🚀 Quick Start\n1️⃣ Add subscription plans\n2️⃣ Connect channel/group\n3️⃣ Configure UPI/QR or gateway\n4️⃣ Edit and preview welcome message\n5️⃣ Test payment, approval and invite link\n\n🛠 Commands\n/start — Seller opens Admin Panel; users open Welcome Menu\n/admin — Open Admin Panel\n/help — Full user and seller guide\n/connectgroup — Connect subscription group\n/connectsupport — Connect Live Support forum group\n/version — Show deployed runtime version\n\n📦 Plans — Add, edit, enable, disable or delete plans\n📂 Channels / Groups — Connect chats and resend links\n💳 Payments — UPI/QR, gateways, pending proofs and history\n👥 Users — Give, extend, remove, ban or unban\n💬 Welcome Editor — Text, media, buttons and preview\n🎫 Live Support — Topics, templates and auto remove\n📢 Broadcast — Send now, schedule and retry failed\n🎟 Coupons — Create and manage discounts\n🤝 Referral — User and seller referral controls\n📊 Statistics — Users, payments, plans and revenue\n\n🧪 Troubleshooting\n• Group not connecting: make bot admin and use /connectgroup inside it\n• Invite not sent: enable Invite Users permission\n• Live Support not working: enable forum topics and reconnect\n• Payment issue: verify UPI/QR or gateway credentials\n• Bot not replying: check runtime status and logs', reply_markup=self.back('a_home'))
        return True
    if a == 'a_terms':
        parts = []
        for key in ('terms', 'privacy', 'refund', 'support'):
            policy = await get_policy(key)
            parts.append(f"{key.title()}:\n{policy.get('text')}")
        await q.edit_message_text('📜 Terms & Policy\n\n' + '\n\n'.join(parts), reply_markup=self.admin_menu())
        return True
    return False
