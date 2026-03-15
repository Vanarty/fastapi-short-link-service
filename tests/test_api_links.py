"""Функциональные тесты: CRUD ссылок, редирект, поиск,
статистика, expired-эндпоинт, unused-threshold."""

from datetime import datetime, timezone, timedelta

from httpx import AsyncClient
from sqlalchemy import update

from src.models import Link


# ---------------------------------------------------------------------------
# Создание ссылок  POST /links/shorten
# ---------------------------------------------------------------------------
class TestCreateLink:
    async def test_create_anonymous(self, client: AsyncClient):
        resp = await client.post(
            "/links/shorten",
            json={"original_url": "https://example.com"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert "short_code" in data
        assert data["original_url"].startswith("https://example.com")

    async def test_create_authenticated(self, auth_client: AsyncClient):
        resp = await auth_client.post(
            "/links/shorten",
            json={"original_url": "https://authed.com"},
        )
        assert resp.status_code == 201

    async def test_create_with_custom_alias(self, client: AsyncClient):
        resp = await client.post(
            "/links/shorten",
            json={"original_url": "https://google.com", "custom_alias": "ggl"},
        )
        assert resp.status_code == 201
        assert resp.json()["short_code"] == "ggl"

    async def test_create_invalid_alias_chars(self, client: AsyncClient):
        resp = await client.post(
            "/links/shorten",
            json={"original_url": "https://example.com", "custom_alias": "bad alias!"},
        )
        assert resp.status_code == 400

    async def test_create_duplicate_alias(self, auth_client: AsyncClient):
        await auth_client.post(
            "/links/shorten",
            json={"original_url": "https://a.com", "custom_alias": "dup"},
        )
        resp = await auth_client.post(
            "/links/shorten",
            json={"original_url": "https://b.com", "custom_alias": "dup"},
        )
        assert resp.status_code == 409

    async def test_create_with_expiration(self, auth_client: AsyncClient):
        future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        resp = await auth_client.post(
            "/links/shorten",
            json={"original_url": "https://temp.com", "expires_at": future},
        )
        assert resp.status_code == 201
        assert resp.json()["expires_at"] is not None

    async def test_create_invalid_url(self, client: AsyncClient):
        resp = await client.post(
            "/links/shorten",
            json={"original_url": "not-a-url"},
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Редирект  GET /links/{short_code}
# ---------------------------------------------------------------------------
class TestRedirect:
    async def test_redirect_success(self, client: AsyncClient):
        create = await client.post(
            "/links/shorten",
            json={"original_url": "https://example.com"},
        )
        code = create.json()["short_code"]
        resp = await client.get(f"/links/{code}", follow_redirects=False)
        assert resp.status_code == 307
        assert "example.com" in resp.headers["location"]

    async def test_redirect_not_found(self, client: AsyncClient):
        resp = await client.get("/links/nope999", follow_redirects=False)
        assert resp.status_code == 404

    async def test_redirect_expired(self, client: AsyncClient):
        past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        create = await client.post(
            "/links/shorten",
            json={"original_url": "https://expired.com", "expires_at": past},
        )
        code = create.json()["short_code"]
        resp = await client.get(f"/links/{code}", follow_redirects=False)
        assert resp.status_code == 410

    async def test_redirect_increments_clicks(self, client: AsyncClient):
        await client.post(
            "/links/shorten",
            json={"original_url": "https://clicks.com", "custom_alias": "clk"},
        )
        await client.get("/links/clk", follow_redirects=False)
        await client.get("/links/clk", follow_redirects=False)
        stats = await client.get("/links/clk/stats")
        assert stats.json()["click_count"] == 2

    async def test_redirect_not_cached(self, client: AsyncClient, test_cache):
        """Редирект без попадания в кэш (путь через БД)."""
        await client.post(
            "/links/shorten",
            json={"original_url": "https://nocache.com", "custom_alias": "nc1"},
        )
        test_cache.clear()
        resp = await client.get("/links/nc1", follow_redirects=False)
        assert resp.status_code == 307

    async def test_redirect_expired_not_cached(self, client: AsyncClient, test_cache):
        """Истекшая ссылка без кэша."""
        past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        create = await client.post(
            "/links/shorten",
            json={"original_url": "https://expnc.com", "expires_at": past},
        )
        code = create.json()["short_code"]
        test_cache.clear()
        resp = await client.get(f"/links/{code}", follow_redirects=False)
        assert resp.status_code == 410

    async def test_redirect_cached_but_expired(self, client: AsyncClient, db_session):
        """Ссылка в кэше, но уже истекла → 410 и удаление из кэша."""
        future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        create = await client.post(
            "/links/shorten",
            json={
                "original_url": "https://willexp.com",
                "custom_alias": "cexp",
                "expires_at": future,
            },
        )
        await client.get("/links/cexp", follow_redirects=False)

        await db_session.execute(
            update(Link)
            .where(Link.short_code == "cexp")
            .values(expires_at=datetime.now(timezone.utc) - timedelta(hours=1))
        )
        await db_session.commit()

        resp = await client.get("/links/cexp", follow_redirects=False)
        assert resp.status_code == 410

    async def test_root_redirect(self, client: AsyncClient):
        """GET /{short_code} перенаправляет на /links/{short_code}."""
        await client.post(
            "/links/shorten",
            json={"original_url": "https://root.com", "custom_alias": "rt1"},
        )
        resp = await client.get("/rt1", follow_redirects=False)
        assert resp.status_code == 307


# ---------------------------------------------------------------------------
# Обновление  PUT /links/{short_code}
# ---------------------------------------------------------------------------
class TestUpdateLink:
    async def test_update_success(self, auth_client: AsyncClient):
        await auth_client.post(
            "/links/shorten",
            json={"original_url": "https://old.com", "custom_alias": "upd"},
        )
        resp = await auth_client.put(
            "/links/upd",
            json={"original_url": "https://new.com"},
        )
        assert resp.status_code == 200
        assert "new.com" in resp.json()["original_url"]

    async def test_update_not_found(self, auth_client: AsyncClient):
        resp = await auth_client.put(
            "/links/missing",
            json={"original_url": "https://new.com"},
        )
        assert resp.status_code == 404

    async def test_update_unauthorized(self, client: AsyncClient):
        resp = await client.put(
            "/links/any",
            json={"original_url": "https://new.com"},
        )
        assert resp.status_code == 401

    async def test_update_forbidden_anonymous_link(self, client: AsyncClient):
        """Попытка обновить анонимную ссылку авторизованным пользователем."""
        await client.post(
            "/links/shorten",
            json={"original_url": "https://anon.com", "custom_alias": "anon1"},
        )
        await client.post(
            "/users/register",
            json={"username": "other", "password": "pass"},
        )
        login = await client.post(
            "/users/login",
            data={"username": "other", "password": "pass"},
        )
        token = login.json()["access_token"]
        resp = await client.put(
            "/links/anon1",
            json={"original_url": "https://changed.com"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403

    async def test_update_other_users_link(self, client: AsyncClient):
        """Попытка обновить чужую ссылку → 403."""
        await client.post(
            "/users/register", json={"username": "userA", "password": "p"}
        )
        tok_a = (
            await client.post(
                "/users/login", data={"username": "userA", "password": "p"}
            )
        ).json()["access_token"]
        await client.post(
            "/links/shorten",
            json={"original_url": "https://owner.com", "custom_alias": "own1"},
            headers={"Authorization": f"Bearer {tok_a}"},
        )

        await client.post(
            "/users/register", json={"username": "userB", "password": "p"}
        )
        tok_b = (
            await client.post(
                "/users/login", data={"username": "userB", "password": "p"}
            )
        ).json()["access_token"]
        resp = await client.put(
            "/links/own1",
            json={"original_url": "https://hacked.com"},
            headers={"Authorization": f"Bearer {tok_b}"},
        )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Удаление  DELETE /links/{short_code}
# ---------------------------------------------------------------------------
class TestDeleteLink:
    async def test_delete_success(self, auth_client: AsyncClient):
        await auth_client.post(
            "/links/shorten",
            json={"original_url": "https://del.com", "custom_alias": "del1"},
        )
        resp = await auth_client.delete("/links/del1")
        assert resp.status_code == 204
        check = await auth_client.get("/links/del1", follow_redirects=False)
        assert check.status_code == 404

    async def test_delete_unauthorized(self, client: AsyncClient):
        resp = await client.delete("/links/any")
        assert resp.status_code == 401

    async def test_delete_not_found(self, auth_client: AsyncClient):
        resp = await auth_client.delete("/links/missing")
        assert resp.status_code == 404

    async def test_delete_forbidden(self, client: AsyncClient):
        """Попытка удалить анонимную ссылку авторизованным пользователем."""
        await client.post(
            "/links/shorten",
            json={"original_url": "https://forbid.com", "custom_alias": "fb1"},
        )
        await client.post(
            "/users/register", json={"username": "deluser", "password": "p"}
        )
        tok = (
            await client.post(
                "/users/login", data={"username": "deluser", "password": "p"}
            )
        ).json()["access_token"]
        resp = await client.delete(
            "/links/fb1",
            headers={"Authorization": f"Bearer {tok}"},
        )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Поиск  GET /links/search
# ---------------------------------------------------------------------------
class TestSearchLink:
    async def test_search_found(self, client: AsyncClient):
        await client.post(
            "/links/shorten",
            json={"original_url": "https://searchme.com"},
        )
        resp = await client.get(
            "/links/search",
            params={"original_url": "https://searchme.com/"},
        )
        assert resp.status_code == 200

    async def test_search_not_found(self, client: AsyncClient):
        resp = await client.get(
            "/links/search",
            params={"original_url": "https://nowhere.com"},
        )
        assert resp.status_code == 404

    async def test_search_expired(self, client: AsyncClient):
        past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        await client.post(
            "/links/shorten",
            json={"original_url": "https://oldsearch.com", "expires_at": past},
        )
        resp = await client.get(
            "/links/search",
            params={"original_url": "https://oldsearch.com/"},
        )
        assert resp.status_code == 410

    async def test_search_cached(self, client: AsyncClient):
        """Повторный поиск берёт short_code из кэша."""
        await client.post(
            "/links/shorten",
            json={"original_url": "https://cachesearch.com"},
        )
        await client.get(
            "/links/search",
            params={"original_url": "https://cachesearch.com/"},
        )
        resp = await client.get(
            "/links/search",
            params={"original_url": "https://cachesearch.com/"},
        )
        assert resp.status_code == 200

    async def test_search_cached_but_expired(self, client: AsyncClient, db_session):
        """Кэш есть, но ссылка истекла → фолбэк к БД → 410."""
        future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        await client.post(
            "/links/shorten",
            json={
                "original_url": "https://willexp-search.com",
                "custom_alias": "ws1",
                "expires_at": future,
            },
        )
        await client.get(
            "/links/search",
            params={"original_url": "https://willexp-search.com/"},
        )
        await db_session.execute(
            update(Link)
            .where(Link.short_code == "ws1")
            .values(expires_at=datetime.now(timezone.utc) - timedelta(hours=1))
        )
        await db_session.commit()

        resp = await client.get(
            "/links/search",
            params={"original_url": "https://willexp-search.com/"},
        )
        assert resp.status_code == 410


# ---------------------------------------------------------------------------
# Статистика  GET /links/{short_code}/stats
# ---------------------------------------------------------------------------
class TestLinkStats:
    async def test_stats_success(self, client: AsyncClient):
        await client.post(
            "/links/shorten",
            json={"original_url": "https://stats.com", "custom_alias": "st1"},
        )
        resp = await client.get("/links/st1/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["short_code"] == "st1"
        assert data["click_count"] == 0

    async def test_stats_not_found(self, client: AsyncClient):
        resp = await client.get("/links/nope/stats")
        assert resp.status_code == 404

    async def test_stats_expired(self, client: AsyncClient):
        past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        await client.post(
            "/links/shorten",
            json={
                "original_url": "https://statexp.com",
                "custom_alias": "stexp",
                "expires_at": past,
            },
        )
        resp = await client.get("/links/stexp/stats")
        assert resp.status_code == 410

    async def test_stats_cached(self, client: AsyncClient):
        """Повторный запрос статистики берётся из кэша."""
        await client.post(
            "/links/shorten",
            json={"original_url": "https://stcache.com", "custom_alias": "stc"},
        )
        await client.get("/links/stc/stats")
        resp = await client.get("/links/stc/stats")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Expired-ссылки  GET /links/expired
# ---------------------------------------------------------------------------
class TestExpiredLinks:
    async def test_expired_links_unauthorized(self, client: AsyncClient):
        resp = await client.get("/links/expired")
        assert resp.status_code == 401

    async def test_expired_links_success(self, auth_client: AsyncClient):
        resp = await auth_client.get("/links/expired")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)


# ---------------------------------------------------------------------------
# Unused-threshold  PUT /links/unused-threshold
# ---------------------------------------------------------------------------
class TestUnusedThreshold:
    async def test_set_threshold_success(self, auth_client: AsyncClient):
        resp = await auth_client.put(
            "/links/unused-threshold", params={"days": 30}
        )
        assert resp.status_code == 200

    async def test_set_threshold_unauthorized(self, client: AsyncClient):
        resp = await client.put(
            "/links/unused-threshold", params={"days": 30}
        )
        assert resp.status_code == 401

    async def test_set_threshold_zero(self, auth_client: AsyncClient):
        resp = await auth_client.put(
            "/links/unused-threshold", params={"days": 0}
        )
        assert resp.status_code == 422

    async def test_set_threshold_negative(self, auth_client: AsyncClient):
        resp = await auth_client.put(
            "/links/unused-threshold", params={"days": -5}
        )
        assert resp.status_code == 422
