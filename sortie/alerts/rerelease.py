from datetime import date

from sortie.normalize import has_rerelease_marker


def is_rerelease(
    us_date: date | None,
    showing_date: date,
    raw_titles: set[str],
    aliases: set[str],
    fathom_titles: set[str],
    gap_years: int,
) -> bool:
    # the gap only makes a film a candidate, it never decides on its own (spec §9)
    if us_date is None:
        return False
    # ponytail: 365-day years, leap days cannot matter at a two-year gap
    if (showing_date - us_date).days < gap_years * 365:
        return False
    # second signal: the listing itself says so
    for title in raw_titles:
        if has_rerelease_marker(title):
            return True
    # second signal: fathom lists the film under one of its known titles
    return bool(aliases & fathom_titles)
