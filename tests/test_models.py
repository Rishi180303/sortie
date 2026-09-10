from datetime import UTC, date, datetime

from sqlalchemy import inspect, select

from sortie.models import Film, FilmAlias, Showing, SourceFilm, Theatre


def test_all_tables_exist(engine):
    names = set(inspect(engine).get_table_names())
    assert names >= {
        "theatre",
        "film",
        "film_alias",
        "watchlist_entry",
        "source_film",
        "showing",
        "film_state",
        "match_queue",
        "fetch_log",
    }


def test_round_trip_showing(db):
    now = datetime.now(UTC)
    t = Theatre(source="fandango", source_theatre_id="zz001", name="Example 12", tracked=True)
    f = Film(tmdb_id=1, title="Example Film")
    sf = SourceFilm(source="fandango", source_film_id="900", raw_title="Example Film (2026)")
    db.add_all([t, f, sf])
    db.flush()
    db.add(FilmAlias(tmdb_id=1, alias_normalized="example film", origin="primary"))
    db.add(
        Showing(
            source_film_id=sf.id,
            theatre_id=t.id,
            show_date=date(2026, 9, 10),
            show_times=["19:30", "22:00"],
            first_seen=now,
            last_seen=now,
        )
    )
    db.flush()
    got = db.execute(select(Showing)).scalar_one()
    assert got.show_times == ["19:30", "22:00"]
    assert got.theatre_id == t.id
