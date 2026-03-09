from typing import Tuple


class RateLimiter:
    """
    Token-bucket rate limiting by IP and/or user to prevent brute force.
    Backed by Redis for atomic, distributed counting. Works alongside
    device trust.
    """

    def __init__(self, redis_client):
        self.redis = redis_client

    async def check_rate_limit(
        self, identifier: str, max_attempts: int = 5, window_seconds: int = 300
    ) -> Tuple[bool, int, int]:
        """
        Check if the identifier (IP or username) has exceeded the rate limit.

        Uses a Lua script executed atomically on Redis so the GET → compare →
        INCR sequence is not subject to race conditions between concurrent
        requests from the same identifier.

        Args:
            identifier:      Unique string to rate-limit (IP address, username, etc.)
            max_attempts:    Maximum allowed attempts in the window.
            window_seconds:  Sliding window size in seconds.

        Returns:
            Tuple of (is_allowed, remaining_attempts, retry_after_seconds).
            ``retry_after_seconds`` is 0 when the request is allowed,
            and the TTL of the rate-limit key when it is blocked — so callers
            can set a ``Retry-After`` response header.
        """
        key = f"rate_limit:{identifier}"

        # FIX: was a non-atomic GET → compare → INCR sequence.
        # Two concurrent requests from the same IP can both read the same
        # counter value before either increments it, allowing both through
        # even when one should be blocked.
        #
        # The Lua script below runs atomically on Redis:
        #   1. INCR the counter (creates it at 1 if absent).
        #   2. On first creation (count == 1), set the TTL.
        #   3. Return [count, ttl].
        lua_script = """
local key = KEYS[1]
local max = tonumber(ARGV[1])
local window = tonumber(ARGV[2])

local count = redis.call('INCR', key)
if count == 1 then
    redis.call('EXPIRE', key, window)
end
local ttl = redis.call('TTL', key)
return {count, ttl}
"""
        result = await self.redis.eval(
            lua_script, 1, key, str(max_attempts), str(window_seconds)
        )
        count, ttl = int(result[0]), int(result[1])

        if count > max_attempts:
            # FIX: was returning (False, 0) with no TTL — callers had no way
            # to set a correct Retry-After header. Now return the remaining TTL.
            retry_after = max(ttl, 0)
            return False, 0, retry_after

        remaining = max_attempts - count
        return True, remaining, 0