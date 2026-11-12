"""Local web UI for the HSR relic grader.

    python ui/app.py                 # plain UI, opens your browser
    python ui/app.py --ui v2         # V2: the character's art behind the grader
    python ui/app.py --port 8800     # pick a port
    python ui/app.py --no-browser    # just serve

Both layouts are always reachable: ``/`` serves the chosen one, ``/v1/`` and
``/v2/`` always serve theirs.

Only stdlib + the packages the grader already needs (Pillow, numpy) - no server
framework. Everything runs on 127.0.0.1; nothing leaves the machine.
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import os
import socket
import sys
import threading
import urllib.error
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from relic_grades.characters import characters, find_character  # noqa: E402
from relic_grades.fribbels import RATING_TIERS  # noqa: E402
from relic_grades.grade import grade_image, grade_payload  # noqa: E402

STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')
ART = os.path.join(STATIC, 'art')
CONTENT_TYPES = {'.html': 'text/html; charset=utf-8', '.css': 'text/css; charset=utf-8',
                 '.js': 'application/javascript; charset=utf-8', '.ico': 'image/x-icon',
                 '.png': 'image/png', '.svg': 'image/svg+xml',
                 '.webp': 'image/webp'}

# V2 shows one WebP per character. It is HoYoverse's art, so it is not shipped in
# the repo - tools/fetch_character_art.py fills this folder, and a request for a
# character we do not have yet fetches just that one file.
ART_URL = ('https://raw.githubusercontent.com/fribbels/hsr-optimizer/main/'
           'public/assets/image/character_preview/{id}.webp')
DEFAULT_UI = 'v1'
INDEX_FOR = {'v1': 'index.html', 'v2': 'v2/index.html'}


# --------------------------------------------------------------------------- #
# grading
# --------------------------------------------------------------------------- #
def character_list() -> list[dict]:
    """Alphabetical (case-insensitive) list, one entry per name."""
    seen, out = set(), []
    for cid, c in characters().items():
        name = c['name']
        if name.lower() in seen:
            continue
        seen.add(name.lower())
        entry = {'id': cid, 'name': name, 'element': c.get('element'),
                 'path': c.get('path'), 'rarity': c.get('rarity')}
        if os.path.isfile(os.path.join(ART, f'{cid}.webp')):
            entry['art'] = f'/art/{cid}.webp'
        out.append(entry)
    out.sort(key=lambda c: (c['name'].lower(), c['id']))
    return out


# --------------------------------------------------------------------------- #
# character art (V2)
# --------------------------------------------------------------------------- #
def art_path(cid: str, allow_fetch: bool = True) -> str | None:
    """Local path to a character's art, downloading just that file if needed."""
    path = os.path.join(ART, f'{cid}.webp')
    if os.path.isfile(path):
        return path
    if not allow_fetch:
        return None
    req = urllib.request.Request(ART_URL.format(id=cid),
                                headers={'User-Agent': 'hsr-relic-grader-ui'})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            blob = r.read()
    except (urllib.error.URLError, OSError, TimeoutError):
        return None
    if not blob.startswith(b'RIFF') or b'WEBP' not in blob[:16]:
        return None
    os.makedirs(ART, exist_ok=True)
    with open(path, 'wb') as f:
        f.write(blob)
    return path


def resolve_character(query: str) -> dict | None:
    """Accept an id, or a name (fuzzy, same resolver the grader uses)."""
    query = (query or '').strip()
    if not query:
        return None
    try:
        return find_character(query)
    except ValueError:
        return None


def handle_score(body: dict) -> dict:
    data = body.get('image') or ''
    if ',' in data[:64]:
        data = data.split(',', 1)[1]
    try:
        blob = base64.b64decode(data, validate=False)
    except Exception:
        raise ValueError('could not read the pasted image')
    if not blob:
        raise ValueError('no image received')
    return grade_image(io.BytesIO(blob), body.get('character') or '')


def handle_rescore(body: dict) -> dict:
    """Re-grade an already parsed relic for another character (no OCR)."""
    relic = body.get('relic') or {}
    needed = ('part', 'mainStat', 'mainValue', 'substats', 'grade')
    if any(k not in relic for k in needed):
        raise ValueError('relic data missing')
    return grade_payload(relic, body.get('character') or '')


