from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal

from sortie.models import FilmState

Kind = Literal["new_anywhere", "new_at_favourite", "earliest_moved_earlier", "approaching"]


@dataclass(frozen=True)
class Alert:
    kind: Kind
    tmdb_id: int


def transitions(state: FilmState, today: date, approaching_days: int) -> list[Alert]:
    # non-watchlist non-rerelease films never alert
    if not (state.is_watchlist or state.is_rerelease):
        return []
    if state.earliest_date_anywhere is None:
        return []

    out: list[Alert] = []

    # first sighting anywhere
    if state.alerted_new_at is None:
        out.append(Alert("new_anywhere", state.tmdb_id))

    # first sighting at favourite theatre
    if state.earliest_date_at_fav is not None and state.alerted_fav_at is None:
        out.append(Alert("new_at_favourite", state.tmdb_id))

    # earliest date moved earlier than when we last alerted
    if (
        state.alerted_new_at is not None
        and state.alerted_earliest_date is not None
        and state.earliest_date_anywhere < state.alerted_earliest_date
    ):
        out.append(Alert("earliest_moved_earlier", state.tmdb_id))

    # approaching: use favourite date if available, otherwise anywhere date
    actionable = state.earliest_date_at_fav or state.earliest_date_anywhere
    days_out = (actionable - today).days
    if (
        state.alerted_new_at is not None
        and state.alerted_soon_at is None
        and 0 <= days_out <= approaching_days
    ):
        out.append(Alert("approaching", state.tmdb_id))

    return out


def mark_alerted(state: FilmState, alerts: list[Alert], now: datetime) -> None:
    for a in alerts:
        if a.kind == "new_anywhere":
            state.alerted_new_at = now
            state.alerted_earliest_date = state.earliest_date_anywhere
        elif a.kind == "new_at_favourite":
            state.alerted_fav_at = now
        elif a.kind == "earliest_moved_earlier":
            state.alerted_earlier_at = now
            state.alerted_earliest_date = state.earliest_date_anywhere
        elif a.kind == "approaching":
            state.alerted_soon_at = now
