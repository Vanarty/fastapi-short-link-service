import json
import logging
from typing import Optional

import redis.asyncio as aioredis

from src.config import settings

logger = logging.getLogger(__name__)


class CacheService:
    """Обертка над Redis для кэширования данных ссылок."""

    def __init__(self):
        self._redis: Optional[aioredis.Redis] = None

    async def connect(self):
        try:
            self._redis = aioredis.from_url(
                settings.redis_url, decode_responses=True
            )
            await self._redis.ping()
            logger.info("Redis подключен")
        except Exception as e:
            logger.warning("Не удалось подключиться к Redis: %s", e)
            self._redis = None

    async def disconnect(self):
        if self._redis:
            await self._redis.close()

    async def get(self, key: str) -> Optional[str]:
        if not self._redis:
            return None
        try:
            return await self._redis.get(key)
        except Exception:
            return None

    async def set(self, key: str, value: str, ttl: Optional[int] = None):
        if not self._redis:
            return
        try:
            await self._redis.set(key, value, ex=ttl or settings.cache_ttl_seconds)
        except Exception:
            pass

    async def delete(self, key: str):
        if not self._redis:
            return
        try:
            await self._redis.delete(key)
        except Exception:
            pass

    async def get_json(self, key: str) -> Optional[dict]:
        raw = await self.get(key)
        if raw:
            return json.loads(raw)
        return None

    async def set_json(self, key: str, value: dict, ttl: Optional[int] = None):
        await self.set(key, json.dumps(value, default=str), ttl)

    async def get_int(self, key: str) -> Optional[int]:
        raw = await self.get(key)
        if raw is not None:
            return int(raw)
        return None

    async def set_int(self, key: str, value: int):
        await self.set(key, str(value))


cache = CacheService()
