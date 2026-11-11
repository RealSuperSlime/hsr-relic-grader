"""Local web UI for the HSR relic grader.

    python ui/app.py                 # starts the server and opens your browser
    python ui/app.py --port 8800     # pick a port
    python ui/app.py --no-browser    # just serve

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
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from relic_grades.characters import characters  # noqa: E402
from relic_grades.fribbels import RATING_TIERS  # noqa: E402
from relic_grades.grade import grade_image, grade_payload  # noqa: E402

STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')
CONTENT_TYPES = {'.html': 'text/html; charset=utf-8', '.css': 'text/css; charset=utf-8',
                 '.js': 'application/javascript; charset=utf-8', '.ico': 'image/x-icon',
                 '.png': 'image/png', '.svg': 'image/svg+xml'}


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
        out.append({'id': cid, 'name': name, 'element': c.get('element'),
                    'path': c.get('path'), 'rarity': c.get('rarity')})
    out.sort(key=lambda c: (c['name'].lower(), c['id']))
    return out


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
        route = urlparse(self.path).path
        if route == '/api/characters':
            self._json({'characters': character_list(),
                        'tiers': [t[1] for t in RATING_TIERS]})
            return
        if route in ('/', '/index.html'):
            self._static('index.html')
            return
        self._static(route)

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
    ap = argparse.ArgumentParser(description='HSR relic grader UI')
    ap.add_argument('--port', type=int, default=8770)
    ap.add_argument('--no-browser', action='store_true')
    args = ap.parse_args()

    port = free_port(args.port)
    httpd = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    url = f'http://127.0.0.1:{port}/'
    print(f'HSR relic grader UI running at {url}')
    print(f'  {len(character_list())} characters loaded.  Ctrl-C to stop.')
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
