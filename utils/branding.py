from __future__ import annotations

import os

from database.settings import get_setting_value

BRANDING_SEPARATOR = "━━━━━━━━━━━━━━━━━━━━━━━━━━━━"


def default_branding_text() -> str:
    username = os.getenv("MAIN_BOT_USERNAME", "").strip().lstrip("@")
    return f"🤖 Powered by @{username}" if username else "🤖 Powered by Main Bot"


async def get_branding_block() -> str:
    enabled = bool(await get_setting_value("branding_enabled", True))
    if not enabled:
        return ""
    text = str(await get_setting_value("branding_text", "") or "").strip()
    if not text:
        text = default_branding_text()
    return f"\n\n{BRANDING_SEPARATOR}\n\n{text}"
