from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select

from sortie.http import FetchError
from sortie.models import Showing, SourceFilm, Theatre
from sortie.sources.base import ShowingInfo
from sortie.sync.showtimes import sweep_showtimes
from tests.conftest import FakeSource

NOW = datetime(2026, 9, 8, 9, 0, tzinfo=UTC)
TODAY = date(2026, 9, 8)


def seed_theatres(db, *ids, source="fake", tracked=True):
    out = []
    for i in ids:
        t = Theatre(source=source, source_theatre_id=i, name=f"T {i}", tracked=tracked)
        db.add(t)
        out.append(t)
    db.flush()
    return out


S1 = ShowingInfo(
    "900",
    "Example Film (2026)",
    2026,
    date(2026, 9, 10),
    ["19:30"],
    "/example-film-2026-900/movie-overview",
)
S2 = ShowingInfo("900", "Example Film (2026)", 2026, date(2026, 9, 11), ["16:00", "21:00"])
OLD = ShowingInfo("901", "Old One", None, date(2026, 9, 1), ["12:00"])


def test_sweep_inserts_source_films_and_showings(db):
    seed_theatres(db, "zz001")
    r = sweep_showtimes(db, FakeSource(showings={"zz001": [S1, S2, OLD]}), NOW, TODAY)
    assert (r.theatres, r.source_films_new, r.showings_upserted, r.failures) == (1, 1, 2, [])
    sf = db.execute(select(SourceFilm)).scalar_one()
    assert sf.source == "fake" and sf.source_film_id == "900"
    assert sf.raw_title == "Example Film (2026)" and sf.raw_year == 2026
    assert sf.film_url == "/example-film-2026-900/movie-overview"
    assert sf.resolution == "unresolved"
    shows = db.execute(select(Showing).order_by(Showing.show_date)).scalars().all()
    assert [s.show_date for s in shows] == [date(2026, 9, 10), date(2026, 9, 11)]
    assert shows[1].show_times == ["16:00", "21:00"]
    assert shows[0].first_seen == NOW == shows[0].last_seen


def test_second_sweep_updates_last_seen_without_new_films(db):
    seed_theatres(db, "zz001")
    src = FakeSource(showings={"zz001": [S1]})
    sweep_showtimes(db, src, NOW, TODAY)
    later = NOW + timedelta(days=1)
    r = sweep_showtimes(db, src, later, TODAY + timedelta(days=1))
    assert r.source_films_new == 0 and r.showings_upserted == 1
    s = db.execute(select(Showing)).scalar_one()
    assert s.first_seen == NOW and s.last_seen == later


def test_zero_results_after_recent_showings_is_a_failure(db):
    seed_theatres(db, "zz001")
    sweep_showtimes(db, FakeSource(showings={"zz001": [S1]}), NOW, TODAY)
    later_now = NOW + timedelta(hours=24)
    later_today = TODAY + timedelta(days=1)
    r = sweep_showtimes(db, FakeSource(showings={"zz001": []}), later_now, later_today)
    assert len(r.failures) == 1 and "0" in r.failures[0]
    assert db.execute(select(Showing)).scalar_one().last_seen == NOW  # untouched


def test_zero_results_with_no_history_is_fine(db):
    seed_theatres(db, "zz001")
    r = sweep_showtimes(db, FakeSource(showings={"zz001": []}), NOW, TODAY)
    assert r.failures == []


def test_fetch_error_isolated_per_theatre(db):
    seed_theatres(db, "zz001", "zz002")

    class Flaky(FakeSource):
        def showings(self, source_theatre_id):
            if source_theatre_id == "zz001":
                raise FetchError("https://x", 403, "blocked")
            return super().showings(source_theatre_id)

    r = sweep_showtimes(db, Flaky(showings={"zz002": [S1]}), NOW, TODAY)
    assert len(r.failures) == 1 and "T zz001" in r.failures[0]
    assert r.showings_upserted == 1


def test_untracked_and_other_source_theatres_are_skipped(db):
    seed_theatres(db, "zz001", tracked=False)
    seed_theatres(db, "other1", source="othersrc")
    src = FakeSource(showings={"zz001": [S1], "other1": [S1]})
    r = sweep_showtimes(db, src, NOW, TODAY)
    assert r.theatres == 0 and src.showing_calls == []
