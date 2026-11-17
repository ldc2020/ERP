from functools import lru_cache

from fastapi import FastAPI
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.exceptions import CustomException


@lru_cache(maxsize=1)
def _engine() -> AsyncEngine:
    return create_async_engine(settings.SQL_DB_URL.unicode_string(), pool_pre_ping=True)


def session_connect() -> AsyncSession:
    if not settings.SQL_DB_ENABLE:
        raise CustomException(msg="请先配置SQL数据库链接并启用", desc="请启用 app/core/config.py: SQL_DB_ENABLE")

    session_factory = async_sessionmaker(_engine(), autoflush=False, expire_on_commit=False)
    return session_factory()


async def close_database() -> None:
    if _engine.cache_info().currsize:
        await _engine().dispose()
        _engine.cache_clear()


async def redis_connect(app: FastAPI, status: bool) -> None:
    if not settings.REDIS_ENABLE:
        raise CustomException(msg="请先配置Redis数据库链接并启用", desc="请启用 app/core/config.py: REDIS_ENABLE")

    if status:
        redis = Redis.from_url(
            settings.REDIS_URL.unicode_string(),
            decode_responses=True,
            health_check_interval=20,
        )
        try:
            await redis.ping()
        except BaseException:
            await redis.aclose()
            raise
        app.state.redis = redis
    else:
        await app.state.redis.aclose()
