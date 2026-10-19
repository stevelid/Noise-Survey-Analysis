"""Repeat the same real-dashboard benchmark from a frozen local source copy.

Pass --source-root when executing this harness independently of the frozen copy.
Large fixtures/HTML remain local; --evidence copies only JSON and screenshots.
"""
from __future__ import annotations

import argparse
import gc
import importlib.util
import json
import logging
from pathlib import Path
import shutil
import sys
import time


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, default=Path.cwd())
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--evidence", type=Path)
    parser.add_argument("--ghosts-all", action="store_true")
    parser.add_argument("--startup-runs", type=int, default=3)
    parser.add_argument("--iterations", type=int, default=20)
    args = parser.parse_args()
    args.output = args.output.resolve()
    source = args.source_root.resolve()
    if source.drive.upper() == "G:":
        parser.error("The source must be a frozen local verification copy")
    sys.path.insert(0, str(source))
    spec = importlib.util.spec_from_file_location("benchmark_harness", source / "scripts/annotation_benchmark.py")
    harness = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(harness)
    logging.disable(logging.CRITICAL)
    from bokeh.document import Document
    from bokeh.embed import file_html
    from bokeh.resources import INLINE

    args.output.mkdir(parents=True, exist_ok=True)
    report = {"local_copy_path": str(source), "harness_path": str(Path(__file__)),
              "fixture": json.loads((args.fixture / "fixture.json").read_text()),
              "ghosts_all": args.ghosts_all,
              "limitations": ["Server timing is not measured by this static comparison."]}
    manager = harness.load_manager(args.fixture)
    doc = Document()
    report["static_build_ms"] = harness.build_document(doc, manager, False)
    started = time.perf_counter()
    html = args.output / "benchmark.html"
    html.write_text(file_html(doc, INLINE, "NSA annotation benchmark"), encoding="utf-8")
    report["static_serialize_ms"] = (time.perf_counter() - started) * 1000
    report["static_html_bytes"] = html.stat().st_size
    del manager, doc
    gc.collect()
    if args.ghosts_all:
        harness.LOAD_REGIONS = """regions => {
            const app = window.NoiseSurveyApp;
            app.store.dispatch(app.actions.regionReplaceAll(regions));
            app.store.dispatch(app.actions.regionGhostModeSet('all'));
            return app.store.getState().regions.allIds.length;
        }"""
    images = args.output / "static"
    images.mkdir(exist_ok=True)
    regions = json.loads((args.fixture / "regions.json").read_text())
    report["modes"] = {"static": harness.browser_measure(html.as_uri(), regions, images,
                                                       args.startup_runs, args.iterations)}
    (args.output / "measurements.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    if args.evidence:
        args.evidence.mkdir(parents=True, exist_ok=True)
        shutil.copy2(args.output / "measurements.json", args.evidence)
        shutil.copytree(images, args.evidence / "static", dirs_exist_ok=True)
    print(json.dumps({name: report["modes"]["static"][name]["median_ms"]
                      for name in ("startup", "render", "export")}))


if __name__ == "__main__":
    main()
