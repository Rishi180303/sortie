# fetch fandango napi endpoints once, archive the responses under raw/, and print their shapes.
# usage: uv run python scripts/fandango_discover.py <zip> [<theatre-id>]
# reads nothing from config; prints top-level keys and one sample element per list.
import json
import sys
from pathlib import Path

from sortie.sources.fandango import BASE, make_fandango_http, parse_calendar

_JSON_HEADERS = {"Accept": "application/json"}


def shape(x, depth=0, max_depth=4):
    pad = "  " * depth
    if isinstance(x, dict):
        for k, v in list(x.items())[:25]:
            print(f"{pad}{k}: {type(v).__name__}")
            if depth < max_depth and isinstance(v, dict | list):
                shape(v, depth + 1, max_depth)
    elif isinstance(x, list) and x:
        print(f"{pad}[{len(x)} items] first:")
        shape(x[0], depth + 1, max_depth)


def main():
    zip_code = sys.argv[1]
    theatre = sys.argv[2] if len(sys.argv) > 2 else None
    http = make_fandango_http(Path("raw"))

    print("== nearby ==")
    r = http.get(
        f"{BASE}/napi/nearbyTheaters",
        target="nearby",
        headers=_JSON_HEADERS,
        params={"zipCode": zip_code, "limit": "100"},
    )
    nearby = json.loads(r.text)
    shape(nearby)

    if theatre is None:
        print("\npass a theatre id as the second argument to fetch its calendar + showtimes.")
        return

    print("\n== calendar ==")
    r = http.get(
        f"{BASE}/napi/theaterCalendar/{theatre}",
        target=f"calendar-{theatre}",
        headers=_JSON_HEADERS,
    )
    cal = json.loads(r.text)
    shape(cal)

    print("\n== showtimes (first calendar date) ==")
    dates = parse_calendar(cal)
    d = dates[0].isoformat() if dates else None
    r = http.get(
        f"{BASE}/napi/theaterMovieShowtimes/{theatre}",
        target=f"showtimes-{theatre}-{d}",
        headers=_JSON_HEADERS,
        params={"date": d} if d else None,
    )
    shape(json.loads(r.text))


if __name__ == "__main__":
    main()
