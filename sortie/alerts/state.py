from collections import defaultdict
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from sortie.alerts.rerelease import is_rerelease
from sortie.models import Film, FilmState, Showing, SourceFilm, Theatre, WatchlistEntry
from sortie.sync.films import alias_set


def compute_film_states(
    db: Session,
    today: date,
    now: datetime,
    reappear_days: int = 14,
    fathom_titles: set[str] | None = None,
    gap_years: int = 2,
) -> int:
    fathom = fathom_titles or set()

    # query all future showings at tracked theatres for resolved films
    q = (
        select(SourceFilm.tmdb_id, SourceFilm.raw_title, Showing.show_date, Theatre)
        .join(Showing, Showing.source_film_id == SourceFilm.id)
        .join(Theatre, Theatre.id == Showing.theatre_id)
        .where(
            SourceFilm.tmdb_id.is_not(None),
            Showing.show_date >= today,
            Theatre.tracked.is_(True),
        )
        .order_by(
            SourceFilm.tmdb_id,
            Showing.show_date,
            Theatre.is_favourite.desc(),
            Theatre.distance_miles.nulls_last(),
            Theatre.id,
        )
    )

    # group rows by tmdb_id, and remember every raw title a source used for the film
    by_film = defaultdict(list)
    raw_titles = defaultdict(set)
    for tmdb_id, raw_title, show_date, theatre in db.execute(q):
        by_film[tmdb_id].append((show_date, theatre))
        raw_titles[tmdb_id].add(raw_title)

    # get active watchlist entries
    watchlisted = set(
        db.execute(
            select(WatchlistEntry.tmdb_id).where(
                WatchlistEntry.tmdb_id.is_not(None),
                WatchlistEntry.removed_at.is_(None),
            )
        ).scalars()
    )

    # compute state for each film
    for tmdb_id, rows in by_film.items():
        state = db.get(FilmState, tmdb_id)
        if state is None:
            state = FilmState(tmdb_id=tmdb_id)
            db.add(state)
        else:
            # check for reappearance: was absent for >= reappear_days
            if (
                state.last_seen_showing is not None
                and (today - state.last_seen_showing).days >= reappear_days
            ):
                state.alerted_new_at = None
                state.alerted_fav_at = None
                state.alerted_earlier_at = None
                state.alerted_soon_at = None
                state.alerted_earliest_date = None

        # earliest anywhere: first row in ordered list
        state.earliest_date_anywhere = rows[0][0]
        state.earliest_theatre_id = rows[0][1].id

        # earliest at favourite: first row at a theatre marked as a favourite
        earliest_fav = None
        for show_date, theatre in rows:
            if theatre.is_favourite:
                earliest_fav = (show_date, theatre.id)
                break

        if earliest_fav:
            state.earliest_date_at_fav = earliest_fav[0]
            state.earliest_fav_theatre_id = earliest_fav[1]
        else:
            state.earliest_date_at_fav = None
            state.earliest_fav_theatre_id = None

        state.is_watchlist = tmdb_id in watchlisted
        film = db.get(Film, tmdb_id)
        state.is_rerelease = is_rerelease(
            film.us_theatrical_date,
            state.earliest_date_anywhere,
            raw_titles[tmdb_id],
            alias_set(db, tmdb_id),
            fathom,
            gap_years,
        )
        state.last_seen_showing = today
        state.last_computed = now

    db.flush()
    return len(by_film)
