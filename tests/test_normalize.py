import pytest

from sortie.normalize import normalize_name, normalize_title, strip_year


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Practical Magic 2 (2026)", ("Practical Magic 2", 2026)),
        ("Alien", ("Alien", None)),
        ("Romeo + Juliet (1996)", ("Romeo + Juliet", 1996)),
        ("Gone With The Wind (2026) ", ("Gone With The Wind", 2026)),
    ],
)
def test_strip_year(raw, expected):
    assert strip_year(raw) == expected


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("The Transformers: The Movie 40th Anniversary (2026)", "the transformers the movie"),
        ("ALIEN 45TH ANNIV.", "alien"),
        ("Cars: 20th Anniversary", "cars"),
        ("Princess Mononoke – Studio Ghibli Fest 2026", "princess mononoke"),
        ("Look Back (Dubbed)", "look back"),
        ("Look Back (Subtitled)", "look back"),
        ("Spider-Man: Across the Spider-Verse", "spider man across the spider verse"),
        ("The Metropolitan Opera: Macbeth (2026)", "macbeth"),
        ("Interstellar - IMAX", "interstellar"),
        ("Interstellar: The IMAX Experience", "interstellar"),
        ("Blade Runner: The Final Cut", "blade runner"),
        ("Aliens (Extended Edition)", "aliens"),
        ("Coraline 3D", "coraline"),
        ("Mononoke\xa0Hime", "mononoke hime"),
        ("Amélie", "amelie"),
        ("Fast & Furious", "fast and furious"),
        ("RiffTrax: Plan 9 from Outer Space", "plan 9 from outer space"),
        ("World Premiere", "world premiere"),
        ("The Restoration", "the restoration"),
    ],
)
def test_normalize_title(raw, expected):
    assert normalize_title(raw) == expected


def test_normalize_name():
    assert normalize_name("Hayao Miyazaki") == "hayao miyazaki"
    assert normalize_name("  Guillermo del Toro ") == "guillermo del toro"
    assert normalize_name("Ang Lee") == normalize_name("ANG LEE")
