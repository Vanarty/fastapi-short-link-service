import string
import random
from datetime import datetime, timezone
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.models import Link, LinkHistory, User
from src.schemas import (
    LinkCreate,
    LinkUpdate,
    LinkResponse,
    LinkStats,
    LinkHistoryResponse,
)
from src.auth import get_current_user, require_user
from src.cache import cache
from src.config import settings

router = APIRouter(prefix="/links", tags=["links"])

CACHE_PREFIX_LINK = "link:"
CACHE_PREFIX_STATS = "stats:"
CACHE_PREFIX_SEARCH = "search:"


def _generate_short_code(length: int = settings.short_code_length) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(random.choices(alphabet, k=length))


async def _get_link_or_404(short_code: str, db: AsyncSession) -> Link:
    result = await db.execute(select(Link).where(Link.short_code == short_code))
    link = result.scalar_one_or_none()
    if not link:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ссылка не найдена",
        )
    return link


def _check_expired(link: Link) -> bool:
    if link.expires_at and link.expires_at.replace(tzinfo=timezone.utc) < datetime.now(
        timezone.utc
    ):
        return True
    return False


# POST /links/shorten
@router.post(
    "/shorten", response_model=LinkResponse, status_code=status.HTTP_201_CREATED
)
async def create_short_link(
    body: LinkCreate,
    db: AsyncSession = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    # Проверяем, если custom_alias не пустой, то проверяем, что он содержит только буквы, цифры, дефис и подчеркивание
    if body.custom_alias:
        if not all(
            s in string.ascii_letters + string.digits + "-_" for s in body.custom_alias
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Alias может содержать только буквы, цифры, дефис и подчеркивание",
            )

        # Проверяем, если URL уже занят то выбрасываем ошибку
        existing_url = await db.execute(
            select(Link).where(
                Link.original_url == str(body.original_url)
                and Link.expires_at >= datetime.now(timezone.utc)
                and Link.user_id == user.id
                if user
                else None
            )
        )
        if existing_url.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Этот URL уже занят",
            )

        # Ищем alias в БД
        # Проверяем, если alias уже занят то выбрасываем ошибку
        existing_short = await db.execute(
            select(Link).where(Link.short_code == body.custom_alias)
        )
        # Проверяем, если alias уже занят то выбрасываем ошибку
        if existing_short.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Этот alias уже занят",
            )

        short_code = body.custom_alias
    else:
        # Генерируем короткий код пока не найдем свободный (возможно в будущем добавлю ограничение на количество попыток)
        while True:
            short_code = _generate_short_code()
            exists = await db.execute(select(Link).where(Link.short_code == short_code))
            if not exists.scalar_one_or_none():
                break

    link = Link(
        short_code=short_code,
        original_url=str(body.original_url),
        user_id=user.id if user else None,
        expires_at=body.expires_at,
    )
    db.add(link)
    await db.commit()
    # Обновляем объект link, чтобы получить id
    await db.refresh(link)

    await cache.set(f"{CACHE_PREFIX_LINK}{short_code}", link.original_url)

    return link


# GET /links/search
# Поиск ссылки по оригинальному URL
@router.get("/search", response_model=LinkResponse)
async def search_by_url(
    original_url: str = Query(
        ..., description="Оригинальный URL для поиска"
    ),  # три точки означают обязательное поле (без него эндпоинт вернёт ошибку)
    db: AsyncSession = Depends(get_db),
):
    # Проверяем, если в кэше есть ссылка, то возвращаем её
    cached = await cache.get(f"{CACHE_PREFIX_SEARCH}{original_url}")
    if cached:
        result = await db.execute(select(Link).where(Link.short_code == cached))
        link = result.scalar_one_or_none()
        if link and not _check_expired(link):
            return link

    # Если в кэше нет ссылки, то ищем в БД
    result = await db.execute(select(Link).where(Link.original_url == original_url))
    link = result.scalar_one_or_none()

    if not link:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ссылка с таким URL не найдена",
        )

    # Проверяем, если ссылка просрочена то выбрасываем ошибку
    if _check_expired(link):
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Срок действия ссылки истек",
        )

    # Сохраняем ссылку в кэш
    await cache.set(f"{CACHE_PREFIX_SEARCH}{original_url}", link.short_code, ttl=300)
    return link


# GET /links/expired
# Дополнительный функционал - получение всех просроченных ссылок
@router.get("/expired", response_model=List[LinkHistoryResponse])
async def get_expired_links(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_user),
):
    # Получаем все просроченные ссылки
    result = await db.execute(
        select(LinkHistory).where(LinkHistory.reason == "expired")
    )
    return result.scalars().all()


# PUT /links/unused-threshold
# Дополнительный функционал - установка порога неактивности через Redis
@router.put("/unused-threshold")
async def set_unused_threshold(
    days: int = Query(
        ..., gt=0, description="Порог неактивности в днях"
    ),  # gt=0 - значит, что число должно быть больше 0
    user: User = Depends(require_user),
):
    # Сохраняем порог неактивности в кэш
    await cache.set_int("config:unused_link_days", days)
    return {"detail": f"Порог неактивности установлен: {days} дней"}


