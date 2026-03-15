from typing import AsyncGenerator, Optional

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.pool import StaticPool

from src.database import Base, get_db
from src.cache import CacheService


class FakeCacheService(CacheService):
    """In-memory замена Redis для тестов."""

    def __init__(self):
        super().__init__()
        self._store: dict[str, str] = {}

    async def connect(self):
        pass

    async def disconnect(self):
        pass

    async def get(self, key: str) -> Optional[str]:
        return self._store.get(key)

    async def set(self, key: str, value: str, ttl: Optional[int] = None):
        self._store[key] = value

    async def delete(self, key: str):
        self._store.pop(key, None)

    def clear(self):
        self._store.clear()


# создает тестовую базу данных
test_engine = create_async_engine(
    "sqlite+aiosqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
# создает сессию для тестовой базы данных
TestSessionLocal = async_sessionmaker(
    test_engine, class_=AsyncSession, expire_on_commit=False
)

# создает тестовый кэш
fake_cache = FakeCacheService()


# заменяет реальную зависимость get_db на тестовую
async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
    async with TestSessionLocal() as session:
        yield session


# создает и удаляет тестовую базу данных
@pytest_asyncio.fixture(
    autouse=True
)  # autouse=True означает, что эта фикстура запускается автоматически для каждого теста, даже если её не указывать явно
async def setup_database():
    # Перед каждым тестом создаём все таблицы
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    # После каждого теста удаляем все таблицы
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


# очищает кэш
@pytest_asyncio.fixture(autouse=True)
async def setup_cache(monkeypatch):
    fake_cache.clear()  # Очищаем кэш перед тестом

    import src.cache
    import src.routers.links
    import src.main

    # Подменяем реальный cache на fake_cache во всех модулях
    monkeypatch.setattr(src.cache, "cache", fake_cache)
    monkeypatch.setattr(src.routers.links, "cache", fake_cache)
    monkeypatch.setattr(src.main, "cache", fake_cache)


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    from src.main import app  # Импортируем приложение

    # Подменяем зависимость get_db на нашу тестовую
    app.dependency_overrides[get_db] = override_get_db
    # Создаем тестовый клиент для запросов
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",  # Базовый URL не важен для тестов
    ) as ac:
        yield ac  # Возвращаем тестовый клиент
    # Сбрасываем подмену зависимостей после теста
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def auth_client(client: AsyncClient) -> AsyncClient:
    """Клиент с зарегистрированным и авторизованным пользователем."""
    # Регистрируем пользователя
    await client.post(
        "/users/register",
        json={"username": "testuser", "password": "testpass123"},
    )
    # Логинимся и получаем токен
    resp = await client.post(
        "/users/login",
        data={"username": "testuser", "password": "testpass123"},
    )
    token = resp.json()["access_token"]
    client.headers["Authorization"] = f"Bearer {token}"
    return client


@pytest.fixture
def test_cache():
    return fake_cache  # Доступ к тестовому кэшу


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    async with TestSessionLocal() as session:
        yield session  # Доступ к сессии БД
