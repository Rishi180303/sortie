import inspect
import os
from urllib.parse import urlencode

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from sortie.http import HttpClient
from sortie.models import Base
from sortie.sources.base import FilmDetails

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
        for sub, status, response_text in self.routes:
            if sub in full:
                return status, response_text
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


class FakeSource:
    name = "fake"

    def __init__(self, theatres=None, showings=None, details=None):
        self.theatres = list(theatres or [])
        self.showings_by_theatre = dict(showings or {})
        self.details_by_film = dict(details or {})
        self.detail_calls: list[str] = []
        self.showing_calls: list[str] = []

    def nearby_theatres(self, postal_code, radius_miles):
        return self.theatres

    def showings(self, source_theatre_id):
        self.showing_calls.append(source_theatre_id)
        return self.showings_by_theatre.get(source_theatre_id, [])

    def film_details(self, source_film_id, film_url=None):
        self.detail_calls.append(source_film_id)
        return self.details_by_film.get(source_film_id, FilmDetails(None, None, []))


@pytest.fixture(autouse=True)
def _truncate_after(request, engine):
    # run_daily commits its own sessions, so those tests need a clean db after
    yield
    # request.fixturenames includes engine transitively (via db), so it can't
    # tell those tests apart from every other db test. check the test's own
    # signature instead, so only tests that ask for engine directly pay for it.
    params = inspect.signature(request.node.function).parameters
    if "engine" in params:
        with engine.begin() as conn:
            for t in reversed(Base.metadata.sorted_tables):
                conn.execute(text(f'TRUNCATE TABLE "{t.name}" RESTART IDENTITY CASCADE'))
