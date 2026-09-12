import json

from sortie.http import HttpClient
from sortie.normalize import normalize_title

FATHOM_URL = "https://api.fathomentertainment.com/api/events"


def parse_active_titles(payload: dict) -> list[str]:
    out = []
    for event in payload.get("Events", []):
        title = event.get("Title") or ""
        # the feed carries live test records named matt test
        if title.upper().startswith("MATT TEST"):
            continue
        # only active events with dates are screenings we can corroborate
        if event.get("Status") != "Active" or not event.get("Dates"):
            continue
        out.append(title.strip())
    return out


class FathomClient:
    def __init__(self, http: HttpClient):
        self.http = http

    def active_titles(self) -> set[str]:
        r = self.http.get(FATHOM_URL, target="events", headers={"Accept": "application/json"})
        titles = set()
        for title in parse_active_titles(json.loads(r.text)):
            titles.add(normalize_title(title))
        return titles
