"""Exercise published NTi, Noise Sentry and SVAN imports in the installed runtime."""
import argparse
from pathlib import Path
import subprocess
import sys
import tempfile

import numpy as np
import pandas as pd

parser = argparse.ArgumentParser()
parser.add_argument('release', type=Path)
args = parser.parse_args()
sys.path.insert(0, str(args.release / 'Noise Survey Analysis'))
sys.path.insert(0, str(args.release / 'SLM Parsers' / 'src'))
sys.path.insert(0, str(args.release / 'SLM Parsers' / 'src' / 'Svan'))
from noise_survey_analysis.core.data_parsers import NTiFileParser, NoiseSentryFileParser
from Svan.readSvan import process_svan_file
from Svan.process_svan958a import process_svan958a_directory

root = Path(tempfile.mkdtemp(prefix='Venta parser smoke '))
data = pd.DataFrame({
    'Time (Date hh:mm:ss.ms)': pd.date_range('2026-10-01 09:00', periods=121, freq='min'),
    'LEQ dB-A': np.full(121, 45.0),
    'Lmax dB-A': np.full(121, 55.0),
})
for extension in ('csv', 'xlsx'):
    source = root / f'noise-sentry.{extension}'
    if extension == 'csv':
        data.to_csv(source, index=False)
    else:
        data.to_excel(source, index=False)
    result = subprocess.run([
        sys.executable, str(args.release / 'SLM Parsers/src/process_files.py'), str(source),
        '--no-pause', '--no-prompt', '--start', '2026-10-01 09:00:00', '--end', '2026-10-01 11:00:00',
    ], capture_output=True, text=True)
    if result.returncode:
        raise AssertionError(result.stdout + result.stderr)
    output = root / 'noise-sentry_summary.csv'
    if not output.exists():
        raise AssertionError(f'Missing parser output: {list(root.iterdir())}')
    values = pd.read_csv(output)
    assert len(values) > 0 and np.isclose(values['LEQ dB-A'].dropna(), 45.0).all(), values
    parsed = NoiseSentryFileParser().parse(str(output))
    assert parsed.totals_df is not None and not parsed.totals_df.empty, parsed.metadata
    for path in root.glob('noise-sentry*_log.csv'):
        path.unlink()
    output.unlink()
    print(f'PASS: Noise Sentry {extension} -> summary -> dashboard parser')

nti = root / '2026-10-01_SLM_001_123_Rpt_Report.txt'
nti.write_text(
    '# Hardware Configuration\nSerial Number: TEST\n# Measurement Setup\n'
    '# Broadband Results\nDate\tTime\tLAeq\tLAFmax\tLAF90\n'
    '2026-10-01\t09:00:00\t45\t55\t40\n'
    '2026-10-01\t09:05:00\t46\t56\t41\n', encoding='utf-8')
parsed = NTiFileParser().parse(str(nti))
assert parsed.totals_df is not None and len(parsed.totals_df) == 2, parsed.metadata
assert parsed.totals_df['LAeq'].tolist() == [45, 46]
print('PASS: NTi report -> dashboard parser; SVAN 971/958A entry points import')
print(f'Synthetic fixtures: {root}')
