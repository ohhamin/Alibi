from psycopg_pool import AsyncConnectionPool

from .config import get_settings

settings = get_settings()
pool = AsyncConnectionPool(
    conninfo=settings.database_url,
    min_size=1,
    max_size=8,
    open=False,
    kwargs={'autocommit': False},
)


async def open_pool() -> None:
    await pool.open()
    await pool.wait()


async def close_pool() -> None:
    await pool.close()
