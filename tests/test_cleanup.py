"""Тесты фоновой задачи cleanup_task (очистка истекших и неиспользуемых ссылок)."""

import asyncio
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

import pytest
from sqlalchemy import select

from src.main import cleanup_task
from src.models import Link, LinkHistory
from tests.conftest import TestSessionLocal, fake_cache


class TestCleanupTask:
    async def test_cleanup_expired_links(self):
        async with TestSessionLocal() as db:
            db.add(
                Link(
                    short_code="exp1",
                    original_url="https://expired.com",
                    expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
                    click_count=5,
                    created_at=datetime.now(timezone.utc) - timedelta(days=1),
                )
            )
            await db.commit()

        call_count = 0

        async def mock_sleep(_seconds):
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                raise asyncio.CancelledError()

        with (
            patch("src.main.asyncio.sleep", side_effect=mock_sleep),
            patch("src.main.async_session_maker", TestSessionLocal),
        ):
            with pytest.raises(asyncio.CancelledError):
                await cleanup_task()

        async with TestSessionLocal() as db:
            link = (
                await db.execute(
                    select(Link).where(Link.short_code == "exp1")
                )
            ).scalar_one_or_none()
            assert link is None

            history = (
                await db.execute(
                    select(LinkHistory).where(LinkHistory.short_code == "exp1")
                )
            ).scalar_one_or_none()
            assert history is not None
            assert history.reason == "expired"
            assert history.click_count == 5

    async def test_cleanup_unused_links(self):
        async with TestSessionLocal() as db:
            db.add(
                Link(
                    short_code="unused1",
                    original_url="https://unused.com",
                    last_used_at=datetime.now(timezone.utc) - timedelta(days=365),
                    click_count=1,
                    created_at=datetime.now(timezone.utc) - timedelta(days=400),
                )
            )
            await db.commit()

        call_count = 0

        async def mock_sleep(_seconds):
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                raise asyncio.CancelledError()

        with (
            patch("src.main.asyncio.sleep", side_effect=mock_sleep),
            patch("src.main.async_session_maker", TestSessionLocal),
        ):
            with pytest.raises(asyncio.CancelledError):
                await cleanup_task()

        async with TestSessionLocal() as db:
            link = (
                await db.execute(
                    select(Link).where(Link.short_code == "unused1")
                )
            ).scalar_one_or_none()
            assert link is None

            history = (
                await db.execute(
                    select(LinkHistory).where(
                        LinkHistory.short_code == "unused1"
                    )
                )
            ).scalar_one_or_none()
            assert history is not None
            assert history.reason == "unused"

    async def test_cleanup_no_links_to_clean(self):
        """Если удалять нечего — задача завершается без ошибок."""
        call_count = 0

        async def mock_sleep(_seconds):
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                raise asyncio.CancelledError()

        with (
            patch("src.main.asyncio.sleep", side_effect=mock_sleep),
            patch("src.main.async_session_maker", TestSessionLocal),
        ):
            with pytest.raises(asyncio.CancelledError):
                await cleanup_task()
