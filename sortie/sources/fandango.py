import json
import re
from datetime import date, datetime
from pathlib import Path

from bs4 import BeautifulSoup

from sortie.http import HttpClient
from sortie.normalize import strip_year
from sortie.sources.base import FilmDetails, ShowingInfo, TheatreInfo

BASE = "https://www.fandango.com"

# fandango's napi is undocumented, so field names are guessed from limited
# live observation. first match wins. extend after running
# scripts/fandango_discover.py against a real response.
_KEYS = {
    "theatre_list": ("theaters", "Theaters", "results", "items"),
    "theatre_id": ("id", "theaterId", "theatreId", "tid"),
    "chain": ("chainName", "chain", "brand"),
    "city": ("city",),
    "distance": ("distance", "distanceMiles", "distance_miles"),
    "lat": ("latitude", "lat"),
    "lng": ("longitude", "lng", "lon"),
    "dates_list": ("dates", "calendar", "availableDates", "showDates"),
    "movie_list": ("movies", "Movies", "films"),
    "movie_id": ("id", "movieId", "filmId"),
    "movie_title": ("title", "name", "movieName"),
    "movie_url": ("movieUrl", "url", "href", "slug"),
    "showtime_value": ("date", "showtime", "time", "startTime", "dateTime"),
}

_ISO_DUR = re.compile(r"^PT(?:(\d+)H)?(?:(\d+)M)?(?:\d+S)?$")
_TIME_12H = re.compile(r"^\s*(\d{1,2}):(\d{2})\s*([AP]M)\s*$", re.IGNORECASE)


def _first(d: dict, key: str):
    # try each candidate spelling for this key, in order, first non-empty wins
    for name in _KEYS[key]:
        if name in d and d[name] not in (None, ""):
            return d[name]
    return None


def _list_under(payload, key: str) -> list:
    # the list we want can be at the top level, or one level inside a wrapper
    # dict like {"viewModel": {...}}
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []
    found = _first(payload, key)
    if isinstance(found, list):
        return found
    for inner in payload.values():
        if isinstance(inner, dict):
            found = _first(inner, key)
            if isinstance(found, list):
                return found
    return []


def parse_nearby(payload) -> list[TheatreInfo]:
    out = []
    for t in _list_under(payload, "theatre_list"):
        if not isinstance(t, dict):
            continue
        tid = _first(t, "theatre_id")
        name = t.get("name")
        if tid is None or not name:
            continue

        # lat/lng/city are sometimes on the theatre dict itself, sometimes
        # nested under "geo"/"location"/"address"
        geo = t.get("geo") or t.get("location") or {}
        lat = _first(t, "lat")
        if lat is None:
            lat = _first(geo, "lat")
        lng = _first(t, "lng")
        if lng is None:
            lng = _first(geo, "lng")
        city = _first(t, "city")
        if city is None:
            address = t.get("address") or {}
            city = address.get("city")

        dist = _first(t, "distance")
        out.append(
            TheatreInfo(
                source_theatre_id=str(tid),
                name=str(name),
                chain=_first(t, "chain"),
                city=city,
                lat=lat,
                lng=lng,
                distance_miles=float(dist) if dist is not None else None,
            )
        )
    return out


def _to_date(v) -> date | None:
    # a calendar entry is either a plain "YYYY-MM-DD" string or {"date": "..."}
    s = v.get("date") if isinstance(v, dict) else v
    if not isinstance(s, str) or len(s) < 10:
        return None
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


def parse_calendar(payload) -> list[date]:
    out = []
    for v in _list_under(payload, "dates_list"):
        d = _to_date(v)
        if d and d not in out:
            out.append(d)
    out.sort()
    return out


def _find_showtimes(node) -> list[dict]:
    # walk the payload for "showtimes" lists, however deep they are nested
    out = []
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "showtimes" and isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        out.append(item)
            else:
                out.extend(_find_showtimes(value))
    elif isinstance(node, list):
        for item in node:
            out.extend(_find_showtimes(item))
    return out


def _hhmm(raw) -> str | None:
    if not isinstance(raw, str):
        return None
    m = _TIME_12H.match(raw)
    if m:
        hour = int(m.group(1)) % 12
        if m.group(3).upper() == "PM":
            hour += 12
        return f"{hour:02d}:{m.group(2)}"
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).strftime("%H:%M")
    except ValueError:
        return None


