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

            supported = "/".join(FEATURE_CALLBACKS)
            raise ValueError(
                "Target must be URL, @username, or feature:" + supported
            )

        if row:
            rows.append(row)

    if not rows:
        raise ValueError("No buttons found")
    return rows


def build_editor_keyboard(
    rows: Iterable[Iterable[dict[str, Any]]] | None,
) -> InlineKeyboardMarkup | None:
    """Build a Telegram inline keyboard from the stored editor-button schema."""
    if not rows:
        return None

    keyboard: list[list[InlineKeyboardButton]] = []
    for row in rows:
        built: list[InlineKeyboardButton] = []
        for item in row:
            text = str(item.get("text") or "Button")
            if item.get("type") == "url":
                value = str(item.get("value") or "")
                if value:
                    built.append(InlineKeyboardButton(text, url=value))
            else:
                callback = str(item.get("value") or "c_home")
                built.append(InlineKeyboardButton(text, callback_data=callback))
        if built:
            keyboard.append(built)

    return InlineKeyboardMarkup(keyboard) if keyboard else None
