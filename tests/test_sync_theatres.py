from sqlalchemy import select

from sortie.models import Theatre
from sortie.sources.base import TheatreInfo
from sortie.sync.theatres import refresh_theatres
from tests.conftest import FakeSource

T1 = TheatreInfo("zz001", "Example 12", chain="AMC", city="Example City", distance_miles=1.5)
T2 = TheatreInfo("zz002", "Riverside 8", chain="Regal", city="Example City", distance_miles=9.0)


def test_first_refresh_inserts_tracked_non_favourite(db):
    n = refresh_theatres(db, FakeSource(theatres=[T1, T2]), "10001", 25)
    assert n == 2
    rows = db.execute(select(Theatre).order_by(Theatre.source_theatre_id)).scalars().all()
    assert [r.name for r in rows] == ["Example 12", "Riverside 8"]
    assert all(r.source == "fake" and r.tracked and not r.is_favourite for r in rows)
    assert rows[0].distance_miles == 1.5


def test_refresh_preserves_flags_and_updates_metadata(db):
    refresh_theatres(db, FakeSource(theatres=[T1]), "10001", 25)
    t = db.execute(select(Theatre)).scalar_one()
    t.is_favourite = True
    t.tracked = False
    db.flush()
    renamed = TheatreInfo("zz001", "Example 12 & IMAX", chain="AMC", distance_miles=1.7)
    refresh_theatres(db, FakeSource(theatres=[renamed]), "10001", 25)
    t = db.execute(select(Theatre)).scalar_one()
    assert t.name == "Example 12 & IMAX" and t.distance_miles == 1.7
    assert t.is_favourite is True and t.tracked is False


def test_theatres_absent_from_refresh_are_kept(db):
    refresh_theatres(db, FakeSource(theatres=[T1, T2]), "10001", 25)
    refresh_theatres(db, FakeSource(theatres=[T1]), "10001", 25)
    assert len(db.execute(select(Theatre)).scalars().all()) == 2
