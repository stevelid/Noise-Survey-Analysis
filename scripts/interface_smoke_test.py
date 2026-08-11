#!/usr/bin/env python3
"""
Interface smoke test for the Noise Survey Analysis dashboard.

Drives the live Bokeh app with real mouse/keyboard events via Playwright and
verifies outcomes against the NoiseSurveyApp store state. Covers the region
and marker interaction surface: tap, arrow nudge, R-R creation, Esc cancel,
Shift+drag creation, panel selection, resize, notes, add-area, split, merge,
copy-to-all, auto day/night, all delete paths, undo/redo, marker create/
nudge/delete, visibility toggles.

Usage:
    python scripts/interface_smoke_test.py [--url http://localhost:5006/noise_survey_analysis]

The app should be serving the example survey config (data on 2026-02-02);
the script deep-links to that window via ?start=&end=.
"""
import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone

from playwright.sync_api import sync_playwright

DEFAULT_URL = "http://localhost:5006/noise_survey_analysis"

# Viewport window with data on screen (example survey: Svan + Sentry afternoon)
WINDOW_START = datetime(2026, 2, 2, 10, 30, tzinfo=timezone.utc)
WINDOW_END = datetime(2026, 2, 2, 16, 0, tzinfo=timezone.utc)

RESULTS = []


def record(name, ok, detail=""):
    RESULTS.append((name, ok, detail))
    status = "PASS" if ok else "FAIL"
    print(f"[{status}] {name}" + (f" -- {detail}" if detail else ""), flush=True)


class Harness:
    def __init__(self, page):
        self.page = page
        self.charts = {}   # position -> element handle of its timeseries canvas
        self.primary = None

    # ---- state access ----------------------------------------------------
    def slice(self, name):
        return self.page.evaluate(
            "(name) => JSON.parse(JSON.stringify(window.NoiseSurveyApp.store.getState()[name]))",
            name,
        )

    def regions(self):
        return self.slice("regions")

    def markers(self):
        return self.slice("markers")

    def tap(self):
        return self.slice("interaction")["tap"]

    def region_count(self):
        return len(self.regions()["allIds"])

    def marker_count(self):
        return len(self.markers()["allIds"])

    # ---- input drivers ---------------------------------------------------
    def _chart_bbox(self, position=None):
        el = self.charts[position or self.primary]
        el.scroll_into_view_if_needed()
        self.page.wait_for_timeout(150)
        return el.bounding_box()

    def click_chart(self, fx, fy=0.5, modifiers=None, position=None):
        bbox = self._chart_bbox(position)
        x = bbox["x"] + bbox["width"] * fx
        y = bbox["y"] + bbox["height"] * fy
        if modifiers:
            for m in modifiers:
                self.page.keyboard.down(m)
        self.page.mouse.click(x, y)
        if modifiers:
            for m in reversed(modifiers):
                self.page.keyboard.up(m)
        self.page.wait_for_timeout(250)

    def drag_chart(self, fx1, fx2, fy=0.5, shift=True, position=None):
        bbox = self._chart_bbox(position)
        y = bbox["y"] + bbox["height"] * fy
        x1 = bbox["x"] + bbox["width"] * fx1
        x2 = bbox["x"] + bbox["width"] * fx2
        if shift:
            self.page.keyboard.down("Shift")
        self.page.mouse.move(x1, y)
        self.page.mouse.down()
        for i in range(1, 6):
            self.page.mouse.move(x1 + (x2 - x1) * i / 5, y, steps=2)
        self.page.mouse.up()
        if shift:
            self.page.keyboard.up("Shift")
        self.page.wait_for_timeout(400)

    def press(self, combo, settle=250):
        self.page.keyboard.press(combo)
        self.page.wait_for_timeout(settle)

    def button(self, label, exact=False):
        return self.page.get_by_role("button", name=label, exact=exact).first

    def click_button(self, label, settle=350, exact=False):
        self.button(label, exact=exact).click()
        self.page.wait_for_timeout(settle)

    def click_tab(self, title):
        self.page.locator(".bk-tab", has_text=title).first.click()
        self.page.wait_for_timeout(400)

    def available_positions(self):
        return self.page.evaluate(
            "() => window.NoiseSurveyApp.store.getState().view.availablePositions || []"
        )

    # ---- discovery ---------------------------------------------------------
    def discover_charts(self):
        candidates = []
        for el in self.page.locator("canvas").all():
            bb = el.bounding_box()
            if bb and bb["width"] > 700 and bb["height"] > 120:
                candidates.append((bb["y"], el))
        candidates.sort(key=lambda c: c[0])
        print(f"  candidate canvases at y: {[round(y) for y, _ in candidates]}")
        for _, el in candidates:
            el.scroll_into_view_if_needed()
            self.page.wait_for_timeout(150)
            bb = el.bounding_box()
            if not bb:
                continue
            self.page.mouse.click(bb["x"] + bb["width"] * 0.5, bb["y"] + bb["height"] * 0.5)
            self.page.wait_for_timeout(300)
            tap = self.tap()
            pos = tap.get("position")
            if pos and pos not in self.charts:
                self.charts[pos] = el
                print(f"  mapped position {pos!r}")
        if not self.charts:
            raise RuntimeError("No chart canvases discovered")
        self.primary = list(self.charts.keys())[0]
        self.page.mouse.wheel(0, -100000)
        self.page.wait_for_timeout(300)
        print(f"  primary position: {self.primary}; positions in state: {self.available_positions()}")


