from datetime import UTC, datetime

from sqlalchemy import select

from sortie.clients.letterboxd import WatchlistItem
from sortie.http import FetchError
from sortie.models import Film, WatchlistEntry
from sortie.sync.watchlist import sync_watchlist

NOW = datetime(2026, 9, 8, 9, 0, tzinfo=UTC)


class FakeLb:
    def __init__(self, items, ids):
        self.items = items
        self.ids = ids
        self.id_calls = []

    def watchlist(self, username, max_pages=100):
        return self.items

    def tmdb_id_for(self, slug):
        self.id_calls.append(slug)
        return self.ids.get(slug)


def bare_film(db):
    def ensure(tmdb_id):
        if db.get(Film, tmdb_id) is None:
            db.add(Film(tmdb_id=tmdb_id, title=f"film {tmdb_id}"))
            db.flush()

    return ensure


def test_first_sync_adds_and_resolves(db):
    lb = FakeLb([WatchlistItem("a", "A", 2026), WatchlistItem("b", "B", None)], {"a": 11})
    r = sync_watchlist(db, lb, "example-user", NOW, bare_film(db))
    assert (r.added, r.removed, r.resolved, r.unresolved, r.total_active) == (2, 0, 1, 1, 2)
    a = db.get(WatchlistEntry, "a")
    assert a.tmdb_id == 11 and a.first_seen == NOW and a.removed_at is None
    assert db.get(WatchlistEntry, "b").tmdb_id is None


def test_second_sync_soft_deletes_and_retries_unresolved(db):
    lb = FakeLb([WatchlistItem("a", "A", 2026), WatchlistItem("b", "B", None)], {"a": 11})
    sync_watchlist(db, lb, "u", NOW, bare_film(db))
    lb2 = FakeLb([WatchlistItem("b", "B", None), WatchlistItem("c", "C", 1999)], {"b": 22, "c": 33})
    r = sync_watchlist(db, lb2, "u", NOW, bare_film(db))
    assert (r.added, r.removed, r.resolved, r.total_active) == (1, 1, 2, 2)
    assert db.get(WatchlistEntry, "a").removed_at == NOW
    assert db.get(WatchlistEntry, "b").tmdb_id == 22
    assert lb2.id_calls == ["b", "c"]  # "a" is removed; already-resolved slugs are not re-fetched


def test_entry_that_fails_to_resolve_is_isolated(db):
    class FlakyLb(FakeLb):
        def tmdb_id_for(self, slug):
            self.id_calls.append(slug)
            if slug == "bad":
                raise FetchError("https://x", 404, "not found")
            return self.ids.get(slug)

    lb = FlakyLb(
        [WatchlistItem("bad", "Bad", None), WatchlistItem("good", "Good", 2026)], {"good": 11}
    )
    r = sync_watchlist(db, lb, "u", NOW, bare_film(db))
    assert r.resolved == 1 and r.unresolved == 1
    assert len(r.errors) == 1 and "bad" in r.errors[0]
    assert db.get(WatchlistEntry, "good").tmdb_id == 11


def test_readded_entry_is_reactivated(db):
    lb = FakeLb([WatchlistItem("a", "A", 2026)], {"a": 11})
    sync_watchlist(db, lb, "u", NOW, bare_film(db))
    sync_watchlist(db, FakeLb([], {}), "u", NOW, bare_film(db))
    assert db.get(WatchlistEntry, "a").removed_at == NOW
    sync_watchlist(db, lb, "u", NOW, bare_film(db))
    e = db.get(WatchlistEntry, "a")
    assert e.removed_at is None and e.tmdb_id == 11
    assert db.execute(select(WatchlistEntry)).scalars().all().__len__() == 1
