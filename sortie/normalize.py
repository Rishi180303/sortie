import re
import unicodedata

_YEAR_PAREN = re.compile(r"\s*\(((?:19|20)\d{2})\)\s*$")

# 40th anniversary, 45th anniv., 50th anniversary edition
_ANNIVERSARY = re.compile(
    r"\s*\b\d{1,3}(?:st|nd|rd|th)\s+anniv(?:ersary)?\.?(?:\s+(?:edition|screening|event))?\b",
    re.IGNORECASE,
)

# trailing festival names like "– studio ghibli fest 2026"
_FESTIVAL_SUFFIX = re.compile(r"\s*[-–—]\s*[^-–—]*\bfest(?:ival)?\b[^-–—]*$", re.IGNORECASE)

# these are clearly formats even without a separator, like "coraline 3d"
# ambiguous words like premiere only strip after a separator or in parens
_BARE_FORMAT_WORDS = (
    r"imax|the imax experience|3d|2d|4dx|dolby(?: cinema| atmos)?|real ?d ?3d|"
    r"dubbed|subtitled|remastered|4k(?: restoration| remaster)?|re-?release"
)
_FORMAT_WORDS = (
    r"imax|the imax experience|3d|2d|4dx|dolby(?: cinema| atmos)?|real ?d ?3d|"
    r"dubbed|subtitled|sub|dub|extended(?: edition| cut)?|director'?s (?:cut|edition)|"
    r"the final cut|final cut|remastered|restoration|4k(?: restoration| remaster)?|"
    r"re-?release|encore|special engagement|fan event|early access|premiere"
)
# " - imax", ": the imax experience", " (dubbed)", " 3d"
_FORMAT_SUFFIX = re.compile(
    rf"(?:\s*[-–—:]\s*(?:the\s+)?(?:{_FORMAT_WORDS})|\s*\((?:{_FORMAT_WORDS})\)|\s+(?:{_BARE_FORMAT_WORDS}))\s*$",
    re.IGNORECASE,
)

_DISTRIBUTOR_PREFIX = re.compile(
    r"^(?:the metropolitan opera|met opera|rifftrax|fathom events?|national theatre live|"
    r"nt live|(?:studio )?ghibli fest(?: \d{4})?|amc classics?|bring backs?)\s*:\s*",
    re.IGNORECASE,
)


def strip_year(raw: str) -> tuple[str, int | None]:
    m = _YEAR_PAREN.search(raw)
    if not m:
        return raw.strip(), None
    return raw[: m.start()].strip(), int(m.group(1))


def _fold(s: str) -> str:
    s = s.replace("\xa0", " ")
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.replace("&", " and ")
    s = re.sub(r"[^\w\s]", " ", s)
    s = re.sub(r"_", " ", s)
    return re.sub(r"\s+", " ", s).strip().lower()


def normalize_title(raw: str) -> str:
    s, _ = strip_year(raw)
    s = _DISTRIBUTOR_PREFIX.sub("", s)
    s = _ANNIVERSARY.sub("", s)
    s = _FESTIVAL_SUFFIX.sub("", s)
    # formats can stack like "imax 3d", so keep stripping until nothing changes
    prev = None
    while prev != s:
        prev = s
        s = _FORMAT_SUFFIX.sub("", s)
    s = s.rstrip(" :-–—")
    return _fold(s)


def normalize_name(raw: str) -> str:
    return _fold(raw)


# the words a listing uses when it brings an old film back (spec §9)
_RERELEASE_MARKER = re.compile(
    r"\b(?:anniversary|restoration|remastered|re-?release)\b", re.IGNORECASE
)


def has_rerelease_marker(raw: str) -> bool:
    return _RERELEASE_MARKER.search(raw) is not None
