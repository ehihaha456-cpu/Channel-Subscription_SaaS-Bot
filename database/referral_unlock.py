from datetime import datetime, timezone

from database.mongo import get_database

COLLECTION = "clone_referral_unlocks"


def _now():
    return datetime.now(timezone.utc)


async def get_referral_unlock(owner_id: int, user_id: int):
    db = get_database()
    return await db[COLLECTION].find_one({
        "owner_id": int(owner_id),
        "user_id": int(user_id),
    })


async def save_referral_unlock(owner_id: int, user_id: int, chat_id: int, invite_link: str):
    db = get_database()
    now = _now()
    await db[COLLECTION].update_one(
        {"owner_id": int(owner_id), "user_id": int(user_id)},
        {
            "$set": {
                "chat_id": int(chat_id),
                "invite_link": str(invite_link),
                "unlocked": True,
                "updated_at": now,
            },
            "$setOnInsert": {"created_at": now},
        },
        upsert=True,
    )
    return await get_referral_unlock(owner_id, user_id)
