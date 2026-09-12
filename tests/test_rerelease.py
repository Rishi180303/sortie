from datetime import date

from sortie.alerts.rerelease import is_rerelease

OLD = date(1986, 8, 8)
SHOW = date(2026, 9, 17)
PLAIN = {"The Transformers: The Movie (2026)"}
MARKED = {"The Transformers: The Movie 40th Anniversary (2026)"}
ALIASES = {"the transformers the movie", "transformers the movie"}


def test_gap_alone_never_decides():
    assert is_rerelease(OLD, SHOW, PLAIN, ALIASES, set(), 2) is False


def test_gap_plus_title_marker():
    assert is_rerelease(OLD, SHOW, MARKED, ALIASES, set(), 2) is True


def test_gap_plus_fathom_listing():
    fathom = {"the transformers the movie", "spirited away"}
    assert is_rerelease(OLD, SHOW, PLAIN, ALIASES, fathom, 2) is True


def test_fathom_listing_of_another_film_does_not_count():
    assert is_rerelease(OLD, SHOW, PLAIN, ALIASES, {"spirited away"}, 2) is False


def test_marker_without_gap_is_not_a_rerelease():
    assert (
        is_rerelease(date(2026, 3, 1), SHOW, {"Sinners: 4K Restoration"}, set(), set(), 2) is False
    )


def test_unknown_release_date_is_never_a_rerelease():
    assert is_rerelease(None, SHOW, MARKED, ALIASES, ALIASES, 2) is False


def test_gap_uses_configured_years():
    assert is_rerelease(date(2024, 6, 1), SHOW, {"Film Remastered"}, set(), set(), 2) is True
    assert is_rerelease(date(2024, 6, 1), SHOW, {"Film Remastered"}, set(), set(), 3) is False
