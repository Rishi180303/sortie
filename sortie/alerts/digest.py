import html as _html
from collections import defaultdict
from collections.abc import Sequence
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
    db: Session, tmdb_id: int, kinds: Sequence[str], today: date
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


# the html digest follows the visual direction approved 2026-09-16: rifle green
# ground, one orange accent, a heavy system font since mail clients strip web fonts
FONT = "'Helvetica Neue',Arial,sans-serif"
GREEN = "#3b4134"
ORANGE = "#e2562c"
SNOW = "#f2f0eb"
SAGE = "#9aa08c"
LINE = "#575e4b"


def _paint(colour: str, extra: str = "") -> str:
    # every element carries its own background and text colour, inline, so a
    # mail client's dark mode can't override one and leave the other unreadable
    style = f"background:{GREEN};color:{colour}"
    return f"{style};{extra}" if extra else style


def _html_date(d: date) -> str:
    return d.strftime("%a %d %b").replace(" 0", " ")


def _theatre(ln: TheatreLine) -> str:
    # a diamond marks one of his own cinemas
    if ln.is_favourite:
        diamond_style = _paint(ORANGE)
        return f'<span style="{diamond_style}">&#9670;</span> {_html.escape(ln.name)}'
    return _html.escape(ln.name)


def _with_miles(ln: TheatreLine) -> str:
    miles = _mi(ln.distance_miles)
    return f"{_theatre(ln)} &middot; {miles}" if miles else _theatre(ln)


def _sprocket(height: int) -> str:
    # film perforations, the cinema motif. css masks do not survive mail clients,
    # so stripe alternating table cells instead, which every client can render
    cells = "".join(
        f'<td width="5%" style="background:{ORANGE if i % 2 == 0 else GREEN};'
        f'height:{height}px;font-size:1px;line-height:1px">&nbsp;</td>'
        for i in range(20)
    )
    return (
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'style="margin:20px 0"><tr>{cells}</tr></table>'
    )


def _html_entry(e: FilmEntry) -> list[str]:
    year = ""
    if e.year:
        year = f' <span style="{_paint(SAGE, "font-size:13px;font-weight:400")}">{e.year}</span>'
    title_style = _paint(SNOW, "font-weight:700;font-size:21px;line-height:1.15;margin:16px 0 0")
    line_style = _paint(SNOW, "font-size:14px;margin:5px 0 0")
    dim_style = _paint(SAGE, "font-size:14px;margin:5px 0 0")

    out = [
        f'<div style="{title_style}">{_html.escape(e.title)}{year}</div>',
        f'<div style="{line_style}"><b>{_html_date(e.earliest.date)}</b> &middot; '
        f"{_with_miles(e.earliest)}</div>",
    ]

    if e.at_fav is None:
        nearest = _mi(e.earliest.distance_miles) or "unknown"
        out.append(
            f'<div style="{dim_style}">Not at your theatres &middot; nearest {nearest}</div>'
        )
    elif e.at_fav != e.earliest:
        gap = (e.at_fav.date - e.earliest.date).days
        later = f" &middot; {gap} day{'s' if gap != 1 else ''} later" if gap > 0 else ""
        out.append(
            f'<div style="{line_style}"><b>{_html_date(e.at_fav.date)}</b> &middot; '
            f"{_theatre(e.at_fav)}{later}</div>"
        )

    if e.others:
        # name the three nearest and count the rest, a chain-wide event lists nine
        bits = []
        for o in e.others[:3]:
            bit = f"{_short_date(o.date)} {_theatre(o)}"
            if o.distance_miles is not None:
                bit += f" ({_mi(o.distance_miles)})"
            bits.append(bit)
        rest = len(e.others) - 3
        if rest > 0:
            bits.append(f"and {rest} more")
        out.append(f'<div style="{dim_style}">Also {", ".join(bits)}</div>')
    return out


def render_html(d: Digest) -> str:
    n = _count(d)
    subtitle = f"{_html_date(d.today)} &middot; {n} film{'s' if n != 1 else ''}"

    wordmark_style = _paint(ORANGE, "font-weight:800;font-size:26px;letter-spacing:-.02em")
    subtitle_style = _paint(
        SAGE, "font-size:11px;letter-spacing:.16em;text-transform:uppercase;margin:4px 0 0"
    )
    page_style = _paint(SNOW, f"font-family:{FONT};font-size:15px;line-height:1.5")
    label_style = _paint(
        ORANGE,
        "font-weight:800;font-size:11px;letter-spacing:.2em;"
        "text-transform:uppercase;margin:26px 0 10px",
    )

    out = [
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'bgcolor="{GREEN}" style="background:{GREEN}"><tr>'
        f'<td align="center" style="background:{GREEN};padding:28px 16px">',
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'style="max-width:560px;background:{GREEN}"><tr><td style="{page_style}">',
        f'<div style="{wordmark_style}">sortie</div>',
        f'<div style="{subtitle_style}">{subtitle}</div>',
    ]

    if d.failures:
        k = len(d.failures)
        notice_style = _paint(SNOW, "font-weight:700;font-size:14px;margin:14px 0 0")
        out.append(f'<div style="{notice_style}">{k} error{"s" if k != 1 else ""} today</div>')

    out.append(_sprocket(16))

    for title, entries in (
        ("From your watchlist", d.watchlist),
        ("Re-releases", d.rereleases),
        ("Showing soon", d.soon),
    ):
        if entries:
            out.append(f'<div style="{label_style}">{title}</div>')
            for e in entries:
                out += _html_entry(e)

    parts: list[str] = []
    if d.needs_input:
        m = d.needs_input
        parts.append(f"{m} film{'s' if m != 1 else ''} waiting on you")
    if d.failures:
        parts.append("<br>".join(_html.escape(f) for f in d.failures))
    if d.health:
        parts.append("<br>".join(_html.escape(h) for h in d.health))
    if parts:
        foot_style = _paint(
            SAGE, f"font-size:12px;margin:26px 0 0;padding:12px 0 0;border-top:1px solid {LINE}"
        )
        out.append(f'<div style="{foot_style}">{"<br>".join(parts)}</div>')

    out.append("</td></tr></table></td></tr></table>")
    return "".join(out)
