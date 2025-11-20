class RateLimiter:
    """
    Rate limiting by IP and user to prevent brute force.
    Works alongside device trust.
    """

    def __init__(self, redis_client):
        self.redis = redis_client

    async def check_rate_limit(
        self, identifier: str, max_attempts: int = 5, window_seconds: int = 300
    ) -> tuple[bool, int]:
        """
        Check if identifier (IP or user) has exceeded rate limit.
        Returns (is_allowed, remaining_attempts)
        """
        key = f"rate_limit:{identifier}"
        current = await self.redis.get(key)

        if current is None:
            await self.redis.setex(key, window_seconds, 1)
            return True, max_attempts - 1

        current = int(current)
        if current >= max_attempts:
            ttl = await self.redis.ttl(key)
            return False, 0

        await self.redis.incr(key)
        return True, max_attempts - current - 1
