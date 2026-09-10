from dataclasses import dataclass, field
from datetime import date
from typing import Protocol


@dataclass(frozen=True)
class TheatreInfo:
    source_theatre_id: str
    name: str
    chain: str | None = None
    city: str | None = None
    lat: float | None = None
    lng: float | None = None
    distance_miles: float | None = None


@dataclass(frozen=True)
class ShowingInfo:
    source_film_id: str
    raw_title: str
    raw_year: int | None
    show_date: date
    show_times: list[str] = field(default_factory=list)  # "HH:MM" local, 24h
    film_url: str | None = None


@dataclass(frozen=True)
class FilmDetails:
    runtime_minutes: int | None
    director: str | None
    cast_top: list[str] = field(default_factory=list)


class ShowtimeSource(Protocol):
    name: str

    def nearby_theatres(self, postal_code: str, radius_miles: int) -> list[TheatreInfo]: ...

    def showings(self, source_theatre_id: str) -> list[ShowingInfo]: ...

    def film_details(self, source_film_id: str, film_url: str | None) -> FilmDetails: ...