# GET /links/{short_code} (redirect)
# Перенаправление на оригинальный URL
@router.get("/{short_code}")
async def redirect_to_url(
    short_code: str,
    db: AsyncSession = Depends(get_db),
):
    # Проверяем, если в кэше есть ссылка, то возвращаем её
    cached_url = await cache.get(f"{CACHE_PREFIX_LINK}{short_code}")

    if cached_url:
        link = await _get_link_or_404(short_code, db)
        # Проверяем, если ссылка просрочена то выбрасываем ошибку
        if _check_expired(link):
            await cache.delete(f"{CACHE_PREFIX_LINK}{short_code}")
            raise HTTPException(
                status_code=status.HTTP_410_GONE,
                detail="Срок действия ссылки истек",
            )
        # Увеличиваем счётчик кликов и обновляем время последнего использования
        link.click_count += 1
        link.last_used_at = datetime.now(timezone.utc)
        await db.commit()

        # Удаляем статистику из кэша
        await cache.delete(f"{CACHE_PREFIX_STATS}{short_code}")
        # Возвращаем RedirectResponse с оригинальным URL
        return RedirectResponse(url=cached_url)

    # Если в кэше нет ссылки, то ищем в БД
    link = await _get_link_or_404(short_code, db)

    # Проверяем, если ссылка просрочена то выбрасываем ошибку
    if _check_expired(link):
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Срок действия ссылки истек",
        )

    # Увеличиваем счётчик кликов и обновляем время последнего использования
    link.click_count += 1
    link.last_used_at = datetime.now(timezone.utc)
    await db.commit()

    # Сохраняем ссылку в кэш
    await cache.set(f"{CACHE_PREFIX_LINK}{short_code}", link.original_url)
    # Удаляем статистику из кэша
    await cache.delete(f"{CACHE_PREFIX_STATS}{short_code}")

    return RedirectResponse(url=link.original_url)


# PUT /links/{short_code}
# Обновление ссылки
@router.put("/{short_code}", response_model=LinkResponse)
async def update_link(
    short_code: str,
    body: LinkUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_user),
):
    # Проверяем, если ссылка принадлежит пользователю
    link = await _get_link_or_404(short_code, db)

    if link.user_id is None or link.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Нет прав на изменение этой ссылки",
        )

    # Обновляем оригинальный URL и время последнего обновления
    link.original_url = str(body.original_url)
    link.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(link)

    # Сохраняем ссылку в кэш
    await cache.set(f"{CACHE_PREFIX_LINK}{short_code}", link.original_url)
    # Удаляем статистику из кэша
    await cache.delete(f"{CACHE_PREFIX_STATS}{short_code}")
    # Удаляем ссылку из кэша поиска
    await cache.delete(f"{CACHE_PREFIX_SEARCH}{link.original_url}")

    return link


# DELETE /links/{short_code}
# Удаление ссылки
@router.delete("/{short_code}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_link(
    short_code: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_user),
):
    # Проверяем, если ссылка принадлежит пользователю
    link = await _get_link_or_404(short_code, db)

    if link.user_id is None or link.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Нет прав на удаление этой ссылки",
        )

    # Создаём запись в истории удаления ссылки
    history = LinkHistory(
        short_code=link.short_code,
        original_url=link.original_url,
        user_id=link.user_id,
        created_at=link.created_at,
        reason="deleted_by_user",
        click_count=link.click_count,
    )
    db.add(history)
    await db.delete(link)
    await db.commit()

    # Удаляем ссылку из кэша
    await cache.delete(f"{CACHE_PREFIX_LINK}{short_code}")
    # Удаляем статистику из кэша
    await cache.delete(f"{CACHE_PREFIX_STATS}{short_code}")


# GET /links/{short_code}/stats
# Получение статистики по ссылке
@router.get("/{short_code}/stats", response_model=LinkStats)
async def get_link_stats(
    short_code: str,
    db: AsyncSession = Depends(get_db),
):
    # Проверяем, если в кэше есть статистика, то возвращаем её
    cached = await cache.get_json(f"{CACHE_PREFIX_STATS}{short_code}")
    if cached:
        return cached

    # Если в кэше нет статистики, то ищем в БД
    link = await _get_link_or_404(short_code, db)

    # Проверяем, если ссылка просрочена то выбрасываем ошибку
    if _check_expired(link):
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Срок действия ссылки истек",
        )

    stats = {
        "short_code": link.short_code,
        "original_url": link.original_url,
        "created_at": link.created_at,
        "click_count": link.click_count,
        "last_used_at": link.last_used_at,
    }
    # Сохраняем статистику в кэш
    await cache.set_json(f"{CACHE_PREFIX_STATS}{short_code}", stats, ttl=300)
    return stats
