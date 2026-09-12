import json

import pytest

from sortie.clients.fathom import FATHOM_URL, FathomClient, parse_active_titles
from sortie.http import FetchError

FEED = {
    "Events": [
        {
            "EventID": 1659,
            "Title": "The Passion of the Christ",
            "SuperTitle": None,
            "SubTitle": None,
            "Slug": "the-passion-of-the-christ",
            "Status": "Active",
            "FirstDate": "2026-09-12T00:00:00",
            "NextDate": "2026-09-12T00:00:00",
            "RunTime": None,
            "Dates": [
                {
                    "Date": "2026-09-12T00:00:00",
                    "PublicOnSale": "2026-07-24T00:00:00",
                    "PrivateOnSale": None,
                    "Tags": [],
                },
                {
                    "Date": "2026-09-13T00:00:00",
                    "PublicOnSale": None,
                    "PrivateOnSale": None,
                    "Tags": [],
                },
            ],
        },
        {
            "EventID": 1626,
            "Title": "The Transformers: The Movie 40th Anniversary",
            "SuperTitle": "The Movie 40th Anniversary",
            "SubTitle": "The Transformers",
            "Slug": "the-transformers-the-movie-40th-anniversary",
            "Status": "Active",
            "Dates": [
                {
                    "Date": "2026-09-17T00:00:00",
                    "PublicOnSale": None,
                    "PrivateOnSale": None,
                    "Tags": [],
                }
            ],
        },
        {
            "EventID": 1700,
            "Title": "Princess Mononoke – Studio Ghibli Fest 2026",
            "Status": "Active",
            "Dates": [
                {
                    "Date": "2026-10-03T00:00:00",
                    "PublicOnSale": None,
                    "PrivateOnSale": None,
                    "Tags": [],
                }
            ],
        },
        {
            "EventID": 1084,
            "Title": "Cinderella",
            "SuperTitle": "The Met: Live in HD",
            "Slug": "the-metropolitan-opera-cinderella",
            "Status": "Archive",
            "FirstDate": "2022-01-08T00:00:00",
            "NextDate": None,
            "RunTime": 110,
            "Dates": [],
        },
        {
            "EventID": 1467,
            "Title": "MATT TEST",
            "Status": "Active",
            "Dates": [{"Date": "2027-01-01T00:00:00"}],
        },
        {
            "EventID": 1468,
            "Title": "MATT TEST 2",
            "Status": "Active",
            "Dates": [{"Date": "2027-01-01T00:00:00"}],
        },
        {"EventID": 1800, "Title": "Announced Without Dates", "Status": "Active", "Dates": []},
    ]
}


def test_parse_keeps_active_dated_real_events_in_feed_order():
    assert parse_active_titles(FEED) == [
        "The Passion of the Christ",
        "The Transformers: The Movie 40th Anniversary",
        "Princess Mononoke – Studio Ghibli Fest 2026",
    ]


def test_parse_empty_feed():
    assert parse_active_titles({"Events": []}) == []
    assert parse_active_titles({}) == []


def test_client_returns_normalized_titles(routed, http):
    routed.add("api.fathomentertainment.com/api/events", 200, json.dumps(FEED))
    titles = FathomClient(http).active_titles()
    assert titles == {
        "the passion of the christ",
        "the transformers the movie",
        "princess mononoke",
    }
    assert routed.calls[0][1] == FATHOM_URL


def test_client_failure_raises(routed, http):
    routed.add("api.fathomentertainment.com/api/events", 500, "down")
    with pytest.raises(FetchError):
        FathomClient(http).active_titles()
