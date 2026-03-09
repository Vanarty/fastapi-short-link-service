import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from sqlalchemy import select

from src.database import async_session_maker
from src.cache import cache
from src.config import settings
from src.models import Link, LinkHistory
from src.routers import users, links

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def cleanup_task():
    """Периодическая очистка истекших и неиспользуемых ссылок."""
    while True:
        try:
            # Удаляем просроченные ссылки каждую минуту
            await asyncio.sleep(60)  # 1 минут
            async with async_session_maker() as db:
                now = datetime.now(timezone.utc)

                # Полуичим из БД истекшие ссылки и удалим
                result = await db.execute(
                    select(Link).where(
                        Link.expires_at.isnot(None),
                        Link.expires_at < now,
                    )
                )
                expired_links = result.scalars().all()
                for link in expired_links:
                    history = LinkHistory(
                        short_code=link.short_code,
                        original_url=link.original_url,
                        user_id=link.user_id,
                        created_at=link.created_at,
                        reason="expired",
                        click_count=link.click_count,
                    )
                    db.add(history)
                    await cache.delete(f"link:{link.short_code}")
                    await cache.delete(f"stats:{link.short_code}")
                    await db.delete(link)

                # Неиспользуемые ссылки
                threshold = await cache.get_int("config:unused_link_days")
                if threshold is None:
                    threshold = settings.unused_link_days
                cutoff = now - timedelta(days=threshold)

                result = await db.execute(
                    select(Link).where(
                        Link.last_used_at.isnot(None),
                        Link.last_used_at < cutoff,
                    )
                )
                unused_links = result.scalars().all()
                for link in unused_links:
                    history = LinkHistory(
                        short_code=link.short_code,
                        original_url=link.original_url,
                        user_id=link.user_id,
                        created_at=link.created_at,
                        reason="unused",
                        click_count=link.click_count,
                    )
                    db.add(history)
                    await cache.delete(f"link:{link.short_code}")
                    await cache.delete(f"stats:{link.short_code}")
                    await db.delete(link)

                await db.commit()

                total_cleaned = len(expired_links) + len(unused_links)
                if total_cleaned:
                    logger.info(
                        "Очистка: удалено %d истекших, %d неиспользуемых ссылок",
                        len(expired_links),
                        len(unused_links),
                    )

        except Exception as e:
            logger.error("Ошибка в задаче очистки: %s", e)

        await asyncio.sleep(settings.cleanup_interval_minutes * 60)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await cache.connect()
    task = asyncio.create_task(cleanup_task())
    logger.info("Сервис запущен")
    yield
    task.cancel()
    await cache.disconnect()
    logger.info("Сервис остановлен")


app = FastAPI(
    title="URL Shortener",
    description="API-сервис сокращения ссылок",
    version="1.0.0",
    lifespan=lifespan,
)

# Настройка CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # В продакшене замените на конкретные домены
    allow_credentials=True,
    allow_methods=["*"],  # Разрешить все методы (GET, POST, etc.)
    allow_headers=["*"],  # Разрешить все заголовки
)

app.include_router(users.router)
app.include_router(links.router)


@app.get("/{short_code}", include_in_schema=False)
async def root_redirect(short_code: str):
    """Перенаправление с корневого пути (короткая ссылка)."""
    return RedirectResponse(url=f"/links/{short_code}", status_code=307)
