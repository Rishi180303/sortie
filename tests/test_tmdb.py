import json
from datetime import date

from sortie.clients.tmdb import TmdbClient

SEARCH = {
    "results": [
        {
            "id": 2,
            "title": "Look Back",
            "original_title": "ルックバック",
            "release_date": "2024-06-28",
            "popularity": 40.0,
        },
        {
            "id": 7,
            "title": "Look Back",
            "original_title": "Look Back",
            "release_date": "2026-10-02",
            "popularity": 12.0,
        },
        {
            "id": 9,
            "title": "Look Back in Anger",
            "original_title": "Look Back in Anger",
            "release_date": "1959-05-28",
            "popularity": 3.0,
        },
    ]
}

FILM = {
    "id": 7,
    "title": "Look Back",
    "original_title": "Look Back",
    "runtime": 98,
    "poster_path": "/lb.jpg",
    "credits": {
        "crew": [{"job": "Producer", "name": "P"}, {"job": "Director", "name": "Jane Doe"}],
        "cast": [{"name": f"Actor {i}"} for i in range(8)],
    },
    "release_dates": {
        "results": [
            {
                "iso_3166_1": "JP",
                "release_dates": [{"type": 3, "release_date": "2026-08-01T00:00:00.000Z"}],
            },
            {
                "iso_3166_1": "US",
                "release_dates": [
                    {"type": 1, "release_date": "2026-09-01T00:00:00.000Z"},  # premiere — ignored
                    {"type": 2, "release_date": "2026-10-02T00:00:00.000Z"},  # limited
                    {"type": 3, "release_date": "2026-10-09T00:00:00.000Z"},  # theatrical
                ],
            },
        ]
    },
    "alternative_titles": {"titles": [{"iso_3166_1": "GB", "title": "Looking Back", "type": ""}]},
    "translations": {
        "translations": [
            {"iso_639_1": "fr", "data": {"title": "Regarde en arrière"}},
            {"iso_639_1": "de", "data": {"title": ""}},
        ]
    },
}


def test_search_sorts_by_popularity_and_limits(routed, http):
    routed.add("/3/search/movie", 200, json.dumps(SEARCH))
    c = TmdbClient("k", http)
    got = c.search("look back", limit=2)
    assert [g.tmdb_id for g in got] == [2, 7]
    assert got[0].release_year == 2024
    assert "query=look+back" in routed.calls[0][1]
    assert "api_key=k" in routed.calls[0][1]
    assert "year=" not in routed.calls[0][1]


def test_film_parses_everything(routed, http):
    routed.add("/3/movie/7", 200, json.dumps(FILM))
    c = TmdbClient("k", http)
    f = c.film(7)
    assert f.runtime_minutes == 98
    assert f.director == "Jane Doe"
    assert f.cast_top == [f"Actor {i}" for i in range(5)]
    assert f.us_theatrical_date == date(2026, 10, 2)
    assert f.alternative_titles == ["Looking Back"]
    assert f.translation_titles == ["Regarde en arrière"]
    assert f.poster_path == "/lb.jpg"
    assert "append_to_response=credits" in routed.calls[0][1]


def test_film_without_us_release(routed, http):
    data = dict(FILM)
    data["release_dates"] = {"results": []}
    data["credits"] = {"crew": [], "cast": []}
    routed.add("/3/movie/7", 200, json.dumps(data))
    f = TmdbClient("k", http).film(7)
    assert f.us_theatrical_date is None
    assert f.director is None
    assert f.cast_top == []
