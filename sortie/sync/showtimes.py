from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from sortie.models import Showing, SourceFilm, Theatre
from sortie.sources.base import ShowtimeSource


@dataclass
class SweepResult:
    theatres: int = 0
    source_films_new: int = 0
    showings_upserted: int = 0
    failures: list[str] = field(default_factory=list)


def _had_recent_showings(db: Session, theatre_id: int, now: datetime) -> bool:
    cutoff = now - timedelta(hours=48)
    row = db.execute(
        select(Showing.theatre_id)
        .where(Showing.theatre_id == theatre_id, Showing.last_seen >= cutoff)
        .limit(1)
    ).first()
    return row is not None


def sweep_showtimes(db: Session, source: ShowtimeSource, now: datetime, today: date) -> SweepResult:
    res = SweepResult()
    theatres = (
        db.execute(select(Theatre).where(Theatre.source == source.name, Theatre.tracked.is_(True)))
        .scalars()
        .all()
    )

    for t in theatres:
        try:
            infos = source.showings(t.source_theatre_id)
        except Exception as e:  # one theatre failing must not stop the sweep
            res.failures.append(f"{t.name}: {e}")
            continue
        res.theatres += 1
        infos = [i for i in infos if i.show_date >= today]
        if not infos:
            if _had_recent_showings(db, t.id, now):
                res.failures.append(
                    f"{t.name}: returned 0 films but had showings within the last 48h"
                )
            continue

        for info in infos:
            sf = db.execute(
                select(SourceFilm).where(
                    SourceFilm.source == source.name,
                    SourceFilm.source_film_id == info.source_film_id,
                )
            ).scalar_one_or_none()
            if sf is None:
                sf = SourceFilm(
                    source=source.name,
                    source_film_id=info.source_film_id,
                    raw_title=info.raw_title,
                    raw_year=info.raw_year,
                    film_url=info.film_url,
                    resolution="unresolved",
                )
                db.add(sf)
                db.flush()
                res.source_films_new += 1
            else:
                sf.raw_title = info.raw_title
                if info.film_url:
                    sf.film_url = info.film_url

            show = db.get(Showing, (sf.id, t.id, info.show_date))
            if show is None:
                db.add(
                    Showing(
                        source_film_id=sf.id,
                        theatre_id=t.id,
                        show_date=info.show_date,
                        show_times=list(info.show_times),
                        first_seen=now,
                        last_seen=now,
                    )
                )
            else:
                show.show_times = list(info.show_times)
                show.last_seen = now
            res.showings_upserted += 1

        # drop showings the source no longer lists for this theatre
        db.execute(
            delete(Showing).where(
                Showing.theatre_id == t.id,
                Showing.show_date >= today,
                Showing.last_seen < now,
            )
        )
        db.commit()
    return res
