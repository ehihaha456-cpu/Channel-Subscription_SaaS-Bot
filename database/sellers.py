from datetime import datetime, timezone

from database.mongo import get_database

COLLECTION = "sellers"


def sellers_collection():
    return get_database()[COLLECTION]


async def get_seller(owner_id: int):
    return await sellers_collection().find_one({"owner_id": owner_id})


async def create_seller(owner_id: int, first_name=None, username=None):
    now = datetime.now(timezone.utc)

    document = {
        "owner_id": owner_id,
        "first_name": first_name,
        "username": username,
        "active": False,
        "approved": False,
        "suspended": False,
        "plan": None,
        "expiry_date": None,
        "created_at": now,
        "updated_at": now,
    }

    await sellers_collection().insert_one(document)
    return document


async def get_or_create_seller(user):
    seller = await get_seller(user.id)

    if seller:
        return seller

    return await create_seller(
        owner_id=user.id,
        first_name=user.first_name,
        username=user.username,
    )


async def approve_seller(owner_id: int):
    await sellers_collection().update_one(
        {"owner_id": owner_id},
        {
            "$set": {
                "approved": True,
                "active": True,
                "suspended": False,
                "updated_at": datetime.now(timezone.utc),
            }
        },
    )


async def suspend_seller(owner_id: int):
    await sellers_collection().update_one(
        {"owner_id": owner_id},
        {
            "$set": {
                "suspended": True,
                "active": False,
                "updated_at": datetime.now(timezone.utc),
            }
        },
    )


async def unsuspend_seller(owner_id: int):
    await sellers_collection().update_one(
        {"owner_id": owner_id},
        {
            "$set": {
                "suspended": False,
                "active": True,
                "updated_at": datetime.now(timezone.utc),
            }
        },
    )


async def get_all_sellers():
    return await sellers_collection().find().to_list(length=None)


async def total_sellers():
    return await sellers_collection().count_documents({})

async def find_seller_by_identifier(identifier):
    """Find a seller by Telegram ID or username across current and legacy records.

    Older records may contain numeric IDs as strings or use alternate field names,
    so the owner search must not depend on one exact schema/type.
    """
    raw = str(identifier or "").strip()
    if not raw:
        return None

    username = raw[1:] if raw.startswith("@") else raw
    username = username.strip().lstrip("@").strip()
    collection = sellers_collection()

    # Telegram numeric ID: support both integer and string values plus legacy keys.
    if raw.lstrip("+").isdigit():
        try:
            numeric_id = int(raw)
        except (TypeError, ValueError):
            numeric_id = None
        if numeric_id is not None:
            id_variants = [numeric_id, str(numeric_id)]
            seller = await collection.find_one({
                "$or": [
                    {"owner_id": {"$in": id_variants}},
                    {"user_id": {"$in": id_variants}},
                    {"seller_id": {"$in": id_variants}},
                    {"telegram_id": {"$in": id_variants}},
                    {"telegram_user_id": {"$in": id_variants}},
                    {"id": {"$in": id_variants}},
                ]
            })
            if seller:
                return seller

    # Username search: accept @username / username, mixed case, and legacy fields.
    if username and not any(ch.isspace() for ch in username):
        import re
        exact = {"$regex": f"^{re.escape(username)}$", "$options": "i"}
        at_exact = {"$regex": f"^@?{re.escape(username)}$", "$options": "i"}
        seller = await collection.find_one({
            "$or": [
                {"username": at_exact},
                {"username_normalized": {"$regex": f"^{re.escape(username.lower())}$", "$options": "i"}},
                {"telegram_username": at_exact},
                {"user.username": at_exact},
                {"profile.username": at_exact},
            ]
        })
        if seller:
            return seller

    return None

