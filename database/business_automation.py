"""Separate MongoDB storage for Business Automation message editors.

Welcome message, auto reply, and reply templates intentionally use separate
collections. Seller-wide runtime switches remain in seller settings.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from database.mongo import get_database

WELCOME_COLLECTION = "business_automation_welcome"
AUTO_REPLY_COLLECTION = "business_automation_auto_reply"
TEMPLATE_COLLECTION = "business_automation_reply_templates"


def _now():
    return datetime.now(timezone.utc)


def _collection(name: str):
    """Return the initialized MongoDB collection.

    ``get_database`` is synchronous; awaiting it caused every Business
    Automation editor callback to fail before rendering.
    """
    return get_database()[name]


async def get_business_welcome(owner_id: int) -> dict:
    col = _collection(WELCOME_COLLECTION)
    doc = await col.find_one({"owner_id": int(owner_id)}, {"_id": 0})
    if doc:
        if not doc.get("media") and doc.get("media_file_id"):
            doc["media"] = [{"type": str(doc.get("media_type") or ""), "file_id": str(doc.get("media_file_id") or "")}]
        return doc
    # One-time transparent migration from the previous seller-settings fields.
    from database.seller_data import get_seller_settings
    legacy = await get_seller_settings(owner_id)
    item = {
        "owner_id": int(owner_id),
        "enabled": bool(legacy.get("business_welcome_enabled", True)),
        "text": str(legacy.get("business_welcome_message") or ""),
        "media_type": str(legacy.get("business_welcome_media_type") or ""),
        "media_file_id": str(legacy.get("business_welcome_media_file_id") or ""),
        "media": ([{"type": str(legacy.get("business_welcome_media_type") or ""), "file_id": str(legacy.get("business_welcome_media_file_id") or "")}] if legacy.get("business_welcome_media_file_id") else []),
        "buttons": legacy.get("business_welcome_buttons") or [],
    }
    if item["text"] or item["media_file_id"] or item["buttons"]:
        return await update_business_welcome(owner_id, **{k: v for k, v in item.items() if k != "owner_id"})
    return item


async def update_business_welcome(owner_id: int, **fields) -> dict:
    allowed = {"enabled", "text", "media_type", "media_file_id", "media", "buttons"}
    payload = {k: v for k, v in fields.items() if k in allowed}
    payload["updated_at"] = _now()
    col = _collection(WELCOME_COLLECTION)
    await col.update_one(
        {"owner_id": int(owner_id)},
        {"$set": payload, "$setOnInsert": {"created_at": _now()}},
        upsert=True,
    )
    return await get_business_welcome(owner_id)


async def get_business_auto_reply(owner_id: int) -> dict:
    col = _collection(AUTO_REPLY_COLLECTION)
    doc = await col.find_one({"owner_id": int(owner_id)}, {"_id": 0})
    if doc:
        if not doc.get("media") and doc.get("media_file_id"):
            doc["media"] = [{"type": str(doc.get("media_type") or ""), "file_id": str(doc.get("media_file_id") or "")}]
        return doc
    from database.seller_data import get_seller_settings
    legacy = await get_seller_settings(owner_id)
    item = {
        "owner_id": int(owner_id),
        "enabled": bool(legacy.get("business_auto_reply_enabled", True)),
        "text": str(legacy.get("business_auto_reply_message") or ""),
        "media_type": str(legacy.get("business_auto_reply_media_type") or ""),
        "media_file_id": str(legacy.get("business_auto_reply_media_file_id") or ""),
        "media": ([{"type": str(legacy.get("business_auto_reply_media_type") or ""), "file_id": str(legacy.get("business_auto_reply_media_file_id") or "")}] if legacy.get("business_auto_reply_media_file_id") else []),
        "buttons": legacy.get("business_auto_reply_buttons") or [],
    }
    if item["text"] or item["media_file_id"] or item["buttons"]:
        return await update_business_auto_reply(owner_id, **{k: v for k, v in item.items() if k != "owner_id"})
    return item


async def update_business_auto_reply(owner_id: int, **fields) -> dict:
    allowed = {"enabled", "text", "media_type", "media_file_id", "media", "buttons"}
    payload = {k: v for k, v in fields.items() if k in allowed}
    payload["updated_at"] = _now()
    col = _collection(AUTO_REPLY_COLLECTION)
    await col.update_one(
        {"owner_id": int(owner_id)},
        {"$set": payload, "$setOnInsert": {"created_at": _now()}},
        upsert=True,
    )
    return await get_business_auto_reply(owner_id)


async def list_business_reply_templates(owner_id: int) -> list[dict]:
    col = _collection(TEMPLATE_COLLECTION)
    cursor = col.find({"owner_id": int(owner_id)}, {"_id": 0}).sort("created_at", 1)
    docs = [doc async for doc in cursor]
    for doc in docs:
        if not doc.get("media") and doc.get("media_file_id"):
            doc["media"] = [{"type": str(doc.get("media_type") or ""), "file_id": str(doc.get("media_file_id") or "")}]
    if docs:
        return docs
    from database.seller_data import get_seller_settings
    legacy = await get_seller_settings(owner_id)
    for old in legacy.get("business_reply_templates") or []:
        if not isinstance(old, dict):
            continue
        created = await create_business_reply_template(
            owner_id,
            str(old.get("shortcut") or "template"),
            str(old.get("name") or old.get("shortcut") or "Template"),
        )
        await update_business_reply_template(
            owner_id,
            created["template_id"],
            text=str(old.get("text") or ""),
            media_type=str(old.get("media_type") or ""),
            media_file_id=str(old.get("media_file_id") or ""),
            buttons=old.get("buttons") or [],
        )
    if legacy.get("business_reply_templates"):
        cursor = col.find({"owner_id": int(owner_id)}, {"_id": 0}).sort("created_at", 1)
        return [doc async for doc in cursor]
    return []


async def get_business_reply_template(owner_id: int, template_id: str) -> dict | None:
    col = _collection(TEMPLATE_COLLECTION)
    doc = await col.find_one(
        {"owner_id": int(owner_id), "template_id": str(template_id)},
        {"_id": 0},
    )
    if doc and not doc.get("media") and doc.get("media_file_id"):
        doc["media"] = [{"type": str(doc.get("media_type") or ""), "file_id": str(doc.get("media_file_id") or "")}]
    return doc


async def create_business_reply_template(owner_id: int, shortcut: str, name: str) -> dict:
    doc = {
        "owner_id": int(owner_id),
        "template_id": uuid4().hex[:12],
        "shortcut": shortcut[:64],
        "name": name[:80],
        "text": "",
        "media_type": "",
        "media_file_id": "",
        "media": [],
        "buttons": [],
        "created_at": _now(),
        "updated_at": _now(),
    }
    col = _collection(TEMPLATE_COLLECTION)
    await col.insert_one(doc)
    doc.pop("_id", None)
    return doc


async def update_business_reply_template(owner_id: int, template_id: str, **fields) -> dict | None:
    allowed = {"shortcut", "name", "text", "media_type", "media_file_id", "media", "buttons"}
    payload = {k: v for k, v in fields.items() if k in allowed}
    payload["updated_at"] = _now()
    col = _collection(TEMPLATE_COLLECTION)
    await col.update_one(
        {"owner_id": int(owner_id), "template_id": str(template_id)},
        {"$set": payload},
    )
    return await get_business_reply_template(owner_id, template_id)


async def delete_business_reply_template(owner_id: int, template_id: str) -> bool:
    col = _collection(TEMPLATE_COLLECTION)
    result = await col.delete_one({"owner_id": int(owner_id), "template_id": str(template_id)})
    return bool(result.deleted_count)
