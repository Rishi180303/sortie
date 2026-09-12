from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from sortie.clients.letterboxd import LetterboxdClient
from sortie.http import FetchError
from sortie.models import WatchlistEntry


@dataclass
class WatchlistSyncResult:
    added: int
    removed: int
    resolved: int
    unresolved: int
    total_active: int
    errors: list[str] = field(default_factory=list)


def sync_watchlist(
    db: Session,
    lb: LetterboxdClient,
    username: str,
    now: datetime,
    ensure_film: Callable[[int], None],
) -> WatchlistSyncResult:
    items = lb.watchlist(username)

    # build dict of fetched items by slug
    fetched = {}
    for item in items:
        fetched[item.slug] = item

    # build dict of existing entries by slug
    existing = {}
    for entry in db.execute(select(WatchlistEntry)).scalars():
        existing[entry.letterboxd_slug] = entry

    # add new entries and reactivate removed ones
    added = 0
    for slug, item in fetched.items():
        e = existing.get(slug)
        if e is None:
            db.add(
                WatchlistEntry(
                    letterboxd_slug=slug, title_raw=item.title, year_raw=item.year, first_seen=now
                )
            )
            added += 1
        else:
            e.title_raw = item.title
            e.year_raw = item.year
            e.removed_at = None

    # soft delete entries no longer on the list
    removed = 0
    for slug, e in existing.items():
        if slug not in fetched and e.removed_at is None:
            e.removed_at = now
            removed += 1

    db.flush()

    # resolve unresolved entries in deterministic order
    resolved = 0
    unresolved = 0
    active = (
        db.execute(
            select(WatchlistEntry)
            .where(WatchlistEntry.removed_at.is_(None))
            .order_by(WatchlistEntry.first_seen, WatchlistEntry.letterboxd_slug)
        )
        .scalars()
        .all()
    )

    errors: list[str] = []
    for e in active:
        if e.tmdb_id is not None:
            continue
        try:
            tid = lb.tmdb_id_for(e.letterboxd_slug)
        except FetchError as err:
            unresolved += 1
            errors.append(f"{e.letterboxd_slug}: {err}")
            continue
        if tid is None:
            unresolved += 1
            continue
        ensure_film(tid)
        e.tmdb_id = tid
        resolved += 1

    db.flush()
    return WatchlistSyncResult(added, removed, resolved, unresolved, len(active), errors)
