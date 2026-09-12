import html as _html
from collections import defaultdict
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from sortie.alerts.diff import Alert
from sortie.models import Film, FilmState, Showing, SourceFilm, Theatre

KIND_LABEL = {
    "new_anywhere": "new near you",
    "new_at_favourite": "now at a favourite",
    "earliest_moved_earlier": "earlier date added",
    "approaching": "showing soon",
}


@dataclass(frozen=True)
class TheatreLine:
    name: str
    distance_miles: float | None
    date: date
    is_favourite: bool


@dataclass(frozen=True)
class FilmEntry:
    tmdb_id: int
    title: str
    year: int | None
    kinds: tuple[str, ...]
    earliest: TheatreLine
    at_fav: TheatreLine | None
    others: tuple[TheatreLine, ...]


@dataclass(frozen=True)
class Digest:
    today: date
    watchlist: tuple[FilmEntry, ...]
    rereleases: tuple[FilmEntry, ...]
    soon: tuple[FilmEntry, ...]
    needs_input: int
    health: tuple[str, ...]
    failures: tuple[str, ...]


def _lines_for(db: Session, tmdb_id: int, today: date) -> dict[int, TheatreLine]:
    # find earliest showing at each tracked theatre for this film
    q = (
        select(Theatre, Showing.show_date)
        .join(Showing, Showing.theatre_id == Theatre.id)
        .join(SourceFilm, SourceFilm.id == Showing.source_film_id)
        .where(
            SourceFilm.tmdb_id == tmdb_id,
            Showing.show_date >= today,
            Theatre.tracked.is_(True),
        )
    )
    earliest: dict[int, tuple[Theatre, date]] = {}
    for theatre, d in db.execute(q):
        cur = earliest.get(theatre.id)
        if cur is None or d < cur[1]:
            earliest[theatre.id] = (theatre, d)

    lines: dict[int, TheatreLine] = {}
    for tid, (t, d) in earliest.items():
        lines[tid] = TheatreLine(t.name, t.distance_miles, d, t.is_favourite)
    return lines


def _entry(db: Session, tmdb_id: int, kinds: list[str], today: date) -> FilmEntry | None:
    film, state = db.get(Film, tmdb_id), db.get(FilmState, tmdb_id)
    if film is None or state is None or state.earliest_theatre_id is None:
        return None
    lines = _lines_for(db, tmdb_id, today)
    earliest = lines.get(state.earliest_theatre_id)
    if earliest is None:
        return None
    at_fav = lines.get(state.earliest_fav_theatre_id) if state.earliest_fav_theatre_id else None
    used = {state.earliest_theatre_id, state.earliest_fav_theatre_id}

    # build others: all theatre lines except earliest and at_fav, sorted by fav-first
    others: list[TheatreLine] = []
    for tid, ln in lines.items():
        if tid not in used:
            others.append(ln)

    def sort_key(ln: TheatreLine) -> tuple:
        return (ln.is_favourite is False, ln.date, ln.distance_miles or 1e9)

    others.sort(key=sort_key)

    year = film.us_theatrical_date.year if film.us_theatrical_date else None
    return FilmEntry(
        tmdb_id, film.title, year, tuple(sorted(kinds)), earliest, at_fav, tuple(others)
    )


def _sort_entry(e: FilmEntry) -> tuple:
    # order by: has fav, then earliest date, then title
    return (e.at_fav is None, e.earliest.date, e.title)


def build_digest(
    db: Session,
    alerts: dict[int, list[Alert]],
    today: date,
    needs_input: int,
    health: list[str],
    failures: list[str],
) -> Digest:
    sections: dict[str, list[FilmEntry]] = defaultdict(list)
    for tmdb_id, film_alerts in alerts.items():
        kinds = [a.kind for a in film_alerts]
        entry = _entry(db, tmdb_id, kinds, today)
        if entry is None:
            continue
        state = db.get(FilmState, tmdb_id)
        if kinds == ["approaching"]:
            sections["soon"].append(entry)
        elif state is not None and state.is_watchlist:
            sections["watchlist"].append(entry)
        else:
            sections["rereleases"].append(entry)

    return Digest(
        today=today,
        watchlist=tuple(sorted(sections["watchlist"], key=_sort_entry)),
        rereleases=tuple(sorted(sections["rereleases"], key=_sort_entry)),
        soon=tuple(sorted(sections["soon"], key=_sort_entry)),
        needs_input=needs_input,
        health=tuple(health),
        failures=tuple(failures),
    )


