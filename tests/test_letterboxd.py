from sortie.clients.letterboxd import (
    LetterboxdClient,
    parse_film_tmdb_id,
    parse_watchlist_page,
)

PAGE = """
<html><body>
<ul class="poster-list">
  <li class="poster-container">
    <div class="react-component" data-item-slug="look-back-2026"
         data-item-name="Look Back (2026)" data-item-link="/film/look-back-2026/"></div>
  </li>
  <li class="poster-container">
    <div class="react-component" data-item-slug="infernal-affairs"
         data-item-name="Infernal Affairs (2002)" data-item-link="/film/infernal-affairs/"></div>
  </li>
  <li class="poster-container">
    <div class="react-component" data-item-slug="remain" data-item-name="Remain"></div>
  </li>
  <li class="poster-container">
    <div class="react-component" data-item-slug="remain" data-item-name="Remain"></div>
  </li>
</ul>
</body></html>
"""

LEGACY_PAGE = """
<ul><li><div class="film-poster" data-film-slug="secretary"
         data-film-name="Secretary (2002)"></div></li></ul>
"""

FILM_PAGE = """
<html><body class="film" data-tmdb-id="12345" data-film-id="99">
<a data-track-action="TMDB" href="https://www.themoviedb.org/movie/12345/"></a>
</body></html>
"""


def test_parse_watchlist_page_dedupes_and_splits_year():
    items = parse_watchlist_page(PAGE)
    assert [i.slug for i in items] == ["look-back-2026", "infernal-affairs", "remain"]
    assert items[0].title == "Look Back" and items[0].year == 2026
    assert items[2].year is None


def test_parse_watchlist_page_legacy_markup():
    items = parse_watchlist_page(LEGACY_PAGE)
    assert items == [type(items[0])("secretary", "Secretary", 2002)]


def test_parse_film_tmdb_id():
    assert parse_film_tmdb_id(FILM_PAGE) == 12345
    assert parse_film_tmdb_id("<html><body></body></html>") is None


def test_watchlist_paginates_until_empty(routed, http):
    routed.add("/example-user/watchlist/page/2/", 200, PAGE.replace("look-back-2026", "second"))
    routed.add("/example-user/watchlist/page/3/", 200, "<html><body></body></html>")
    routed.add("/example-user/watchlist/", 200, PAGE)
    c = LetterboxdClient(http)
    items = c.watchlist("example-user")
    assert len(items) == 4  # 3 from page 1 + "second" from page 2 (rest dedup)
    assert [call[1] for call in routed.calls] == [
        "https://letterboxd.com/example-user/watchlist/",
        "https://letterboxd.com/example-user/watchlist/page/2/",
        "https://letterboxd.com/example-user/watchlist/page/3/",
    ]


def test_watchlist_stops_when_page_repeats(routed, http):
    routed.add("/watchlist/", 200, PAGE)  # every page identical
    items = LetterboxdClient(http).watchlist("example-user", max_pages=10)
    assert len(items) == 3
    assert len(routed.calls) == 2  # page 1, then page 2 detected as all-duplicates


def test_tmdb_id_for_uses_film_page(routed, http):
    routed.add("/film/look-back-2026/", 200, FILM_PAGE)
    assert LetterboxdClient(http).tmdb_id_for("look-back-2026") == 12345
    assert routed.calls[0][1] == "https://letterboxd.com/film/look-back-2026/"
