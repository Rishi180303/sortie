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


def _entry(
    db: Session, tmdb_id: int, kinds: list[str], today: date
) -> tuple[FilmEntry | None, bool]:
    film = db.get(Film, tmdb_id)
    state = db.get(FilmState, tmdb_id)
    if film is None or state is None or state.earliest_theatre_id is None:
        return None, False
    lines = _lines_for(db, tmdb_id, today)
    earliest = lines.get(state.earliest_theatre_id)
    if earliest is None:
        return None, False
    at_fav = lines.get(state.earliest_fav_theatre_id) if state.earliest_fav_theatre_id else None
    used = {state.earliest_theatre_id, state.earliest_fav_theatre_id}

    # build others: all theatre lines except earliest and at_fav, sorted by fav-first
    others: list[TheatreLine] = []
    for tid, ln in lines.items():
        if tid not in used:
            others.append(ln)

    def sort_key(ln: TheatreLine) -> tuple:
        dist = ln.distance_miles if ln.distance_miles is not None else 1e9
        return (not ln.is_favourite, ln.date, dist)

    others.sort(key=sort_key)

    year = film.us_theatrical_date.year if film.us_theatrical_date else None
    return (
        FilmEntry(tmdb_id, film.title, year, tuple(sorted(kinds)), earliest, at_fav, tuple(others)),
        state.is_watchlist,
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
        entry, is_watchlist = _entry(db, tmdb_id, kinds, today)
        if entry is None:
            continue
        if kinds == ["approaching"]:
            sections["soon"].append(entry)
        elif is_watchlist:
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

    out.append(
        f"  Earliest anywhere   {_fmt_date(e.earliest.date)}  ·  "
        f"{e.earliest.name:<24}  {_mi(e.earliest.distance_miles)}"
    )

    if e.at_fav is not None:
        out.append(f"  Your theatres       {_fmt_date(e.at_fav.date)}  ·  {e.at_fav.name}")
        gap = (e.at_fav.date - e.earliest.date).days
        if gap > 0:
            out.append(f"  ↳ {gap} day{'s' if gap != 1 else ''} earlier if you drive")
    else:
        out.append("  Your theatres       — not playing at your favourites —")
        out.append(f"  ↳ nearest is {_mi(e.earliest.distance_miles) or 'unknown'}")

    if e.others:
        # build "Also" line: one part per theatre showing date, format each, join
        also_parts: list[str] = []
        for o in e.others:
            part = f"{_short_date(o.date)} {o.name}"
            if o.distance_miles is not None:
                part = part + f" ({_mi(o.distance_miles)})"
            also_parts.append(part)
        out.append(f"  Also  {'  ·  '.join(also_parts)}")
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
        film_s = "s" if n != 1 else ""
        need_s = "s" if n == 1 else ""
        lines += [f"{n} film{film_s} need{need_s} your input in the match queue.", ""]
    if d.health:
        lines += ["—", *(f"  {h}" for h in d.health)]
    return "\n".join(lines).rstrip() + "\n"


# the html digest is set like a repertory programme: one serif, red for his own
# theatres and for anything that went wrong, no boxes
SERIF = "Georgia,'Times New Roman',serif"
RED = "#a3111f"
GREY = "#666666"
PAGE = (
    f"max-width:540px;margin:0 auto;font-family:{SERIF};color:#000;font-size:15px;line-height:1.55"
)
TITLE = "font-size:21px;font-weight:bold;letter-spacing:0.02em;line-height:1.2"
KINDS = f"font-style:italic;color:{GREY};font-size:14px;margin:3px 0 8px"
SECTION = "margin:40px 0 14px;font-style:italic;font-size:17px"
FOOT = f"margin-top:44px;padding-top:14px;border-top:1px solid #ddd;font-size:13px;color:{GREY}"


def _html_date(d: date) -> str:
    return d.strftime("%a %d %b").replace(" 0", " ")


def _long_date(d: date) -> str:
    return d.strftime("%A %d %B").replace(" 0", " ")


def _theatre(ln: TheatreLine) -> str:
    # a star marks one of his own theatres
    if ln.is_favourite:
        return f'<span style="color:{RED}">&#9733;</span> {_html.escape(ln.name)}'
    return _html.escape(ln.name)


def _with_miles(ln: TheatreLine) -> str:
    miles = _mi(ln.distance_miles)
    return f"{_theatre(ln)}, {miles}" if miles else _theatre(ln)


def _html_entry(e: FilmEntry) -> list[str]:
    year = ""
    if e.year:
        year = f' <span style="font-weight:normal;letter-spacing:0;color:{GREY}">{e.year}</span>'
    kinds = ", ".join(KIND_LABEL[k] for k in e.kinds)
    out = [
        f'<div style="{TITLE}">{_html.escape(e.title.upper())}{year}</div>',
        f'<div style="{KINDS}">{_html.escape(kinds[:1].upper() + kinds[1:])}</div>',
        f"<div><b>{_html_date(e.earliest.date)}</b> at {_with_miles(e.earliest)}.</div>",
    ]

    if e.at_fav is None:
        nearest = _mi(e.earliest.distance_miles) or "unknown"
        out.append(f"<div>Not at your theatres. The nearest is {nearest}.</div>")
    elif e.at_fav != e.earliest:
        gap = (e.at_fav.date - e.earliest.date).days
        later = f", {gap} day{'s' if gap != 1 else ''} later" if gap > 0 else ""
        out.append(f"<div><b>{_html_date(e.at_fav.date)}</b> at {_theatre(e.at_fav)}{later}.</div>")

    if e.others:
        # name the three nearest and count the rest, a chain-wide event lists nine
        bits = []
        for o in e.others[:3]:
            bit = f"{_short_date(o.date)} at {_theatre(o)}"
            if o.distance_miles is not None:
                bit += f" ({_mi(o.distance_miles)})"
            bits.append(bit)
        rest = len(e.others) - 3
        if rest > 0:
            bits.append(f"and {rest} more")
        out.append(f'<div style="color:#444">Also {", ".join(bits)}.</div>')
    return out


def render_html(d: Digest) -> str:
    out = [
        f'<div style="{PAGE}">',
        '<table width="100%" cellpadding="0" cellspacing="0"'
        f' style="border-collapse:collapse;border-bottom:2px solid {RED}">',
        '<tr><td style="font-size:30px;font-style:italic;padding:0 0 6px;'
        'line-height:1">Sortie</td>',
        f'<td align="right" style="font-size:14px;color:{GREY};padding:0 0 8px;'
        f'vertical-align:bottom">{_long_date(d.today)}</td></tr></table>',
    ]
    if d.failures:
        n = len(d.failures)
        out.append(
            f'<p style="margin:14px 0 0;color:{RED};font-size:14px">'
            f"{n} error{'s' if n != 1 else ''} today. Details at the end.</p>"
        )

    for title, entries in (
        ("From your watchlist", d.watchlist),
        ("Re-releases near you", d.rereleases),
        ("Showing soon", d.soon),
    ):
        if entries:
            out.append(f'<p style="{SECTION}">{title}</p>')
            for e in entries:
                out.append('<div style="margin:0 0 26px">')
                out += _html_entry(e)
                out.append("</div>")

    out.append(f'<div style="{FOOT}">')
    if d.needs_input:
        n = d.needs_input
        out.append(
            f'<p style="margin:0 0 12px;color:#000;font-size:14px">'
            f"{n} film{'s' if n != 1 else ''} waiting in the match queue.</p>"
        )
    if d.failures:
        body = "<br>".join(_html.escape(f) for f in d.failures)
        out.append(f'<p style="margin:0 0 12px;color:{RED}">{body}</p>')
    if d.health:
        body = "<br>".join(_html.escape(h) for h in d.health)
        out.append(f'<p style="margin:0">{body}</p>')
    out.append("</div></div>")
    return "".join(out)
