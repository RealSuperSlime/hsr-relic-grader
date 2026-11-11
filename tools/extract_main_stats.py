"""Extract max main-stat values per relic grade from constants.ts -> data/main_stats_max.json"""
import json
import os
import re
import sys

STAT_LABEL = {
    'ATK_P': 'ATK%', 'ATK': 'ATK', 'BE': 'Break Effect', 'CD': 'CRIT DMG', 'CR': 'CRIT Rate',
    'DEF_P': 'DEF%', 'DEF': 'DEF', 'EHR': 'Effect Hit Rate', 'ERR': 'Energy Regeneration Rate',
    'Fire_DMG': 'Fire DMG Boost', 'HP_P': 'HP%', 'HP': 'HP', 'Ice_DMG': 'Ice DMG Boost',
    'Imaginary_DMG': 'Imaginary DMG Boost', 'Lightning_DMG': 'Lightning DMG Boost',
    'OHB': 'Outgoing Healing Boost', 'Physical_DMG': 'Physical DMG Boost',
    'Quantum_DMG': 'Quantum DMG Boost', 'RES': 'Effect RES', 'SPD_P': 'SPD%', 'SPD': 'SPD',
    'Wind_DMG': 'Wind DMG Boost',
}
MAX_ENHANCE = {5: 15, 4: 12, 3: 9, 2: 6}


def main(repo):
    src = open(os.path.join(repo, 'src/lib/constants/constants.ts'), encoding='utf8').read()
    i = src.index('export const MainStatsValues')
    block = src[i:i + 9000]
    out = {}
    for m in re.finditer(r'\[Stats\.(\w+)\]:\s*\{((?:\s*\d:\s*\{[^}]*\},?)+)', block):
        stat = STAT_LABEL[m.group(1)]
        per = {}
        for g, base, inc in re.findall(r'(\d):\s*\{\s*base:\s*([\d.]+),\s*increment:\s*([\d.]+)', m.group(2)):
            g = int(g)
            per[g] = round(float(base) + float(inc) * MAX_ENHANCE[g], 4)
        if per:
            out[stat] = per
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..',
                        'relic_grades', 'data', 'main_stats_max.json')
    json.dump(out, open(path, 'w'), indent=1, sort_keys=True)
    print('stats:', len(out))
    for k in ('CRIT Rate', 'ATK%', 'SPD', 'Outgoing Healing Boost', 'Energy Regeneration Rate'):
        print(k, out.get(k))


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else '.')
