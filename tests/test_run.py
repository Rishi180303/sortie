from datetime import UTC, date, datetime

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from sortie.clients.letterboxd import WatchlistItem
from sortie.clients.tmdb import TmdbCandidate, TmdbFilm
from sortie.config import (
    AlertsCfg,
    Config,
    LetterboxdCfg,
    LocationCfg,
    MatchingCfg,
    Secrets,
    SourcesCfg,
)
from sortie.http import FetchError
from sortie.models import FetchLog, FilmState, Theatre
from sortie.run import Runtime, run_daily
from sortie.sources.base import FilmDetails, ShowingInfo, TheatreInfo
from tests.conftest import FakeSource

NOW = datetime(2026, 9, 8, 9, 0, tzinfo=UTC)
TODAY = date(2026, 9, 8)
CFG = Config(
    location=LocationCfg(postal_code="10001"),
    letterboxd=LetterboxdCfg(username="example-user"),
    sources=SourcesCfg(amc=False, fandango=True, fathom=False),
    alerts=AlertsCfg(),
    matching=MatchingCfg(),
)
SECRETS = Secrets(
    database_url="unused", tmdb_api_key="k", resend_api_key="r", alert_email_to="me@example.com"
)


class FakeLb:
    def watchlist(self, username, max_pages=100):
        return [WatchlistItem("primetime", "Primetime", 2026)]

    def tmdb_id_for(self, slug):
        return 1


class FakeTmdb:
    def search(self, query, limit=5):
        return [TmdbCandidate(1, "Primetime", "Primetime", 2026, 10.0)]

    def film(self, tmdb_id):
        return TmdbFilm(
            tmdb_id=1,
            title="Primetime",
            original_title="Primetime",
            runtime_minutes=101,
            director="Jane Doe",
            cast_top=["A", "B"],
            us_theatrical_date=date(2026, 9, 25),
            poster_path=None,
            alternative_titles=[],
            translation_titles=[],
        )


class Mailer:
    def __init__(self):
        self.sent = []

    def __call__(self, subject, text, html):
        self.sent.append((subject, text, html))
        return "msg_1"


def make_source(showings=None):
    return FakeSource(
        theatres=[
            TheatreInfo("fav", "AMC Metro 14", distance_miles=2.0),
            TheatreInfo("far", "Landmark Midtown", distance_miles=18.0),
        ],
        showings=showings or {},
        details={"900": FilmDetails(101, "Jane Doe", ["A", "B"])},
    )


def runtime(source, mailer):
    return Runtime(sources=[source], tmdb=FakeTmdb(), lb=FakeLb(), http_clients=[], mailer=mailer)


def factory(engine):
    return sessionmaker(bind=engine, expire_on_commit=False)


def test_first_run_emails_watchlist_hit(engine, db):
    src = make_source(
        {
            "far": [
                ShowingInfo(
                    "900",
                    "Primetime (2026)",
                    2026,
                    date(2026, 9, 25),
                    ["19:00"],
                    "/primetime-2026-900/movie-overview",
                )
            ]
        }
    )
    m = Mailer()
    report = run_daily(factory(engine), CFG, SECRETS, runtime(src, m), today=TODAY, now=NOW)
    assert report.theatres_refreshed == 2 and report.alerts == 1 and report.emailed is True
    assert report.failures == []
    assert len(m.sent) == 1 and "PRIMETIME" in m.sent[0][1] and "Landmark Midtown" in m.sent[0][1]
    with factory(engine)() as s:
        assert s.get(FilmState, 1).alerted_new_at is not None
        assert s.execute(select(func.count()).select_from(Theatre)).scalar() == 2
        assert (
            s.execute(select(FetchLog).where(FetchLog.target == "theatres")).scalar_one().ok is True
        )


def test_no_mailer_does_not_mark_alert_sent(engine, db):
    src = make_source(
        {"far": [ShowingInfo("900", "Primetime (2026)", 2026, date(2026, 9, 25), ["19:00"])]}
    )
    report = run_daily(factory(engine), CFG, SECRETS, runtime(src, None), today=TODAY, now=NOW)
    assert report.emailed is False
    with factory(engine)() as s:
        assert s.get(FilmState, 1).alerted_new_at is None


