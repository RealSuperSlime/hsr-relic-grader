"""Player showcase lookup: UID -> showcased characters -> graded relics.

Data source: the public HSR showcase API (api.mihomo.me). The response gives each
character's equipped relics as numeric affix ids; `relic_main_affixes.json` /
`relic_sub_affixes.json` (copied from the optimizer's data) turn those into real
stats, and the resulting relic is scored by the same engine as the screenshot
path, so the numbers match everywhere.

API shape used:
  detailInfo
    uid, nickname, level
    avatarDetailList[]            <- the characters on the profile
      avatarId, level, rank (eidolon)
      equipment {tid, ...}        <- light cone (not scored)
      relicList[]
        tid                       <- relic id: set + slot + rarity (data/relics_min.json)
        type                      <- 1 Head 2 Hands 3 Body 4 Feet 5 Sphere 6 Rope
        level, mainAffixId
        subAffixList[] {affixId, cnt, step}
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request

from .characters import characters
from .fribbels import pct_to_rating
from .grade import grade_payload

from .paths import data_dir

DATA = data_dir()
API = 'https://api.mihomo.me/sr_info/{uid}'
USER_AGENT = 'Mozilla/5.0 (hsr-relic-scorer)'

SLOT_BY_TYPE = {1: 'Head', 2: 'Hands', 3: 'Body', 4: 'Feet',
                5: 'PlanarSphere', 6: 'LinkRope'}

PROPERTY = {
    'HPDelta': 'HP', 'AttackDelta': 'ATK', 'DefenceDelta': 'DEF',
    'HPAddedRatio': 'HP%', 'AttackAddedRatio': 'ATK%', 'DefenceAddedRatio': 'DEF%',
    'SpeedDelta': 'SPD', 'CriticalChanceBase': 'CRIT Rate',
    'CriticalDamageBase': 'CRIT DMG', 'StatusProbabilityBase': 'Effect Hit Rate',
    'StatusResistanceBase': 'Effect RES', 'BreakDamageAddedRatioBase': 'Break Effect',
    'SPRatioBase': 'Energy Regeneration Rate', 'HealRatioBase': 'Outgoing Healing Boost',
    'PhysicalAddedRatio': 'Physical DMG Boost', 'FireAddedRatio': 'Fire DMG Boost',
    'IceAddedRatio': 'Ice DMG Boost', 'ThunderAddedRatio': 'Lightning DMG Boost',
    'WindAddedRatio': 'Wind DMG Boost', 'QuantumAddedRatio': 'Quantum DMG Boost',
    'ImaginaryAddedRatio': 'Imaginary DMG Boost',
}
FLAT_DISPLAY = frozenset(('HP', 'ATK', 'DEF'))
# stats the game data stores as a ratio (0.324) but prints as a percentage (32.4%)
PERCENT_STATS = frozenset((
    'ATK%', 'HP%', 'DEF%', 'CRIT Rate', 'CRIT DMG', 'Effect Hit Rate', 'Effect RES',
    'Break Effect', 'Energy Regeneration Rate', 'Outgoing Healing Boost',
    'Physical DMG Boost', 'Fire DMG Boost', 'Ice DMG Boost', 'Lightning DMG Boost',
    'Wind DMG Boost', 'Quantum DMG Boost', 'Imaginary DMG Boost'))

_TABLES: dict | None = None
_FETCH_CACHE: dict[str, tuple[float, dict]] = {}
CACHE_SECONDS = 900


class ShowcaseError(Exception):
    """Anything that stops us from showing a profile (bad UID, private, offline)."""


def _json(name: str) -> dict:
    with open(os.path.join(DATA, name), encoding='utf8') as f:
        return json.load(f)


def tables() -> dict:
    global _TABLES
    if _TABLES is None:
        _TABLES = {
            'main': _json('relic_main_affixes.json'),
            'sub': _json('relic_sub_affixes.json'),
            'relics': _json('relics_min.json'),
            'sets': _json('relic_sets_min.json'),
            'names': _json('characters_min.json'),
        }
    return _TABLES


def _display(value: float, stat: str) -> float:
    """How the game prints it: flat HP/ATK/DEF as ints, percentages 1 decimal."""
    import math
    if stat in PERCENT_STATS:
        return math.floor(value * 1000 + 1e-9) / 10      # ratio -> percentage
    if stat in FLAT_DISPLAY:
        return float(math.floor(value + 1e-9))
    return math.floor(value * 10 + 1e-9) / 10            # SPD & friends


def fetch(uid: str, use_cache: bool = True) -> dict:
    uid = str(uid).strip()
    if not uid.isdigit() or not (9 <= len(uid) <= 10):
        raise ShowcaseError(f'`{uid}` does not look like a UID (9 digits, e.g. 101000000).')
    hit = _FETCH_CACHE.get(uid)
    if use_cache and hit and time.time() - hit[0] < CACHE_SECONDS:
        return hit[1]
    req = urllib.request.Request(API.format(uid=uid),
                                 headers={'User-Agent': USER_AGENT, 'Accept': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            payload = json.load(r)
    except urllib.error.HTTPError as e:
        raise ShowcaseError({
            400: 'That UID is not valid for this game.',
            404: 'No player found with that UID on this server.',
            429: 'The showcase service is rate-limiting right now — try again in a minute.',
            500: 'The showcase service returned an error for that UID — try again shortly.',
        }.get(e.code, f'The showcase service returned HTTP {e.code}.')) from e
    except Exception as e:
        raise ShowcaseError(f'Could not reach the showcase service ({type(e).__name__}).') from e
    _FETCH_CACHE[uid] = (time.time(), payload)
    return payload


def character_name(avatar_id) -> str:
    t = tables()
    hit = t['names'].get(str(avatar_id))
    if hit:
        return hit['name']
    hit = characters().get(str(avatar_id))
    return hit['name'] if hit else f'Character {avatar_id}'


def parse_relic(api_relic: dict) -> dict:
    """API relic -> our relic dict (part, mainStat, mainValue, substats, grade, names)."""
    t = tables()
    tid = str(api_relic.get('tid'))
    meta = t['relics'].get(tid)
    slot_no = api_relic.get('type')
    part = SLOT_BY_TYPE.get(slot_no)
    if part is None:
        raise ValueError(f'unknown relic slot type {slot_no!r}')
    rarity = int(meta['rarity']) if meta else 5
    level = int(api_relic.get('level') or 0)

    group = t['main'].get(f'{rarity}{slot_no}', {}).get('affixes', {})
    main_entry = group.get(str(api_relic.get('mainAffixId')))
    if main_entry is None:
        raise ValueError(f'unknown main affix {api_relic.get("mainAffixId")!r} for {group}')
    main_stat = PROPERTY.get(main_entry['property'], main_entry['property'])
    main_value = main_entry['base'] + level * main_entry['step']

    subs = []
    sub_table = t['sub'].get(str(rarity), {}).get('affixes', {})
    for s in api_relic.get('subAffixList') or []:
        entry = sub_table.get(str(s.get('affixId')))
        if entry is None:
            continue
        stat = PROPERTY.get(entry['property'], entry['property'])
        if stat not in ('ATK%', 'ATK', 'HP%', 'HP', 'DEF%', 'DEF', 'SPD', 'CRIT Rate',
                        'CRIT DMG', 'Effect Hit Rate', 'Effect RES', 'Break Effect'):
            continue
        total = int(s.get('cnt') or 0) * entry['base'] + int(s.get('step') or 0) * entry['step']
        subs.append({'stat': stat, 'value': _display(total, stat)})

    set_name = t['sets'].get(str(meta['set_id']), {}).get('name') if meta else None
    return {
        'part': part, 'mainStat': main_stat, 'mainValue': _display(main_value, main_stat),
        'substats': subs, 'grade': rarity, 'level': level,
        'set': set_name, 'piece': (meta or {}).get('name'),
        'verified': True,
    }


def grade_character(entry: dict) -> dict:
    """One avatarDetailList entry -> graded character."""
    avatar_id = str(entry.get('avatarId'))
    name = character_name(avatar_id)
    known = avatar_id in characters()

    relics, scores = [], []
    for api_relic in entry.get('relicList') or []:
        try:
            relic = parse_relic(api_relic)
        except (ValueError, KeyError):
            continue
        info = {'slot': relic['part'], 'set': relic['set'], 'piece': relic['piece'],
                'main': f"{relic['mainStat']} {relic['mainValue']:g}", 'score': None,
                'rating': '?' if not known else None,
                'subs': [{k: s[k] for k in ('stat', 'value')} for s in relic['substats']]}
        if known:
            try:
                graded = grade_payload(relic, avatar_id)
                info['score'] = graded['score']['value']
                info['rating'] = graded['score']['grade']
                info['subs'] = [{'stat': s['stat'], 'shown': s['shown'], 'badge': s['badge'],
                                 'weight': s['weight'], 'weighted': s['weighted']}
                                for s in graded['substats']]
                scores.append(graded['score']['value'])
            except Exception:
                pass
        relics.append(info)

    total = round(sum(scores) / len(scores), 1) if scores else None
    rating = pct_to_rating(total, 5, None, True) if total else None
    return {'id': avatar_id, 'name': name, 'level': entry.get('level'),
            'eidolon': entry.get('rank'), 'known': known,
            'relics': relics, 'total': total, 'rating': rating}


def showcase(uid: str, character: str | None = None, limit: int = 10) -> dict:
    """Look up a UID and grade every showcased character."""
    payload = fetch(uid)
    detail = payload.get('detailInfo') or {}
    entries = detail.get('avatarDetailList') or []
    if not entries:
        raise ShowcaseError('That profile has no characters on public display '
                            '(the player has Showcase turned off).')

    wanted = None
    if character:
        query = character.strip().lower()
        wanted = query

    out = []
    for entry in entries:
        graded = grade_character(entry)
        if wanted and wanted not in graded['name'].lower():
            continue
        out.append(graded)
    out.sort(key=lambda c: (-(c['total'] or -1), c['name']))
    return {'uid': str(detail.get('uid') or uid),
            'nickname': detail.get('nickname') or '?',
            'level': detail.get('level'),
            'characters': out[:limit],
            'total_characters': len(entries)}
