import json
from dataclasses import dataclass
from datetime import date

from sortie.http import HttpClient

BASE = "https://api.themoviedb.org/3"
_US_THEATRICAL_TYPES = {2, 3}


@dataclass
class TmdbCandidate:
    tmdb_id: int
    title: str
    original_title: str
    release_year: int | None
    popularity: float


@dataclass
class TmdbFilm:
    tmdb_id: int
    title: str
    original_title: str | None
    runtime_minutes: int | None
    director: str | None
    cast_top: list[str]
    us_theatrical_date: date | None
    poster_path: str | None
    alternative_titles: list[str]
    translation_titles: list[str]


def _year(s: str | None) -> int | None:
    return int(s[:4]) if s and len(s) >= 4 and s[:4].isdigit() else None


def _popularity(candidate: TmdbCandidate) -> float:
    return candidate.popularity


class TmdbClient:
    def __init__(self, api_key: str, http: HttpClient):
        self.api_key = api_key
        self.http = http

    def search(self, query: str, limit: int = 5) -> list[TmdbCandidate]:
        r = self.http.get(
            f"{BASE}/search/movie",
            target=f"search-{query}",
            params={"api_key": self.api_key, "query": query, "include_adult": "false"},
        )
        results = json.loads(r.text).get("results", [])
        candidates = []
        for item in results:
            candidates.append(
                TmdbCandidate(
                    tmdb_id=item["id"],
                    title=item.get("title") or "",
                    original_title=item.get("original_title") or "",
                    release_year=_year(item.get("release_date")),
                    popularity=float(item.get("popularity") or 0.0),
                )
            )
        # most popular first, so the obvious match is at the top
        candidates.sort(key=_popularity, reverse=True)
        return candidates[:limit]

    def film(self, tmdb_id: int) -> TmdbFilm:
        r = self.http.get(
            f"{BASE}/movie/{tmdb_id}",
            target=f"movie-{tmdb_id}",
            params={
                "api_key": self.api_key,
                "append_to_response": "credits,release_dates,alternative_titles,translations",
            },
        )
        d = json.loads(r.text)
        crew = d.get("credits", {}).get("crew", [])
        # tmdb lists the director under crew, not cast
        director = None
        for member in crew:
            if member.get("job") == "Director":
                director = member["name"]
                break

        cast_top = []
        for c in d.get("credits", {}).get("cast", [])[:5]:
            cast_top.append(c["name"])

        us_dates: list[date] = []
        for entry in d.get("release_dates", {}).get("results", []):
            if entry.get("iso_3166_1") != "US":
                continue
            for rd in entry.get("release_dates", []):
                if rd.get("type") in _US_THEATRICAL_TYPES and rd.get("release_date"):
                    us_dates.append(date.fromisoformat(rd["release_date"][:10]))

        alt = []
        for t in d.get("alternative_titles", {}).get("titles", []):
            if t.get("title"):
                alt.append(t["title"])

        tr = []
        for t in d.get("translations", {}).get("translations", []):
            title = t.get("data", {}).get("title")
            if title:
                tr.append(title)

        return TmdbFilm(
            tmdb_id=d["id"],
            title=d.get("title") or "",
            original_title=d.get("original_title"),
            runtime_minutes=d.get("runtime"),
            director=director,
            cast_top=cast_top,
            us_theatrical_date=min(us_dates) if us_dates else None,
            poster_path=d.get("poster_path"),
            alternative_titles=alt,
            translation_titles=tr,
        )
