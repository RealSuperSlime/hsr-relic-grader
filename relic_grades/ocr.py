"""Screenshot -> structured relic, using Tesseract OCR.

Pipeline
  1. build a text mask (bright-enough pixels, minus the green roll-count badges)
  2. segment the card into text rows by horizontal projection
  3. OCR each row twice: left part = stat name, right part = value
     (values are binarised first; the header is OCR'd whole, since names wrap)
  4. fuzzy-match names against the game's stat / relic-piece tables, then
     sanity-check every number against the max roll range of its stat

Tesseract is looked up in vendor/tesseract (bundled with this project) first.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from difflib import SequenceMatcher

import numpy as np
from PIL import Image

from .fribbels import ALL_STATS, match_roll_sum, sub_high

from .paths import USER_TESSERACT_DIR, data_dir

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = data_dir()

# --------------------------------------------------------------------------- #
# tesseract discovery
# --------------------------------------------------------------------------- #
_TESS_CACHE: str | None = None


def find_tesseract() -> str:
    global _TESS_CACHE
    if _TESS_CACHE:
        return _TESS_CACHE
    candidates = [
        os.environ.get('RELIC_TESSERACT'),
        os.path.join(ROOT, 'vendor', 'tesseract', 'tesseract.exe'),   # repo checkout
        os.path.join(USER_TESSERACT_DIR, 'tesseract.exe'),            # pip install
        shutil.which('tesseract'),
        r'C:\Program Files\Tesseract-OCR\tesseract.exe',
        r'C:\Program Files (x86)\Tesseract-OCR\tesseract.exe',
    ]
    for c in candidates:
        if c and os.path.isfile(c):
            _TESS_CACHE = c
            return c
    raise RuntimeError(
        'Tesseract not found.\n'
        '  Easiest: run "hsr-relic-grader-tesseract" (or tools/install_tesseract.py)\n'
        '  Already have it? Set RELIC_TESSERACT to tesseract.exe, or put it on PATH.')


def _tess_env(tess: str) -> dict:
    env = dict(os.environ)
    tessdata = os.path.join(os.path.dirname(tess), 'tessdata')
    if os.path.isdir(tessdata):
        env['TESSDATA_PREFIX'] = tessdata
    return env


def _ocr(img: Image.Image, psm: int = 7, whitelist: str | None = None,
         target_px: int = 90, scale: int | None = None) -> str:
    tess = find_tesseract()
    img = img.convert('L')
    if scale is None:
        scale = max(1, min(6, int(round(target_px / max(1, img.height)))))
    if scale > 1:
        img = img.resize((img.width * scale, img.height * scale), Image.LANCZOS)
    fd, path = tempfile.mkstemp(suffix='.png')
    os.close(fd)
    try:
        img.save(path)
        cmd = [tess, path, 'stdout', '--psm', str(psm)]
        if whitelist:
            cmd += ['-c', f'tessedit_char_whitelist={whitelist}']
        out = subprocess.run(cmd, capture_output=True, text=True,
                             env=_tess_env(tess), timeout=60)
        return out.stdout.strip()
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


# --------------------------------------------------------------------------- #
# image -> rows
# --------------------------------------------------------------------------- #
def _green(a: np.ndarray) -> np.ndarray:
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    return (g > r + 30) & (g > b + 20) & (g > 110)


def _lum(a: np.ndarray) -> np.ndarray:
    return 0.299 * a[..., 0] + 0.587 * a[..., 1] + 0.114 * a[..., 2]


def _text_mask(im: Image.Image, thr: float = 130) -> np.ndarray:
    a = np.asarray(im.convert('RGB')).astype(np.int16)
    return (_lum(a) > thr) & ~_green(a)


def _binarise(im: Image.Image, thr: float = 110) -> Image.Image:
    """black text on white, badge-free"""
    a = np.asarray(im.convert('RGB')).astype(np.int16)
    keep = (_lum(a) > thr) & ~_green(a)
    return Image.fromarray(np.where(keep, 0, 255).astype(np.uint8))


def _bands(mask: np.ndarray, min_h: int = 6, gap: int = 3) -> list[tuple[int, int]]:
    rows = mask.sum(axis=1)
    bands, start, last = [], None, None
    for y, v in enumerate(rows):
        if v > 2:
            if start is None:
                start = y
            last = y
        elif start is not None and y - last > gap:
            if last - start + 1 >= min_h:
                bands.append((start, last + 1))
            start = None
    if start is not None and last - start + 1 >= min_h:
        bands.append((start, last + 1))
    return bands


def _split_label_value(im: Image.Image, mask_band: np.ndarray, y0: int, y1: int):
    """Split a row into its label cell and its (right-aligned) value cell.

    The value is the row's right-most wide ink cluster: badges/icons are narrow
    (dropped), and the number itself may reach the very edge of the card, so the
    value cell is taken to the full image width and the badges are masked out."""
    h, w = mask_band.shape
    cols = mask_band.sum(axis=0)
    spans, x = [], 0
    while x < w:
        if cols[x] > 0:
            s = x
            while x < w and cols[x] > 0:
                x += 1
            spans.append([s, x])
        else:
            x += 1
    merged = []
    for s, e in spans:                              # glue glyphs of one word
        if merged and s - merged[-1][1] <= max(3, int(w * 0.02)):
            merged[-1][1] = e
        else:
            merged.append([s, e])
    wide = [sp for sp in merged if sp[1] - sp[0] >= max(5, int(w * 0.03))]
    split = wide[-1][0] - 2 if wide else int(w * 0.62)
    split = max(int(w * 0.3), min(split, int(w * 0.97)))
    pad = 3
    top, bottom = max(0, y0 - pad), min(im.height, y1 + pad)
    return im.crop((0, top, split, bottom)), im.crop((split, top, w, bottom))


# --------------------------------------------------------------------------- #
# text -> fields
# --------------------------------------------------------------------------- #
_STAT_ALIASES = {
    'atk': 'ATK', 'attack': 'ATK', 'atkpercent': 'ATK%', 'attackpercent': 'ATK%',
    'hp': 'HP', 'hppercent': 'HP%', 'def': 'DEF', 'defence': 'DEF', 'defense': 'DEF',
    'defpercent': 'DEF%', 'defencepercent': 'DEF%', 'defensepercent': 'DEF%',
    'speed': 'SPD', 'spd': 'SPD', 'spdpercent': 'SPD%',
    'critrate': 'CRIT Rate', 'critchance': 'CRIT Rate', 'cr': 'CRIT Rate',
    'critdmg': 'CRIT DMG', 'critdamage': 'CRIT DMG', 'cd': 'CRIT DMG',
    'effecthitrate': 'Effect Hit Rate', 'ehr': 'Effect Hit Rate',
    'effectres': 'Effect RES', 'effectresistance': 'Effect RES',
    'breakeffect': 'Break Effect', 'be': 'Break Effect',
    'energyregenerationrate': 'Energy Regeneration Rate', 'err': 'Energy Regeneration Rate',
    'outgoinghealingboost': 'Outgoing Healing Boost', 'ohb': 'Outgoing Healing Boost',
    'physicaldmgboost': 'Physical DMG Boost', 'firedmgboost': 'Fire DMG Boost',
    'icedmgboost': 'Ice DMG Boost', 'lightningdmgboost': 'Lightning DMG Boost',
    'winddmgboost': 'Wind DMG Boost', 'quantumdmgboost': 'Quantum DMG Boost',
    'imaginarydmgboost': 'Imaginary DMG Boost',
    'physicaldamageboost': 'Physical DMG Boost', 'firedamageboost': 'Fire DMG Boost',
    'icedamageboost': 'Ice DMG Boost', 'lightningdamageboost': 'Lightning DMG Boost',
    'winddamageboost': 'Wind DMG Boost', 'quantumdamageboost': 'Quantum DMG Boost',
    'imaginarydamageboost': 'Imaginary DMG Boost',
}


def _norm(text: str) -> str:
    return ''.join(re.findall(r'[A-Za-z]+', text)).lower()


_STAT_BY_NORM = {_norm(s): s for s in ALL_STATS + ['Outgoing Healing Boost',
                                                  'Energy Regeneration Rate', 'SPD%']}
_STAT_BY_NORM.update(_STAT_ALIASES)


def match_stat(text: str, threshold: float = 0.72) -> str | None:
    n = _norm(text)
    if not n:
        return None
    if n in _STAT_BY_NORM:
        return _STAT_BY_NORM[n]
    best, best_r = None, 0.0
    for key, stat in _STAT_BY_NORM.items():
        r = SequenceMatcher(None, n, key).ratio()
        if len(n) > 5 and (key in n or n in key):
            r = max(r, 0.92)
        # 'hpae', 'hpx' -> HP: OCR often glues a stray glyph onto a short label
        if len(key) >= 2 and len(n) <= len(key) + 2 and n.startswith(key):
            r = max(r, 0.95)
        if r > best_r:
            best, best_r = stat, r
    return best if best_r >= threshold else None


_SLOT_WORDS = {
    'body': 'Body', 'chest': 'Body', 'armor': 'Body',
    'feet': 'Feet', 'boots': 'Feet', 'shoes': 'Feet',
    'head': 'Head', 'helm': 'Head',
    'hands': 'Hands', 'gloves': 'Hands',
    'planarsphere': 'PlanarSphere', 'sphere': 'PlanarSphere', 'orb': 'PlanarSphere',
    'linkrope': 'LinkRope', 'rope': 'LinkRope',
}

_NUM_RE = re.compile(r'\d+(?:[.,]\d+)?')


_MAIN_MAX: dict | None = None


def _main_max(stat: str) -> float:
    global _MAIN_MAX
    if _MAIN_MAX is None:
        try:
            with open(os.path.join(DATA, 'main_stats_max.json'), encoding='utf8') as f:
                _MAIN_MAX = json.load(f)
        except OSError:
            _MAIN_MAX = {}
    return max(_MAIN_MAX.get(stat, {}).values() or [0])


def _plausible(stat: str | None, value: float) -> bool:
    """A relic can put at most 9 rolls into one substat (4 initial + 5 upgrades),
    and a main stat is bigger than any substat could be."""
    if value <= 0:
        return False
    if not stat or stat not in ('ATK%', 'ATK', 'HP%', 'HP', 'DEF%', 'DEF', 'SPD',
                                'CRIT Rate', 'CRIT DMG', 'Effect Hit Rate',
                                'Effect RES', 'Break Effect'):
        return value <= 200          # unknown stats: loose bound
    return value <= max(sub_high(stat) * 9.5, _main_max(stat) * 1.02)


def _otsu(grey: np.ndarray) -> int:
    hist = np.bincount(grey.ravel(), minlength=256).astype(np.float64)
    total = float(grey.size)
    idx = np.arange(256)
    w_b = np.cumsum(hist)
    w_f = total - w_b
    sum_b = np.cumsum(hist * idx)
    sum_all = sum_b[-1]
    with np.errstate(invalid='ignore', divide='ignore'):
        m_b = sum_b / w_b
        m_f = (sum_all - sum_b) / w_f
        var = w_b * w_f * (m_b - m_f) ** 2
    return int(np.nanargmax(var))


def _auto_binarise(im: Image.Image, floor_gap: int = 12) -> Image.Image:
    """Otsu threshold for THIS cell, so a highlighted row (lighter bar) or a dim
    row still separates text from background - fixed thresholds do not."""
    a = np.asarray(im.convert('RGB')).astype(np.int16)
    grey = _lum(a)
    if grey.max() - grey.min() < 25:            # blank cell, nothing to read
        return im.convert('L')
    if len(np.unique(grey.astype(np.uint8))) <= 4:      # already black/white
        return im.convert('L')
    thr = max(_otsu(grey.astype(np.uint8)), int(np.percentile(grey, 55)) + floor_gap)
    thr = min(thr, int(grey.max()) - 8)
    keep = (grey > thr) & ~_green(a)
    if not (0.002 <= keep.mean() <= 0.6):       # degenerate threshold: split the range
        thr = int((grey.min() + grey.max()) / 2)
        keep = (grey > thr) & ~_green(a)
    return Image.fromarray(np.where(keep, 0, 255).astype(np.uint8))


def _auto_double(im: Image.Image) -> Image.Image:
    """auto-threshold first, then crop to the ink it found (drops background
    sparkle that would otherwise sit inside the crop and derail tesseract)."""
    bw = _auto_binarise(im)
    a = np.asarray(bw)
    ys, xs = np.where(a < 128)
    if len(xs) == 0:
        return bw
    return bw.crop((int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1))


def _auto_tight(im: Image.Image):
    """bbox of the auto-thresholded text, so the crop hugs the glyphs."""
    a = np.asarray(im.convert('RGB')).astype(np.int16)
    grey = _lum(a)
    thr = max(_otsu(grey.astype(np.uint8)), int(np.percentile(grey, 55)) + 12)
    keep = (grey > thr) & ~_green(a)
    if not keep.any():
        return im
    ys, xs = np.where(keep)
    return im.crop((int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1))


def _masked_grey(im: Image.Image) -> Image.Image:
    """grayscale, with the green roll badges painted out to background white"""
    a = np.asarray(im.convert('RGB')).astype(np.int16)
    grey = _lum(a).astype(np.uint8)
    grey[_green(a)] = 255
    return Image.fromarray(grey)


def _tight(img: Image.Image, thr: float = 110):
    a = np.asarray(img.convert('RGB')).astype(np.int16)
    keep = (_lum(a) > thr) & ~_green(a)
    if not keep.any():
        return img
    ys, xs = np.where(keep)
    return img.crop((int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1))


def read_value(value_img: Image.Image, stat: str | None,
               verbose: list | None = None,
               main_values: list[float] | None = None) -> tuple[float | None, bool]:
    """Read a value cell with several preprocessing passes and vote.

    A candidate that snaps onto a real combination of substat rolls is strongly
    preferred, which kills misreads like 12.9 -> 292.9 / 2.9."""
    auto = _auto_tight(value_img)
    double = _auto_double(value_img)
    variants: list[tuple[Image.Image, int, int]] = []
    if double.width > 2 and double.height > 4:
        # a hard-black/white image reads best at native size; upscaling its
        # edges with LANCZOS blurs the strokes back together
        variants.extend([(double, 1, 6), (double, 1, 7), (double, 2, 6), (double, 4, 6)])
    for crop in (auto, value_img):
        if crop.width <= 2 or crop.height <= 4:
            continue
        for scale in (1, 2, 4):
            variants.append((_auto_binarise(crop), scale, 6))
        variants.append((_auto_binarise(crop), 4, 7))
        variants.append((_auto_binarise(crop), 4, 8))
        variants.append((_masked_grey(crop), 4, 7))
        variants.append((crop, 4, 7))
    tight = _tight(value_img, 110)
    if tight.width > 2 and tight.height > 4:
        for thr in (110, 130):
            variants.append((_binarise(tight, thr), 4, 7))
        variants.append((_binarise(tight, 130), 4, 8))

    texts = []
    for img, scale, psm in variants:
        try:
            texts.append(_ocr(img, psm, '0123456789.,%+-', scale=scale))
        except Exception:
            pass
    if verbose is not None:
        verbose.extend(texts)

    # a flat stat cell may belong to its % version (the '%' shows up in the value)
    stats = [stat] if stat not in ('ATK', 'HP', 'DEF') else [stat, stat + '%']

    def achievable_value(val: float) -> bool:
        if any(match_roll_sum(s, val) is not None for s in stats if s):
            return True
        # a main stat is not a roll total, but it is one of a few known numbers
        return any(abs(val - mv) <= max(0.35, 0.02 * mv) for mv in (main_values or []))

    votes: dict[float, float] = {}
    for text in texts:
        has_pct = '%' in text
        for val, _pct, quality in _candidates(text):
            achievable = achievable_value(val)
            score = 1.0 + 3.0 * quality
            if achievable:
                score += 4.0
            if has_pct:
                score += 2.0
            votes[val] = votes.get(val, 0.0) + score
    if not votes:
        return None, False
    best = max(votes.items(), key=lambda kv: (kv[1], len(f'{kv[0]:g}')))[0]
    pct_seen = any('%' in t for t in texts)
    return best, pct_seen


def _candidates(text: str) -> list[tuple[float, bool, float]]:
    """All plausible (value, followed-by-%, quality) readings of an OCR'd value cell.

    quality says how trustworthy the reading is: an intact token beats a repaired
    one (lost/spurious decimal point), which beats a token with junk chopped off
    its front - otherwise the repaired variants outvote the real number."""
    cleaned = text.replace(' ', '').replace('O', '0').replace('o', '0').replace('S', '5')
    out: list[tuple[float, bool, float]] = []
    best_quality: dict[float, float] = {}
    for m in _NUM_RE.finditer(cleaned):
        tok = m.group(0).replace(',', '.')
        pct = cleaned[m.end():m.end() + 1] == '%'
        variants = [(tok, 1.0)]
        if '.' not in tok and len(tok) >= 2:        # '86%' is really '8.6%'
            variants.append((tok[:-1] + '.' + tok[-1], 0.6))
        elif '.' in tok and len(tok.split('.')[0]) >= 2:   # '86.0%' is really '8.6%'
            variants.append((tok.replace('.', ''), 0.6))
        for cut in range(1, 3):
            if cut < len(tok):
                variants.append((tok[cut:], 0.3))
        for variant, quality in variants:
            try:
                v = float(variant)
            except ValueError:
                continue
            if not (0 < v <= 200):
                continue
            if best_quality.get(v, 0) < quality:
                best_quality[v] = quality
    for v, q in best_quality.items():
        out.append((v, True, q))
    return out


def parse_value(text: str, stat: str | None = None) -> float | None:
    """Pick the number in an OCR'd value cell, repairing common misreads
    ('112.9%' for '12.9%', '-..12.9%' for '12.9%')."""
    cleaned = text.replace(' ', '').replace('O', '0').replace('o', '0')
    tokens = [(m.start(), m.group(0)) for m in _NUM_RE.finditer(cleaned)]
    if not tokens:
        return None
    pct = [t for t in tokens if cleaned[t[0] + len(t[1]):][:1] == '%']
    order = pct + [t for t in tokens if t not in pct]
    for _pos, tok in order:
        cand = tok.replace(',', '.')
        for cut in range(0, 3):
            if cut >= len(cand):
                break
            try:
                v = float(cand[cut:])
            except ValueError:
                continue
            if _plausible(stat, v):
                return v
    v = float(order[-1][1].replace(',', '.'))
    return v if v > 0 else None


# --------------------------------------------------------------------------- #
# relic piece table
# --------------------------------------------------------------------------- #
_PIECES: dict | None = None


def pieces() -> dict:
    global _PIECES
    if _PIECES is None:
        with open(os.path.join(DATA, 'relic_pieces.json'), encoding='utf8') as f:
            _PIECES = json.load(f)
    return _PIECES


def _best_piece(name: str) -> tuple[dict | None, float]:
    n = _norm(name)
    if len(n) < 6:
        return None, 0.0
    best, best_r = None, 0.0
    for piece, info in pieces()['pieces'].items():
        r = SequenceMatcher(None, n, _norm(piece)).ratio()
        if r > best_r:
            best, best_r = {'piece': piece, **info}, r
    return best, best_r


def match_piece(name: str, threshold: float = 0.72) -> dict | None:
    best, r = _best_piece(name)
    return best if best and r >= threshold else None


def match_piece_any(names: list[str], threshold: float = 0.72) -> dict | None:
    """Best piece match over several OCR readings of the same header."""
    best, best_r = None, 0.0
    for name in names:
        cand, r = _best_piece(name)
        if cand and r > best_r:
            best, best_r = cand, r
    return best if best and best_r >= threshold else None


def match_set(text: str) -> str | None:
    n = _norm(text)
    if len(n) < 5:
        return None
    best, best_r = None, 0.0
    for s in pieces()['sets']:
        r = SequenceMatcher(None, n, _norm(s)).ratio()
        if r > best_r:
            best, best_r = s, r
    return best if best_r >= 0.8 else None


# --------------------------------------------------------------------------- #
# public API
# --------------------------------------------------------------------------- #
def parse_relic_image(source, raw_lines: list | None = None) -> dict:
    """OCR a relic screenshot -> {set, piece, part, level, grade, mainStat,
    mainValue, substats, warnings}. `source` is a path or any binary stream."""
    im = Image.open(source)
    if im.mode != 'RGB':
        im = im.convert('RGB')

    mask = _text_mask(im)
    bands = _bands(mask)
    h_img, w_img = mask.shape

    rows = []
    for (y0, y1) in bands:
        label_img, value_img = _split_label_value(im, mask[y0:y1], y0, y1)
        label = _ocr(label_img, 7)
        stat = match_stat(label)
        if stat is None:
            # highlighted/dim row, or the crop is mostly background sparkle:
            # re-crop to the glyphs with an adaptive threshold and retry
            trimmed = _auto_tight(label_img)
            for candidate in (_ocr(trimmed, 7), _ocr(trimmed, 6),
                              _ocr(_auto_binarise(trimmed), 7),
                              _ocr(_auto_binarise(trimmed), 6)):
                if match_stat(candidate) is not None:
                    label, stat = candidate, match_stat(candidate)
                    break
                if not label.strip() and candidate.strip():
                    label = candidate
        if not label.strip():                       # dimmer chrome (slot line etc.)
            label = _ocr(_binarise(im.crop((0, y0, int(w_img * 0.6), y1)), 95), 7)
            stat = stat or match_stat(label)
        raw_texts: list[str] = []
        value, pct = (None, False)
        if stat:
            value, pct = read_value(value_img, stat, raw_texts)
            # a '%' in the value cell means the flat stat is really its % version
            if pct and stat in ('ATK', 'HP', 'DEF'):
                stat += '%'
        rows.append({'y0': y0, 'y1': y1, 'label': label.strip(), 'stat': stat,
                     'value_raw': ' | '.join(raw_texts), 'value': value, 'pct': pct,
                     'value_img': value_img})
    if raw_lines is not None:
        raw_lines.extend(rows)

    relic = {'set': None, 'piece': None, 'part': None, 'level': None, 'grade': 5,
             'mainStat': None, 'mainValue': None, 'mainRead': None, 'substats': [],
             'warnings': []}

    # ---- classify rows: a stat row needs a recognisable name + a valid number ----
    stat_rows = []
    for r in rows:
        stat = r['stat']
        val = r['value']
        if stat and val is not None:
            stat_rows.append({'y0': r['y0'], 'stat': stat, 'value': val,
                              'raw': r['value_raw'], 'value_img': r.get('value_img')})

    first_stat_y = stat_rows[0]['y0'] if stat_rows else h_img

    # ---- header: piece name / slot / level, read as one block with sparse text ----
    hdr_img = im.crop((0, 0, w_img, max(8, first_stat_y)))
    header_text = []
    if hdr_img.height >= 8:
        for thr in (130, 150):
            for scale in (3, 2):
                header_text.append(_ocr(_binarise(hdr_img, thr), 11, scale=scale))
        header_text.append(_ocr(_auto_binarise(hdr_img), 11, scale=3))
        header_text.append(_ocr(hdr_img, 6, target_px=60))
    header_text = [t for t in header_text if t.strip()]
    joined = ' '.join(header_text)

    piece = match_piece_any(header_text)
    if piece:
        relic['piece'] = piece['piece']
        relic['set'] = piece['set']
        relic['part'] = piece['slot']

    if not relic['part']:
        hn = _norm(joined)
        for word, slot in _SLOT_WORDS.items():
            if word in hn:
                relic['part'] = slot
                break
    if not relic['set']:
        relic['set'] = match_set(joined)

    relic['level'] = _read_level(header_text)

    # ---- main stat + substats ----
    if stat_rows:
        relic['mainStat'] = stat_rows[0]['stat']
        # the main stat is one of a handful of known numbers: re-read the cell
        # knowing the main-stat table so a partial read ('5' for '25') loses
        main_values = list((_main_table().get(stat_rows[0]['stat']) or {}).values())
        if main_values and stat_rows[0].get('value_img') is not None:
            better, _pct = read_value(stat_rows[0]['value_img'], stat_rows[0]['stat'],
                                      main_values=[float(v) for v in main_values])
            if better is not None:
                stat_rows[0]['value'] = better
        relic['mainRead'] = stat_rows[0]['value']       # exactly what the card shows
        relic['grade'], relic['mainValue'] = _resolve_main(stat_rows[0]['stat'],
                                                          stat_rows[0]['value'],
                                                          relic['level'])
        for r in stat_rows[1:]:
            relic['substats'].append({'stat': r['stat'], 'value': r['value']})

    if not relic['part']:
        relic['warnings'].append('Could not read the relic slot')
    if not relic['mainStat']:
        relic['warnings'].append('Could not read the main stat')
    if len(relic['substats']) < 2:
        relic['warnings'].append('Read fewer than 2 substats')
    return relic


def _read_level(header_text: list[str]) -> int | None:
    """The '+15' line OCRs as '+15', '#15' or '415' depending on the pass."""
    for text in header_text:                       # explicit +N wins
        for m in re.finditer(r'[+\uFF0B#tT]\s*(\d{1,2})\b', text):
            v = int(m.group(1))
            if 1 <= v <= 15:
                return v
    cands = []
    for text in header_text:
        letters = len(re.findall(r'[A-Za-z]', text))
        for tok in re.findall(r'\d+', text):
            for n in (tok, tok[-2:] if len(tok) == 3 else ''):
                if not n:
                    continue
                v = int(n)
                if 1 <= v <= 15:
                    cands.append((letters, abs(len(tok) - len(n)), v))
    if not cands:
        return None
    cands.sort()
    return cands[0][2]


MAX_ENHANCE = {5: 15, 4: 12, 3: 9, 2: 6}


def _resolve_main(main_stat: str, value: float | None,
                  level: int | None = None) -> tuple[int, float | None]:
    """Infer the relic grade and snap the main value onto the exact table value.

    A main stat is a fixed number for (stat, grade, level), so a close read is
    snapped; a read that lost its decimal point ('3.2' for '32.4') is rescaled."""
    if value is None:
        return 5, None
    per = _main_table().get(main_stat)
    if not per:
        return 5, value
    per = {int(k): float(v) for k, v in per.items()}
    best = None
    for cand in (value, value * 10):
        for g, tv in per.items():
            d = abs(tv - cand)
            if best is None or d < best[0]:
                best = (d, g, tv)
    d, g, tv = best
    if tv and d <= max(0.35, 0.03 * tv):
        if level is None or level >= MAX_ENHANCE.get(g, 15):
            return g, round(tv, 4)
        return g, value
    return 5, value


_MAIN_TABLE: dict | None = None


def _main_table() -> dict:
    global _MAIN_TABLE
    if _MAIN_TABLE is None:
        try:
            with open(os.path.join(DATA, 'main_stats_max.json'), encoding='utf8') as f:
                _MAIN_TABLE = json.load(f)
        except OSError:
            _MAIN_TABLE = {}
    return _MAIN_TABLE


def _infer_grade(main_stat: str, value: float | None) -> int:
    if value is None:
        return 5
    try:
        with open(os.path.join(DATA, 'main_stats_max.json'), encoding='utf8') as f:
            table = json.load(f)
    except OSError:
        return 5
    per = table.get(main_stat)
    if not per:
        return 5
    best, best_diff = 5, 1e9
    for g, v in per.items():
        d = abs(float(v) - value)
        if d < best_diff:
            best, best_diff = int(g), d
    return best if best_diff < max(1.0, 0.03 * value) else 5
