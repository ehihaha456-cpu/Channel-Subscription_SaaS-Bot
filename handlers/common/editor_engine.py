"""Shared message-editor helpers for clone-bot editable messages.

This module centralizes URL/username/feature-button parsing, keyboard building,
and the common editor help header. Existing callback values are preserved.
"""

from __future__ import annotations

from typing import Any, Iterable

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


FEATURE_CALLBACKS: dict[str, str] = {
    "plans": "c_plans",
    "buy": "c_buy",
    "profile": "c_profile",
    "renew": "c_renew",
    "referral": "c_referral",
    "referral_unlock": "c_referral_unlock",
    "support": "c_support",
    "home": "c_home",
}


def url_buttons_header() -> str:
    """Return the single shared URL/username/feature-button instruction header."""
    return (
        "🔗 Send URL, Username or Feature buttons\n\n"
        "• URL Button:\n"
        "Button Title - https://example.com\n\n"
        "• Username Button:\n"
        "Button Title - @username\n\n"
        "• Same Row:\n"
        "Plans - feature:plans && Join - https://example.com\n\n"
        "• Feature Button:\n"
        "Button Title - feature:plans\n"
        "Button Title - feature:buy\n"
        "Button Title - feature:profile\n"
        "Button Title - feature:renew\n"
        "Button Title - feature:referral\n"
        "Button Title - feature:referral_unlock\n"
        "Button Title - feature:support\n"
        "Button Title - feature:home"
    )



def business_url_buttons_header() -> str:
    """Business Automation button instructions. feature:* opens Clone Bot features."""
    return (
        "🔗 Send URL, Username or Feature buttons\n\n"
        "• URL Button:\n"
        "Button Title - https://example.com\n\n"
        "• Username Button:\n"
        "Button Title - @username\n\n"
        "• Same Row (use &&):\n"
        "Plans - feature:plans && Profile - feature:profile\n\n"
        "• Feature Buttons:\n"
        "Plans - feature:plans\n"
        "Buy - feature:buy\n"
        "Profile - feature:profile\n"
        "Renew - feature:renew\n"
        "Referral - feature:referral\n"
        "Unlock - feature:referral_unlock\n"
        "Support - feature:support\n"
        "Home - feature:home"
    )

def parse_editor_buttons(text: str) -> list[list[dict[str, str]]]:
    """Parse editable message buttons while preserving the existing schema."""
    rows: list[list[dict[str, str]]] = []
    for raw_line in (text or "").splitlines():
        raw_line = raw_line.strip()
        if not raw_line:
            continue

        row: list[dict[str, str]] = []
        for item in raw_line.split("&&"):
            item = item.strip()
            if " - " not in item:
                raise ValueError("Use: Button title - URL")

            title, target = [part.strip() for part in item.split(" - ", 1)]
            if not title or not target:
                raise ValueError("Button title and target required")

            if target.startswith(("http://", "https://", "tg://")) or target.startswith("t.me/"):
                if target.startswith("t.me/"):
                    target = "https://" + target
                row.append({"text": title, "type": "url", "value": target})
                continue

            if target.startswith("@"):
                username = target[1:].strip()
                if (
                    not username
                    or len(username) > 32
                    or not all(ch.isalnum() or ch == "_" for ch in username)
                ):
                    raise ValueError(
                        "Invalid Telegram username. Example: Button title - @username"
                    )
                row.append(
                    {
                        "text": title,
                        "type": "url",
                        "value": f"https://t.me/{username}",
                    }
                )
                continue

            if target.startswith("feature:"):
                feature = target.split(":", 1)[1].lower()
                callback = FEATURE_CALLBACKS.get(feature)
                if not callback:
                    raise ValueError("Unknown feature button")
                row.append({"text": title, "type": "callback", "value": callback})
                continue

            if target.startswith("clone:"):
                feature = target.split(":", 1)[1].lower()
                if feature not in FEATURE_CALLBACKS:
                    raise ValueError("Unknown Clone Bot feature")
                row.append({"text": title, "type": "clone", "value": feature})
                continue

            supported = "/".join(FEATURE_CALLBACKS)
            raise ValueError(
                "Target must be URL, @username, feature:" + supported + ", or clone:" + supported
            )

        if row:
            rows.append(row)

    if not rows:
        raise ValueError("No buttons found")
    return rows