def parse_showtimes(payload, show_date: date) -> list[ShowingInfo]:
    out = []
    for m in _list_under(payload, "movie_list"):
        if not isinstance(m, dict):
            continue
        movie_id = _first(m, "movie_id")
        title = _first(m, "movie_title")
        if movie_id is None or not title:
            continue

        times = []
        for s in _find_showtimes(m):
            hhmm = _hhmm(_first(s, "showtime_value"))
            if hhmm and hhmm not in times:
                times.append(hhmm)
        times.sort()

        _, year = strip_year(str(title))
        out.append(
            ShowingInfo(
                source_film_id=str(movie_id),
                raw_title=str(title),
                raw_year=year,
                show_date=show_date,
                show_times=times,
                film_url=_first(m, "movie_url"),
            )
        )
    return out


def iso_duration_minutes(s: str | None) -> int | None:
    if not s:
        return None
    m = _ISO_DUR.match(s.strip())
    if not m or (m.group(1) is None and m.group(2) is None):
        return None
    hours = int(m.group(1) or 0)
    minutes = int(m.group(2) or 0)
    return hours * 60 + minutes


def _names(value) -> list[str]:
    # collect "name" fields out of a schema.org person, or a list of them
    out = []
    if isinstance(value, dict):
        if value.get("name"):
            out.append(value["name"])
    elif isinstance(value, list):
        for item in value:
            out.extend(_names(item))
    elif isinstance(value, str):
        out.append(value)
    return out


def parse_jsonld_details(html: str) -> FilmDetails:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "")
        except json.JSONDecodeError:
            continue
        items = data if isinstance(data, list) else [data]
        for item in items:
            if isinstance(item, dict) and item.get("@type") == "Movie":
                directors = _names(item.get("director"))
                return FilmDetails(
                    runtime_minutes=iso_duration_minutes(item.get("duration")),
                    director=directors[0] if directors else None,
                    cast_top=_names(item.get("actor"))[:5],
                )
    return FilmDetails(None, None, [])


def make_fandango_http(archive_dir: Path) -> HttpClient:
    return HttpClient(
        source="fandango",
        min_interval_s=1.0,
        archive_dir=archive_dir,
        warm_url=f"{BASE}/",
        retries=3,
        backoff_s=(5, 30, 120),
    )


class FandangoSource:
    name = "fandango"

    def __init__(self, http: HttpClient, max_dates: int = 120):
        self.http = http
        self.max_dates = max_dates
        self._json_headers = {"Accept": "application/json"}

    def nearby_theatres(self, postal_code: str, radius_miles: int) -> list[TheatreInfo]:
        r = self.http.get(
            f"{BASE}/napi/nearbyTheaters",
            target=f"nearby-{postal_code}",
            headers=self._json_headers,
            params={"zipCode": postal_code, "limit": "100"},
        )
        theatres = parse_nearby(json.loads(r.text))
        out = []
        for t in theatres:
            # keep theatres with an unknown distance rather than drop them
            if t.distance_miles is None or t.distance_miles <= radius_miles:
                out.append(t)
        return out

    def showings(self, source_theatre_id: str) -> list[ShowingInfo]:
        r = self.http.get(
            f"{BASE}/napi/theaterCalendar/{source_theatre_id}",
            target=f"calendar-{source_theatre_id}",
            headers=self._json_headers,
        )
        dates = parse_calendar(json.loads(r.text))[: self.max_dates]
        out = []
        for d in dates:
            r = self.http.get(
                f"{BASE}/napi/theaterMovieShowtimes/{source_theatre_id}",
                target=f"showtimes-{source_theatre_id}-{d.isoformat()}",
                headers=self._json_headers,
                params={"date": d.isoformat()},
            )
            out.extend(parse_showtimes(json.loads(r.text), d))
        return out

    def film_details(self, source_film_id: str, film_url: str | None) -> FilmDetails:
        if not film_url:
            return FilmDetails(None, None, [])
        url = film_url if film_url.startswith("http") else f"{BASE}{film_url}"
        r = self.http.get(url, target=f"film-{source_film_id}")
        return parse_jsonld_details(r.text)
