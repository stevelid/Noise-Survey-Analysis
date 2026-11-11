"""Check native imports and every pinned version without PowerShell -c quoting."""
import argparse
import importlib
import importlib.metadata
import struct
import sys
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--requirements', type=Path)
args = parser.parse_args()
if sys.version_info[:2] != (3, 13) or struct.calcsize('P') != 8:
    raise SystemExit('Python 3.13 x64 is required.')
for module in ('bokeh', 'pandas', 'numpy', 'scipy', 'soundfile', 'openpyxl', 'pytz', 'xlrd', 'tzdata', 'vlc'):
    importlib.import_module(module)
import vlc
vlc.libvlc_get_version()
if args.requirements:
    for row in args.requirements.read_text(encoding='utf-8-sig').splitlines():
        if not row.strip() or row.lstrip().startswith('#'):
            continue
        name, expected = row.strip().split('==')
        actual = importlib.metadata.version(name)
        if actual != expected:
            raise SystemExit(f'{name}: expected {expected}, found {actual}')
print('All runtime imports and pinned package versions passed.')
