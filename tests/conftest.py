import os
from urllib.parse import urlencode

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from sortie.http import HttpClient
from sortie.models import Base

TEST_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://sortie:sortie@localhost:5432/sortie_test"
)


class RoutedTransport:
    """Routes requests to canned responses by URL substring, in registration order."""

    def __init__(self):
        self.routes: list[tuple[str, int, str]] = []
        self.calls: list[tuple[str, str, str | None]] = []

    def add(self, substring: str, status: int, text: str) -> None:
        self.routes.append((substring, status, text))

    def __call__(self, method, url, headers, params, body):
        full = url + ("?" + urlencode(params) if params else "")
        self.calls.append((method, full, body))
        for sub, status, text in self.routes:
            if sub in full:
                return status, text
        raise AssertionError(f"unrouted request: {method} {full}")


@pytest.fixture
def routed():
    return RoutedTransport()


@pytest.fixture
def http(routed):
    return HttpClient(source="test", transport=routed, min_interval_s=0, sleeper=lambda s: None)


@pytest.fixture(scope="session")
def engine():
    eng = create_engine(TEST_URL)
    Base.metadata.drop_all(eng)
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def db(engine):
    # a session inside a transaction that is rolled back after each test
    conn = engine.connect()
    tx = conn.begin()
    session = Session(bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False)
    try:
        yield session
    finally:
        session.close()
        tx.rollback()
        conn.close()
