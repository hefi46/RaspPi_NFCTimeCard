import sqlite3
import pytest
from src.database import init_db


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:", check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    init_db(c)
    yield c
    c.close()


@pytest.fixture(autouse=True)
def _reset_login_rate_limit():
    """Wipe the in-memory failed-login tracker so tests don't bleed state."""
    from src.web import auth
    auth._login_attempts.clear()
    yield
    auth._login_attempts.clear()
