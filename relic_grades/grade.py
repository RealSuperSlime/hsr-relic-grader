"""One place that turns (image | parsed relic, character) into a grade payload.

Both the local UI (ui/app.py) and the Discord bot use this, so the number on
screen and the number in Discord are always produced by the same code.
"""
from __future__ import annotations

from .characters import find_character, score_for_character
from .fribbels import roll_count
from .ocr import parse_relic_image


def grade_payload(relic: dict, character_query: str) -> dict:
    """Score an already parsed relic for one character."""
    character = find_character(character_query)
    fields = {k: relic[k] for k in ('part', 'mainStat', 'mainValue', 'substats', 'grade')}
    score = score_for_character(character, fields, refine=True)

    weights = character['weights']
    shown_by_stat = {s.get('stat'): s.get('value') for s in relic.get('substats', [])}
    subs = []
    for d in score['detail']:
        subs.append({'stat': d['stat'],
                     'shown': d.get('shown', shown_by_stat.get(d['stat'])),
                     'exact': d['value'],
                     'rolls': roll_count(d['stat'], d['value'], relic.get('grade', 5)),
                     'badge': (roll_count(d['stat'], d['value'], relic.get('grade', 5)) - 1)
                              if roll_count(d['stat'], d['value'], relic.get('grade', 5)) else None,
                     'weight': weights.get(d['stat'], 0),
                     'weighted': d['weighted']})
    top = max([s['weighted'] for s in subs], default=0) or 1
    for s in subs:
        s['share'] = round(min(1.0, s['weighted'] / top), 4)

    return {
        'character': {'id': character['id'], 'name': character['name'],
                      'element': character.get('element'), 'path': character.get('path'),
                      'weights': {k: v for k, v in weights.items() if v}},
        'score': {'value': score['percent'], 'grade': score['rating'],
                  'raw': round(score['raw'], 4), 'ideal': round(score['ideal'], 4),
                  'correctMain': score['correctMain']},
        'relic': relic,
        'substats': subs,
    }


def grade_image(source, character_query: str) -> dict:
    """OCR a screenshot (path or binary stream) and score it."""
    return grade_payload(parse_relic_image(source), character_query)
