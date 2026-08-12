from __future__ import annotations

from typing import Any, Iterable
from urllib.parse import quote

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

try:
    from telegram import CopyTextButton
except Exception:  # compatibility fallback
    CopyTextButton = None


def group_buttons_header() -> str:
    return (
        "👉 Set the buttons to be placed under the message\n"
        "Send a message structured as follows:\n\n"
        "• Add a single button:\n"
        "Button title - t.me/LinkExample\n\n"
        "• Add multiple buttons on a single line:\n"
        "Button title - t.me/LinkExample && Button text - t.me/LinkExample\n\n"
        "• Add multiple rows of buttons:\n"
        "Button title - t.me/LinkExample\n"
        "Button title - t.me/LinkExample\n\n"
        "Special buttons\n\n"
        "• Add a button that shows a popup:\n"
        "Button title - popup: Popup text\n"
        "or\n"
        "Button title - alert: Popup text\n\n"
        "• Add a button with a link to the group rules:\n"
        "Button title - rules\n\n"
        "• Add a share button:\n"
        "Button title - share: Text to be shared\n\n"
        "• Add a button with copyable text:\n"
        "Button title - copy: Text copied on click"
    )


def parse_group_buttons(text: str) -> list[list[dict[str, str]]]:
    rows: list[list[dict[str, str]]] = []

    for raw_line in (text or "").splitlines():
        raw_line = raw_line.strip()
        if not raw_line:
            continue

        row: list[dict[str, str]] = []
        for chunk in raw_line.split("&&"):
            chunk = chunk.strip()
            if " - " not in chunk:
                raise ValueError("Use: Button title - target")

            title, target = [part.strip() for part in chunk.split(" - ", 1)]
            if not title or not target:
                raise ValueError("Button title and target required")

            lower = target.lower()

            if target.startswith(("http://", "https://", "tg://")) or lower.startswith("t.me/"):
                if lower.startswith("t.me/"):
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
                    raise ValueError("Invalid Telegram username")
                row.append({
                    "text": title,
                    "type": "url",
                    "value": f"https://t.me/{username}",
                })
                continue

            if lower.startswith("popup:"):
                value = target.split(":", 1)[1].strip()
                if not value:
                    raise ValueError("Popup text required")
                row.append({"text": title, "type": "popup", "value": value})
                continue

            if lower.startswith("alert:"):
                value = target.split(":", 1)[1].strip()
                if not value:
                    raise ValueError("Alert text required")
                row.append({"text": title, "type": "alert", "value": value})
                continue

            if lower == "rules":
                row.append({"text": title, "type": "rules", "value": "rules"})
                continue

            if lower.startswith("share:"):
                value = target.split(":", 1)[1].strip()
                if not value:
                    raise ValueError("Share text required")
                row.append({"text": title, "type": "share", "value": value})
                continue

            if lower.startswith("copy:"):
                value = target.split(":", 1)[1].strip()
                if not value:
                    raise ValueError("Copy text required")
                row.append({"text": title, "type": "copy", "value": value})
                continue

            raise ValueError(
                "Target must be URL, @username, popup:, alert:, rules, share:, or copy:"
            )

        if row:
            rows.append(row)

    if not rows:
        raise ValueError("No buttons found")
    return rows


def build_group_keyboard(
    rows: Iterable[Iterable[dict[str, Any]]] | None,
    *,
    item_key: str,
    preview_group_id: int | None = None,
) -> InlineKeyboardMarkup | None:
    if not rows:
        return None

    keyboard: list[list[InlineKeyboardButton]] = []
    for row_index, row in enumerate(rows):
        built: list[InlineKeyboardButton] = []
        for col_index, item in enumerate(row):
            title = str(item.get("text") or "Button")
            typ = str(item.get("type") or "url")
            value = str(item.get("value") or "")

            if typ == "url":
                if value:
                    built.append(InlineKeyboardButton(title, url=value))
                continue

            if typ == "share":
                share_url = "https://t.me/share/url?url=&text=" + quote(value)
                built.append(InlineKeyboardButton(title, url=share_url))
                continue

            if typ == "copy" and CopyTextButton is not None:
                try:
                    built.append(
                        InlineKeyboardButton(
                            title,
                            copy_text=CopyTextButton(text=value),
                        )
                    )
                    continue
                except Exception:
                    pass

            # popup / alert / rules / copy fallback use callback query.
            if preview_group_id is None:
                callback = f"gmsp_{item_key}_{row_index}_{col_index}"
            else:
                callback = f"gmspv_{int(preview_group_id)}_{item_key}_{row_index}_{col_index}"
            built.append(InlineKeyboardButton(title, callback_data=callback[:64]))

        if built:
            keyboard.append(built)

    return InlineKeyboardMarkup(keyboard) if keyboard else None


def find_button(item: dict[str, Any], row_index: int, col_index: int) -> dict[str, Any] | None:
    rows = item.get("buttons") or []
    try:
        return rows[int(row_index)][int(col_index)]
    except (IndexError, TypeError, ValueError):
        return None
