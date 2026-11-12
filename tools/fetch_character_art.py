"""Fetch the per-character art the V2 UI puts behind the grader.

Fribbels' HSR Optimizer ships one WebP per character at
``public/assets/image/character_preview/<id>.webp`` - a static 376x512 splash. The
app uses exactly this file for the same purpose (see ``src/lib/rendering/assets.ts``).

That artwork is HoYoverse's, so it is **not** redistributed with this repo: the art
directory is git-ignored. Fetch it once and the UI picks it up.

    python tools/fetch_character_art.py                  # download only what is missing
    python tools/fetch_character_art.py --from <checkout> # copy out of a local clone
    python tools/fetch_character_art.py --force           # re-fetch everything

``--from`` accepts either the optimizer checkout root or its ``public/assets`` dir.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEST = os.path.join(ROOT, 'ui', 'static', 'art')
WEIGHTS = os.path.join(ROOT, 'relic_grades', 'data', 'weights.json')

RAW = ('https://raw.githubusercontent.com/fribbels/hsr-optimizer/main/'
       'public/assets/image/character_preview/{id}.webp')
CDN = ('https://fribbels.github.io/hsr-optimizer/assets/image/'
       'character_preview/{id}.webp')


def character_ids() -> list[str]:
    with open(WEIGHTS, encoding='utf-8') as f:
        return sorted(json.load(f))


def find_local_assets(path: str) -> str | None:
    """Accept the checkout root, its public/assets dir, or the preview dir itself."""
    for candidate in (os.path.join(path, 'image', 'character_preview'),
                      os.path.join(path, 'public', 'assets', 'image', 'character_preview'),
                      os.path.join(path, 'assets', 'image', 'character_preview'),
                      path):
        if os.path.isdir(candidate) and any(f.endswith('.webp') for f in os.listdir(candidate)):
            return candidate
    return None


def download(url: str, dest: str) -> bool:
    req = urllib.request.Request(url, headers={'User-Agent': 'hsr-relic-grader'})
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            blob = r.read()
    except (urllib.error.URLError, OSError, TimeoutError):
        return False
    if not blob.startswith(b'RIFF') or b'WEBP' not in blob[:16]:
        return False
    with open(dest, 'wb') as f:
        f.write(blob)
    return True


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description='Fetch character art for the V2 UI.')
    ap.add_argument('--from', dest='source', default=None,
                    help='a local hsr-optimizer checkout to copy from')
    ap.add_argument('--force', action='store_true', help='re-fetch art already present')
    ap.add_argument('--dest', default=DEST)
    args = ap.parse_args(argv)

    ids = character_ids()
    os.makedirs(args.dest, exist_ok=True)

    local = find_local_assets(args.source) if args.source else None
    if args.source and not local:
        print(f'No character_preview folder under {args.source!r}.', file=sys.stderr)
        return 1

    copied = fetched = skipped = failed = 0
    for cid in ids:
        dest = os.path.join(args.dest, f'{cid}.webp')
        if os.path.isfile(dest) and not args.force:
            skipped += 1
            continue
        if local:
            shutil.copyfile(os.path.join(local, f'{cid}.webp'), dest)
            copied += 1
            continue
        if download(RAW.format(id=cid), dest) or download(CDN.format(id=cid), dest):
            fetched += 1
        else:
            failed += 1

    print(f'character art -> {args.dest}')
    if copied:
        print(f'  copied from local checkout : {copied}')
    if fetched:
        print(f'  downloaded                 : {fetched}')
    if skipped:
        print(f'  already present            : {skipped}')
    if failed:
        print(f'  FAILED                     : {failed}')
    print(f'  total characters           : {len(ids)}')
    if not (copied or fetched or skipped):
        print('\nNothing fetched. Check your connection, or point --from at a clone.',
              file=sys.stderr)
        return 1
    print('\nThe art is HoYoverse\'s and stays out of the repo (ui/static/art/ is ignored).')
    return 0


if __name__ == '__main__':
    sys.exit(main())
