"""Exact Python port of Fribbels' HSR Optimizer relic scoring.

Source of truth (fribbels/hsr-optimizer, src/lib/relics/scoring/*):
  currentScore.ts   -> score_current_relic()
  optimalScore.ts   -> compute_optimal_score(), resolve_optimal_mainstat()
  scoringMetadata.ts-> prepare_scoring_metadata()
  substatScoring.ts -> mainStatWeight(), getEffectiveSubstatAccessors()
  scoreFormatting.ts-> pct_to_rating()

Formula (per relic, for one character):
    raw    = SUM over substats of  value * weight[stat] * (6.48 / max_high_roll[stat])
    ideal  = optimal substat score for that part/mainstat (see compute_optimal_score)
    pct    = truncate10ths(round5(raw / ideal * 100))
    grade  = pct_to_rating(pct, relic.grade, part, correct_main)
"""
from __future__ import annotations

import json
import math
import os
from difflib import SequenceMatcher

# --------------------------------------------------------------------------- #
# constants (lib/constants/constants.ts)
# --------------------------------------------------------------------------- #
STATS = {
    'ATK_P': 'ATK%', 'ATK': 'ATK', 'BE': 'Break Effect', 'CD': 'CRIT DMG', 'CR': 'CRIT Rate',
    'DEF_P': 'DEF%', 'DEF': 'DEF', 'EHR': 'Effect Hit Rate', 'ERR': 'Energy Regeneration Rate',
    'Fire_DMG': 'Fire DMG Boost', 'HP_P': 'HP%', 'HP': 'HP', 'Ice_DMG': 'Ice DMG Boost',
    'Imaginary_DMG': 'Imaginary DMG Boost', 'Lightning_DMG': 'Lightning DMG Boost',
    'OHB': 'Outgoing Healing Boost', 'Physical_DMG': 'Physical DMG Boost',
    'Quantum_DMG': 'Quantum DMG Boost', 'RES': 'Effect RES', 'SPD_P': 'SPD%', 'SPD': 'SPD',
    'Wind_DMG': 'Wind DMG Boost', 'Elation': 'Elation',
}

# Order matters: prepareScorerStats() iterates Constants.SubStats and JS sort is stable.
SUBSTATS = ['ATK%', 'ATK', 'HP%', 'HP', 'DEF%', 'DEF', 'SPD', 'CRIT Rate', 'CRIT DMG',
            'Effect Hit Rate', 'Effect RES', 'Break Effect']

ALL_STATS = ['ATK%', 'ATK', 'Break Effect', 'CRIT DMG', 'CRIT Rate', 'DEF%', 'DEF',
             'Effect Hit Rate', 'Energy Regeneration Rate', 'Fire DMG Boost', 'HP%', 'HP',
             'Ice DMG Boost', 'Imaginary DMG Boost', 'Lightning DMG Boost',
             'Outgoing Healing Boost', 'Physical DMG Boost', 'Quantum DMG Boost',
             'Effect RES', 'SPD%', 'SPD', 'Wind DMG Boost']

PERCENT_TO_FLAT_STAT = {'ATK%': 'ATK', 'HP%': 'HP', 'DEF%': 'DEF'}
FLAT_STAT_SCALING = {'HP': 0.4, 'ATK': 0.4, 'DEF': 0.4}

