# cache system
from app.core.cache import cache

# Automatically uses Redis if available, falls back to memory
await cache.set("key", "value", ttl=300)

@cached(ttl=300, key_prefix="user")
async def get_user(db, user_id):
    return await db.get(User, user_id)

@cache_invalidate("user:*", "users:list")
async def update_user(db, user_id, data):
    return await db.update(User, user_id, data)

user = await cache.get_or_set(
    key=f"user:{user_id}",
    factory=lambda: get_user_from_db(user_id),
    ttl=300
)

# Invalidate all user caches
await cache.delete_pattern("user:*")

# Invalidate specific patterns
await cache.delete_pattern("posts:user:123:*")