def run(url):
    start_ms = int(WINDOW_START.timestamp() * 1000)
    end_ms = int(WINDOW_END.timestamp() * 1000)
    full_url = f"{url}?start={start_ms}&end={end_ms}"

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 2100, "height": 1200})
        console_errors = []
        page.on(
            "console",
            lambda m: console_errors.append(m.text) if m.type == "error" else None,
        )
        print(f"Loading {full_url}")
        page.set_default_timeout(10000)
        page.goto(full_url, wait_until="networkidle", timeout=90000)
        page.wait_for_function(
            "() => window.NoiseSurveyApp && window.NoiseSurveyApp.store"
            " && window.NoiseSurveyApp.store.getState().interaction"
        , timeout=60000)
        page.wait_for_timeout(9000)  # let charts finish first render

        h = Harness(page)
        print("Discovering charts...")
        h.discover_charts()

        # ------------------------------------------------------------------
        # 01 tap
        try:
            h.click_chart(0.12)
            t = h.tap()
            ok = t["isActive"] and t["position"] == h.primary and t["timestamp"]
            record("01 tap places cursor", bool(ok), f"tap={t['timestamp']} pos={t['position']}")
        except Exception as e:
            record("01 tap places cursor", False, repr(e))

        # 02 arrow nudge
        try:
            t0 = h.tap()["timestamp"]
            h.press("ArrowRight")
            t1 = h.tap()["timestamp"]
            h.press("ArrowLeft")
            t2 = h.tap()["timestamp"]
            record("02 arrow keys nudge tap line", t1 > t0 and t2 == t0,
                   f"{t0} -> {t1} -> {t2}")
        except Exception as e:
            record("02 arrow keys nudge tap line", False, repr(e))

        # 03 R-R region creation
        try:
            n0 = h.region_count()
            h.click_chart(0.18)
            h.press("r")
            pend = h.slice("interaction")["pendingRegionStart"]
            h.click_chart(0.24)
            h.press("r")
            n1 = h.region_count()
            record("03 R..R creates region", n1 == n0 + 1 and pend is not None,
                   f"count {n0}->{n1}, pending was {pend}")
        except Exception as e:
            record("03 R..R creates region", False, repr(e))

        # 04 Esc cancels creation
        try:
            n0 = h.region_count()
            h.click_chart(0.30)
            h.press("r")
            h.press("Escape")
            pend = h.slice("interaction")["pendingRegionStart"]
            n1 = h.region_count()
            record("04 Esc cancels region creation", n1 == n0 and pend is None,
                   f"count {n0}->{n1}, pending={pend}")
        except Exception as e:
            record("04 Esc cancels region creation", False, repr(e))

        # 05 shift+drag creates region
        try:
            n0 = h.region_count()
            h.drag_chart(0.40, 0.46)
            n1 = h.region_count()
            record("05 Shift+drag draws region", n1 == n0 + 1, f"count {n0}->{n1}")
        except Exception as e:
            record("05 Shift+drag draws region", False, repr(e))

        # 06 select region via panel row
        try:
            rows = page.locator(".region-panel-table .slick-row")
            rows.first.click()
            page.wait_for_timeout(400)
            sel = h.regions()["selectedId"]
            record("06 panel row selects region", sel is not None, f"selectedId={sel}")
        except Exception as e:
            record("06 panel row selects region", False, repr(e))

        # 07 resize selected region with Ctrl/Alt + arrows
        try:
            st = h.regions()
            sel = st["selectedId"]
            areas0 = st["byId"][str(sel)]["areas"] if str(sel) in st["byId"] else st["byId"][sel]["areas"]
            h.press("Alt+ArrowRight")
            h.press("Control+ArrowLeft")
            st1 = h.regions()
            areas1 = st1["byId"][str(sel)]["areas"] if str(sel) in st1["byId"] else st1["byId"][sel]["areas"]
            record("07 Ctrl/Alt+arrows resize region", areas0 != areas1,
                   f"{areas0} -> {areas1}")
        except Exception as e:
            record("07 Ctrl/Alt+arrows resize region", False, repr(e))

        # 08 region note input
        try:
            ta = page.locator("textarea:visible").first
            ta.click()
            ta.fill("smoke-test note")
            page.keyboard.press("Tab")
            page.wait_for_timeout(400)
            st = h.regions()
            sel = st["selectedId"]
            note = (st["byId"].get(str(sel)) or st["byId"].get(sel) or {}).get("note", "")
            record("08 region note persists", "smoke-test note" in note, f"note={note!r}")
        except Exception as e:
            record("08 region note persists", False, repr(e))

        # 09 add area appends to selected region
        try:
            st = h.regions()
            sel = st["selectedId"]
            reg = st["byId"].get(str(sel)) or st["byId"].get(sel)
            n_areas0 = len(reg["areas"])
            h.click_button("Add Area")
            h.drag_chart(0.52, 0.56)
            st1 = h.regions()
            reg1 = st1["byId"].get(str(sel)) or st1["byId"].get(sel)
            n_areas1 = len(reg1["areas"]) if reg1 else -1
            record("09 Add Area appends segment", n_areas1 == n_areas0 + 1,
                   f"areas {n_areas0}->{n_areas1}")
        except Exception as e:
            record("09 Add Area appends segment", False, repr(e))

        # 10 split areas
        try:
            n0 = h.region_count()
            h.click_button("Split Areas")
            n1 = h.region_count()
            record("10 Split Areas splits region", n1 == n0 + 1, f"count {n0}->{n1}")
        except Exception as e:
            record("10 Split Areas splits region", False, repr(e))

        # 11 merge regions (two-step: Merge Regions -> pick source -> Confirm Merge)
        try:
            page.locator(".region-panel-table .slick-row").first.click()
            page.wait_for_timeout(300)
            n0 = h.region_count()
            h.click_button("Merge Regions")
            merge_mode = h.regions().get("isMergeModeActive")
            h.click_button("Confirm Merge")
            n1 = h.region_count()
            record("11 Merge Regions merges", merge_mode is True and n1 == n0 - 1,
                   f"mergeMode={merge_mode} count {n0}->{n1}")
        except Exception as e:
            record("11 Merge Regions merges", False, repr(e))

        # 12 copy region to all positions
        try:
            n0 = h.region_count()
            n_pos = len(h.available_positions())
            h.click_button("Copy to All Positions")
            n1 = h.region_count()
            record("12 Copy to All Positions", n1 == n0 + (n_pos - 1),
                   f"count {n0}->{n1} (positions={n_pos})")
        except Exception as e:
            record("12 Copy to All Positions", False, repr(e))

        # 13 auto day/night
        try:
            n0 = h.region_count()
            h.click_button("Auto Day & Night", settle=1500)
            n1 = h.region_count()
            record("13 Auto Day & Night creates regions", n1 > n0, f"count {n0}->{n1}")
        except Exception as e:
            record("13 Auto Day & Night creates regions", False, repr(e))

        # 14 Delete key removes selected region
        try:
            page.locator(".region-panel-table .slick-row").first.click()
            page.wait_for_timeout(300)
            n0 = h.region_count()
            sel = h.regions()["selectedId"]
            h.press("Delete")
            n1 = h.region_count()
            record("14 Delete key removes region", sel is not None and n1 == n0 - 1,
                   f"sel={sel} count {n0}->{n1}")
        except Exception as e:
            record("14 Delete key removes region", False, repr(e))

        # 15 undo / redo
        try:
            n0 = h.region_count()
            h.press("Control+z")
            n1 = h.region_count()
            h.press("Control+y")
            n2 = h.region_count()
            record("15 undo/redo of delete", n1 == n0 + 1 and n2 == n0,
                   f"{n0} -> undo {n1} -> redo {n2}")
        except Exception as e:
            record("15 undo/redo of delete", False, repr(e))

        # 16 Delete Region button
        try:
            page.locator(".region-panel-table .slick-row").first.click()
            page.wait_for_timeout(300)
            n0 = h.region_count()
            h.click_button("Delete Region")
            n1 = h.region_count()
            record("16 Delete Region button", n1 == n0 - 1, f"count {n0}->{n1}")
        except Exception as e:
            record("16 Delete Region button", False, repr(e))

        # 17 ctrl+click inside region removes it
        try:
            n0 = h.region_count()
            h.drag_chart(0.60, 0.66)
            n1 = h.region_count()
            h.click_chart(0.63, modifiers=["Control"])
            n2 = h.region_count()
            record("17 Ctrl+click removes region", n1 == n0 + 1 and n2 == n0,
                   f"{n0} -> draw {n1} -> ctrl-click {n2}")
        except Exception as e:
            record("17 Ctrl+click removes region", False, repr(e))

        # cleanup: remove all remaining regions so taps during the marker tests
        # don't land inside (and select) the full-width Auto Day & Night regions,
        # which would flip the side panel back to the Regions tab.
        try:
            for _ in range(30):
                n_before = h.region_count()
                if n_before == 0:
                    break
                page.locator(".region-panel-table .slick-row").first.click()
                page.wait_for_timeout(200)
                h.press("Delete")
                if h.region_count() == n_before:
                    print("  (region cleanup stalled - row click did not select)")
                    break
            print(f"  (region cleanup done, remaining={h.region_count()})")
        except Exception as e:
            print(f"  (region cleanup failed: {e!r})")

        # 18 M creates marker at tap
        try:
            m0 = h.marker_count()
            h.click_chart(0.70)
            h.press("m")
            m1 = h.marker_count()
            record("18 M key creates marker", m1 == m0 + 1, f"count {m0}->{m1}")
        except Exception as e:
            record("18 M key creates marker", False, repr(e))

        # switch side panel to Markers tab
        try:
            h.click_tab("Markers")
        except Exception as e:
            print(f"  (markers tab switch failed: {e!r})")

        # 19 Add Marker at Tap button
        try:
            m0 = h.marker_count()
            h.click_chart(0.74)
            h.click_button("Add Marker at Tap")
            m1 = h.marker_count()
            record("19 Add Marker at Tap button", m1 == m0 + 1, f"count {m0}->{m1}")
        except Exception as e:
            record("19 Add Marker at Tap button", False, repr(e))

        # 20 select marker via panel + ctrl+arrow nudge
        try:
            page.locator(".marker-panel-table .slick-row").first.click()
            page.wait_for_timeout(400)
            mst = h.markers()
            sel = mst["selectedId"]
            mk = mst["byId"].get(str(sel)) or mst["byId"].get(sel)
            ts0 = mk["timestamp"] if mk else None
            h.press("Control+ArrowRight")
            mst1 = h.markers()
            mk1 = mst1["byId"].get(str(sel)) or mst1["byId"].get(sel)
            ts1 = mk1["timestamp"] if mk1 else None
            record("20 marker select + Ctrl+arrow nudge",
                   sel is not None and ts0 is not None and ts1 is not None and ts1 > ts0,
                   f"sel={sel} ts {ts0}->{ts1}")
        except Exception as e:
            record("20 marker select + Ctrl+arrow nudge", False, repr(e))

        # 21 marker note
        try:
            ta = page.locator("textarea:visible").first
            ta.click()
            ta.fill("marker smoke note")
            page.keyboard.press("Tab")
            page.wait_for_timeout(400)
            mst = h.markers()
            sel = mst["selectedId"]
            note = (mst["byId"].get(str(sel)) or mst["byId"].get(sel) or {}).get("note", "")
            record("21 marker note persists", "marker smoke note" in note, f"note={note!r}")
        except Exception as e:
            record("21 marker note persists", False, repr(e))

        # 22 Delete key removes selected marker
        try:
            m0 = h.marker_count()
            sel = h.markers()["selectedId"]
            h.press("Delete")
            m1 = h.marker_count()
            record("22 Delete key removes marker", sel is not None and m1 == m0 - 1,
                   f"sel={sel} count {m0}->{m1}")
        except Exception as e:
            record("22 Delete key removes marker", False, repr(e))

        # 23 Delete Marker button
        try:
            page.locator(".marker-panel-table .slick-row").first.click()
            page.wait_for_timeout(300)
            m0 = h.marker_count()
            h.click_button("Delete Marker")
            m1 = h.marker_count()
            record("23 Delete Marker button", m1 == m0 - 1, f"count {m0}->{m1}")
        except Exception as e:
            record("23 Delete Marker button", False, repr(e))

        # 24 ctrl+click near marker removes it
        try:
            m0 = h.marker_count()
            h.click_chart(0.78)
            h.press("m")
            m1 = h.marker_count()
            h.click_chart(0.78, modifiers=["Control"])
            m2 = h.marker_count()
            record("24 Ctrl+click removes marker", m1 == m0 + 1 and m2 == m0,
                   f"{m0} -> m {m1} -> ctrl-click {m2}")
        except Exception as e:
            record("24 Ctrl+click removes marker", False, repr(e))

        # 25 region overlay visibility toggle (label is dynamic: "Regions (n)")
        try:
            h.click_tab("Regions")
            toggle = page.locator("button").filter(
                has_text=re.compile(r"^Regions(\s*\(\d+\))?$")).first
            v0 = h.regions()["overlaysVisible"]
            toggle.click()
            page.wait_for_timeout(350)
            v1 = h.regions()["overlaysVisible"]
            toggle.click()
            page.wait_for_timeout(350)
            v2 = h.regions()["overlaysVisible"]
            record("25 region visibility toggle", v1 == (not v0) and v2 == v0,
                   f"{v0}->{v1}->{v2}")
        except Exception as e:
            record("25 region visibility toggle", False, repr(e))

        # 26 Clear All Markers (toolbar menu?)
        try:
            h.click_chart(0.80)
            h.press("m")
            m0 = h.marker_count()
            h.click_button("Clear All Markers")
            m1 = h.marker_count()
            record("26 Clear All Markers", m0 > 0 and m1 == 0, f"count {m0}->{m1}")
        except Exception as e:
            record("26 Clear All Markers", False, repr(e))

        # ------------------------------------------------------------------
        print("\n--- console errors during run ---")
        for msg in console_errors[:20]:
            print("  ", msg[:300])
        if not console_errors:
            print("   (none)")

        browser.close()

    n_pass = sum(1 for _, ok, _ in RESULTS if ok)
    print(f"\n==== {n_pass}/{len(RESULTS)} passed ====")
    for name, ok, detail in RESULTS:
        if not ok:
            print(f"  FAILED: {name} -- {detail}")
    return 0 if n_pass == len(RESULTS) else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=DEFAULT_URL)
    args = ap.parse_args()
    sys.exit(run(args.url))
