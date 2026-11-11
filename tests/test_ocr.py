"""OCR tests against the bundled sample screenshots."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from relic_grades.characters import find_character, score_for_character  # noqa: E402
from relic_grades.ocr import parse_relic_image  # noqa: E402

SAMPLES = os.path.join(ROOT, 'samples')


def _score(image, character):
    r = parse_relic_image(os.path.join(SAMPLES, image))
    relic = {k: r[k] for k in ('part', 'mainStat', 'mainValue', 'substats', 'grade')}
    return r, score_for_character(find_character(character), relic)


def test_acheron_pioneer_body_parses_exactly():
    r = parse_relic_image(os.path.join(SAMPLES, 'acheron_pioneer_body.png'))
    assert r['set'] == 'Pioneer Diver of Dead Waters'
    assert r['piece'] == "Pioneer's Sealed Lead Apron"
    assert r['part'] == 'Body'
    assert r['level'] == 15
    assert r['grade'] == 5
    assert r['mainStat'] == 'CRIT Rate'
    assert r['mainValue'] == 32.4
    assert [(s['stat'], s['value']) for s in r['substats']] == [
        ('ATK%', 8.6), ('CRIT DMG', 12.9), ('Effect Hit Rate', 3.4), ('Break Effect', 18.1)]
    assert r['warnings'] == []


def test_acheron_pioneer_body_scores_54():
    _r, score = _score('acheron_pioneer_body.png', 'Acheron')
    assert score['percent'] == 54.0 and score['rating'] == 'S'


def test_boothill_eagle_feet_parses_exactly():
    r = parse_relic_image(os.path.join(SAMPLES, 'boothill_eagle_feet.png'))
    assert r['set'] == 'Eagle of Twilight Line'
    assert r['piece'] == "Eagle's Quilted Puttees"
    assert r['part'] == 'Feet'
    assert r['level'] == 15
    assert r['mainStat'] == 'SPD'
    assert r['mainRead'] == 25
    assert [(s['stat'], s['value']) for s in r['substats']] == [
        ('HP%', 7.3), ('CRIT Rate', 6.1), ('Effect RES', 3.4), ('Break Effect', 24.6)]


def test_dahlia_iron_cavalry_body_parses_exactly():
    r = parse_relic_image(os.path.join(SAMPLES, 'dahlia_ironcavalry_body.png'))
    assert r['set'] == 'Iron Cavalry Against the Scourge'
    assert r['piece'] == "Iron Cavalry's Silvery Armor"
    assert r['part'] == 'Body'
    assert r['level'] == 15
    assert r['mainStat'] == 'HP%'
    assert r['mainValue'] == 43.2
    assert [(s['stat'], s['value']) for s in r['substats']] == [
        ('DEF', 16.0), ('ATK%', 10.8), ('CRIT DMG', 5.1), ('Break Effect', 22.6)]


def test_sample_scores_per_character():
    _r, boothill = _score('boothill_eagle_feet.png', 'Boothill')
    assert (boothill['percent'], boothill['rating']) == (63.3, 'SS')
    _r, dahlia = _score('dahlia_ironcavalry_body.png', 'Dahlia')
    assert (dahlia['percent'], dahlia['rating']) == (50.0, 'S')


if __name__ == '__main__':
    for name, fn in sorted(globals().items()):
        if name.startswith('test_') and callable(fn):
            fn()
            print('ok', name)
