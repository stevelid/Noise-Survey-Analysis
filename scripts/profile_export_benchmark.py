"""Profile/re-time the 300-region export using already-generated source CSVs.

Run against a frozen local source snapshot. Artifacts stay outside that snapshot;
the workspace and its source files are reused without editing or regeneration.
"""
from __future__ import annotations

import argparse
import cProfile
from contextlib import nullcontext
import importlib.util
import io
import json
import os
from pathlib import Path
import pstats
import sys
import time


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=Path.cwd())
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--profile", action="store_true")
    parser.add_argument("--compare-to", type=Path)
    args = parser.parse_args()
    root, output = args.source_root.resolve(), args.output.resolve()
    if root.drive.upper() == "G:" or output.drive.upper() == "G:":
        parser.error("Use local source and artifact paths, not Drive")
    if output == root or root in output.parents:
        parser.error("Artifacts must be outside the copied source")
    os.chdir(root)
    sys.path.insert(0, str(root))
    import numpy as np
    import pandas as pd
    from noise_survey_analysis.export.annotations import export_annotations, read_export_section

    # Share the existing RSS sampler instead of introducing another definition.
    spec = importlib.util.spec_from_file_location("full_export_harness", root / "scripts/full_export_benchmark.py")
    harness = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(harness)
    output.mkdir(parents=True, exist_ok=True)
    target = output / "annotations.csv"
    report = {"local_copy": str(root), "workspace": str(args.workspace.resolve()),
              "python": sys.version, "pandas": pd.__version__, "numpy": np.__version__,
              "profiled": args.profile, "source_generation": "reused, outside timing"}
    profiler = cProfile.Profile() if args.profile else None
    try:
        # Keep sampler-thread waits out of deterministic cProfile reports.
        # An unprofiled run measures RSS separately against the same workspace.
        with (nullcontext(None) if profiler else harness.PeakRSS()) as rss:
            started = time.perf_counter()
            if profiler:
                profiler.runcall(export_annotations, args.workspace, target)
            else:
                export_annotations(args.workspace, target)
            report["export_seconds"] = time.perf_counter() - started
        report["rss"] = rss.report if rss else {"available": False, "reason": "Profile without sampler; use an unprofiled run for RSS"}
        report["output_bytes"] = target.stat().st_size
        tables = {section: read_export_section(target, section)
                  for section in ("REGIONS", "OVERALL", "SPECTRAL")}
        report["row_counts"] = {name: len(table) for name, table in tables.items()}
        assert report["row_counts"] == {"REGIONS": 300, "OVERALL": 1200, "SPECTRAL": 1200}
        assert set(tables["OVERALL"].data_resolution) == {"log"}
        assert np.isfinite(tables["OVERALL"][["LAeq_dB", "LAFmax_dB"]].to_numpy(dtype=float)).all()
        bands = [name for name in tables["SPECTRAL"] if name.endswith("Hz")]
        assert len(bands) == 31
        assert np.isfinite(tables["SPECTRAL"][bands].to_numpy(dtype=float)).all()
        if args.compare_to:
            for section, table in tables.items():
                before = read_export_section(args.compare_to, section)
                pd.testing.assert_frame_equal(before, table, check_dtype=False,
                                              check_exact=False, rtol=1e-10, atol=1e-6)
            report["equivalent_to"] = str(args.compare_to.resolve())
            report["comparison_tolerance"] = {"relative": 1e-10, "absolute": 1e-6}
        report["verified"] = True
    except Exception as error:
        report.update(verified=False, error=f"{type(error).__name__}: {error}")
        raise
    finally:
        if profiler:
            profiler.dump_stats(str(output / "export.prof"))
            stream = io.StringIO()
            stats = pstats.Stats(profiler, stream=stream).sort_stats("cumulative")
            stats.print_stats(35)
            (output / "profile.txt").write_text(stream.getvalue(), encoding="utf-8")
            report["profile_total_calls"] = stats.total_calls
            report["profile_total_seconds"] = stats.total_tt
        (output / "benchmark.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
