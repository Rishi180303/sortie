import json
from datetime import date

from sortie.sources.fandango import (
    FandangoSource,
    iso_duration_minutes,
    parse_calendar,
    parse_jsonld_details,
    parse_nearby,
    parse_showtimes,
)

NEARBY = {
    "theaters": [
        {
            "id": "aatyg",
            "name": "Harkins Northfield 18",
            "chainName": "Harkins",
            "address": {"city": "Denver"},
            "geo": {"latitude": 39.8, "longitude": -104.9},
            "distance": 3.2,
        },
        {
            "theaterId": "aaxvl",
            "name": "Harkins Cerritos 16",
            "chain": "Harkins",
            "city": "Cerritos",
            "latitude": 33.86,
            "longitude": -118.09,
            "distanceMiles": 12.7,
        },
    ]
}

CALENDAR = {"dates": ["2026-09-08", "2026-09-09", {"date": "2026-09-10"}]}

SHOWTIMES = {
    "viewModel": {
        "movies": [
            {
                "id": 246473,
                "title": "Practical Magic 2 (2026)",
                "movieUrl": "/practical-magic-2-2026-246473/movie-overview",
                "variants": [
                    {
                        "amenityGroups": [
                            {
                                "showtimes": [
                                    {"date": "2026-09-08T16:30:00"},
                                    {"date": "2026-09-08T19:45:00"},
                                ]
                            }
                        ]
                    }
                ],
            },
            {
                "movieId": 8821,
                "name": "The Transformers: The Movie 40th Anniversary (2026)",
                "url": "/the-transformers-the-movie-40th-anniversary-2026-8821/movie-overview",
                "showtimes": [{"time": "7:00 PM"}],
            },
        ]
    }
}

OVERVIEW_HTML = """<html><head>
<script type="application/ld+json">{"@context":"https://schema.org","@type":"Movie",
"name":"Practical Magic 2 (2026)","datePublished":"2026-09-18","duration":"PT1H52M",
"director":{"@type":"Person","name":"Susanne Bier"},
"actor":[{"name":"Sandra Bullock"},{"name":"Nicole Kidman"},{"name":"A"},{"name":"B"},
{"name":"C"},{"name":"D"}]}
</script></head><body></body></html>"""


def test_parse_nearby_tolerates_key_variants():
    t = parse_nearby(NEARBY)
    assert [x.source_theatre_id for x in t] == ["aatyg", "aaxvl"]
    assert t[0].chain == "Harkins" and t[0].city == "Denver" and t[0].distance_miles == 3.2
    assert t[0].lat == 39.8 and t[1].lat == 33.86 and t[1].distance_miles == 12.7


def test_parse_calendar():
    assert parse_calendar(CALENDAR) == [date(2026, 9, 8), date(2026, 9, 9), date(2026, 9, 10)]
    assert parse_calendar(["2026-09-08"]) == [date(2026, 9, 8)]
    assert parse_calendar({}) == []


def test_parse_showtimes_recurses_and_normalizes_times():
    s = parse_showtimes(SHOWTIMES, date(2026, 9, 8))
    assert [x.source_film_id for x in s] == ["246473", "8821"]
    assert s[0].raw_title == "Practical Magic 2 (2026)" and s[0].raw_year == 2026
    assert s[0].film_url == "/practical-magic-2-2026-246473/movie-overview"
    assert s[0].show_times == ["16:30", "19:45"] and s[0].show_date == date(2026, 9, 8)
    assert s[1].show_times == ["19:00"]


def test_iso_duration():
    assert iso_duration_minutes("PT1H52M") == 112
    assert iso_duration_minutes("PT45M") == 45
    assert iso_duration_minutes("PT2H") == 120
    assert iso_duration_minutes(None) is None and iso_duration_minutes("junk") is None


def test_parse_jsonld_details():
    d = parse_jsonld_details(OVERVIEW_HTML)
    assert d.runtime_minutes == 112 and d.director == "Susanne Bier"
    assert d.cast_top == ["Sandra Bullock", "Nicole Kidman", "A", "B", "C"]
    assert parse_jsonld_details("<html></html>").director is None


def test_source_end_to_end(routed, http):
    routed.add("/napi/nearbyTheaters", 200, json.dumps(NEARBY))
    routed.add(
        "/napi/theaterCalendar/aatyg", 200, json.dumps({"dates": ["2026-09-08", "2026-09-09"]})
    )
    routed.add("/napi/theaterMovieShowtimes/aatyg?date=2026-09-08", 200, json.dumps(SHOWTIMES))
    routed.add(
        "/napi/theaterMovieShowtimes/aatyg?date=2026-09-09",
        200,
        json.dumps({"viewModel": {"movies": []}}),
    )
    routed.add("/practical-magic-2-2026-246473/movie-overview", 200, OVERVIEW_HTML)
    src = FandangoSource(http)
    assert len(src.nearby_theatres("10001", 25)) == 2
    shows = src.showings("aatyg")
    assert len(shows) == 2 and all(s.show_date == date(2026, 9, 8) for s in shows)
    d = src.film_details("246473", "/practical-magic-2-2026-246473/movie-overview")
    assert d.director == "Susanne Bier" and d.runtime_minutes == 112
    urls = [c[1] for c in routed.calls]
    assert urls[1].endswith("/napi/theaterCalendar/aatyg")
    assert "zipCode=10001" in urls[0]


def test_showings_respects_max_dates(routed, http):
    routed.add(
        "/napi/theaterCalendar/aatyg",
        200,
        json.dumps({"dates": [f"2026-09-{d:02d}" for d in range(1, 30)]}),
    )
    routed.add("/napi/theaterMovieShowtimes/aatyg", 200, json.dumps({"viewModel": {"movies": []}}))
    FandangoSource(http, max_dates=3).showings("aatyg")
    assert len(routed.calls) == 1 + 3
