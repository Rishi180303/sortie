from sqlalchemy import select
from sqlalchemy.orm import Session

from sortie.models import Theatre
from sortie.sources.base import ShowtimeSource


def refresh_theatres(
    db: Session, source: ShowtimeSource, postal_code: str, radius_miles: int
) -> int:
    infos = source.nearby_theatres(postal_code, radius_miles)
    existing = {}
    for t in db.execute(select(Theatre).where(Theatre.source == source.name)).scalars():
        existing[t.source_theatre_id] = t
    for info in infos:
        t = existing.get(info.source_theatre_id)
        if t is None:
            t = Theatre(
                source=source.name,
                source_theatre_id=info.source_theatre_id,
                name=info.name,
                tracked=True,
                is_favourite=False,
            )
            db.add(t)
        t.name = info.name
        t.chain = info.chain
        t.city = info.city
        t.lat = info.lat
        t.lng = info.lng
        t.distance_miles = info.distance_miles
    db.flush()
    return len(infos)