def _count(d: Digest) -> int:
    return len(d.watchlist) + len(d.rereleases) + len(d.soon)


def is_empty(d: Digest) -> bool:
    return _count(d) == 0 and not d.failures


def subject(d: Digest) -> str:
    n = _count(d)
    if n:
        return f"sortie: {n} new film{'s' if n != 1 else ''} near you"
    if d.failures:
        k = len(d.failures)
        return f"sortie: {k} fetch failure{'s' if k != 1 else ''}"
    return "sortie: weekly check-in"


def _fmt_date(d: date) -> str:
    return d.strftime("%a %b %d").replace(" 0", " ")


def _short_date(d: date) -> str:
    return d.strftime("%b %d").replace(" 0", " ")


def _mi(m: float | None) -> str:
    return f"{m:.0f} mi" if m is not None else ""


def _render_entry(e: FilmEntry) -> list[str]:
    head = e.title.upper() + (f" ({e.year})" if e.year else "")
    kinds_str = ", ".join(KIND_LABEL[k] for k in e.kinds)
    out = [f"{head}  — {kinds_str}"]

    earliest_line = (
        f"  Earliest anywhere   {_fmt_date(e.earliest.date)}  ·  "
        f"{e.earliest.name:<24}{_mi(e.earliest.distance_miles)}"
    )
    out.append(earliest_line)

    if e.at_fav is not None:
        fav_line = f"  Your theatres       {_fmt_date(e.at_fav.date)}  ·  {e.at_fav.name}"
        out.append(fav_line)
        gap = (e.at_fav.date - e.earliest.date).days
        if gap > 0:
            gap_text = f"  ↳ {gap} day{'s' if gap != 1 else ''} earlier if you drive"
            out.append(gap_text)
    else:
        out.append("  Your theatres       — not playing at your favourites —")
        nearest_text = f"  ↳ nearest is {_mi(e.earliest.distance_miles) or 'unknown'}"
        out.append(nearest_text)

    if e.others:
        # build "Also" line: one part per theatre showing date, format each, join
        also_parts: list[str] = []
        for o in e.others:
            part = f"{_short_date(o.date)} {o.name}"
            if o.distance_miles:
                part = part + f" ({_mi(o.distance_miles)})"
            also_parts.append(part)
        also = "  ·  ".join(also_parts)
        out.append(f"  Also  {also}")
    return out


def render_text(d: Digest) -> str:
    lines: list[str] = [f"sortie · {_fmt_date(d.today)}", ""]
    if d.failures:
        lines += ["FAILURES", *(f"  ! {f}" for f in d.failures), ""]
    for title, entries in (
        ("FROM YOUR WATCHLIST", d.watchlist),
        ("RE-RELEASES NEAR YOU", d.rereleases),
        ("SHOWING SOON", d.soon),
    ):
        if entries:
            lines.append(title)
            for e in entries:
                lines += _render_entry(e) + [""]
    if d.needs_input:
        n = d.needs_input
        plural = "s" if n != 1 else ""
        verb_form = "s" if n == 1 else ""
        input_line = f"{n} film{plural} need{verb_form} your input in the match queue."
        lines += [input_line, ""]
    if d.health:
        lines += ["—", *(f"  {h}" for h in d.health)]
    return "\n".join(lines).rstrip() + "\n"


def render_html(d: Digest) -> str:
    body = _html.escape(render_text(d))
    div_style = "font-family:-apple-system,Segoe UI,sans-serif;max-width:720px"
    pre_style = "font-family:ui-monospace,Menlo,monospace;font-size:13px;white-space:pre-wrap"
    return f'<div style="{div_style}"><pre style="{pre_style}">{body}</pre></div>'
