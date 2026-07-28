"""Remember where a subscriber last contacted Business Automation.

Used to mirror subscription invite links into the connected Normal/Business
account chat when the clone-bot DM is blocked or unavailable.
"""

from __future__ import annotations

from datetime import datetime, timezone

from database.mongo import get_database

COLLECTION = "business_automation_contact_routes"


def _col():
    return get_database()[COLLECTION]


def _now():
    return datetime.now(timezone.utc)


async def record_business_contact(
    owner_id: int,
    user_id: int,
    *,
    mode: str,
    account_user_id: int = 0,
    connection_id: str = "",
    chat_id: int = 0,
) -> None:
    """Upsert the latest route for one subscriber and connected account."""
    mode = str(mode or "").strip().lower()
    if mode not in {"normal", "official"}:
        return
    key = {
        "owner_id": int(owner_id),
        "user_id": int(user_id),
        "mode": mode,
        "account_user_id": int(account_user_id or 0),
        "connection_id": str(connection_id or ""),
    }
    await _col().update_one(
        key,
        {
            "$set": {
                **key,
                "chat_id": int(chat_id or user_id),
                "updated_at": _now(),
            },
            "$setOnInsert": {"created_at": _now()},
        },
        upsert=True,
    )


async def list_business_contact_routes(owner_id: int, user_id: int) -> list[dict]:
    cursor = _col().find(
        {"owner_id": int(owner_id), "user_id": int(user_id)},
        {"_id": 0},
    ).sort("updated_at", -1)
    return await cursor.to_list(length=20)
