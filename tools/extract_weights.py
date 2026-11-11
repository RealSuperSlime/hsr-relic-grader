"""Extract per-character relic substat weights from a clone of fribbels/hsr-optimizer.

Run:  python tools/extract_weights.py <path-to-hsr-optimizer-repo>
Writes: data/weights.json
"""
import glob
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
    'Wind_DMG': 'Wind DMG Boost', 'Elation': 'Elation',
}


def match_brace(s, i):
    """s[i] == '{' -> index of matching '}'"""
    depth = 0
    j = i
    instr = None
    while j < len(s):
        ch = s[j]
        if instr:
            if ch == '\\':
                j += 2
                continue
            if ch == instr:
                instr = None
        else:
            if ch in '"\'':
                instr = ch
            elif ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    return j
        j += 1
    return -1


def main(repo):
    out = {}
    for path in glob.glob(os.path.join(repo, 'src/lib/conditionals/character/*/*.ts')):
        src = open(path, encoding='utf8').read()
        m = re.search(r'const scoring\s*=\s*\(\s*\)\s*:\s*ScoringMetadata\s*=>\s*\(\s*\{', src)
        if not m:
            continue
        start = src.index('{', m.start())
        block = src[start:match_brace(src, start) + 1]

        ms = re.search(r'stats:\s*\{', block)
        if not ms:
            continue
        sb = block.index('{', ms.start())
        statblock = block[sb:match_brace(block, sb) + 1]
        weights = {}
        for mm in re.finditer(r'\[\s*Stats\.(\w+)\s*\]\s*:\s*(-?[\d.]+)', statblock):
            weights[STAT_LABEL[mm.group(1)]] = float(mm.group(2))

        # ids declared in the exported CharacterConfig blocks (a file may export several, e.g. male/female TB)
        ids = []
        for em in re.finditer(r':\s*CharacterConfig\s*=\s*\{', src):
            bb = src.index('{', em.start())
            export_block = src[bb:match_brace(src, bb) + 1]
            im = re.search(r"id:\s*'([\w]+)'", export_block)
            if im:
                ids.append(im.group(1))
        if not ids:
            continue

        fb = re.search(r'flatMainstatBoost:\s*Stats\.(\w+)', block)
        parts = {}
        pm = re.search(r'parts:\s*\{', block)
        if pm:
            pb = block.index('{', pm.start())
            pblock = block[pb:match_brace(block, pb) + 1]
            for mm in re.finditer(r'\[\s*Parts\.(\w+)\s*\]\s*:\s*\[(.*?)\]', pblock, re.S):
                parts[mm.group(1)] = [STAT_LABEL[x] for x in re.findall(r'Stats\.(\w+)', mm.group(2))]

        for cid in ids:
            out[cid] = {
                'sourceFile': os.path.basename(path)[:-3],
                'weights': weights,
                'parts': parts,
                'flatMainstatBoost': STAT_LABEL[fb.group(1)] if fb else None,
            }

    gd = json.load(open(os.path.join(repo, 'src/data/game_data.json'), encoding='utf8'))
    chars = {}
    for cid, meta in gd['characters'].items():
        w = out.get(cid)
        if not w:
            continue
        chars[cid] = {
            'name': meta['name'],
            'rarity': meta.get('rarity'),
            'path': meta.get('path'),
            'element': meta.get('element'),
            'released': not meta.get('unreleased', False),
            'weights': w['weights'],
            'parts': w['parts'],
            'flatMainstatBoost': w['flatMainstatBoost'],
        }
    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..',
                           'relic_grades', 'data')
    os.makedirs(out_dir, exist_ok=True)
    json.dump(chars, open(os.path.join(out_dir, 'weights.json'), 'w'), indent=1, sort_keys=True)
    print('characters with weights:', len(chars))
    missing = [k for k in gd['characters'] if k not in out]
    print('no scoring config (unreleased/skip):', missing)


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else 'hsr-opt')
