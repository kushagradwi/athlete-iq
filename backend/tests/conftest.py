import os
import tempfile

_tmp = tempfile.mkdtemp(prefix="athleteiq-test-")
os.environ.update(DATABASE_URL=f"sqlite:///{_tmp}/test.db", LOCAL_STORAGE_DIR=f"{_tmp}/storage", JOB_MODE="inline",
                  STORAGE="local", GEMINI_API_KEY="", GC_API_URL="http://127.0.0.1:9", GC_AUTOIMPORT_DIR="")

import pytest  # noqa: E402

from athleteiq.config import settings  # noqa: E402

settings.cache_clear()


@pytest.fixture()
def db():
    """Fresh schema per test (SQLite)."""
    from athleteiq import models  # noqa: F401
    from athleteiq.db import Base, engine, reset_engine, session
    from athleteiq.repo import sync_registry
    reset_engine()
    eng = engine()
    Base.metadata.drop_all(eng)
    Base.metadata.create_all(eng)
    with session() as s:
        sync_registry(s)
    yield session
    reset_engine()