# --------------------------------------------------------------------------- #
# server
# --------------------------------------------------------------------------- #
class Handler(BaseHTTPRequestHandler):
    server_version = 'RelicGraderUI/1.0'
    protocol_version = 'HTTP/1.1'

    def log_message(self, fmt, *args):        # keep the console readable
        if 'api/score' in (self.path or '') or 'api/rescore' in (self.path or ''):
            sys.stderr.write('  %s\n' % (fmt % args))

    # ---- helpers ----
    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code: int = 200) -> None:
        self._send(code, json.dumps(obj).encode('utf-8'), 'application/json; charset=utf-8')

    def _static(self, rel: str) -> None:
        path = os.path.normpath(os.path.join(STATIC, rel.lstrip('/')))
        if not path.startswith(STATIC) or not os.path.isfile(path):
            self._send(404, b'not found', 'text/plain; charset=utf-8')
            return
        with open(path, 'rb') as f:
            body = f.read()
        ctype = CONTENT_TYPES.get(os.path.splitext(path)[1], 'application/octet-stream')
        self._send(200, body, ctype)

    # ---- routes ----
    def do_GET(self):
        parsed = urlparse(self.path)
        route = parsed.path
        if route == '/api/characters':
            self._json({'characters': character_list(),
                        'tiers': [t[1] for t in RATING_TIERS]})
            return
        if route == '/api/art':
            self._art(parse_qs(parsed.query))
            return
        if route in ('/', '/index.html'):
            self._static(INDEX_FOR[DEFAULT_UI])
            return
        if route.rstrip('/') in ('/v1', '/v2'):
            self._static(INDEX_FOR[route.rstrip('/')[1:]])
            return
        self._static(route)

    def _art(self, params: dict) -> None:
        """Which art file belongs to a character - fetching it once if needed."""
        query = (params.get('id') or params.get('character') or [''])[0]
        found = resolve_character(query)
        if not found:
            self._json({'error': 'unknown character', 'hint': 'pick one from the list'}, 404)
            return
        path = art_path(found['id'])
        if not path:
            self._json({'error': 'no art for this character',
                        'hint': 'run  python tools/fetch_character_art.py',
                        'id': found['id'], 'name': found['name']}, 404)
            return
        self._json({'id': found['id'], 'name': found['name'],
                    'url': f"/art/{found['id']}.webp"})

    def do_POST(self):
        route = urlparse(self.path).path
        try:
            length = int(self.headers.get('Content-Length') or 0)
            body = json.loads(self.rfile.read(length) or b'{}')
        except (ValueError, TypeError):
            self._json({'error': 'bad request body'}, 400)
            return
        try:
            if route == '/api/score':
                self._json(handle_score(body))
            elif route == '/api/rescore':
                self._json(handle_rescore(body))
            else:
                self._json({'error': 'unknown route'}, 404)
        except ValueError as e:
            self._json({'error': str(e)}, 400)
        except Exception as e:                    # keep the UI alive on surprises
            self._json({'error': f'{type(e).__name__}: {e}'}, 500)


def free_port(preferred: int = 8770) -> int:
    for p in (preferred, 0):
        with socket.socket() as s:
            try:
                s.bind(('127.0.0.1', p))
                return s.getsockname()[1]
            except OSError:
                continue
    return 0


def open_browser(url: str) -> None:
    """Prefer an app-style window (Edge/Chrome) so it feels like a native tool."""
    for exe in (r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',
                r'C:\Program Files\Microsoft\Edge\Application\msedge.exe',
                r'C:\Program Files\Google\Chrome\Application\chrome.exe',
                r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe'):
        if os.path.isfile(exe):
            try:
                import subprocess
                subprocess.Popen([exe, f'--app={url}', '--window-size=1280,900'])
                return
            except OSError:
                break
    webbrowser.open(url)


def main() -> None:
    global DEFAULT_UI
    ap = argparse.ArgumentParser(description='HSR relic grader UI')
    ap.add_argument('--port', type=int, default=8770)
    ap.add_argument('--no-browser', action='store_true')
    ap.add_argument('--ui', choices=('v1', 'v2'), default='v1',
                    help='which layout / serves (v2 = character art background)')
    args = ap.parse_args()
    DEFAULT_UI = args.ui

    port = free_port(args.port)
    httpd = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    url = f'http://127.0.0.1:{port}/'
    art = len([f for f in os.listdir(ART) if f.endswith('.webp')]) if os.path.isdir(ART) else 0
    print(f'HSR relic grader UI running at {url}   [{DEFAULT_UI.upper()}]')
    print(f'  {len(character_list())} characters loaded.  Ctrl-C to stop.')
    if DEFAULT_UI == 'v2':
        print(f'  character art on disk: {art}'
              + ('' if art else '  (run: python tools/fetch_character_art.py)'))
        print(f'  plain layout at {url}v1/')
    if not args.no_browser:
        threading.Timer(0.6, open_browser, args=(url,)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print('\nstopped')
    finally:
        httpd.server_close()


if __name__ == '__main__':
    main()
