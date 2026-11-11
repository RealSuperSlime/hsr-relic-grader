"""Download a portable Tesseract so OCR works - Windows, no admin needed.

    hsr-relic-grader-tesseract           # after `pip install hsr-relic-grader`
    python tools/install_tesseract.py    # from a repo checkout

Downloads the UB-Mannheim build and unpacks it with 7-Zip (7z.exe), so nothing
is installed system-wide and no installer/UAC prompt appears. Without 7-Zip,
install Tesseract-OCR normally instead - the grader also looks it up on PATH,
in Program Files, and at $RELIC_TESSERACT.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request

from .paths import PROJECT_ROOT, USER_TESSERACT_DIR

URL = ('https://github.com/UB-Mannheim/tesseract/releases/download/'
       'v5.4.0.20240606/tesseract-ocr-w64-setup-5.4.0.20240606.exe')

SEVEN_ZIPS = [
    r'C:\Program Files\7-Zip\7z.exe',
    r'C:\Program Files (x86)\7-Zip\7z.exe',
]


def default_dest() -> str:
    """A repo checkout keeps its bundle in vendor/; an installed package cannot
    write there, so it uses a per-user folder instead."""
    vendor = os.path.join(PROJECT_ROOT, 'vendor')
    if os.path.isdir(vendor):
        return os.path.join(vendor, 'tesseract')
    return USER_TESSERACT_DIR


def find_7z() -> str | None:
    for p in SEVEN_ZIPS + [shutil.which('7z') or '', shutil.which('7za') or '']:
        if p and os.path.isfile(p):
            return p
    return None


def extract_with_7z(exe: str, dest: str) -> bool:
    seven = find_7z()
    if not seven:
        return False
    subprocess.run([seven, 'x', exe, '-o' + dest, '-y'], check=False,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return os.path.isfile(os.path.join(dest, 'tesseract.exe'))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description='Bundle a portable Tesseract.')
    ap.add_argument('--dest', default=None, help='where to unpack it')
    args = ap.parse_args(argv)
    dest = args.dest or default_dest()

    if os.path.isfile(os.path.join(dest, 'tesseract.exe')):
        print('Tesseract already bundled at', dest)
        return 0
    os.makedirs(dest, exist_ok=True)
    tmp = os.path.join(tempfile.gettempdir(), 'tesseract-setup.exe')
    if not os.path.isfile(tmp):
        print('Downloading', URL)
        urllib.request.urlretrieve(URL, tmp)
    if extract_with_7z(tmp, dest):
        print('Bundled Tesseract at', dest)
        return 0
    print('Could not unpack the installer automatically: 7-Zip (7z.exe) is required.\n'
          'Options:\n'
          '  1) install 7-Zip, then re-run this command, or\n'
          '  2) install Tesseract-OCR normally (https://github.com/UB-Mannheim/tesseract)\n'
          '     -- the grader also looks it up on PATH and in Program Files.')
    return 1


if __name__ == '__main__':
    sys.exit(main())
