"""Measure the full Python export against the baseline four-meter NPZ fixture.

Run from a throwaway local source snapshot. --output is an absolute artifact
directory, never a source directory. CSV generation is outside the export timer.
The script can also be supplied on stdin with --source-root pointing at a frozen
local snapshot; no source files in that snapshot need to be edited.
"""
from __future__ import annotations

import argparse
import gc
import hashlib
import json
import os
from pathlib import Path
import sys
import threading
import time

THIRD_OCTAVE_BANDS_HZ = (20, 25, 31.5, 40, 50, 63, 80, 100, 125, 160,
                        200, 250, 315, 400, 500, 630, 800, 1000, 1250,
                        1600, 2000, 2500, 3150, 4000, 5000, 6300, 8000,
                        10000, 12500, 16000, 20000)
METER_IDS = ("P1", "P2", "P3", "P4")
EXPECTED_SAMPLES = 259200
EXPECTED_REGIONS = 300
RSS_INTERVAL_S = 1.0


def _is_drive_path(path: Path) -> bool:
    return path.drive.upper() == "G:" or any(part.lower() in ("my drive", "shared drives") for part in path.parts)


class PeakRSS:
    """Optional current-process RSS sampling; includes a final immediate read."""
    def __init__(self):
        self.report = {"available": False, "sample_interval_s": RSS_INTERVAL_S}
        self.stop = threading.Event()
        self.thread = None

    def __enter__(self):
        try:
            import psutil
            self.process = psutil.Process()
            initial = self.process.memory_info().rss
            self.report.update(available=True, baseline_bytes=initial, peak_bytes=initial, samples=1)
        except Exception as error:
            self.report["reason"] = f"RSS unavailable: {error}"
            return self

        def sample():
            count = 0
            while not self.stop.wait(RSS_INTERVAL_S):
                try:
                    self.report["peak_bytes"] = max(self.report["peak_bytes"], self.process.memory_info().rss)
                    self.report["samples"] += 1
                    count += 1
                    if count % 60 == 0:
                        print(f"Export still running: {count}s; sampled peak RSS {self.report['peak_bytes'] / 1024**2:.1f} MiB", flush=True)
                except Exception as error:
                    self.report["sampling_error"] = str(error)
                    break
        self.thread = threading.Thread(target=sample, name="nsa-export-rss", daemon=True)
        self.thread.start()
        return self

    def __exit__(self, *_):
        if self.thread:
            self.stop.set()
            self.thread.join(timeout=RSS_INTERVAL_S + .5)
            try:
                self.report["peak_bytes"] = max(self.report["peak_bytes"], self.process.memory_info().rss)
                self.report["samples"] += 1
                self.report["peak_increase_bytes"] = self.report["peak_bytes"] - self.report["baseline_bytes"]
            except Exception as error:
                self.report["sampling_error"] = str(error)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, required=True, help="Baseline survey folder containing P1--P4.npz and regions.json")
    parser.add_argument("--output", type=Path, required=True, help="Absolute local artifact directory")
    parser.add_argument("--source-root", type=Path, default=Path.cwd(), help="Frozen local application source snapshot")
    args = parser.parse_args(argv)
    source_root, fixture = args.source_root.resolve(), args.fixture.resolve()
    if not args.output.is_absolute():
        parser.error("--output must be absolute")
    output = args.output.resolve()
    if any(_is_drive_path(path) for path in (source_root, fixture, output)):
        parser.error("Use a throwaway local source copy, fixture and output, not Google Drive")
    if not (source_root / "noise_survey_analysis").is_dir():
        parser.error("--source-root must contain the copied application package")
    if output == source_root or source_root in output.parents:
        parser.error("Generated artifacts must be outside the source snapshot")
    os.chdir(source_root)
    sys.path.insert(0, str(source_root))
    import numpy as np
    import pandas as pd
    from noise_survey_analysis.core.annotation_workspace import migrate_workspace
    from noise_survey_analysis.export.annotations import export_annotations, read_export_section
    import noise_survey_analysis.export.annotations as exporter

    imported = Path(exporter.__file__).resolve()
    if source_root not in imported.parents:
        raise RuntimeError(f"Exporter was not imported from the frozen source copy: {imported}")
    output.mkdir(parents=True, exist_ok=True)
    generated = output / "generated-sources"
    generated.mkdir(exist_ok=True)
    report = {"local_copy_path": str(source_root), "exporter_path": str(imported),
              "exporter_sha256": hashlib.sha256(imported.read_bytes()).hexdigest(),
              "fixture": str(fixture), "python": sys.version,
              "notes": ["Source CSV generation excluded from export timing.",
                        "All regions present at all four meters; original origins and multi-area geometry retained.",
                        "RSS is sampled for this Python process every second; it can miss shorter peaks.",
                        "Generation arrays are released before export; allocator-retained pages can remain in baseline RSS."]}
    report_path = output / "full-export-benchmark.json"
    try:
        started = time.perf_counter()
        sources = []
        for meter in METER_IDS:
            print(f"Generating {meter} CSV from baseline NPZ", flush=True)
            with np.load(fixture / f"{meter}.npz") as packed:
                times, levels, spectra = packed["times"], packed["levels"], packed["spectrum"]
            if len(times) != EXPECTED_SAMPLES or spectra.shape != (EXPECTED_SAMPLES, len(THIRD_OCTAVE_BANDS_HZ)):
                raise ValueError(f"Unexpected {meter} fixture shape: {len(times)} / {spectra.shape}")
            frame = pd.DataFrame({"Datetime": pd.to_datetime(times, unit="ms", utc=True),
                "LAeq": levels, "LAFmax": levels + 3, "LAF90": levels - 2, "LAF10": levels + 1,
                **{f"LZeq_{frequency:g}": spectra[:, index] for index, frequency in enumerate(THIRD_OCTAVE_BANDS_HZ)}})
            path = generated / f"{meter}_log.csv"
            frame.to_csv(path, index=False, float_format="%.3f", chunksize=10000)
            sources.append({"position_name": meter, "file_paths": [str(path)], "parser_type": "generic",
                            "timezone": "UTC", "data_profile": "log", "sample_interval_s": 1})
            del frame, times, levels, spectra
            gc.collect()
        regions = json.loads((fixture / "regions.json").read_text(encoding="utf-8"))
        if len(regions) != EXPECTED_REGIONS:
            raise ValueError(f"Expected {EXPECTED_REGIONS} fixture regions, got {len(regions)}")
        for region in regions:
            region["meterStates"] = dict.fromkeys(METER_IDS, "present")
        workspace, _ = migrate_workspace({"version": 2, "sourceConfigs": sources, "appState": {
            "view": {"availablePositions": list(METER_IDS), "positionChartOffsets": dict.fromkeys(METER_IDS, 0)},
            "regions": regions, "markers": {"byId": {}, "allIds": []}}})
        workspace_path = output / "benchmark-workspace.json"
        workspace_path.write_text(json.dumps(workspace), encoding="utf-8")
        report["generation_seconds"] = time.perf_counter() - started
        report["source_csv_bytes"] = sum(Path(source["file_paths"][0]).stat().st_size for source in sources)
        report["samples_per_meter"] = EXPECTED_SAMPLES
        report["meters"] = len(METER_IDS)
        report["spectral_bands"] = len(THIRD_OCTAVE_BANDS_HZ)
        report["generation_rounding_decimals"] = 3
        del workspace, regions
        gc.collect()
        print("Running full Python export (generation excluded)", flush=True)
        with PeakRSS() as rss:
            started = time.perf_counter()
            csv_path = export_annotations(workspace_path, output / "annotations.full-resolution.csv")
            report["export_seconds"] = time.perf_counter() - started
        report["rss"] = rss.report
        report["output_csv"] = str(csv_path)
        report["output_bytes"] = csv_path.stat().st_size
        tables = {name: read_export_section(csv_path, name) for name in ("REGIONS", "OVERALL", "SPECTRAL")}
        report["row_counts"] = {name: len(table) for name, table in tables.items()}
        expected = {"REGIONS": EXPECTED_REGIONS, "OVERALL": EXPECTED_REGIONS * len(METER_IDS), "SPECTRAL": EXPECTED_REGIONS * len(METER_IDS)}
        if report["row_counts"] != expected:
            raise AssertionError(f"Wrong section sizes: {report['row_counts']}; expected {expected}")
        for name, table in tables.items():
            if set(table.data_resolution) != {"log"}:
                raise AssertionError(f"Unexpected {name} resolution: {set(table.data_resolution)}")
        if not np.isfinite(tables["OVERALL"][["LAeq_dB", "LAFmax_dB"]].to_numpy(dtype=float)).all():
            raise AssertionError("Non-finite overall headline metrics")
        band_columns = [column for column in tables["SPECTRAL"] if column.endswith("Hz")]
        if len(band_columns) != len(THIRD_OCTAVE_BANDS_HZ) or not np.isfinite(tables["SPECTRAL"][band_columns].to_numpy(dtype=float)).all():
            raise AssertionError("Missing or non-finite spectral metrics")
        report["verified"] = True
        print(f"Verified {expected}; full export {report['export_seconds']:.3f}s", flush=True)
    except Exception as error:
        report["verified"] = False
        report["error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"Benchmark report: {report_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
