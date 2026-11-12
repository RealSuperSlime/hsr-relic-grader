"""Create Start-menu shortcuts so the grader and the bot are searchable Windows apps.

Run once (or again after moving the folder):

    python tools/create_shortcuts.py
"""
from __future__ import annotations

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PYTHON = os.path.join(ROOT, '.venv', 'Scripts', 'python.exe')

# name, what it runs, description
SHORTCUTS = [
    ('HSR Relic Grader', os.path.join(ROOT, 'run_ui.bat'),
     'Grade HSR relics: pick a character, paste a screenshot'),
    ('HSR Relic Grader V2', os.path.join(ROOT, 'run_ui_v2.bat'),
     "Grade HSR relics with the character's art behind the grader"),
    ('HSR Relic Grader Bot', os.path.join(ROOT, 'discord_bot', 'start_bot.bat'),
     'Run the HSR relic grader Discord bot'),
    ('HSR Relic Grader (CLI)', os.path.join(ROOT, 'run.bat'),
     'Grade HSR relics from the command line'),
]


def powershell(script: str) -> subprocess.CompletedProcess:
    return subprocess.run(['powershell', '-NoProfile', '-NonInteractive', '-Command', script],
                          capture_output=True, text=True)


def main() -> int:
    if os.name != 'nt':
        print('Windows only.')
        return 1
    missing = [t for _n, t, _d in SHORTCUTS if not os.path.isfile(t)]
    if missing:
        print('Missing launcher files:', *missing, sep='\n  ')
        return 1

    made = []
    for name, target, desc in SHORTCUTS:
        # user-level Start menu: appears in Windows search, no admin needed
        # ($env:APPDATA is PowerShell syntax - %APPDATA% would be taken literally)
        icon = PYTHON if os.path.isfile(PYTHON) else target
        script = (
            f'$w = New-Object -ComObject WScript.Shell; '
            f'$lnk = Join-Path $env:APPDATA ("Microsoft\\Windows\\Start Menu\\Programs\\'
            f'{name}.lnk"); '
            f'$s = $w.CreateShortcut($lnk); '
            f'$s.TargetPath = "{target}"; '
            f'$s.WorkingDirectory = "{os.path.dirname(target)}"; '
            f'$s.IconLocation = "{icon},0"; '
            f'$s.Description = "{desc}"; '
            f'$s.Save(); '
            f'Write-Output $s.FullName'
        )
        res = powershell(script)
        out = (res.stdout or '').strip()
        if res.returncode == 0 and out:
            made.append(out)
            print('created:', out)
        else:
            print('failed :', name, (res.stderr or '').strip()[:200])
    print(f'\n{len(made)} shortcut(s) installed. Press the Windows key and type "HSR" to find them.')
    return 0 if made else 1


if __name__ == '__main__':
    sys.exit(main())
