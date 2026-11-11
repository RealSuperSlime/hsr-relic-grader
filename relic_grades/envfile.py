"""Minimal .env reader - standard library only, no python-dotenv needed.

    from relic_grades.envfile import load_env
    load_env()                      # reads <project root>/.env

Rules (the subset that matters for this project):

* ``KEY=value``, one per line. Blank lines and ``#`` comments are ignored.
* A leading ``export `` is allowed, so the file can also be ``source``d.
* Values may be wrapped in matching single or double quotes; inside double
  quotes ``\\n``, ``\\t``, ``\\"`` and ``\\\\`` are unescaped.
* An unquoted value is cut at a `` #`` inline comment.
* Windows files are handled: CRLF, trailing whitespace and a UTF-8 BOM are all
  fine, so the .env can be edited in Notepad and still parse.
* Real environment variables always win unless ``override=True``, so an
  exported DISCORD_BOT_TOKEN beats the file.
"""
from __future__ import annotations

import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_ENV = os.path.join(PROJECT_ROOT, '.env')


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
        quote, inner = value[0], value[1:-1]
        if quote == "'":
            return inner                                   # single quotes are literal
        out, i = [], 0
        escapes = {'n': '\n', 't': '\t', 'r': '\r', '"': '"', '\\': '\\'}
        while i < len(inner):
            ch = inner[i]
            if ch == '\\' and i + 1 < len(inner) and inner[i + 1] in escapes:
                out.append(escapes[inner[i + 1]])
                i += 2
            else:
                out.append(ch)
                i += 1
        return ''.join(out)
    # unquoted: strip an inline comment (" #..." or "\t#...")
    for i, ch in enumerate(value):
        if ch == '#' and i > 0 and value[i - 1] in ' \t':
            return value[:i].rstrip()
    return value


def parse_env(text: str) -> dict[str, str]:
    """Parse .env text into a dict. Never raises on a malformed line."""
    result: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip().lstrip('\ufeff')
        if not line or line.startswith('#'):
            continue
        if line.startswith('export ') or line.startswith('export\t'):
            line = line[7:].lstrip()
        if '=' not in line:
            continue
        key, _, value = line.partition('=')
        key = key.strip()
        if not key.isidentifier():
            continue
        result[key] = _unquote(value.strip())
    return result


def load_env(path: str | None = None, *, override: bool = False) -> dict[str, str]:
    """Load a .env file into os.environ. Returns only the keys it applied.

    Existing environment variables are left alone unless ``override=True``.
    A missing file is not an error - it just returns ``{}``.
    """
    path = path or DEFAULT_ENV
    if not os.path.isfile(path):
        return {}
    with open(path, encoding='utf-8-sig') as f:
        parsed = parse_env(f.read())
    applied = {}
    for key, value in parsed.items():
        if override or key not in os.environ:
            os.environ[key] = value
            applied[key] = value
    return applied
