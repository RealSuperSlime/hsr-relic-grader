"""Tests: run with  python -m pytest -q   (or: python tests/test_scoring.py)"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from relic_grades.characters import find_character, score_for_character  # noqa: E402
from relic_grades.fribbels import (  # noqa: E402
    compute_optimal_score, ScorerMeta, pct_to_rating, snap_value,
)

ACHERON_RELIC = {
    'part': 'Body', 'mainStat': 'CRIT Rate', 'mainValue': 32.4, 'grade': 5,
    'substats': [
        {'stat': 'ATK%', 'value': 8.6},
        {'stat': 'CRIT DMG', 'value': 12.9},
        {'stat': 'Effect Hit Rate', 'value': 3.4},
        {'stat': 'Break Effect', 'value': 18.1},
    ],
}


def test_snap_to_real_rolls():
    # the game prints 1 decimal; Fribbels scores the true roll total
    assert abs(snap_value('ATK%', 8.6) - 8.64) < 1e-9
    assert abs(snap_value('CRIT DMG', 12.9) - 12.96) < 1e-9
    assert abs(snap_value('Effect Hit Rate', 3.4) - 3.456) < 1e-9
    assert abs(snap_value('Break Effect', 18.1) - 18.144) < 1e-9
    assert abs(snap_value('ATK', 21) - 21.168754) < 1e-6      # flat stats print as ints


def test_acheron_reference_relic_is_54_s():
    r = score_for_character(find_character('Acheron'), ACHERON_RELIC)
    assert r['percent'] == 54.0
    assert r['rating'] == 'S'
    assert abs(r['ideal'] - 47.952) < 1e-9


def test_unrefined_matches_displayed_values():
    r = score_for_character(find_character('Acheron'), ACHERON_RELIC, refine=False)
    assert r['percent'] == 53.8


def test_ideal_matches_fribbels_formula():
    ac = find_character('Acheron')
    meta = ScorerMeta(ac['weights'], ac['parts'], ac['flatMainstatBoost'])
    # ideal = 6.48 * (6*highest remaining weight + next three)  with CR (main) excluded
    assert abs(compute_optimal_score('Body', 'CRIT Rate', meta) - 6.48 * 7.4) < 1e-9


def test_wrong_main_stat_grades_unknown():
    firefly = find_character('Firefly')
    relic = dict(ACHERON_RELIC, substats=[{'stat': 'Break Effect', 'value': 21.7},
                                          {'stat': 'SPD', 'value': 2.0}])
    r = score_for_character(firefly, relic)
    assert r['correctMain'] is False
    assert r['rating'] == '?'


def test_grade_tiers():
    assert pct_to_rating(0.0) == '?'
    assert pct_to_rating(50.0) == 'S'
    assert pct_to_rating(54.9) == 'S'
    assert pct_to_rating(55.0) == 'S+'
    assert pct_to_rating(90.0) == 'WTF+'          # AEON needs aeon-eligible weights
    assert pct_to_rating(72.0) == 'SSS'


def test_character_lookup_is_fuzzy():
    assert find_character('acheron')['id'] == '1308'
    assert find_character('dan heng imbibitor')['name'].startswith('Dan Heng')
    assert find_character('firefly')['name'] == 'Firefly'


if __name__ == '__main__':
    for name, fn in sorted(globals().items()):
        if name.startswith('test_') and callable(fn):
            fn()
            print('ok', name)
