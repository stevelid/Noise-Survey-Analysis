"""Benchmark first-time (parse-cache MISS) loading of survey logs.

Parses every position of a noise_survey_config_*.json through the real parser and the
real DataManager lazy-load path with the parsed-data cache DISABLED, then prints per-file
parse time, merge time, peak memory and rows. It also writes a fingerprint of the merged
frames so a later run can prove the results are unchanged.

Usage (from the repo root):
    python tools/benchmark_parsing.py CONFIG.json [--positions 6645-4,6645-5A]
        [--save-fingerprint base.json] [--compare base.json] [--cprofile]

Source files are only read, never written.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import logging
import os
import re
import sys
import time
import tracemalloc

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

try:
    import psutil  # noqa: E402
except ImportError:  # pragma: no cover
    psutil = None

from noise_survey_analysis.core.data_manager import DataManager  # noqa: E402
from noise_survey_analysis.core.data_parsers import NoiseParserFactory  # noqa: E402

PERF_RE = re.compile(r"\[LAZY LOAD PERF\] position=(\S+) file=(\S+) cache=\S+ .*?parse_ms=([\d.]+) merge_ms=([\d.]+)")


class _PerfCapture(logging.Handler):
    def __init__(self):
        super().__init__(level=logging.INFO)
        self.rows = []

    def emit(self, record):
        m = PERF_RE.search(record.getMessage())
        if m:
            self.rows.append((m.group(1), m.group(2), float(m.group(3)), float(m.group(4))))


def load_source_configs(config_path, positions=None):
    with open(config_path, 'r', encoding='utf-8-sig') as fh:
        cfg = json.load(fh)
    base = cfg.get('config_base_path') or os.path.dirname(config_path)
    out = []
    for src in cfg['sources']:
        pos = src.get('position') or src.get('position_name')
        if positions and pos not in positions:
            continue
        path = src.get('path') or src.get('file_path')
        if not os.path.isabs(path):
            path = os.path.join(base, path)
        out.append({
            'position_name': pos, 'file_path': os.path.normpath(path),
            'parser_type': src.get('parser_type'), 'enabled': src.get('enabled', True),
        })
    return out


def frame_fingerprint(df):
    if df is None:
        return None
    fp = {'rows': int(len(df)), 'columns': list(map(str, df.columns)),
          'nan_counts': {str(c): int(df[c].isna().sum()) for c in df.columns},
          'dtypes': {str(c): str(df[c].dtype) for c in df.columns}}
    if 'Datetime' in df.columns and len(df):
        fp['first'] = str(df['Datetime'].iloc[0])
        fp['last'] = str(df['Datetime'].iloc[-1])
        fp['datetime_sha'] = hashlib.sha256(df['Datetime'].astype('int64').to_numpy().tobytes()).hexdigest()[:16]
    num = df.drop(columns=['Datetime'], errors='ignore').select_dtypes('number')
    if not num.empty:
        rounded = np.round(num.to_numpy(dtype='float64'), 2)
        fp['values_sha'] = hashlib.sha256(np.nan_to_num(rounded, nan=-9999.0).tobytes()).hexdigest()[:16]
    if 'LAeq' in df.columns:
        fp['laeq_sum_round2'] = float(np.round(np.nansum(np.round(df['LAeq'].to_numpy(dtype='float64'), 2)), 2))
    return fp


def position_fingerprint(pos):
    return {name: frame_fingerprint(getattr(pos, name))
            for name in ('overview_totals', 'overview_spectral', 'log_totals', 'log_spectral')}


def _rss_mb():
    return psutil.Process().memory_info().rss / 1048576 if psutil else float('nan')


def _peak_mb():
    if not psutil:
        return float('nan')
    mi = psutil.Process().memory_info()
    return getattr(mi, 'peak_wset', mi.rss) / 1048576


def run(config_path, positions, cprofile=False, trace=False):
    configs = load_source_configs(config_path, positions)
    capture = _PerfCapture()
    perf_logger = logging.getLogger('noise_survey_analysis.core.data_manager')
    perf_logger.addHandler(capture)
    perf_logger.setLevel(logging.INFO)

    results = {}
    t_all = time.perf_counter()
    if trace:
        tracemalloc.start()
    dm = DataManager(use_cache=False)
    t0 = time.perf_counter()
    dm.load_from_configs(configs)
    eager_s = time.perf_counter() - t0
    print(f"eager (summary/report files) load: {eager_s:.2f}s")

    prof = None
    if cprofile:
        import cProfile
        prof = cProfile.Profile()
    for name in dm.positions():
        pos = dm[name]
        if not pos.log_file_paths:
            continue
        size_mb = sum(os.path.getsize(f['file_path']) for f in pos.log_file_paths if os.path.exists(f['file_path'])) / 1048576
        capture.rows.clear()
        if trace:
            tracemalloc.reset_peak()
        rss0 = _rss_mb()
        t0 = time.perf_counter()
        if prof:
            prof.enable()
        ok = pos.load_log_data_lazy(NoiseParserFactory(), use_cache=False)
        if prof:
            prof.disable()
        elapsed = time.perf_counter() - t0
        peak = tracemalloc.get_traced_memory()[1] if trace else 0
        print(f"\n== {name}: {len(pos.log_file_paths)} log file(s), {size_mb:,.0f} MB, loaded={ok}, total {elapsed:.2f}s, "
              f"process peak working set so far {_peak_mb():,.0f} MB (tracemalloc peak {peak/1048576:,.0f} MB), RSS {rss0:,.0f}->{_rss_mb():,.0f} MB")
        for _p, fname, parse_ms, merge_ms in capture.rows:
            print(f"   {fname:55s} parse {parse_ms/1000:7.2f}s  merge {merge_ms/1000:6.2f}s")
        lt, ls = pos.log_totals, pos.log_spectral
        print(f"   log_totals rows={0 if lt is None else len(lt)}  log_spectral rows={0 if ls is None else len(ls)}")
        results[name] = {'seconds': elapsed, 'peak_mb': peak / 1048576, 'size_mb': size_mb}
    if trace:
        tracemalloc.stop()
    total = time.perf_counter() - t_all
    print(f"\nTOTAL wall (eager + all positions' lazy loads): {total:.2f}s")
    if prof:
        import pstats
        s = io.StringIO()
        pstats.Stats(prof, stream=s).sort_stats('cumulative').print_stats(35)
        print(s.getvalue())

    fingerprint = {n: position_fingerprint(dm[n]) for n in dm.positions()}
    return results, total, fingerprint


def compare(a, b):
    diffs = []
    for pos in sorted(set(a) | set(b)):
        for key in sorted(set(a.get(pos, {})) | set(b.get(pos, {}))):
            fa, fb = a.get(pos, {}).get(key), b.get(pos, {}).get(key)
            if fa == fb:
                continue
            if not fa or not fb:
                diffs.append(f"{pos}.{key}: one side missing"); continue
            for k in sorted(set(fa) | set(fb)):
                if fa.get(k) != fb.get(k):
                    diffs.append(f"{pos}.{key}.{k}: {str(fa.get(k))[:120]} != {str(fb.get(k))[:120]}")
    return diffs


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('config')
    ap.add_argument('--positions', help='comma separated position names (default: all)')
    ap.add_argument('--save-fingerprint')
    ap.add_argument('--compare')
    ap.add_argument('--cprofile', action='store_true')
    ap.add_argument('--tracemalloc', action='store_true', help='exact Python allocation peaks (slows parsing)')
    args = ap.parse_args()
    logging.basicConfig(level=logging.WARNING)
    positions = set(args.positions.split(',')) if args.positions else None
    _, _, fp = run(args.config, positions, args.cprofile, args.tracemalloc)
    if args.save_fingerprint:
        with open(args.save_fingerprint, 'w', encoding='utf-8') as fh:
            json.dump(fp, fh, indent=1)
    if args.compare:
        with open(args.compare, 'r', encoding='utf-8') as fh:
            base = json.load(fh)
        diffs = compare(base, json.loads(json.dumps(fp)))
        print("\nFINGERPRINT COMPARISON:", "IDENTICAL" if not diffs else f"{len(diffs)} DIFFERENCE(S)")
        for d in diffs[:40]:
            print("  ", d)
        sys.exit(1 if diffs else 0)


if __name__ == '__main__':
    main()
