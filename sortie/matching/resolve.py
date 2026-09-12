from dataclasses import dataclass, field
from datetime import datetime
from operator import itemgetter

from sqlalchemy import select
from sqlalchemy.orm import Session

from sortie.clients.tmdb import TmdbClient
from sortie.config import MatchingCfg
from sortie.http import FetchError
from sortie.matching.scoring import Candidate, Observed, pick, score
from sortie.models import MatchQueue, SourceFilm
from sortie.normalize import normalize_title, strip_year
from sortie.sources.base import ShowtimeSource
from sortie.sync.films import alias_set, hydrate_film


@dataclass
class ResolveResult:
    resolved: int = 0
    queued: int = 0
    errors: list[str] = field(default_factory=list)


def resolve_pending(
    db: Session,
    source: ShowtimeSource,
    tmdb: TmdbClient,
    cfg: MatchingCfg,
    now: datetime,
    max_candidates: int = 5,
) -> ResolveResult:
    res = ResolveResult()

    # query for pending films: unresolved, not in an open queue row
    open_queue = select(MatchQueue.source_film_id).where(MatchQueue.resolved_at.is_(None))
    pending = (
        db.execute(
            select(SourceFilm).where(
                SourceFilm.source == source.name,
                SourceFilm.resolution == "unresolved",
                SourceFilm.id.not_in(open_queue),
            )
        )
        .scalars()
        .all()
    )

    for sf in pending:
        # enrich film details if not already done
        if sf.enriched_at is None:
            try:
                d = source.film_details(sf.source_film_id, sf.film_url)
            except FetchError as e:
                res.errors.append(f"{sf.raw_title}: {e}")
                continue
            sf.runtime_minutes = d.runtime_minutes
            sf.director = d.director
            sf.cast_top = list(d.cast_top)
            sf.enriched_at = now
            db.flush()

        # search tmdb and score candidates
        title_n = normalize_title(sf.raw_title)
        year = sf.raw_year if sf.raw_year is not None else strip_year(sf.raw_title)[1]
        obs = Observed(title_n, year, sf.director, sf.runtime_minutes, tuple(sf.cast_top or []))

        scored = []
        for tc in tmdb.search(title_n, limit=max_candidates):
            film = hydrate_film(db, tmdb, tc.tmdb_id, now)
            cand = Candidate(
                tmdb_id=film.tmdb_id,
                title=film.title,
                year=film.us_theatrical_date.year if film.us_theatrical_date else tc.release_year,
                director=film.director,
                runtime_minutes=film.runtime_minutes,
                cast_top=tuple(film.cast_top or []),
                aliases=frozenset(alias_set(db, film.tmdb_id)),
            )
            scored.append((cand, score(obs, cand)))

        # decide: auto-match or queue
        chosen = pick(scored, cfg.min_score, cfg.min_margin)
        if chosen is not None:
            sf.tmdb_id = chosen.tmdb_id
            sf.resolution = "auto"
            # find the score for the chosen candidate
            for cand, s in scored:
                if cand.tmdb_id == chosen.tmdb_id:
                    sf.confidence = s
                    break
            sf.resolved_at = now
            res.resolved += 1
        else:
            # build candidates list sorted by score descending
            cands = []
            for cand, s in sorted(scored, key=itemgetter(1), reverse=True):
                cands.append(
                    {
                        "tmdb_id": cand.tmdb_id,
                        "title": cand.title,
                        "year": cand.year,
                        "director": cand.director,
                        "runtime_minutes": cand.runtime_minutes,
                        "score": s,
                    }
                )

            # match_queue.source_film_id is unique: reuse or insert
            q = db.execute(
                select(MatchQueue).where(MatchQueue.source_film_id == sf.id)
            ).scalar_one_or_none()
            if q is None:
                db.add(MatchQueue(source_film_id=sf.id, candidates=cands, created_at=now))
            else:
                q.candidates = cands
                q.created_at = now
                q.resolved_at = None
            res.queued += 1
        db.flush()
    return res
