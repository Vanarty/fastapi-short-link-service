"""Функциональные тесты: регистрация, логин, авторизация."""

from httpx import AsyncClient


class TestRegister:
    async def test_register_success(self, client: AsyncClient):
        resp = await client.post(
            "/users/register",
            json={"username": "newuser", "password": "pass123"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["username"] == "newuser"
        assert "id" in data
        assert "created_at" in data

    async def test_register_duplicate_username(self, client: AsyncClient):
        payload = {"username": "dup", "password": "pass"}
        await client.post("/users/register", json=payload)
        resp = await client.post("/users/register", json=payload)
        assert resp.status_code == 400


class TestLogin:
    async def test_login_success(self, client: AsyncClient):
        await client.post(
            "/users/register",
            json={"username": "loginuser", "password": "pass"},
        )
        resp = await client.post(
            "/users/login",
            data={"username": "loginuser", "password": "pass"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"

    async def test_login_wrong_password(self, client: AsyncClient):
        await client.post(
            "/users/register",
            json={"username": "user2", "password": "correct"},
        )
        resp = await client.post(
            "/users/login",
            data={"username": "user2", "password": "wrong"},
        )
        assert resp.status_code == 401

    async def test_login_nonexistent_user(self, client: AsyncClient):
        resp = await client.post(
            "/users/login",
            data={"username": "ghost", "password": "pass"},
        )
        assert resp.status_code == 401

    async def test_invalid_token_returns_401(self, client: AsyncClient):
        resp = await client.get(
            "/links/expired",
            headers={"Authorization": "Bearer invalid.jwt.token"},
        )
        assert resp.status_code == 401
