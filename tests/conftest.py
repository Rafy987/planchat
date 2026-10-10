import pytest

from app import rate_limit
from app.config import settings
from app.db import close_pool, get_connection, init_db


@pytest.fixture(autouse=True)
def fresh_rate_limits():
    """Every test starts with empty rate-limit counters and a fresh daily budget."""
    rate_limit.reset()
    yield
    rate_limit.reset()


@pytest.fixture(scope="session")
def database():
    """Make sure tables exist. Skip DB tests if no real DATABASE_URL is set."""
    if not settings.database_url or not settings.database_url.startswith("postgres"):
        pytest.skip("DATABASE_URL is not set")
    init_db()
    yield
    close_pool()


@pytest.fixture
def created_documents(database):
    """Tests add the IDs of documents they create; we delete exactly those afterwards.

    This way tests can use the main database without touching real data.
    Chunks are deleted automatically by ON DELETE CASCADE.
    """
    ids: list[str] = []
    yield ids
    if ids:
        with get_connection() as conn:
            conn.execute("DELETE FROM documents WHERE id = ANY(%s::uuid[])", (ids,))


@pytest.fixture
def db():
    """A database connection for checking what a test saved."""
    with get_connection() as conn:
        yield conn