def build_editor_keyboard(
    rows: Iterable[Iterable[dict[str, Any]]] | None,
    *,
    callback_prefix: str = "",
    clone_username: str = "",
) -> InlineKeyboardMarkup | None:
    """Build a Telegram inline keyboard from the stored editor-button schema."""
    if not rows:
        return None

    keyboard: list[list[InlineKeyboardButton]] = []
    for row in rows:
        built: list[InlineKeyboardButton] = []
        for item in row:
            text = str(item.get("text") or "Button")
            item_type = str(item.get("type") or "callback")
            if item_type == "url":
                value = str(item.get("value") or "")
                if value:
                    built.append(InlineKeyboardButton(text, url=value))
            elif item_type == "clone":
                feature = str(item.get("value") or "home").strip().lower()
                username = str(clone_username or "").strip().lstrip("@")
                if username:
                    built.append(InlineKeyboardButton(text, url=f"https://t.me/{username}?start={feature}"))
            else:
                callback = str(item.get("value") or "c_home")
                if callback_prefix and callback.startswith("c_"):
                    callback = f"{callback_prefix}{callback}"
                built.append(InlineKeyboardButton(text, callback_data=callback))
        if built:
            keyboard.append(built)

    return InlineKeyboardMarkup(keyboard) if keyboard else None


def editor_header(title: str, item: dict[str, Any], *, variables: str = "") -> str:
    """Shared editor summary used by welcome, auto-reply, and templates."""
    button_count = sum(len(row) for row in (item.get("buttons") or []))
    media_count = len(item.get("media") or ([] if not item.get("media_file_id") else [{"file_id": item.get("media_file_id")}]))
    lines = [
        title,
        "",
        f"Status: {'🟢 Enabled' if item.get('enabled', True) else '🔴 Disabled'}",
        f"📝 Text: {'✅ Added' if item.get('text') else '❌ Not added'}",
        f"🖼 Media: {media_count}/10" if media_count else "🖼 Media: ❌ Not added",
        f"🔗 Buttons: {button_count}",
    ]
    if variables:
        lines.extend(["", f"Variables: {variables}"])
    lines.extend([
        "",
        "Use the options below to add, replace, preview, or remove each part.",
    ])
    return "\n".join(lines)


def editor_menu_keyboard(
    prefix: str,
    item: dict[str, Any],
    *,
    back_callback: str,
    allow_toggle: bool = True,
    delete_callback: str | None = None,
) -> InlineKeyboardMarkup:
    """Shared full editor keyboard with the same layout for every message type."""
    rows: list[list[InlineKeyboardButton]] = []
    if allow_toggle:
        rows.append([
            InlineKeyboardButton(
                "🔴 Disable" if item.get("enabled", True) else "🟢 Enable",
                callback_data=f"{prefix}_toggle",
            )
        ])
    rows.extend([
        [
            InlineKeyboardButton("📝 Text", callback_data=f"{prefix}_text"),
            InlineKeyboardButton("🖼 Media", callback_data=f"{prefix}_media"),
        ],
        [InlineKeyboardButton("🔗 Buttons", callback_data=f"{prefix}_buttons")],
        [InlineKeyboardButton("👁 Full Preview", callback_data=f"{prefix}_preview")],
    ])
    if delete_callback:
        rows.append([InlineKeyboardButton("🗑 Delete", callback_data=delete_callback)])
    rows.append([InlineKeyboardButton("⬅ Back", callback_data=back_callback)])
    return InlineKeyboardMarkup(rows)


def editor_text_prompt(title: str, *, variables: str = "") -> str:
    text = f"📝 {title}\n\nSend the message text. HTML formatting is supported."
    if variables:
        text += f"\n\nAvailable variables:\n{variables}"
    return text


def editor_media_prompt(title: str) -> str:
    return (
        f"🖼 {title}\n\n"
        "Send one photo/video/document, or select and send one Telegram album together. "
        "The complete message or album will replace the current media automatically (maximum 10 files).\n\n"
        "Send the complete album in one selection; it will save automatically."
    )
