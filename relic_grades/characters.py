"""Character table + relic scoring entry points."""
from __future__ import annotations

import json
import math
import os
from difflib import SequenceMatcher

from .fribbels import (
    PARTS_MAIN_STATS,
    PART_ALIASES,
    SUBSTATS,
    ScorerMeta,
    compute_optimal_score,
    refine_substats,
    score_current_relic,
)

from .paths import data_dir

DATA_PATH = os.path.join(data_dir(), 'weights.json')

_CHARS: dict | None = None


def characters() -> dict:
    global _CHARS
    if _CHARS is None:
        with open(DATA_PATH, encoding='utf8') as f:
            _CHARS = json.load(f)
    return _CHARS


def _norm(s: str) -> str:
    keep = [c for c in s.lower() if c.isalnum()]
    out = ''.join(keep)
    return out.replace('trailblazer', 'tb')


def find_character(query: str) -> dict:
    """Resolve a character by name (fuzzy) or numeric id. Raises ValueError if ambiguous."""
    q = query.strip()
    chars = characters()
    if q in chars:
        return {'id': q, **chars[q]}
    nq = _norm(q)
    exact = [c for c, v in chars.items() if _norm(v['name']) == nq]
    if len(exact) == 1:
        return {'id': exact[0], **chars[exact[0]]}
    scored = []
    for cid, v in chars.items():
        n = _norm(v['name'])
        r = 1.0 if n == nq else SequenceMatcher(None, nq, n).ratio()
        if nq and (nq in n or n in nq):
            r = max(r, 0.9)
        scored.append((r, cid))
    scored.sort(reverse=True)
    best = scored[0][0] if scored else 0
    if best < 0.55:
        raise ValueError(f"No character matching {query!r}")
    top = [cid for r, cid in scored if r >= best - 1e-9][:8]
    # Duplicate names (e.g. Trailblazer variants, pre-Novaflare 'b1' entries) share
    # weights; prefer the plain released entry for a stable, predictable answer.
    top.sort(key=lambda cid: ('b1' in cid, not chars[cid].get('released', True), cid))
    return {'id': top[0], **chars[top[0]]}


def all_character_names() -> list[str]:
    return sorted({v['name'] for v in characters().values()})


def normalize_part(part: str) -> str:
    p = part.strip().lower().replace('_', ' ')
    if p in PART_ALIASES:
        return PART_ALIASES[p]
    for alias, full in PART_ALIASES.items():
        if alias in p:
            return full
    raise ValueError(f"Unrecognized relic slot {part!r} (expected {', '.join(PARTS_MAIN_STATS)})")


def normalize_stat(stat: str) -> str | None:
    s = stat.strip().lower().replace('%', ' percent').replace('_', ' ')
    s = ' '.join(s.split())
    table = {
        'atk percent': 'ATK%', 'atk': 'ATK', 'attack percent': 'ATK%', 'attack': 'ATK',
        'hp percent': 'HP%', 'hp': 'HP', 'hp percent': 'HP%',
        'def percent': 'DEF%', 'def': 'DEF', 'defence percent': 'DEF%', 'defense percent': 'DEF%',
        'defence': 'DEF', 'defense': 'DEF',
        'speed': 'SPD', 'spd': 'SPD',
        'crit rate': 'CRIT Rate', 'critrate': 'CRIT Rate', 'cr': 'CRIT Rate',
        'crit dmg': 'CRIT DMG', 'crit damage': 'CRIT DMG', 'critdmg': 'CRIT DMG', 'cd': 'CRIT DMG',
        'effect hit rate': 'Effect Hit Rate', 'ehr': 'Effect Hit Rate',
        'effect res': 'Effect RES', 'effect resist': 'Effect RES', 'res': 'Effect RES',
        'break effect': 'Break Effect', 'be': 'Break Effect',
        'energy regeneration rate': 'Energy Regeneration Rate', 'err': 'Energy Regeneration Rate',
        'outgoing healing boost': 'Outgoing Healing Boost', 'ohb': 'Outgoing Healing Boost',
    }
    if s in table:
        return table[s]
    return None


def score_for_character(character, relic: dict, refine: bool = True) -> dict:
    """character: dict from find_character(); relic: {part, mainStat, mainValue, substats, grade}.

    refine=True snaps each displayed substat (1 decimal) back to the true roll
    total, which is what Fribbels scores (e.g. 8.6% displayed -> 8.64 real).
    """
    if refine:
        relic = {**relic,
                 'substats': refine_substats(relic['substats'], relic.get('grade', 5))}
    meta = ScorerMeta(character['weights'], character.get('parts') or {},
                      character.get('flatMainstatBoost'))
    ideal = compute_optimal_score(relic['part'], relic['mainStat'], meta)
    res = score_current_relic(relic, meta, ideal)
    res['character'] = character['name']
    res['characterId'] = character['id']
    return res
