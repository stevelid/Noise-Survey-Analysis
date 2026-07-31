"""Benchmark the live-server streaming path against a synthetic multi-day survey.

Builds a real dashboard (DashBuilder -> components -> ServerDataHandler) from
generated data and times successive viewport updates, which is the work that runs on
Bokeh's document thread every time the user pans or zooms. Use it to compare branches
or to size further work; the per-step timings are what the UI actually waits on.

    python scripts/benchmark_streaming.py
    python scripts/benchmark_streaming.py --days 4 --positions 3 --steps 8

It also asserts the invariants that keep the spectrogram rendering: every streamed
chunk must match the width of the initialized Image glyph buffer (AGENTS.md section 6),
and the payload must carry glyph anchoring metadata. Exits non-zero if any break.
"""
import argparse
import logging
import pathlib
import sys
import time

import numpy as np
import pandas as pd

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from bokeh.document import Document

from noise_survey_analysis.core.config import CHART_SETTINGS
from noise_survey_analysis.core.data_manager import DataManager, PositionData
from noise_survey_analysis.core.server_data_handler import ServerDataHandler
from noise_survey_analysis.visualization.dashBuilder import DashBuilder

BASE = pd.Timestamp("2024-01-01T00:00:00Z")


class _FakeSessionContext:
    """Streaming reservoirs are only attached to the document on the live-server path."""
    id = "benchmark"


def build_position(name, days, bands, with_spectral):
    position = PositionData(name=name)

    overview_times = pd.date_range(BASE, periods=days * 24 * 12, freq="5min", tz="UTC")
    position.overview_totals = pd.DataFrame({
        "Datetime": overview_times,
        "LAeq": np.random.uniform(40, 80, len(overview_times)),
        "LAF90": np.random.uniform(35, 60, len(overview_times)),
        "LAF10": np.random.uniform(50, 85, len(overview_times)),
    })

    log_times = pd.date_range(BASE, periods=days * 24 * 3600, freq="1s", tz="UTC")
    position.log_totals = pd.DataFrame({
        "Datetime": log_times,
        "LAeq": np.random.uniform(40, 80, len(log_times)).astype(np.float32),
    })

    if with_spectral:
        freqs = [round(6.3 * (10 ** (i / 10)), 1) for i in range(bands)]
        position.overview_spectral = pd.DataFrame({
            "Datetime": overview_times,
            **{f"LZeq_{f}": np.random.uniform(30, 90, len(overview_times)) for f in freqs},
        })
        position.log_spectral = pd.DataFrame({
            "Datetime": log_times,
            **{f"LZeq_{f}": np.random.uniform(30, 90, len(log_times)).astype(np.float32)
               for f in freqs},
        })

    position._log_data_loaded = True
    return position


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--days", type=int, default=4, help="Survey length in days (default 4)")
    parser.add_argument("--positions", type=int, default=3, help="Positions to build (default 3)")
    parser.add_argument("--bands", type=int, default=36, help="Spectral bands (default 36)")
    parser.add_argument("--steps", type=int, default=6, help="Viewport updates to time (default 6)")
    parser.add_argument("--viewport-seconds", type=int, default=1800,
                        help="Viewport width in seconds (default 1800)")
    parser.add_argument("--verbose", action="store_true", help="Keep application logging")
    args = parser.parse_args()

    if not args.verbose:
        logging.disable(logging.CRITICAL)

    print(f"Building {args.days}-day survey across {args.positions} position(s) ...")
    started = time.perf_counter()
    positions = {}
    for index in range(args.positions):
        name = f"P{index + 1}"
        # Leave the last position totals-only, mirroring meters without spectral data.
        with_spectral = index < args.positions - 1 or args.positions == 1
        positions[name] = build_position(name, args.days, args.bands, with_spectral)
    print(f"  generated in {time.perf_counter() - started:.1f}s")
    for name, position in positions.items():
        spectral = position.log_spectral.shape if position.has_log_spectral else "none"
        print(f"  {name}: log_totals={position.log_totals.shape} log_spectral={spectral}")

    data_manager = DataManager()
    data_manager._positions_data = positions
    data_manager._position_order = list(positions)

    doc = Document()
    doc._session_context = lambda: _FakeSessionContext()

    print("\nBuilding dashboard ...")
    started = time.perf_counter()
    DashBuilder().build_layout(doc, data_manager, CHART_SETTINGS, server_mode=True)
    print(f"  built in {time.perf_counter() - started:.1f}s")

    handler = ServerDataHandler(doc, data_manager, CHART_SETTINGS)
    pinned = {}
    for position_id in data_manager.positions():
        bundle = handler.position_models[position_id]
        resolve = getattr(handler, "_resolve_display_buffer_width", None)
        pinned[position_id] = resolve(position_id, bundle) if resolve else None
        print(f"  {position_id}: display buffer width = {pinned[position_id]}")

    print(f"\nTiming {args.steps} viewport updates ({args.viewport_seconds}s wide) ...")
    failures = []
    timings = []
    origin = int(BASE.value // 10**6) + 6 * 3600 * 1000
    for step in range(args.steps):
        low = origin + step * (args.viewport_seconds // 2) * 1000
        high = low + args.viewport_seconds * 1000

        started = time.perf_counter()
        handler.handle_range_update(low, high)
        elapsed_ms = (time.perf_counter() - started) * 1000
        timings.append(elapsed_ms)

        for position_id in data_manager.positions():
            source = handler.position_models[position_id].get("spectrogram_log_source")
            if source is None or not source.data:
                continue
            width = source.data["chunk_time_length"][0]
            expected = pinned[position_id]
            if expected is not None and width != expected:
                failures.append(
                    f"{position_id} step {step}: chunk_time_length {width} != buffer {expected}"
                )
            for field in ("initial_glyph_data_y", "initial_glyph_data_dh"):
                if field not in source.data:
                    failures.append(f"{position_id} step {step}: missing {field}")

        print(f"  step {step}: {elapsed_ms:8.1f} ms")

    steady = timings[1:] or timings
    print(f"\n  first update : {timings[0]:.1f} ms (builds the cached time index)")
    print(f"  steady state : {sum(steady) / len(steady):.1f} ms mean, "
          f"{min(steady):.1f}-{max(steady):.1f} ms")

    if failures:
        print("\nFAILURES:")
        for failure in failures:
            print("  -", failure)
        return 1

    print("\nOK: streamed chunks match the initialized glyph buffers")
    return 0


if __name__ == "__main__":
    sys.exit(main())