# SubStatValues[stat][grade] = {high, mid, low}
_SUB = {
    'SPD': {5: (2.6, 2.3, 2.0), 4: (2.0, 1.8, 1.6), 3: (1.4, 1.3, 1.2), 2: (1.2, 1.1, 1.0)},
    'HP': {5: (42.33751, 38.103755, 33.87), 4: (33.87, 30.483, 27.096),
           3: (25.402506, 22.862253, 20.322), 2: (16.935, 15.2415, 13.548)},
    'ATK': {5: (21.168754, 19.051877, 16.935), 4: (16.935, 15.2415, 13.548),
            3: (12.701252, 11.431126, 10.161), 2: (8.4675, 7.62075, 6.774)},
    'DEF': {5: (21.168754, 19.051877, 16.935), 4: (16.935, 15.2415, 13.548),
            3: (12.701252, 11.431126, 10.161), 2: (8.4675, 7.62075, 6.774)},
    'HP%': {5: (4.32, 3.888, 3.456), 4: (3.456, 3.1104, 2.7648),
            3: (2.592, 2.3328, 2.0736), 2: (1.728, 1.5552, 1.3824)},
    'ATK%': {5: (4.32, 3.888, 3.456), 4: (3.456, 3.1104, 2.7648),
             3: (2.592, 2.3328, 2.0736), 2: (1.728, 1.5552, 1.3824)},
    'DEF%': {5: (5.4, 4.86, 4.32), 4: (4.32, 3.888, 3.456),
             3: (3.24, 2.916, 2.592), 2: (2.16, 1.944, 1.728)},
    'Break Effect': {5: (6.48, 5.832, 5.184), 4: (5.184, 4.6656, 4.1472),
                     3: (3.888, 3.4992, 3.1104), 2: (2.592, 2.3328, 2.0736)},
    'Effect Hit Rate': {5: (4.32, 3.888, 3.456), 4: (3.456, 3.1104, 2.7648),
                        3: (2.592, 2.3328, 2.0736), 2: (1.728, 1.5552, 1.3824)},
    'Effect RES': {5: (4.32, 3.888, 3.456), 4: (3.456, 3.1104, 2.7648),
                   3: (2.592, 2.3328, 2.0736), 2: (1.728, 1.5552, 1.3824)},
    'CRIT Rate': {5: (3.24, 2.916, 2.592), 4: (2.592, 2.3328, 2.0736),
                  3: (1.944, 1.7496, 1.5552), 2: (1.296, 1.1664, 1.0368)},
    'CRIT DMG': {5: (6.48, 5.832, 5.184), 4: (5.184, 4.6656, 4.1472),
                 3: (3.888, 3.4992, 3.1104), 2: (2.592, 2.3328, 2.0736)},
}


def sub_high(stat: str, grade: int = 5) -> float:
    return _SUB[stat][grade][0]


# --------------------------------------------------------------------------- #
# displayed value -> true roll value
# --------------------------------------------------------------------------- #
# The game only shows 1 decimal (flat HP/ATK/DEF: none), but a substat is a sum
# of k rolls, each drawn from {low, mid, high}. Fribbels scores the *true* value,
# so we snap the OCR'd display value back to the achievable sum it came from.
_ROLL_CACHE: dict[tuple[str, int], list[tuple[int, float]]] = {}


def _roll_sums(stat: str, grade: int = 5) -> list[tuple[int, float]]:
    key = (stat, grade)
    if key not in _ROLL_CACHE:
        high, mid, low = _SUB[stat][grade]
        rolls = (low, mid, high)
        out = []
        for k in range(1, 7):
            sums = {0.0}
            for _ in range(k):
                sums = {round(s + r, 6) for s in sums for r in rolls}
            out.extend((k, s) for s in sums)
        _ROLL_CACHE[key] = out
    return _ROLL_CACHE[key]


# The game prints flat HP/ATK/DEF as integers and everything else with 1 decimal.
FLAT_DISPLAY_STATS = frozenset(('HP', 'ATK', 'DEF'))


def displayed(value: float, stat: str, floor1: bool = True) -> float:
    """How the game prints a substat value: '8.64' -> 8.6, flat ATK 21.17 -> 21."""
    if stat in FLAT_DISPLAY_STATS:
        return float(math.floor(value + 1e-9))
    return math.floor(value * 10 + 1e-9) / 10


def match_roll_sum(stat: str, shown: float, grade: int = 5) -> float | None:
    """The achievable substat total that the game would print as `shown`, else None."""
    if stat not in _SUB or shown is None or shown <= 0:
        return None
    bucket = shown + (0.5 if stat in FLAT_DISPLAY_STATS else 0.05)
    best, best_err = None, 1e9
    for _k, total in _roll_sums(stat, grade):
        if abs(displayed(total, stat) - shown) < 1e-6:
            err = abs(total - bucket)
            if err < best_err:
                best, best_err = total, err
    return best


def roll_count(stat: str, value: float, grade: int = 5) -> int | None:
    """How many substat rolls (upgrades) add up to this total, or None."""
    if stat not in _SUB or value is None:
        return None
    for k, total in _roll_sums(stat, grade):
        if abs(total - value) < 1e-6:
            return k
    return None


def snap_value(stat: str, shown: float, grade: int = 5) -> float:
    """Return the achievable substat total that the game prints as `shown`."""
    total = match_roll_sum(stat, shown, grade)
    return shown if total is None else total


def refine_substats(substats: list[dict], grade: int = 5) -> list[dict]:
    return [{'stat': s['stat'], 'value': snap_value(s['stat'], s['value'], grade),
             'shown': s['value']} for s in substats]


