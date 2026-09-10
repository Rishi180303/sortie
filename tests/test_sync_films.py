from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select

from sortie.clients.tmdb import TmdbFilm
from sortie.models import Film, FilmAlias
from sortie.sync.films import alias_set, hydrate_film, hydrate_films

NOW = datetime(2026, 9, 8, tzinfo=UTC)


class FakeTmdb:
    def __init__(self):
        self.calls = []

    def film(self, tmdb_id):
        self.calls.append(tmdb_id)
        return TmdbFilm(
            tmdb_id=tmdb_id,
            title="Princess Mononoke",
            original_title="もののけ姫",
            runtime_minutes=134,
            director="Hayao Miyazaki",
            cast_top=["A", "B"],
            us_theatrical_date=date(1999, 10, 29),
            poster_path="/p.jpg",
            alternative_titles=["Mononoke Hime", "Princess Mononoke"],
            translation_titles=["Prinzessin Mononoke", ""],
        )


def test_hydrate_creates_film_and_aliases(db):
    t = FakeTmdb()
    f = hydrate_film(db, t, 128, NOW)
    assert f.title == "Princess Mononoke" and f.director == "Hayao Miyazaki"
    assert f.us_theatrical_date == date(1999, 10, 29)
    assert f.cast_top == ["A", "B"]
    expected_aliases = {"princess mononoke", "もののけ姫", "mononoke hime", "prinzessin mononoke"}
    assert alias_set(db, 128) == expected_aliases
    origins = {a.alias_normalized: a.origin for a in db.execute(select(FilmAlias)).scalars()}
    assert origins["princess mononoke"] == "primary"
    assert origins["mononoke hime"] == "alternative"


def test_hydrate_skips_fresh_rows(db):
    t = FakeTmdb()
    hydrate_film(db, t, 128, NOW)
    hydrate_film(db, t, 128, NOW + timedelta(days=1))
    assert t.calls == [128]


def test_hydrate_refreshes_stale_rows_and_replaces_aliases(db):
    t = FakeTmdb()
    hydrate_film(db, t, 128, NOW)
    db.add(FilmAlias(tmdb_id=128, alias_normalized="stale alias", origin="alternative"))
    db.flush()
    hydrate_film(db, t, 128, NOW + timedelta(days=31))
    assert t.calls == [128, 128]
    assert "stale alias" not in alias_set(db, 128)


def test_hydrate_films_counts_fetches(db):
    t = FakeTmdb()
    db.add(Film(tmdb_id=1, title="x", refreshed_at=NOW))
    db.flush()
    assert hydrate_films(db, t, [1, 2, 3, 2], NOW) == 2
    assert t.calls == [2, 3]
