import pytest

from sortie.matching.scoring import Candidate, Observed, pick, score

ALIASES = frozenset({"the transformers the movie", "transformers the movie"})


def cand(**kw):
    base = dict(
        tmdb_id=1,
        title="The Transformers: The Movie",
        year=1986,
        director="Nelson Shin",
        runtime_minutes=84,
        cast_top=("Orson Welles", "Robert Stack", "Judd Nelson"),
        aliases=ALIASES,
    )
    base.update(kw)
    return Candidate(**base)


def obs(**kw):
    base = dict(
        title_normalized="the transformers the movie",
        year=2026,
        director="Nelson Shin",
        runtime_minutes=84,
        cast_top=("Orson Welles", "Judd Nelson"),
    )
    base.update(kw)
    return Observed(**base)


def test_full_agreement_except_year_scores_0_95():
    # engagement year 2026 vs film year 1986: year contributes nothing, never penalises
    assert score(obs(), cand()) == pytest.approx(0.95)


def test_title_and_director_only_is_0_70():
    assert score(obs(runtime_minutes=None, cast_top=()), cand()) == pytest.approx(0.70)


def test_title_only_is_0_30():
    assert score(
        obs(director="Someone Else", runtime_minutes=None, cast_top=(), year=None), cand()
    ) == pytest.approx(0.30)


def test_year_agreement_adds_0_05():
    assert score(obs(year=1986), cand()) == pytest.approx(1.0)


def test_director_comparison_is_normalized():
    assert score(obs(director="  NELSON SHIN "), cand()) == pytest.approx(0.95)


@pytest.mark.parametrize("rt,expected", [(81, 0.95), (87, 0.95), (88, 0.80), (80, 0.80)])
def test_runtime_tolerance_is_three_minutes(rt, expected):
    assert score(obs(runtime_minutes=rt), cand()) == pytest.approx(expected)


def test_cast_needs_two_overlaps():
    assert score(obs(cast_top=("Orson Welles",)), cand()) == pytest.approx(0.85)


def test_pick_accepts_clear_leader():
    a, b = cand(tmdb_id=1), cand(tmdb_id=2, director="Other", aliases=frozenset())
    assert pick([(a, 0.95), (b, 0.15)], min_score=0.6, min_margin=0.2) is a


def test_pick_rejects_below_min_score():
    assert pick([(cand(), 0.30)], min_score=0.6, min_margin=0.2) is None


def test_pick_rejects_ambiguous_leaders():
    a, b = cand(tmdb_id=1), cand(tmdb_id=2)
    assert pick([(a, 0.70), (b, 0.65)], min_score=0.6, min_margin=0.2) is None


def test_pick_single_candidate_margin_is_its_score():
    assert pick([(cand(), 0.70)], min_score=0.6, min_margin=0.2) is not None


def test_pick_empty():
    assert pick([], 0.6, 0.2) is None
