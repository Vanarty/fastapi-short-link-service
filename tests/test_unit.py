"""Юнит-тесты: генерация коротких кодов, проверка истечения,
хеширование паролей, создание JWT-токенов, CacheService."""

from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from src.auth import hash_password, verify_password, create_access_token
from src.cache import CacheService
from src.config import settings
from src.routers.links import _generate_short_code, _check_expired


# ---------------------------------------------------------------------------
# _generate_short_code
# ---------------------------------------------------------------------------
class TestGenerateShortCode:
    def test_default_length(self):
        code = _generate_short_code()
        assert len(code) == settings.short_code_length

    def test_custom_length(self):
        code = _generate_short_code(length=12)
        assert len(code) == 12

    def test_alphanumeric_only(self):
        code = _generate_short_code(length=200)
        assert code.isalnum()

    def test_generates_different_codes(self):
        codes = {_generate_short_code() for _ in range(50)}
        assert len(codes) > 40


# ---------------------------------------------------------------------------
# _check_expired
# ---------------------------------------------------------------------------
class TestCheckExpired:
    def test_not_expired(self):
        link = MagicMock()  # Создаём фиктивный объект Link
        link.expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
        assert _check_expired(link) is False

    def test_expired(self):
        link = MagicMock()
        link.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
        assert _check_expired(link) is True

    def test_no_expiration(self):
        link = MagicMock()
        link.expires_at = None
        assert _check_expired(link) is False


# ---------------------------------------------------------------------------
# Хеширование паролей
# ---------------------------------------------------------------------------
class TestPasswordHashing:
    def test_hash_and_verify(self):
        hashed = hash_password("secret")
        assert verify_password("secret", hashed) is True

    def test_wrong_password(self):
        hashed = hash_password("correct")
        assert verify_password("wrong", hashed) is False

    def test_hash_differs_from_plain(self):
        assert hash_password("plain") != "plain"


# ---------------------------------------------------------------------------
# JWT-токены
# ---------------------------------------------------------------------------
class TestAccessToken:
    def test_create_token(self):
        token = create_access_token(data={"sub": "user1"})
        assert isinstance(token, str) and len(token) > 0

    def test_create_token_custom_expiry(self):
        token = create_access_token(
            data={"sub": "user1"},
            expires_delta=timedelta(minutes=5),
        )
        assert isinstance(token, str)


# ---------------------------------------------------------------------------
# CacheService (с мок-Redis)
# ---------------------------------------------------------------------------
class TestCacheService:
    async def test_connect_success(self):
        svc = CacheService()
        mock_redis = AsyncMock()
        with patch("src.cache.aioredis.from_url", return_value=mock_redis):
            await svc.connect()
        assert svc._redis is mock_redis

    async def test_connect_failure(self):
        svc = CacheService()
        with patch("src.cache.aioredis.from_url", side_effect=Exception("fail")):
            await svc.connect()
        assert svc._redis is None

    # -- без Redis (self._redis = None) --
    async def test_get_no_redis(self):
        svc = CacheService()
        assert await svc.get("k") is None

    async def test_set_no_redis(self):
        svc = CacheService()
        await svc.set("k", "v")

    async def test_delete_no_redis(self):
        svc = CacheService()
        await svc.delete("k")

    # -- с мок-Redis --
    async def test_get_with_redis(self):
        svc = CacheService()
        svc._redis = AsyncMock()
        svc._redis.get = AsyncMock(return_value="val")
        assert await svc.get("k") == "val"

    async def test_set_with_redis(self):
        svc = CacheService()
        svc._redis = AsyncMock()
        await svc.set("k", "v", ttl=60)
        svc._redis.set.assert_awaited_once_with("k", "v", ex=60)

    async def test_delete_with_redis(self):
        svc = CacheService()
        svc._redis = AsyncMock()
        await svc.delete("k")
        svc._redis.delete.assert_awaited_once_with("k")

    # -- JSON --
    async def test_get_json(self):
        svc = CacheService()
        svc._redis = AsyncMock()
        svc._redis.get = AsyncMock(return_value='{"a": 1}')
        assert await svc.get_json("k") == {"a": 1}

    async def test_get_json_none(self):
        svc = CacheService()
        svc._redis = AsyncMock()
        svc._redis.get = AsyncMock(return_value=None)
        assert await svc.get_json("k") is None

    async def test_set_json(self):
        svc = CacheService()
        svc._redis = AsyncMock()
        await svc.set_json("k", {"a": 1}, ttl=100)
        svc._redis.set.assert_awaited_once()

    # -- int --
    async def test_get_int(self):
        svc = CacheService()
        svc._redis = AsyncMock()
        svc._redis.get = AsyncMock(return_value="42")
        assert await svc.get_int("k") == 42

    async def test_get_int_none(self):
        svc = CacheService()
        svc._redis = AsyncMock()
        svc._redis.get = AsyncMock(return_value=None)
        assert await svc.get_int("k") is None

    async def test_set_int(self):
        svc = CacheService()
        svc._redis = AsyncMock()
        await svc.set_int("k", 42)
        svc._redis.set.assert_awaited_once()

    # -- disconnect --
    async def test_disconnect_with_redis(self):
        svc = CacheService()
        svc._redis = AsyncMock()
        await svc.disconnect()
        svc._redis.close.assert_awaited_once()

    async def test_disconnect_no_redis(self):
        svc = CacheService()
        await svc.disconnect()

    # -- исключения при работе с Redis --
    async def test_get_redis_error(self):
        svc = CacheService()
        svc._redis = AsyncMock()
        svc._redis.get = AsyncMock(side_effect=Exception("err"))
        assert await svc.get("k") is None

    async def test_set_redis_error(self):
        svc = CacheService()
        svc._redis = AsyncMock()
        svc._redis.set = AsyncMock(side_effect=Exception("err"))
        await svc.set("k", "v")

    async def test_delete_redis_error(self):
        svc = CacheService()
        svc._redis = AsyncMock()
        svc._redis.delete = AsyncMock(side_effect=Exception("err"))
        await svc.delete("k")
