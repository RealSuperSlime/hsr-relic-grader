"""Build data/relic_pieces.json: relic piece name -> {set, slot}.

Source: Mar-7th/StarRailRes index_min/en (relics.json + relic_sets.json),
already saved under data/.
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, 'relic_grades', 'data')

SLOT = {'HEAD': 'Head', 'HAND': 'Hands', 'BODY': 'Body', 'FOOT': 'Feet',
        'NECK': 'LinkRope', 'OBJECT': 'PlanarSphere'}

relics = json.load(open(os.path.join(DATA, 'relics_min.json'), encoding='utf8'))
sets = json.load(open(os.path.join(DATA, 'relic_sets_min.json'), encoding='utf8'))

pieces = {}
for rid, r in relics.items():
    set_name = sets.get(r['set_id'], {}).get('name')
    slot = SLOT.get(r['type'])
    if not set_name or not slot:
        continue
    pieces[r['name']] = {'set': set_name, 'slot': slot, 'rarity': r['rarity']}

json.dump({'pieces': pieces, 'sets': sorted({v['set'] for v in pieces.values()})},
          open(os.path.join(DATA, 'relic_pieces.json'), 'w'), indent=1, ensure_ascii=False)
print('pieces:', len(pieces), 'sets:', len({v['set'] for v in pieces.values()}))
