from datetime import UTC, date, datetime

from sortie.alerts.diff import Alert
from sortie.alerts.digest import build_digest, is_empty, render_html, render_text, subject
from sortie.models import Film, FilmState, Showing, SourceFilm, Theatre

NOW = datetime(2026, 9, 8, tzinfo=UTC)
TODAY = date(2026, 9, 8)


def seed(db):
    far = Theatre(source="fake", source_theatre_id="far", name="Landmark Midtown", distance_miles=18.0)
    fav = Theatre(source="fake", source_theatre_id="fav", name="AMC Metro 14", distance_miles=2.0, is_favourite=True)
    mid = Theatre(source="fake", source_theatre_id="mid", name="Regal Riverside", distance_miles=22.0)
    db.add_all([far, fav, mid])
    db.add(Film(tmdb_id=1, title="Primetime", us_theatrical_date=date(2026, 9, 25)))
    db.add(Film(tmdb_id=2, title="Klara and the Sun", us_theatrical_date=date(2026, 10, 2)))
    db.flush()
    s1 = SourceFilm(source="fake", source_film_id="1", raw_title="Primetime (2026)", tmdb_id=1, resolution="auto")
    s2 = SourceFilm(source="fake", source_film_id="2", raw_title="Klara and the Sun", tmdb_id=2, resolution="auto")
    db.add_all([s1, s2])
    db.flush()
    for sf, t, d in [(s1, far, date(2026, 9, 25)), (s1, far, date(2026, 9, 26)), (s1, fav, date(2026, 9, 30)),
                     (s1, mid, date(2026, 9, 26)), (s2, far, date(2026, 10, 2))]:
        db.add(Showing(source_film_id=sf.id, theatre_id=t.id, show_date=d, show_times=["19:00"],
                       first_seen=NOW, last_seen=NOW))
    db.add(FilmState(tmdb_id=1, is_watchlist=True, earliest_date_anywhere=date(2026, 9, 25),
                     earliest_theatre_id=far.id, earliest_date_at_fav=date(2026, 9, 30),
                     earliest_fav_theatre_id=fav.id, last_computed=NOW))
    db.add(FilmState(tmdb_id=2, is_watchlist=True, earliest_date_anywhere=date(2026, 10, 2),
                     earliest_theatre_id=far.id, last_computed=NOW))
    db.flush()


def test_build_digest_release_map(db):
    seed(db)
    alerts = {1: [Alert("new_anywhere", 1), Alert("new_at_favourite", 1)], 2: [Alert("new_anywhere", 2)]}
    d = build_digest(db, alerts, TODAY, needs_input=3, health=["fandango: 4 theatres"], failures=[])
    assert [e.title for e in d.watchlist] == ["Primetime", "Klara and the Sun"]  # fav-first ordering
    p = d.watchlist[0]
    assert p.earliest.name == "Landmark Midtown" and p.earliest.date == date(2026, 9, 25)
    assert p.at_fav.name == "AMC Metro 14" and p.at_fav.date == date(2026, 9, 30)
    assert [(o.name, o.date) for o in p.others] == [("Regal Riverside", date(2026, 9, 26))]
    assert p.kinds == ("new_anywhere", "new_at_favourite")
    k = d.watchlist[1]
    assert k.at_fav is None and k.others == ()
    assert d.needs_input == 3 and d.rereleases == () and d.soon == ()


def test_approaching_only_goes_to_soon(db):
    seed(db)
    d = build_digest(db, {2: [Alert("approaching", 2)]}, TODAY, 0, [], [])
    assert [e.title for e in d.soon] == ["Klara and the Sun"] and d.watchlist == ()


def test_render_text_contains_release_map(db):
    seed(db)
    d = build_digest(db, {1: [Alert("new_anywhere", 1), Alert("new_at_favourite", 1)], 2: [Alert("new_anywhere", 2)]},
                     TODAY, 1, ["fandango: 4 theatres"], [])
    txt = render_text(d)
    assert "PRIMETIME" in txt
    assert "Earliest anywhere   Fri Sep 25  ·  Landmark Midtown" in txt and "18 mi" in txt
    assert "Your theatres       Wed Sep 30  ·  AMC Metro 14" in txt
    assert "5 days earlier if you drive" in txt
    assert "Also  Sep 26 Regal Riverside (22 mi)" in txt
    assert "KLARA AND THE SUN" in txt and "not playing at your favourites" in txt and "nearest is 18 mi" in txt
    assert "1 film needs your input" in txt
    assert "fandango: 4 theatres" in txt
    html = render_html(d)
    assert "<pre" in html and "PRIMETIME" in html


def test_subject_and_emptiness(db):
    seed(db)
    d = build_digest(db, {1: [Alert("new_anywhere", 1)]}, TODAY, 0, [], [])
    assert subject(d) == "sortie: 1 new film near you"
    e = build_digest(db, {}, TODAY, 0, [], [])
    assert is_empty(e) and subject(e) == "sortie: weekly check-in"
    f = build_digest(db, {}, TODAY, 0, [], ["Landmark Midtown: HTTP 403"])
    assert not is_empty(f) and subject(f) == "sortie: 1 fetch failure"
    assert "FAILURES" in render_text(f) and "HTTP 403" in render_text(f)