PARTS_MAIN_STATS = {
    'Head': ['HP'],
    'Hands': ['ATK'],
    'Body': ['HP%', 'ATK%', 'DEF%', 'CRIT Rate', 'CRIT DMG', 'Outgoing Healing Boost',
             'Effect Hit Rate'],
    'Feet': ['HP%', 'ATK%', 'DEF%', 'SPD'],
    'PlanarSphere': ['HP%', 'ATK%', 'DEF%', 'Physical DMG Boost', 'Fire DMG Boost',
                     'Ice DMG Boost', 'Lightning DMG Boost', 'Wind DMG Boost',
                     'Quantum DMG Boost', 'Imaginary DMG Boost'],
    'LinkRope': ['HP%', 'ATK%', 'DEF%', 'Break Effect', 'Energy Regeneration Rate'],
}

DMG_MAINSTATS = ['Physical DMG Boost', 'Fire DMG Boost', 'Ice DMG Boost', 'Lightning DMG Boost',
                 'Wind DMG Boost', 'Quantum DMG Boost', 'Imaginary DMG Boost']

# scoreFormatting.ts  -- each tier is 5% of ideal substat perfection
RATING_TIERS = [(0, 'F'), (5, 'F+'), (10, 'D'), (15, 'D+'), (20, 'C'), (25, 'C+'), (30, 'B'),
                (35, 'B+'), (40, 'A'), (45, 'A+'), (50, 'S'), (55, 'S+'), (60, 'SS'),
                (65, 'SS+'), (70, 'SSS'), (75, 'SSS+'), (80, 'WTF'), (85, 'WTF+'), (90, 'AEON')]

PART_ALIASES = {
    'head': 'Head', 'helm': 'Head', 'hat': 'Head',
    'hands': 'Hands', 'gloves': 'Hands',
    'body': 'Body', 'chest': 'Body', 'torso': 'Body', 'armor': 'Body',
    'feet': 'Feet', 'boots': 'Feet', 'shoes': 'Feet',
    'planarsphere': 'PlanarSphere', 'sphere': 'PlanarSphere', 'orb': 'PlanarSphere',
    'planar': 'PlanarSphere', 'planar orb': 'PlanarSphere',
    'linkrope': 'LinkRope', 'rope': 'LinkRope', 'link': 'LinkRope', 'rope (link)': 'LinkRope',
}


def has_main_stat(part: str) -> bool:
    return part in ('Body', 'Feet', 'LinkRope', 'PlanarSphere')


def precision_round(x: float, precision: int = 5) -> float:
    if precision == 5:
        return round(x * 1e5) / 1e5
    f = 10 ** precision
    return round(x * f) / f


def truncate10ths(x: float) -> float:
    return math.floor(x * 10) / 10


def pct_to_rating(pct: float, grade: int | None = 5, part: str | None = None,
                  has_correct_main: bool = True, aeon_eligible: bool = False) -> str:
    if grade is not None and grade != 5:
        return '?'
    if pct <= 0:
        return '?'
    if part not in ('Head', 'Hands') and has_correct_main is False:
        return '?'
    for threshold, rating in reversed(RATING_TIERS):
        if pct >= threshold:
            if rating == 'AEON' and not aeon_eligible:
                return 'WTF+'
            return rating
    return '?'


# --------------------------------------------------------------------------- #
# scoring metadata (scoringMetadata.ts)
# --------------------------------------------------------------------------- #
class ScorerMeta:
    __slots__ = ('stats', 'parts', 'sorted_substats', 'flat_mainstat_boost', 'contributions')

    def __init__(self, weights: dict, parts: dict, flat_boost: str | None):
        stats = {}
        for stat in SUBSTATS:
            v = weights.get(stat, 0) or 0
            stats[stat] = min(1.0, max(0.0, float(v)))
        # applyFlatStatScaling
        for pct, flat in PERCENT_TO_FLAT_STAT.items():
            stats[flat] = stats.get(pct, 0) * FLAT_STAT_SCALING[flat]

        self.stats = stats
        self.parts = {}
        for part in PARTS_MAIN_STATS:
            lst = parts.get(part) or []
            self.parts[part] = list(lst) if lst else list(PARTS_MAIN_STATS[part])
        self.flat_mainstat_boost = flat_boost
        self.sorted_substats = sorted(
            ((s, stats[s]) for s in SUBSTATS), key=lambda kv: -kv[1]
        )
        scale = {s: 6.48 / sub_high(s) for s in SUBSTATS}
        self.contributions = {s: stats[s] * scale[s] for s in SUBSTATS}

    # substatScoring.ts
    def main_stat_weight(self, part: str, main_stat: str) -> float:
        if not has_main_stat(part):
            return 0.0
        if main_stat in self.parts[part]:
            return 1.0
        return self.stats.get(main_stat, 0) or 0.0

    def _flat_boost(self, main_stat: str):
        stat = PERCENT_TO_FLAT_STAT.get(main_stat)
        if not stat or self.flat_mainstat_boost != stat:
            return None
        weight = self.stats.get(main_stat, 0) or 0
        if weight <= 0:
            return None
        return stat, weight * 6.48  # substatPotentialUnits(high) == 6.48

    def accessors(self, main_stat: str):
        boost = self._flat_boost(main_stat)
        boosted = boost[0] if boost else None
        pct_weight = self.stats.get(main_stat, 0) if boost else 0.0

        def contribution(stat):
            if boosted == stat:
                return pct_weight * (6.48 / sub_high(stat))
            return self.contributions[stat]

        def high(stat):
            return boost[1] if boosted == stat else self.stats.get(stat, 0) * 6.48

        return contribution, high


