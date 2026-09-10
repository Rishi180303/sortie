from collections.abc import Iterable
from datetime import datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from sortie.clients.tmdb import TmdbClient
from sortie.models import Film, FilmAlias
from sortie.normalize import normalize_title


def alias_set(db: Session, tmdb_id: int) -> set[str]:
    rows = db.execute(
        select(FilmAlias.alias_normalized).where(FilmAlias.tmdb_id == tmdb_id)
    ).scalars()
    return set(rows)


def _is_fresh(film: Film | None, now: datetime, max_age_days: int) -> bool:
    return (
        film is not None
        and film.refreshed_at is not None
        and now - film.refreshed_at < timedelta(days=max_age_days)
    )


def hydrate_film(
    db: Session, tmdb: TmdbClient, tmdb_id: int, now: datetime, max_age_days: int = 30
) -> Film:
    film = db.get(Film, tmdb_id)
    if _is_fresh(film, now, max_age_days):
        return film
    tf = tmdb.film(tmdb_id)
    if film is None:
        film = Film(tmdb_id=tmdb_id, title=tf.title)
        db.add(film)
    film.title = tf.title
    film.original_title = tf.original_title
    film.runtime_minutes = tf.runtime_minutes
    film.director = tf.director
    film.cast_top = tf.cast_top
    film.us_theatrical_date = tf.us_theatrical_date
    film.poster_path = tf.poster_path
    film.refreshed_at = now
    db.flush()

    # throw away the old aliases and rebuild them from scratch
    db.execute(delete(FilmAlias).where(FilmAlias.tmdb_id == tmdb_id))
    seen: set[str] = set()

    # add primary title
    n = normalize_title(tf.title)
    if n:
        seen.add(n)
        db.add(FilmAlias(tmdb_id=tmdb_id, alias_normalized=n, origin="primary"))

    # add original title
    if tf.original_title:
        n = normalize_title(tf.original_title)
        if n and n not in seen:
            seen.add(n)
            db.add(FilmAlias(tmdb_id=tmdb_id, alias_normalized=n, origin="original"))

    # add alternative titles
    for t in tf.alternative_titles:
        if t:
            n = normalize_title(t)
            if n and n not in seen:
                seen.add(n)
                db.add(FilmAlias(tmdb_id=tmdb_id, alias_normalized=n, origin="alternative"))

    # add translation titles
    for t in tf.translation_titles:
        if t:
            n = normalize_title(t)
            if n and n not in seen:
                seen.add(n)
                db.add(FilmAlias(tmdb_id=tmdb_id, alias_normalized=n, origin="translation"))

    db.flush()
    return film


def hydrate_films(
    db: Session, tmdb: TmdbClient, tmdb_ids: Iterable[int], now: datetime, max_age_days: int = 30
) -> int:
    fetched = 0
    seen = set()
    for tid in tmdb_ids:
        # skip duplicates in input
        if tid in seen:
            continue
        seen.add(tid)

        before = db.get(Film, tid)
        if _is_fresh(before, now, max_age_days):
            continue
        hydrate_film(db, tmdb, tid, now, max_age_days)
        fetched += 1
    return fetched
