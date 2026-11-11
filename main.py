"""HSR relic grader — Fribbels-compatible.

Usage:
    python main.py                      # interactive: character, then image path
    python main.py -c Acheron -i relic.png
    python main.py -c Acheron -i relic.png --all      # score vs. every character
    python main.py --list                             # list characters
"""
from __future__ import annotations

import argparse
import os
import sys

from relic_grades.characters import (all_character_names, characters, find_character,
                                     score_for_character)
from relic_grades.ocr import parse_relic_image

PARTS = ('Head', 'Hands', 'Body', 'Feet', 'PlanarSphere', 'LinkRope')
SLOT_LABEL = {'PlanarSphere': 'Planar Sphere', 'LinkRope': 'Link Rope'}


def fmt_relic(relic: dict, debug: bool = False) -> str:
    lines = []
    piece = relic.get('piece') or '(unknown piece)'
    slot = SLOT_LABEL.get(relic.get('part'), relic.get('part') or '?')
    level = f"+{relic['level']}" if relic.get('level') is not None else ''
    lines.append(f"Relic : {piece}")
    lines.append(f"Set   : {relic.get('set') or '?'}")
    lines.append(f"Slot  : {slot}   {relic.get('grade', 5)}*   {level}".rstrip())
    if relic.get('mainStat'):
        shown = relic.get('mainRead') or relic['mainValue']
        shown = f"{shown:g}"
        pct = '' if relic['mainStat'] in ('SPD', 'HP', 'ATK', 'DEF') else '%'
        lines.append(f"Main  : {relic['mainStat']} {shown}{pct}")
    subs = ', '.join(f"{s['stat']} {s['value']}" for s in relic.get('substats', []))
    lines.append(f"Subs  : {subs}")
    for w in relic.get('warnings', []):
        lines.append(f"  ! {w}")
    return '\n'.join(lines)


def report(character: dict, relic: dict, score: dict, refine: bool = True) -> str:
    out = [f"{character['name']}: {score['percent']:.1f}   ({score['rating']})"]
    if score.get('detail'):
        bits = []
        for d in score['detail']:
            shown = d.get('shown')
            val = d['value']
            arrow = '' if shown is None or abs(shown - val) < 1e-9 else f" (shown {shown})"
            bits.append(f"    {d['stat']:<16} {val:>8.3f}{arrow}   weighted {d['weighted']:>7.3f}")
        if refine:
            out.append('  weighted substat contribution (roll-exact values):')
        else:
            out.append('  weighted substat contribution:')
        out.extend(bits)
        out.append(f"    {'ideal':<16} {score['ideal']:>8.3f}")
    if not score['correctMain']:
        out.append(f"  ! {relic['mainStat']} is not a recommended main stat for "
                   f"{character['name']} (score still shown, grade suppressed)")
    return '\n'.join(out)


def ask(prompt: str, default: str | None = None) -> str:
    try:
        got = input(prompt).strip().strip('"').strip("'")
    except (EOFError, KeyboardInterrupt):
        print()
        sys.exit(0)
    return got or (default or '')


def resolve(path: str) -> str:
    p = os.path.expanduser(path.strip().strip('"').strip("'"))
    if not os.path.isfile(p):
        raise SystemExit(f"No such image: {p}")
    return p


def run_once(character_query: str, image: str, score_all: bool, refine: bool,
             debug: bool) -> None:
    raw_rows: list = []
    relic = parse_relic_image(resolve(image), raw_lines=raw_rows)
    if debug:
        print('--- OCR rows ---')
        for r in raw_rows:
            print(f"  y{r['y0']:>4}  {r['label']!r:<30} {r['value_raw']!r}")
        print('---------------')

    print()
    print(fmt_relic(relic))
    print()

    if not relic.get('part') or not relic.get('mainStat'):
        print('Could not read this screenshot well enough to score it.')
        if relic.get('substats'):
            print('(substats were read, but slot/main stat are missing)')
        return

    relic_for_score = {k: relic[k] for k in ('part', 'mainStat', 'mainValue',
                                             'substats', 'grade')}
    if score_all:
        rows = []
        for cid, c in characters().items():
            r = score_for_character({'id': cid, **c}, relic_for_score, refine=refine)
            rows.append((r['percent'], r['rating'], c['name']))
        rows.sort(reverse=True)
        print(f"{'score':>6}  {'grade':<6} character")   # score is a value, not a percent
        for pct, rating, name in rows:
            print(f"{pct:6.1f}  {rating:<6} {name}")
        return

    character = find_character(character_query)
    score = score_for_character(character, relic_for_score, refine=refine)
    print(report(character, relic_for_score, score, refine=refine))


def main() -> None:
    ap = argparse.ArgumentParser(description='Grade HSR relics the way Fribbels does.')
    ap.add_argument('-c', '--character', help='character name or id (e.g. Acheron)')
    ap.add_argument('-i', '--image', help='relic screenshot (png/jpg)')
    ap.add_argument('--all', action='store_true', help='score against every character')
    ap.add_argument('--raw', action='store_true',
                    help="don't snap displayed values to exact roll totals")
    ap.add_argument('--debug', action='store_true', help='print raw OCR rows')
    ap.add_argument('--list', action='store_true', help='list known characters')
    args = ap.parse_args()

    if args.list:
        for name in all_character_names():
            print(name)
        return

    refine = not args.raw
    if args.image and (args.character or args.all):
        run_once(args.character or '', args.image, args.all, refine, args.debug)
        return

    print('HSR relic grader (Fribbels scoring). Ctrl-C to quit.\n')
    character = args.character or ask('Character: ')
    while True:
        image = args.image or ask('Relic screenshot path: ')
        if not image:
            break
        try:
            run_once(character, image, args.all, refine, args.debug)
        except SystemExit as e:
            print(e)
        print()
        again = ask('Another relic for the same character? [Enter = yes, n = quit] ')
        if again.lower() in ('n', 'no', 'q', 'quit'):
            break


if __name__ == '__main__':
    main()
