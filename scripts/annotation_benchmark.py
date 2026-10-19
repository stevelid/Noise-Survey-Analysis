"""Deterministic real-dashboard annotation benchmark (run from a local copy).

Example: python scripts/annotation_benchmark.py --output C:/Temp/nsa-benchmark
Generated survey arrays and HTML stay outside Git. Only evidence should be copied
back into docs/evaluation. Dataset generation is excluded from startup timings.
"""
from __future__ import annotations

import argparse
import gc
import json
import logging
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.request

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
BASE = pd.Timestamp("2026-10-01T00:00:00Z")
BANDS = [20, 25, 31.5, 40, 50, 63, 80, 100, 125, 160, 200, 250,
         315, 400, 500, 630, 800, 1000, 1250, 1600, 2000, 2500, 3150,
         4000, 5000, 6300, 8000, 10000, 12500, 16000, 20000]


def generate_fixture(folder: Path, hours: float = 72, step: float = 1) -> dict:
    """Four independent, reproducible meters with daily variation and events."""
    folder.mkdir(parents=True, exist_ok=True)
    count = int(hours * 3600 / step)
    seconds = np.arange(count, dtype=np.float64) * step
    timestamps = BASE.value // 10**6 + np.rint(seconds * 1000).astype(np.int64)
    for meter in range(4):
        print(f"Generating P{meter + 1}: {count:,} samples", flush=True)
        rng = np.random.default_rng(20261018 + meter)
        daily = 5 * np.sin(2 * np.pi * (seconds / 86400 - .3))
        traffic = 10 * np.exp(-((seconds % 1800 - 500) / 35)**2)
        levels = (47 + meter * 2 + daily + traffic + rng.normal(0, 1.5, count)).astype(np.float32)
        spectrum = (levels[:, None] - 15
                    - np.abs(np.log2(np.asarray(BANDS) / 500))[None, :] * 2
                    + rng.normal(0, 1, (count, len(BANDS)))).astype(np.float32)
        np.savez_compressed(folder / f"P{meter + 1}.npz", times=timestamps,
                            levels=levels, spectrum=spectrum)
    regions = []
    width = max(2000, int(hours * 3600 * 1000 / 1200))
    for index in range(300):
        start = int(timestamps[0] + index / 301 * (timestamps[-1] - timestamps[0] - width * 3))
        areas = [{"start": start, "end": start + width}]
        if index % 7 == 0:
            areas.append({"start": start + width * 2, "end": start + width * 3})
        regions.append({"id": f"benchmark-{index:03d}", "positionId": f"P{index % 4 + 1}",
                        "start": start, "end": areas[-1]["end"], "areas": areas,
                        "note": f"Benchmark event {index:03d}", "color": "#1e88e5"})
    (folder / "regions.json").write_text(json.dumps(regions), encoding="utf-8")
    metadata = {"meters": 4, "hours": hours, "sample_interval_seconds": step,
                "samples_per_meter": count, "third_octave_bands": len(BANDS),
                "regions": len(regions), "seed": 20261018}
    (folder / "fixture.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return metadata


def load_manager(folder: Path):
    from noise_survey_analysis.core.data_manager import DataManager, PositionData
    manager = DataManager(use_cache=False)
    manager._positions_data = {}
    manager._position_order = [f"P{i}" for i in range(1, 5)]
    for name in manager._position_order:
        print(f"Loading benchmark {name}", flush=True)
        with np.load(folder / f"{name}.npz") as data:
            dates = pd.to_datetime(data["times"], unit="ms", utc=True)
            levels = data["levels"]
            position = PositionData(name=name)
            position.log_totals = pd.DataFrame({"Datetime": dates, "LAeq": levels,
                "LAFmax": levels + 3, "LAF90": levels - 2, "LAF10": levels + 1})
            position.log_spectral = pd.DataFrame({"Datetime": dates, **{
                f"LZeq_{band}": data["spectrum"][:, i] for i, band in enumerate(BANDS)}})
        # Aggregates mimic a five-minute survey summary, not decimated log points.
        indexed = position.log_totals.set_index("Datetime")
        overview = indexed.resample("5min").agg({"LAeq": lambda x: 10 * np.log10(np.mean(10**(x / 10))),
            "LAFmax": "max", "LAF90": lambda x: np.quantile(x, .1), "LAF10": lambda x: np.quantile(x, .9)})
        position.overview_totals = overview.reset_index()
        spectral = position.log_spectral.set_index("Datetime")
        position.overview_spectral = (10 * np.log10((10**(spectral / 10)).resample("5min").mean())).reset_index()
        position._log_data_loaded = True
        manager._positions_data[name] = position
    return manager


def build_document(doc, manager, server_mode: bool):
    from noise_survey_analysis.core.config import CHART_SETTINGS
    from noise_survey_analysis.visualization.dashBuilder import DashBuilder
    start = time.perf_counter()
    DashBuilder().build_layout(doc, manager, CHART_SETTINGS, server_mode=server_mode)
    if server_mode:
        from noise_survey_analysis.core.server_data_handler import ServerDataHandler
        doc._benchmark_handler = ServerDataHandler(doc, manager, CHART_SETTINGS)
    return (time.perf_counter() - start) * 1000


def serve(folder: Path, port: int):
    from bokeh.application import Application
    from bokeh.application.handlers.function import FunctionHandler
    from bokeh.server.server import Server
    manager = load_manager(folder)
    server = Server({"/benchmark": Application(FunctionHandler(lambda doc: build_document(doc, manager, True)))},
                    port=port, address="127.0.0.1", allow_websocket_origin=[f"127.0.0.1:{port}"],
                    unused_session_lifetime_milliseconds=300000)
    server.start()
    server.io_loop.start()


def summarize(values: list[float]) -> dict:
    return {"runs": len(values), "median_ms": float(np.median(values)),
            "p95_ms": float(np.percentile(values, 95)), "values_ms": values}


READY = """() => !!window.NoiseSurveyApp?.store?.getState &&
    !!window.NoiseSurveyApp?.session?.__testHelpers?.buildAnnotationsCsv &&
    !!window.Bokeh?.documents?.length"""
LOAD_REGIONS = """regions => {
 const app = window.NoiseSurveyApp;
 app.store.dispatch(app.actions.regionReplaceAll(regions));
 return app.store.getState().regions.allIds.length;
}"""
RENDER = """async i => {
 const app=window.NoiseSurveyApp, id=app.store.getState().regions.allIds[0];
 const before=performance.now();
 app.store.dispatch(app.actions.regionUpdate(id,{note:'Benchmark note '+i}));
 await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));
 return performance.now()-before;
}"""
EXPORT = """() => {
 const app=window.NoiseSurveyApp,state=app.store.getState();
 const regions=state.regions.allIds.map(id=>state.regions.byId[id]);
 const before=performance.now();
 const csv=app.session.__testHelpers.buildAnnotationsCsv([],regions,state);
 const blob=new Blob([csv],{type:'text/csv'}),url=URL.createObjectURL(blob);
 URL.revokeObjectURL(url);
 return {ms:performance.now()-before,bytes:blob.size};
}"""


def browser_measure(url: str, regions: list, folder: Path, samples: int, iterations: int) -> dict:
    from playwright.sync_api import sync_playwright
    errors: list[str] = []
    startup: list[float] = []
    result = {"url": url, "viewport": [1600, 1100], "startup_definition":
              "navigation through initialized application and two animation frames; dataset pre-generated"}
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1600, "height": 1100})
        page.on("pageerror", lambda error: errors.append(str(error)))
        for index in range(samples):
            started = time.perf_counter()
            page.goto(url, timeout=180000, wait_until="load")
            page.wait_for_function(READY, timeout=180000)
            page.evaluate("() => new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))")
            startup.append((time.perf_counter()-started)*1000)
        result["startup"] = summarize(startup)
        result["startup"]["first_navigation_ms"] = startup[0]
        result["startup"]["repeat_navigation_median_ms"] = float(np.median(startup[1:])) if len(startup) > 1 else None
        result["regions_loaded"] = page.evaluate(LOAD_REGIONS, regions)
        page.wait_for_timeout(500)
        result["render"] = summarize([page.evaluate(RENDER, i) for i in range(iterations)])
        exports = [page.evaluate(EXPORT) for _ in range(iterations)]
        result["export"] = summarize([value["ms"] for value in exports])
        result["export_bytes"] = exports[-1]["bytes"]
        page.screenshot(path=str(folder / "main-layout.png"))
        # Bokeh layouts can place the sidebar beyond the viewport horizontally.
        # Capture its element, rather than incorrectly cropping the chart edge.
        panel = page.locator(".nsa-annotation-panel, .bk-Tabs, .nsa-side-panel").first
        if panel.count():
            result["side_panel_bounds"] = panel.bounding_box()
            panel.screenshot(path=str(folder / "regions-panel.png"))
        else:
            result["screenshot_limitation"] = "Sidebar element was not found"
        result["console_page_errors"] = errors
        browser.close()
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--hours", type=float, default=72)
    parser.add_argument("--startup-runs", type=int, default=3)
    parser.add_argument("--iterations", type=int, default=20)
    parser.add_argument("--serve", action="store_true")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--reuse-fixture", action="store_true")
    parser.add_argument("--skip-static", action="store_true")
    args = parser.parse_args()
    logging.disable(logging.CRITICAL)
    if ROOT.drive.upper() == "G:":
        parser.error("Run benchmarks from a fresh local copy; do not execute on Drive.")
    folder = args.output.resolve()
    folder.mkdir(parents=True, exist_ok=True)
    if args.serve:
        serve(folder / "survey", args.port)
        return 0
    report = {"local_copy_path": str(ROOT), "python": sys.version, "limitations": [], "modes": {}}
    import bokeh
    report["bokeh"] = bokeh.__version__
    if not args.reuse_fixture:
        generate_fixture(folder / "survey", args.hours)
        generate_fixture(folder / "small-100ms", hours=1/6, step=.1)
    report["fixture"] = json.loads((folder / "survey" / "fixture.json").read_text())
    regions = json.loads((folder / "survey" / "regions.json").read_text())
    report_path = folder / "measurements.json"

    def checkpoint():
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2), flush=True)

    if not args.skip_static:
        try:
            print("Building real static dashboard", flush=True)
            from bokeh.document import Document
            from bokeh.embed import file_html
            from bokeh.resources import INLINE
            manager = load_manager(folder / "survey")
            doc = Document()
            report["static_build_ms"] = build_document(doc, manager, False)
            started = time.perf_counter()
            html = folder / "benchmark.html"
            html.write_text(file_html(
                doc, INLINE, "NSA annotation benchmark",
                template=doc.template, template_variables=doc.template_variables,
            ), encoding="utf-8")
            report["static_serialize_ms"] = (time.perf_counter()-started)*1000
            report["static_html_bytes"] = html.stat().st_size
            print(f"Static HTML: {html.stat().st_size:,} bytes; starting browser", flush=True)
            del doc, manager
            gc.collect()
            evidence = folder / "static"
            evidence.mkdir(exist_ok=True)
            report["modes"]["static"] = browser_measure(html.as_uri(), regions, evidence, args.startup_runs, args.iterations)
        except Exception as error:
            report["limitations"].append(f"Static benchmark failed: {type(error).__name__}: {error}")
        checkpoint()
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    log = (folder / "server.log").open("w", encoding="utf-8")
    process = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "--output", str(folder),
                                "--serve", "--port", str(port)], stdout=log, stderr=subprocess.STDOUT, cwd=ROOT)
    try:
        url = f"http://127.0.0.1:{port}/benchmark"
        for _ in range(180):
            if process.poll() is not None:
                raise RuntimeError(f"Server stopped with {process.returncode}; see server.log")
            try:
                # The server exposes /benchmark only; '/' may legitimately 404.
                with socket.create_connection(("127.0.0.1", port), timeout=.5):
                    pass
                break
            except Exception:
                time.sleep(1)
        evidence = folder / "server"
        evidence.mkdir(exist_ok=True)
        report["modes"]["server"] = browser_measure(url, regions, evidence, args.startup_runs, args.iterations)
    except Exception as error:
        report["limitations"].append(f"Server benchmark failed: {type(error).__name__}: {error}")
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
        log.close()
    checkpoint()
    return 1 if report["limitations"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