def _handling_case(meta: ScorerMeta) -> str:
    s = meta.sorted_substats
    if s[0][1] == 0:
        return 'NONE'
    if s[1][1] == 0:
        return 'SINGLE'
    if s[2][1] > 0:
        return 'NORMAL'
    pair = {s[0][0], s[1][0]}
    if pair == {'HP', 'HP%'}:
        return 'HP'
    if pair == {'ATK', 'ATK%'}:
        return 'ATK'
    if pair == {'DEF', 'DEF%'}:
        return 'DEF'
    return 'NORMAL'


def _resolve_optimal_mainstat(part: str, mainstat: str, meta: ScorerMeta) -> str:
    optimal = meta.parts.get(part) or []
    if mainstat in optimal or meta.stats.get(mainstat) == 1 or not has_main_stat(part):
        return mainstat

    def weight_of(stat):
        v = meta.stats.get(stat, 0) or 0
        if stat in optimal or meta.stats.get(stat) == 1:
            return 1.0
        return v

    score_entries = sorted(((st, weight_of(st)) for st in ALL_STATS), key=lambda kv: -kv[1])
    possible = PARTS_MAIN_STATS[part]

    idx = next((i for i, (name, _w) in enumerate(score_entries) if name in possible), None)
    if idx is None:
        return mainstat
    top_weight = score_entries[idx][1]
    main_stat = score_entries[idx][0]
    is_ideal = False
    is_substat = True
    for i in range(idx, len(score_entries)):
        name, weight = score_entries[i]
        if weight != top_weight:
            break
        if name not in possible:
            continue
        new_ideal = name in optimal
        new_sub = name in SUBSTATS
        if is_ideal and not new_ideal:
            continue
        if not is_substat and new_sub:
            continue
        if is_ideal == new_ideal and is_substat == new_sub:
            continue
        main_stat, is_ideal, is_substat = name, new_ideal, new_sub
    return main_stat


def compute_optimal_score(part: str, mainstat: str, meta: ScorerMeta) -> float:
    case = _handling_case(meta)
    _, high = meta.accessors(mainstat)

    if case == 'NONE':
        return math.inf
    if case in ('HP', 'ATK', 'DEF'):
        st1, st2 = meta.sorted_substats[0][0], meta.sorted_substats[1][0]
        b1, b2 = st1 == mainstat, st2 == mainstat
        if b1 and b2:
            return math.inf
        if b1:
            return 6 * high(st2)
        if b2:
            return 6 * high(st1)
        return 6 * high(st1) + high(st2)
    if case == 'SINGLE':
        st = meta.sorted_substats[0][0]
        if st == mainstat:
            return math.inf
        return 6 * high(st)

    resolved = _resolve_optimal_mainstat(part, mainstat, meta)
    _, high = meta.accessors(resolved)
    filtered = [n for (n, _w) in meta.sorted_substats if n != resolved]
    effective = sorted((high(n) for n in filtered), reverse=True)
    effective += [0.0] * (4 - len(effective))
    return 6 * effective[0] + effective[1] + effective[2] + effective[3]


def score_current_relic(relic: dict, meta: ScorerMeta, ideal: float) -> dict:
    contribution, _high = meta.accessors(relic['mainStat'])
    raw = 0.0
    detail = []
    for s in relic['substats']:
        c = s['value'] * contribution(s['stat'])
        raw += c
        detail.append({'stat': s['stat'], 'value': s['value'], 'weighted': round(c, 4)})
    pct = 0.0 if ideal == math.inf else truncate10ths(precision_round(raw / ideal * 100))
    correct_main = (not has_main_stat(relic['part'])) or meta.main_stat_weight(
        relic['part'], relic['mainStat']) > 0
    rating = pct_to_rating(pct, relic.get('grade', 5), relic['part'], correct_main)
    return {'percent': pct, 'rating': rating, 'raw': round(raw, 4),
            'ideal': round(ideal, 4), 'correctMain': correct_main, 'detail': detail}
