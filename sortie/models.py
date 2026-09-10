from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Theatre(Base):
    __tablename__ = "theatre"
    __table_args__ = (UniqueConstraint("source", "source_theatre_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(16))
    source_theatre_id: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(200))
    chain: Mapped[str | None] = mapped_column(String(100))
    city: Mapped[str | None] = mapped_column(String(100))
    lat: Mapped[float | None] = mapped_column(Float)
    lng: Mapped[float | None] = mapped_column(Float)
    distance_miles: Mapped[float | None] = mapped_column(Float)
    tracked: Mapped[bool] = mapped_column(default=True)
    is_favourite: Mapped[bool] = mapped_column(default=False)


class Film(Base):
    __tablename__ = "film"

    tmdb_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(300))
    original_title: Mapped[str | None] = mapped_column(String(300))
    us_theatrical_date: Mapped[date | None] = mapped_column(Date)
    runtime_minutes: Mapped[int | None] = mapped_column(Integer)
    director: Mapped[str | None] = mapped_column(String(200))
    # top-billed cast from tmdb, used as a scoring signal
    cast_top: Mapped[list | None] = mapped_column(JSONB)
    poster_path: Mapped[str | None] = mapped_column(String(200))
    refreshed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class FilmAlias(Base):
    __tablename__ = "film_alias"
    __table_args__ = (UniqueConstraint("tmdb_id", "alias_normalized"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tmdb_id: Mapped[int] = mapped_column(ForeignKey("film.tmdb_id", ondelete="CASCADE"))
    alias_normalized: Mapped[str] = mapped_column(String(300))
    # primary|original|alternative|translation
    origin: Mapped[str] = mapped_column(String(16))


class WatchlistEntry(Base):
    __tablename__ = "watchlist_entry"

    letterboxd_slug: Mapped[str] = mapped_column(String(200), primary_key=True)
    title_raw: Mapped[str] = mapped_column(String(300))
    year_raw: Mapped[int | None] = mapped_column(Integer)
    tmdb_id: Mapped[int | None] = mapped_column(ForeignKey("film.tmdb_id"))
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SourceFilm(Base):
    __tablename__ = "source_film"
    __table_args__ = (UniqueConstraint("source", "source_film_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(16))
    source_film_id: Mapped[str] = mapped_column(String(64))
    raw_title: Mapped[str] = mapped_column(String(300))
    raw_year: Mapped[int | None] = mapped_column(Integer)
    # the source's own page for the film, needed to fetch director and runtime
    film_url: Mapped[str | None] = mapped_column(String(500))
    runtime_minutes: Mapped[int | None] = mapped_column(Integer)
    director: Mapped[str | None] = mapped_column(String(200))
    cast_top: Mapped[list | None] = mapped_column(JSONB)
    tmdb_id: Mapped[int | None] = mapped_column(ForeignKey("film.tmdb_id"))
    resolution: Mapped[str] = mapped_column(String(16), default="unresolved")
    confidence: Mapped[float | None] = mapped_column(Float)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # when film_details() was last fetched for this source film
    enriched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Showing(Base):
    __tablename__ = "showing"

    source_film_id: Mapped[int] = mapped_column(
        ForeignKey("source_film.id", ondelete="CASCADE"), primary_key=True
    )
    theatre_id: Mapped[int] = mapped_column(
        ForeignKey("theatre.id", ondelete="CASCADE"), primary_key=True
    )
    show_date: Mapped[date] = mapped_column(Date, primary_key=True)
    show_times: Mapped[list] = mapped_column(JSONB)
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class FilmState(Base):
    __tablename__ = "film_state"

    tmdb_id: Mapped[int] = mapped_column(ForeignKey("film.tmdb_id"), primary_key=True)
    earliest_date_anywhere: Mapped[date | None] = mapped_column(Date)
    earliest_theatre_id: Mapped[int | None] = mapped_column(ForeignKey("theatre.id"))
    earliest_date_at_fav: Mapped[date | None] = mapped_column(Date)
    earliest_fav_theatre_id: Mapped[int | None] = mapped_column(ForeignKey("theatre.id"))
    is_watchlist: Mapped[bool] = mapped_column(default=False)
    is_rerelease: Mapped[bool] = mapped_column(default=False)
    alerted_new_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    alerted_fav_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    alerted_earlier_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # earliest_date_anywhere at the time of the last alert, to detect "moved earlier"
    alerted_earliest_date: Mapped[date | None] = mapped_column(Date)
    alerted_soon_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # last date this film had a current showing, for the 14-day reappearance rule
    last_seen_showing: Mapped[date | None] = mapped_column(Date)
    last_computed: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MatchQueue(Base):
    __tablename__ = "match_queue"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_film_id: Mapped[int] = mapped_column(
        ForeignKey("source_film.id", ondelete="CASCADE"), unique=True
    )
    candidates: Mapped[list] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class FetchLog(Base):
    __tablename__ = "fetch_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    source: Mapped[str] = mapped_column(String(16))
    target: Mapped[str] = mapped_column(String(300))
    http_status: Mapped[int | None] = mapped_column(Integer)
    rows: Mapped[int | None] = mapped_column(Integer)
    ok: Mapped[bool] = mapped_column(default=True)
    error: Mapped[str | None] = mapped_column(String(1000))
