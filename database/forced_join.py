from datetime import datetime, timezone
from database.mongo import get_database

COLLECTION = "seller_forced_join"

def c():
    return get_database()[COLLECTION]

def now():
    return datetime.now(timezone.utc)

async def upsert_required(owner_id, chat_id, title, chat_type, invite_link=""):
    key={"owner_id":int(owner_id),"chat_id":int(chat_id)}
    await c().update_one(
        key,
        {"$set":{
            "owner_id":int(owner_id),"chat_id":int(chat_id),
            "title":title or "Group/Channel","chat_type":chat_type,
            "invite_link":invite_link or "","enabled":True,"updated_at":now()
        },"$setOnInsert":{"created_at":now()}},
        upsert=True,
    )
    return await c().find_one(key)

async def list_required(owner_id):
    return await c().find({"owner_id":int(owner_id)}).sort("title",1).to_list(length=200)

async def get_required(owner_id, chat_id):
    return await c().find_one({"owner_id":int(owner_id),"chat_id":int(chat_id)})

async def toggle_required(owner_id, chat_id):
    doc=await get_required(owner_id,chat_id)
    if not doc: return None
    enabled=not bool(doc.get("enabled",True))
    await c().update_one({"_id":doc["_id"]},{"$set":{"enabled":enabled,"updated_at":now()}})
    return await get_required(owner_id,chat_id)

async def remove_required(owner_id, chat_id):
    await c().delete_one({"owner_id":int(owner_id),"chat_id":int(chat_id)})

async def update_invite(owner_id, chat_id, invite_link):
    await c().update_one(
        {"owner_id":int(owner_id),"chat_id":int(chat_id)},
        {"$set":{"invite_link":invite_link or "","updated_at":now()}},
    )
