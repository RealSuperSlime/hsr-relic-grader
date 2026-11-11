"""Where the bundled data tables live.

Resolution order:

1. ``$RELIC_DATA_DIR`` - an explicit override, for tests or odd layouts.
2. ``relic_grades/data/`` - the packaged copy. This is what a ``pip install``
   sees, and what this repository ships.
3. ``<project root>/data/`` - the older layout, kept so an existing checkout
   keeps working.
"""
from __future__ import annotations

import os

PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(PACKAGE_DIR)
_CANDIDATES = (
    os.path.join(PACKAGE_DIR, 'data'),
    os.path.join(PROJECT_ROOT, 'data'),
)


#: Fallback home for a downloaded Tesseract when there is no repo checkout to
#: put it in - e.g. after `pip install hsr-relic-grader`.
USER_TESSERACT_DIR = os.path.join(
    os.environ.get('LOCALAPPDATA') or os.path.expanduser('~'),
    'hsr-relic-grader', 'tesseract')


def data_dir() -> str:
    """Absolute path to the folder holding the .json tables."""
    override = os.environ.get('RELIC_DATA_DIR')
    if override and os.path.isdir(override):
        return override
    for candidate in _CANDIDATES:
        if os.path.isdir(candidate):
            return candidate
    return _CANDIDATES[0]
