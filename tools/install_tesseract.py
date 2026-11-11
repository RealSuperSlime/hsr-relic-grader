"""Bundle a portable Tesseract into vendor/tesseract (Windows, no admin needed).

    python tools/install_tesseract.py

Thin wrapper around relic_grades.tesseract_setup, which is also exposed after a
pip install as the `hsr-relic-grader-tesseract` command.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from relic_grades.tesseract_setup import main  # noqa: E402

if __name__ == '__main__':
    sys.exit(main())