def test_unchanged_second_run_sends_nothing(engine, db):
    src = make_source(
        {"far": [ShowingInfo("900", "Primetime (2026)", 2026, date(2026, 9, 25), ["19:00"])]}
    )
    m = Mailer()
    run_daily(factory(engine), CFG, SECRETS, runtime(src, m), today=TODAY, now=NOW)
    report = run_daily(
        factory(engine), CFG, SECRETS, runtime(src, m), today=date(2026, 9, 9), now=NOW
    )
    assert report.alerts == 0 and report.emailed is False and len(m.sent) == 1


def test_fetch_failure_always_emails(engine, db):
    src = make_source(
        {"far": [ShowingInfo("900", "Primetime (2026)", 2026, date(2026, 9, 25), ["19:00"])]}
    )
    m = Mailer()
    run_daily(factory(engine), CFG, SECRETS, runtime(src, m), today=TODAY, now=NOW)
    broken = make_source({"far": []})  # zero results after history -> failure
    report = run_daily(
        factory(engine), CFG, SECRETS, runtime(broken, m), today=date(2026, 9, 9), now=NOW
    )
    assert report.failures and report.emailed is True
    assert m.sent[-1][0].startswith("sortie: 1 fetch failure")


def test_sunday_heartbeat(engine, db):
    m = Mailer()
    report = run_daily(
        factory(engine), CFG, SECRETS, runtime(make_source(), m), today=date(2026, 9, 13), now=NOW
    )
    assert report.emailed is True and m.sent[0][0] == "sortie: weekly check-in"


def test_health_endpoint(engine, db, monkeypatch):
    from sortie import api

    monkeypatch.setattr(api, "SessionFactory", factory(engine))
    client = TestClient(api.app)
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["ok"] is True


class FakeFathom:
    def __init__(self, titles=None, fail=False):
        self.titles = set(titles or [])
        self.fail = fail

    def active_titles(self):
        if self.fail:
            raise FetchError("https://api.fathomentertainment.com/api/events", 500, "HTTP 500")
        return self.titles


class TwoFilmTmdb(FakeTmdb):
    # primetime (new, on the watchlist) plus heat (1995, not on the watchlist)
    def search(self, query, limit=5):
        if "heat" in query:
            return [TmdbCandidate(2, "Heat", "Heat", 1995, 5.0)]
        return super().search(query, limit)

    def film(self, tmdb_id):
        if tmdb_id == 2:
            return TmdbFilm(
                tmdb_id=2,
                title="Heat",
                original_title="Heat",
                runtime_minutes=170,
                director="Michael Mann",
                cast_top=["Al Pacino", "Robert De Niro"],
                us_theatrical_date=date(1995, 12, 15),
                poster_path=None,
                alternative_titles=[],
                translation_titles=[],
            )
        return super().film(tmdb_id)


def test_fathom_listing_makes_an_old_film_a_rerelease_alert(engine, db):
    src = FakeSource(
        theatres=[TheatreInfo("far", "Landmark Midtown", distance_miles=18.0)],
        showings={"far": [ShowingInfo("902", "Heat (2026)", 2026, date(2026, 9, 20), ["19:00"])]},
        details={"902": FilmDetails(170, "Michael Mann", ["Al Pacino", "Robert De Niro"])},
    )
    m = Mailer()
    rt = Runtime(
        sources=[src],
        tmdb=TwoFilmTmdb(),
        lb=FakeLb(),
        mailer=m,
        fathom=FakeFathom({"heat", "spirited away"}),
    )
    report = run_daily(factory(engine), CFG, SECRETS, rt, today=TODAY, now=NOW)
    assert "fathom: 2 active titles" in report.health
    assert report.alerts == 1 and report.emailed is True
    assert "RE-RELEASES NEAR YOU" in m.sent[0][1] and "HEAT" in m.sent[0][1]
    with factory(engine)() as s:
        assert s.get(FilmState, 2).is_rerelease is True


def test_fathom_failure_is_reported_and_emailed(engine, db):
    m = Mailer()
    rt = Runtime(
        sources=[make_source()],
        tmdb=FakeTmdb(),
        lb=FakeLb(),
        mailer=m,
        fathom=FakeFathom(fail=True),
    )
    report = run_daily(factory(engine), CFG, SECRETS, rt, today=TODAY, now=NOW)
    assert len(report.failures) == 1 and report.failures[0].startswith("fathom: ")
    assert report.emailed is True and m.sent[0][0] == "sortie: 1 fetch failure"
