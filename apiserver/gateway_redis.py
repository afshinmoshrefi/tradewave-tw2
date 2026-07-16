"""One deployment-neutral Redis factory for gateway-owned state.

API rate limits, ML quota, small derived-data caches, and scan single-flight all
use the same configured gateway Redis. The default remains local db4 for today's
co-located topology. A future split deployment sets TW2_GATEWAY_REDIS_URL and does
not change application code. Nothing here reads appserver db0 cache internals.
"""

import redis

from . import settings


def create_client():
    """Return a binary Redis client without opening a connection eagerly."""
    if settings.GATEWAY_REDIS_URL:
        return redis.Redis.from_url(
            settings.GATEWAY_REDIS_URL,
            decode_responses=False,
            socket_connect_timeout=1.0,
            socket_timeout=2.0,
            health_check_interval=30,
        )
    return redis.Redis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        db=settings.REDIS_DB,
        decode_responses=False,
        socket_connect_timeout=1.0,
        socket_timeout=2.0,
        health_check_interval=30,
    )
