from datetime import UTC, date, datetime

from sortie.alerts.diff import mark_alerted, transitions
from sortie.models import FilmState

NOW = datetime(2026, 9, 8, tzinfo=UTC)
TODAY = date(2026, 9, 8)


def st(**kw):
    base = dict(
        tmdb_id=1,
        is_watchlist=True,
        earliest_date_anywhere=date(2026, 9, 25),
        earliest_theatre_id=10,
    )
    base.update(kw)
    return FilmState(**base)


def kinds(s, today=TODAY, days=5):
    return [a.kind for a in transitions(s, today, days)]


def test_non_watchlist_non_rerelease_never_alerts():
    assert kinds(st(is_watchlist=False)) == []
    assert kinds(st(is_watchlist=False, is_rerelease=True)) == ["new_anywhere"]


def test_first_sighting_anywhere():
    assert kinds(st()) == ["new_anywhere"]


def test_first_sighting_at_favourite_fires_both():
    s = st(earliest_date_at_fav=date(2026, 9, 30), earliest_fav_theatre_id=11)
    assert kinds(s) == ["new_anywhere", "new_at_favourite"]


def test_marking_silences_repeat():
    s = st()
    alerts = transitions(s, TODAY, 5)
    mark_alerted(s, alerts, NOW)
    assert s.alerted_new_at == NOW and s.alerted_earliest_date == date(2026, 9, 25)
    assert kinds(s) == []


def test_favourite_arrives_later():
    s = st()
    mark_alerted(s, transitions(s, TODAY, 5), NOW)
    s.earliest_date_at_fav, s.earliest_fav_theatre_id = date(2026, 9, 30), 11
    assert kinds(s) == ["new_at_favourite"]


def test_earliest_moved_earlier():
    s = st()
    mark_alerted(s, transitions(s, TODAY, 5), NOW)
    s.earliest_date_anywhere = date(2026, 9, 22)
    assert kinds(s) == ["earliest_moved_earlier"]
    mark_alerted(s, transitions(s, TODAY, 5), NOW)
    assert s.alerted_earlier_at == NOW and s.alerted_earliest_date == date(2026, 9, 22)
    assert kinds(s) == []
    s.earliest_date_anywhere = date(2026, 9, 23)  # later than alerted: not an alert
    assert kinds(s) == []


def test_approaching_only_after_new_and_within_window():
    s = st(earliest_date_anywhere=date(2026, 9, 12))
    assert kinds(s) == ["new_anywhere"]  # same run: no "approaching" yet
    mark_alerted(s, transitions(s, TODAY, 5), NOW)
    assert kinds(s, today=date(2026, 9, 6)) == []  # 6 days out
    assert kinds(s, today=date(2026, 9, 7)) == ["approaching"]
    mark_alerted(s, transitions(s, date(2026, 9, 7), 5), NOW)
    assert kinds(s, today=date(2026, 9, 8)) == []
    s_past = st(earliest_date_anywhere=date(2026, 9, 1), alerted_new_at=NOW)
    assert kinds(s_past, today=TODAY) == []  # past


def test_approaching_uses_favourite_date_when_present():
    s = st(
        earliest_date_anywhere=date(2026, 9, 10),
        earliest_date_at_fav=date(2026, 9, 20),
        earliest_fav_theatre_id=11,
        alerted_new_at=NOW,
        alerted_fav_at=NOW,
        alerted_earliest_date=date(2026, 9, 10),
    )
    assert kinds(s, today=date(2026, 9, 8)) == []  # fav date is 12 days out
    assert kinds(s, today=date(2026, 9, 16)) == ["approaching"]
