from datetime import UTC, date, datetime, timedelta

from sortie.alerts.state import compute_film_states
from sortie.models import Film, FilmState, Showing, SourceFilm, Theatre, WatchlistEntry

NOW = datetime(2026, 9, 8, tzinfo=UTC)
TODAY = date(2026, 9, 8)


def theatre(db, sid, fav=False, dist=5.0, tracked=True):
    t = Theatre(
        source="fake",
        source_theatre_id=sid,
        name=sid,
        is_favourite=fav,
        distance_miles=dist,
        tracked=tracked,
    )
    db.add(t)
    db.flush()
    return t


def film(db, tid=1, watchlist=False):
    db.add(Film(tmdb_id=tid, title=f"F{tid}"))
    sf = SourceFilm(
        source="fake", source_film_id=str(tid), raw_title=f"F{tid}", tmdb_id=tid, resolution="auto"
    )
    db.add(sf)
    if watchlist:
        db.add(
            WatchlistEntry(
                letterboxd_slug=f"f{tid}", title_raw=f"F{tid}", tmdb_id=tid, first_seen=NOW
            )
        )
    db.flush()
    return sf


def show(db, sf, t, d):
    db.add(
        Showing(
            source_film_id=sf.id,
            theatre_id=t.id,
            show_date=d,
            show_times=["19:00"],
            first_seen=NOW,
            last_seen=NOW,
        )
    )
    db.flush()


def test_earliest_anywhere_and_at_favourite(db):
    far, fav = theatre(db, "far", dist=18.0), theatre(db, "fav", fav=True, dist=2.0)
    sf = film(db, 1, watchlist=True)
    show(db, sf, far, date(2026, 9, 25))
    show(db, sf, fav, date(2026, 9, 30))
    assert compute_film_states(db, TODAY, NOW) == 1
    s = db.get(FilmState, 1)
    assert (s.earliest_date_anywhere, s.earliest_theatre_id) == (date(2026, 9, 25), far.id)
    assert (s.earliest_date_at_fav, s.earliest_fav_theatre_id) == (date(2026, 9, 30), fav.id)
    assert s.is_watchlist is True and s.is_rerelease is False
    assert s.last_seen_showing == TODAY and s.last_computed == NOW


def test_tie_prefers_favourite_then_distance(db):
    a = theatre(db, "a", dist=9.0)
    b = theatre(db, "b", dist=3.0)
    fav = theatre(db, "fav", fav=True, dist=12.0)
    sf = film(db, 1)
    for t in (a, b, fav):
        show(db, sf, t, date(2026, 9, 25))
    compute_film_states(db, TODAY, NOW)
    assert db.get(FilmState, 1).earliest_theatre_id == fav.id
    fav.is_favourite = False
    db.flush()
    compute_film_states(db, TODAY, NOW)
    assert db.get(FilmState, 1).earliest_theatre_id == b.id


def test_past_and_untracked_showings_are_ignored(db):
    t, off = theatre(db, "t"), theatre(db, "off", tracked=False)
    sf = film(db, 1)
    show(db, sf, t, date(2026, 9, 1))
    show(db, sf, off, date(2026, 9, 20))
    assert compute_film_states(db, TODAY, NOW) == 0
    assert db.get(FilmState, 1) is None


def test_no_fav_showing_leaves_fav_fields_none(db):
    t = theatre(db, "t")
    sf = film(db, 1)
    show(db, sf, t, date(2026, 9, 20))
    compute_film_states(db, TODAY, NOW)
    s = db.get(FilmState, 1)
    assert s.earliest_date_at_fav is None and s.earliest_fav_theatre_id is None


def test_reappearance_after_gap_resets_alert_fields(db):
    t = theatre(db, "t")
    sf = film(db, 1)
    show(db, sf, t, date(2026, 10, 20))  # far enough out to still be current 13 days later
    compute_film_states(db, TODAY, NOW)
    s = db.get(FilmState, 1)
    s.alerted_new_at = NOW
    s.alerted_earliest_date = date(2026, 10, 20)
    s.alerted_soon_at = NOW
    db.flush()
    # 13 days later, still showing: same engagement, nothing resets
    compute_film_states(db, TODAY + timedelta(days=13), NOW)
    s = db.get(FilmState, 1)
    assert s.alerted_new_at == NOW and s.last_seen_showing == TODAY + timedelta(days=13)
    # simulate 14 days of absence, then a comeback
    s.last_seen_showing = TODAY
    db.flush()
    later = TODAY + timedelta(days=14)
    show(db, sf, t, later + timedelta(days=3))
    compute_film_states(db, later, NOW)
    s = db.get(FilmState, 1)
    assert (
        s.alerted_new_at is None and s.alerted_soon_at is None and s.alerted_earliest_date is None
    )


def test_film_without_future_showings_keeps_state(db):
    t = theatre(db, "t")
    sf = film(db, 1)
    show(db, sf, t, date(2026, 9, 9))
    compute_film_states(db, TODAY, NOW)
    compute_film_states(db, TODAY + timedelta(days=5), NOW)
    s = db.get(FilmState, 1)
    assert s is not None and s.last_seen_showing == TODAY
