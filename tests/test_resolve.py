from datetime import UTC, date, datetime

from sqlalchemy import select

from sortie.clients.tmdb import TmdbCandidate, TmdbFilm
from sortie.config import MatchingCfg
from sortie.http import FetchError
from sortie.matching.resolve import resolve_pending
from sortie.models import MatchQueue, SourceFilm
from sortie.sources.base import FilmDetails
from tests.conftest import FakeSource

NOW = datetime(2026, 9, 8, tzinfo=UTC)
CFG = MatchingCfg(min_score=0.6, min_margin=0.2)


class FakeTmdb:
    def __init__(self, search_results, films):
        self.search_results = search_results
        self.films = films
        self.search_calls = []

    def search(self, query, limit=5):
        self.search_calls.append(query)
        return self.search_results[:limit]

    def film(self, tmdb_id):
        return self.films[tmdb_id]


def tf(tmdb_id, title, director, runtime, year=1986, alt=()):
    return TmdbFilm(
        tmdb_id=tmdb_id,
        title=title,
        original_title=title,
        runtime_minutes=runtime,
        director=director,
        cast_top=["A", "B"],
        us_theatrical_date=date(year, 1, 1),
        poster_path=None,
        alternative_titles=list(alt),
        translation_titles=[],
    )


def add_sf(db, sfid="900", title="The Transformers: The Movie 40th Anniversary (2026)"):
    sf = SourceFilm(
        source="fake",
        source_film_id=sfid,
        raw_title=title,
        raw_year=2026,
        film_url="/x",
        resolution="unresolved",
    )
    db.add(sf)
    db.flush()
    return sf


def test_resolves_by_title_and_director(db):
    sf = add_sf(db)
    src = FakeSource(details={"900": FilmDetails(84, "Nelson Shin", ["A"])})
    tmdb = FakeTmdb(
        [
            TmdbCandidate(1, "The Transformers: The Movie", "", 1986, 50.0),
            TmdbCandidate(2, "Transformers", "", 2007, 90.0),
        ],
        {
            1: tf(1, "The Transformers: The Movie", "Nelson Shin", 84),
            2: tf(2, "Transformers", "Michael Bay", 144, 2007),
        },
    )
    r = resolve_pending(db, src, tmdb, CFG, NOW)
    assert (r.resolved, r.queued, r.errors) == (1, 0, [])
    db.refresh(sf)
    assert sf.tmdb_id == 1 and sf.resolution == "auto" and sf.confidence >= 0.85
    assert sf.director == "Nelson Shin" and sf.enriched_at == NOW
    assert tmdb.search_calls == ["the transformers the movie"]


def test_ambiguous_goes_to_queue_with_scored_candidates(db):
    sf = add_sf(db, title="Lavender (2026)")
    src = FakeSource(details={"900": FilmDetails(None, None, [])})
    tmdb = FakeTmdb(
        [
            TmdbCandidate(10, "Lavender", "", 2000, 5.0),
            TmdbCandidate(11, "Lavender", "", 2026, 4.0),
        ],
        {10: tf(10, "Lavender", "Dir A", 100, 2000), 11: tf(11, "Lavender", "Dir B", 95, 2026)},
    )
    r = resolve_pending(db, src, tmdb, CFG, NOW)
    assert (r.resolved, r.queued) == (0, 1)
    q = db.execute(select(MatchQueue)).scalar_one()
    assert q.source_film_id == sf.id and q.resolved_at is None
    assert {c["tmdb_id"] for c in q.candidates} == {10, 11}
    assert all("score" in c and "director" in c for c in q.candidates)
    db.refresh(sf)
    assert sf.resolution == "unresolved" and sf.tmdb_id is None


def test_enrichment_failure_is_reported_not_queued(db):
    sf = add_sf(db)

    class Broken(FakeSource):
        def film_details(self, source_film_id, film_url=None):
            raise FetchError("https://x", 403, "blocked")

    r = resolve_pending(db, Broken(), FakeTmdb([], {}), CFG, NOW)
    assert r.errors and r.queued == 0
    db.refresh(sf)
    assert sf.enriched_at is None and sf.resolution == "unresolved"


def test_already_queued_films_are_skipped(db):
    sf = add_sf(db)
    db.add(MatchQueue(source_film_id=sf.id, candidates=[], created_at=NOW))
    db.flush()
    src = FakeSource()
    r = resolve_pending(db, src, FakeTmdb([], {}), CFG, NOW)
    assert (r.resolved, r.queued) == (0, 0) and src.detail_calls == []


def test_enrichment_not_repeated_on_second_run(db):
    add_sf(db)
    src = FakeSource(details={"900": FilmDetails(None, None, [])})
    tmdb = FakeTmdb([], {})
    resolve_pending(db, src, tmdb, CFG, NOW)  # no candidates -> queued
    q = db.execute(select(MatchQueue)).scalar_one()
    q.resolved_at = NOW  # operator dismissed it; film stays unresolved
    db.flush()
    resolve_pending(db, src, tmdb, CFG, NOW)
    assert src.detail_calls == ["900"]
