from dataclasses import dataclass
from operator import itemgetter

from sortie.normalize import normalize_name

WEIGHTS = {"title": 0.30, "director": 0.40, "runtime": 0.15, "cast": 0.10, "year": 0.05}
RUNTIME_TOLERANCE_MIN = 3
CAST_MIN_OVERLAP = 2


@dataclass(frozen=True)
class Observed:
    title_normalized: str
    year: int | None
    director: str | None
    runtime_minutes: int | None
    cast_top: tuple[str, ...]


@dataclass(frozen=True)
class Candidate:
    tmdb_id: int
    title: str
    year: int | None
    director: str | None
    runtime_minutes: int | None
    cast_top: tuple[str, ...]
    aliases: frozenset[str]


def score(obs: Observed, cand: Candidate) -> float:
    s = 0.0
    if obs.title_normalized and obs.title_normalized in cand.aliases:
        s += WEIGHTS["title"]
    if (
        obs.director
        and cand.director
        and normalize_name(obs.director) == normalize_name(cand.director)
    ):
        s += WEIGHTS["director"]
    if (
        obs.runtime_minutes is not None
        and cand.runtime_minutes is not None
        and abs(obs.runtime_minutes - cand.runtime_minutes) <= RUNTIME_TOLERANCE_MIN
    ):
        s += WEIGHTS["runtime"]
    overlap = {normalize_name(c) for c in obs.cast_top} & {normalize_name(c) for c in cand.cast_top}
    if len(overlap) >= CAST_MIN_OVERLAP:
        s += WEIGHTS["cast"]
    if obs.year is not None and cand.year is not None and obs.year == cand.year:
        s += WEIGHTS["year"]
    return round(s, 4)


def pick(
    scored: list[tuple[Candidate, float]], min_score: float, min_margin: float
) -> Candidate | None:
    if not scored:
        return None
    ranked = sorted(scored, key=itemgetter(1), reverse=True)
    leader, top = ranked[0]
    second = ranked[1][1] if len(ranked) > 1 else 0.0
    if top < min_score or (top - second) < min_margin:
        return None
    return leader
