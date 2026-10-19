"""Exercise the production bokeh-serve entry point from a local source copy.

Generated sources and evidence belong under --output, never in Drive source.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import socket
import subprocess
import sys
import time

import numpy as np
import pandas as pd
from playwright.sync_api import sync_playwright


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if root.drive.upper() == "G:":
        parser.error("Run from a fresh local verification copy")
    sys.path.insert(0, str(root))
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    sources = []
    for index in range(4):
        path = output / f"P{index + 1}_log.csv"
        frame = pd.DataFrame({"Datetime": pd.date_range("2026-10-01", periods=1800, freq="s", tz="UTC"),
                      "LAeq": 50 + index + np.sin(np.arange(1800) / 20),
                      "LAFmax": 55 + index + np.sin(np.arange(1800) / 20)})
        frame.to_csv(path, index=False)
        sources.append({"position_name": f"P{index + 1}", "parser_type": "generic",
                        "timezone": "UTC", "data_profile": "log", "file_paths": [str(path)]})
        summary = output / f"P{index + 1}_summary.csv"
        frame.iloc[::60].to_csv(summary, index=False)
        sources.append({"position_name": f"P{index + 1}", "parser_type": "generic",
                        "timezone": "UTC", "data_profile": "overview", "file_paths": [str(summary)]})
    config = output / "config.json"
    config.write_text(json.dumps({"sourceConfigs": sources}), encoding="utf-8")
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    log = (output / "server.log").open("w", encoding="utf-8")
    process = subprocess.Popen([sys.executable, "-m", "bokeh", "serve",
                                "noise_survey_analysis/main.py", "--port", str(port),
                                "--unused-session-lifetime", "300000", "--args", "--config", str(config)],
                               cwd=root, stdout=log, stderr=subprocess.STDOUT)
    report = {"local_copy": str(root), "mode": "production bokeh serve", "page_errors": []}
    try:
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError("Bokeh server stopped; inspect server.log")
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=.5):
                    break
            except OSError:
                time.sleep(.25)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page(viewport={"width": 1600, "height": 1000})
            page.on("pageerror", lambda error: report["page_errors"].append(str(error)))
            started = time.perf_counter()
            page.goto(f"http://localhost:{port}/main", timeout=60000)
            page.wait_for_function("() => !!window.NoiseSurveyApp?.registry?.models?.htmlSidePanel", timeout=90000)
            page.wait_for_function("() => window.NoiseSurveyApp.store.getState().view.viewport.min > 1e12", timeout=30000)
            report["startup_ms"] = (time.perf_counter() - started) * 1000
            page.evaluate("""() => {
                const app=window.NoiseSurveyApp, start=app.store.getState().view.viewport.min;
                app.store.dispatch(app.actions.regionsAdded([{id:1,positionId:'P1',start:start+300000,end:start+310000,note:'Server smoke'}]));
                app.store.dispatch(app.actions.regionSelect(1));
            }""")
            panel = page.locator('[data-nsa-panel="annotations"]')
            panel.locator('.nsa-selected [data-meter="P2"]').click()
            assert "present" in panel.locator('.nsa-selected [data-meter="P2"]').get_attribute("aria-label")
            target = output / "full-resolution.csv"
            queued = page.evaluate("path => window.NoiseSurveyApp.session.handleExportFullResolution({output_path:path})", str(target))
            assert queued, "Browser did not queue full-resolution export"
            deadline = time.monotonic() + 60
            while not target.exists() and time.monotonic() < deadline:
                page.wait_for_timeout(100)
            assert target.exists(), "Full-resolution export did not finish; inspect server status/log"
            from noise_survey_analysis.export.annotations import read_export_section
            overall = read_export_section(target, "OVERALL")
            assert len(overall) == 4
            assert set(overall.data_resolution) == {"log"}
            assert overall.LAeq_dB.notna().all(), "Full export must calculate actual source levels"
            report["export_rows"] = len(overall)
            report["meters"] = page.evaluate("window.NoiseSurveyApp.store.getState().view.availablePositions")
            page.screenshot(path=str(output / "main-layout.png"))
            panel.screenshot(path=str(output / "regions-panel.png"))
            browser.close()
            assert not report["page_errors"], report["page_errors"]
            report["passed"] = True
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
        log.close()
        (output / "server-smoke.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
