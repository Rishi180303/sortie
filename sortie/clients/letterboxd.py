import re
from dataclasses import dataclass

from bs4 import BeautifulSoup

from sortie.http import HttpClient
from sortie.normalize import strip_year

BASE = "https://letterboxd.com"
_TMDB_HREF = re.compile(r"themoviedb\.org/movie/(\d+)")
_TMDB_TV_HREF = re.compile(r"themoviedb\.org/tv/\d+")


def _attr(tag, name: str) -> str:
    # beautifulsoup types an attribute as possibly a list, these are all single
    v = tag.get(name, "")
    return v if isinstance(v, str) else " ".join(v)


@dataclass(frozen=True)
class WatchlistItem:
    slug: str
    title: str
    year: int | None


def parse_watchlist_page(html: str) -> list[WatchlistItem]:
    soup = BeautifulSoup(html, "html.parser")
    seen: set[str] = set()
    items: list[WatchlistItem] = []

    # find all elements with either modern or legacy slug attributes
    for el in soup.select("[data-item-slug], [data-film-slug]"):
        slug = _attr(el, "data-item-slug") or _attr(el, "data-film-slug")
        if not slug or slug in seen:
            continue
        seen.add(slug)

        # get the name from modern or legacy name attributes
        name = _attr(el, "data-item-name") or _attr(el, "data-film-name")
        if not name:
            name = el.get_text(strip=True)
        if not name:
            name = slug

        # split year from title
        title, year = strip_year(name)
        items.append(WatchlistItem(slug=slug, title=title, year=year))

    return items


def parse_film_tmdb_id(html: str) -> int | None:
    # he keeps miniseries on his watchlist, and their hidden film id can be a dead
    # record, so a link to a tmdb tv page means this is not a film we can match
    if _TMDB_TV_HREF.search(html):
        return None

    soup = BeautifulSoup(html, "html.parser")

    # try to get tmdb id from data-tmdb-id on body tag
    if soup.body is not None:
        v = _attr(soup.body, "data-tmdb-id")
        if v and str(v).isdigit():
            return int(v)

    # fall back to finding themoviedb.org link
    m = _TMDB_HREF.search(html)
    if m:
        return int(m.group(1))

    return None


class LetterboxdClient:
    def __init__(self, http: HttpClient):
        self.http = http

    def watchlist(self, username: str, max_pages: int = 100) -> list[WatchlistItem]:
        out: list[WatchlistItem] = []
        seen: set[str] = set()

        for page in range(1, max_pages + 1):
            # page 1 is /{user}/watchlist/, later pages have page/{n}/
            if page == 1:
                url = f"{BASE}/{username}/watchlist/"
            else:
                url = f"{BASE}/{username}/watchlist/page/{page}/"

            r = self.http.get(url, target=f"watchlist-{username}-p{page}")
            items = parse_watchlist_page(r.text)

            # only keep items we haven't seen yet
            fresh: list[WatchlistItem] = []
            for i in items:
                if i.slug not in seen:
                    fresh.append(i)

            # if this page had no new items, stop paginating
            if not fresh:
                break

            # add fresh items to our results and seen set
            for i in fresh:
                seen.add(i.slug)
                out.append(i)

        return out

    def tmdb_id_for(self, slug: str) -> int | None:
        r = self.http.get(f"{BASE}/film/{slug}/", target=f"film-{slug}")
        return parse_film_tmdb_id(r.text)
