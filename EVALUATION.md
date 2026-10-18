# Annotation refactor evaluation

## Current summary

- Status: Stage 0 complete with an explicitly unmeasured server benchmark; Stage 1 verified against baseline.
- Safety snapshot: `66bd8df`, tagged `baseline-pre-annotation-refactor`.
- Branch: `main`; edits and commits remain in the original Google Drive repository.
- Verification: fresh throwaway local source snapshots, never edited or committed there. Each run records its exact directory and source identity.
- Bokeh remains pinned to 3.4.1.
- Final stage, test totals, measurements and real-job checks will replace this progress summary at completion.

## Decisions and approved amendments

1. Retain markers as separate point annotations: global drawing, snapshots, timestamp uniqueness and shortcuts have distinct useful semantics. Share HTML panel presentation, not the region data model.
2. Regions have an immutable origin meter and a whole-region meter-state map. The origin remains present; other meters initially unchecked.
3. Pairwise merge: unchecked defers, equal states persist, present/absent conflicts become unchecked and are named for re-check. A dedicated atomic action makes a merge one undo step. This rule is not associative; do not fold arbitrary bulk merges.
4. Categories have stable IDs, editable names/colours and a workspace catalog. Legacy region colours remain explicit overrides.
5. Legacy consolidation uses equal normalized area counts, endpoints within 1 ms and matching note or non-empty colour. Match each candidate against a fixed representative, not a tolerance chain, and allow at most one member per origin meter.
6. Background means LA90 of pooled context samples; report LAeq from the identical context alongside it. Default context is five minutes either side, excluding regions present at the target meter, with at least sixty seconds usable. State the method and indicative-data limitations in NOTES.
7. Export defaults to the best available resolution per region/meter/parameter. Optional log-plus-overview output is off by default.
8. Python full-resolution export processes source windows one meter/file at a time. Do not use the eager whole-meter lazy-loader/cache path.
9. Follow the latest instruction permitting throwaway local verification copies. Exclude `.git` and `node_modules`; install dependencies and generate evidence without editing copied source. Only evidence returns to Drive.
10. Sub-agents own disjoint files; the primary agent owns integration, commits, tags, pushes and acceptance. No worktrees or development copies.

## Stage 0 — baseline

### Inspected implementation

- Regions: `{id, positionId, areas, start, end, note, color}`; one meter each. Per-chart Quad overlay. Copy, Comparison and Auto Day & Night create unlinked objects.
- Markers: global chart lines, metrics snapshots across meters, duplicate timestamp rejection and separate shortcuts.
- Metrics: browser-side region calculations; duplicate comparison spectrum implementation. Region source queries already subtract chart offsets. Region spectrum can use the selected parameter with LZeq fallback. Comparison no longer substitutes LAeq for missing LAFmax.
- Remaining correctness risks: region cache key lacks meter and requested resolution; auto dataset selection accepts any overlapping streamed log samples without full request coverage. Comparison still queries unadjusted slice bounds.
- Import/export: existing single wide annotation CSV; workspace version 1; regions rehydrate by shallow merge.
- Layout: one Bokeh column containing a chart/sidebar row; sidebar Tabs have no viewport height constraint. Region DataTable has 64 px rows and widgets below it.
- Sizes: `ui/components.py` approximately 3,860 lines; `data-processors.js` approximately 1,560 lines.
- HTML: region notes and display labels are escaped before card rendering. Colours enter style attributes and need validation in the HTML replacement.
- Existing static E2E test references a missing repo-root `6030_survey_dashboard.html`; record the actual suite outcome, without repairing it at baseline.

### Tests, measurements and screenshots

- Local suite copy: `C:\Users\steve\AppData\Local\Temp\nsa-annotation-tests\stage-0-20261018-093151-d5ef10bd\repo`; snapshot app HEAD `66bd8df`; copied source hashes unchanged after all suites.
- Python 3.13.14, pytest 7.4.0, Bokeh 3.4.1; Node 24.13.1, npm 11.8.0.
- Python: **401 passed**, 8 deprecation warnings, 33.71 s.
- Vitest: **436 passed, 3 skipped**, 34 files, 5.08 s. Vitest 1.6 JSON top-level passed total includes skips; report counts use individual statuses.
- Playwright: **3 passed, 5 failed**. Pre-existing failures: selected LCeq remains LZeq in the old harness; initial mode expected overview but is log; old single-R workflow creates no region; old Auto Day & Night harness creates no region; static test references missing `6030_survey_dashboard.html`.
- Reports: `docs/evaluation/stage-0/stage-0-20261018-093151-d5ef10bd/`.
- The first Python runner invocation split the junit argument incorrectly; that was a runner error, not an application test failure. The corrected runner reran Python against the same immutable baseline copy. Both receipts are retained.
- Benchmark copy: `C:\Users\steve\AppData\Local\Temp\nsa-annotation-tests\stage-0-benchmark-20261018-093212-c7eef2bd\repo`, pinned to the pre-refactor application. Four meters × 259,200 one-second samples × 31 bands, 300 regions; seed 20261018. Smaller 100 ms fixture also generated.
- Static DashBuilder: 4,049 ms; serialization: 31,841 ms; HTML: 262,639,255 bytes.
- Static browser startup (3 runs): median 15,062 ms, p95 16,582 ms. These are browser navigation measurements, separate from Python construction and serialization; repeat navigations use OS/browser caches, not a claim of fully cold disk caches.
- Annotation re-render (20 runs): median 57.25 ms, p95 60.60 ms. CSV export (20 runs): median 7.45 ms, p95 10.16 ms; 182,282 bytes. No static page errors.
- Screenshots and complete values: `docs/evaluation/stage-0/benchmark/`. The original panel begins at x=1644, beyond the 1600 px timing viewport; its separate screenshot captures the actual panel rather than a misleading viewport crop.
- Server benchmark: **unmeasured**. The programmatic harness listened on HTTP but produced no Bokeh document/app in a bounded direct diagnostic. This harness lifecycle differs from the production launcher; no production defect is inferred. A faulty readiness probe also introduced a bounded delay. The reusable harness now uses TCP readiness and the documented 300000 ms unused-session lifetime; source copies were never edited. No invented server timings.
- Stage 0 changes no application behaviour and fixes no pre-existing application tests.

## Stage acceptance policy

Every stage records changed behaviour, decisions, test counts/failures, source-copy path, baseline comparison, screenshots and regressions. Empty runner output is inconclusive. Pre-existing failures remain identified separately from new failures. Unavailable measurements are labelled unavailable, never estimated.

The HTML shell is retained only if the required suites and both run modes pass, the layout is simpler and repeatable startup/render regressions stay within 10%; otherwise the prototype is committed and reverted.

## Stage 1 — feature module extraction

- Python: 14 classes/functions extracted to 11 feature modules plus shared helpers. `ui.components` preserves imports and the standalone demo. Implementation ASTs and callback strings match baseline.
- JavaScript: common policy, line processing, spectral processing and frequency processing extracted; original file retains orchestration/public API. Test imports and production load order updated.
- Decision: preserve compatibility facades and public model names; do not combine correctness changes with extraction. Callback guard tests scan extracted Python modules.
- First verification caught a missing TimeSeriesComponent import in navigation annotations; corrected in Drive, then verified from a fresh snapshot.
- Final local copy: `C:\Users\steve\AppData\Local\Temp\nsa-annotation-tests\stage-1-fixed-20261018-093612-074bde02\repo`.
- Final suites: Python **401 passed**, 8 warnings (24.24 s); Vitest **436 passed, 3 skipped** (3.98 s); Playwright **3 passed, same 5 baseline failures** (6.3 s). Copied source unchanged. Initial failed and corrected receipts retained in `docs/evaluation/stage-1*/`.
- Appearance and interactions intentionally unchanged. Full-size static comparison: startup median 15,000 ms (-0.41%); render 60.60 ms (+5.85%); export 7.90 ms (+6.04%). All within the 10% investigation threshold; no page errors. Screenshots and measurements: `docs/evaluation/stage-1/benchmark/`. An additional unselected panel screenshot matches the baseline bounds exactly; selected/unselected captures are labelled separately.

## Stage 2 — per-meter annotation model

- Added workspace-v2 regions with immutable origin, whole-region meter states, editable category catalog and nullable colour overrides. Existing copies now mark presence; Comparison creates one shared region; Auto Day & Night creates one shared region per actual civil-time period, including partial nights and DST boundaries.
- Pairwise merge implements the approved truth table, names conflicting meters and performs one atomic undoable action. Split and category deletion/reassignment are atomic. Classification elevation reuses/creates a category and preserves source context.
- Explicit non-mutating Python/JS migrations upgrade v1, consolidate conservatively and reject future versions. Server startup, browser loads and control bridge use migration. Legacy CSV/JSON consolidation reports counts. The origin remains present and temporarily missing meter keys are preserved.
- Metrics cache now distinguishes meter, requested resolution, geometry, offset and refreshed source identity. Manual recalculation follows the displayed series; explicit auto export remains independent. This fixes the old cache collision without silently changing the recalculation workflow.
- Local verification copy: `C:\Users\steve\AppData\Local\Temp\nsa-annotation-tests\stage-2-fixed-20261018-144535-e9a66592\repo`; source hashes unchanged.
- Vitest **461 passed, 3 skipped**, 36 files. Stage-2 Python coverage **405 passed** (the same full run also exercised 15 unregistered future exporter tests: 14 passed, one marker round-trip failure assigned for Stage 5). Playwright remains **3 passed, the same 5 baseline failures**.
- Earlier failing receipts are retained. Five JS expectation updates reflect v2/schema/creation semantics; a real resolution-cache regression was fixed rather than weakening its test. A tolerance-chain fixture was corrected to isolate same-origin rejection.
- Legacy panel appearance remains in place until Stages 3/4. Stage-2 full-size static benchmark: startup 13,833 ms, render 58.70 ms (+2.53% against 57.25 ms baseline), export 7.40 ms. No page errors; evidence `docs/evaluation/stage-2/benchmark/`. Runs later in the day have different OS cache/load conditions, so startup differences are observations rather than attributed speedups. No Stage-5 exporter implementation is included in this checkpoint.

## Stage 3 — per-meter drawing and interaction

- Present bands use category colour, absent bands are neutral grey, unchecked ghosts use a separate faint dashed Quad renderer. Source rows retain region/meter/state/area IDs. Display timestamps remain unchanged; source offsets are applied only to calculations.
- Added persisted off/selected/all ghost mode (selected default), a temporary legacy-panel selector, selected-band click cycling, and guarded 1–9 meter shortcuts. Modified gestures, editable controls, repeats and classification lane precedence are preserved. State clicks do not seek.
- Undo restores annotations without rewinding ghost visibility. Both overlay sources are reused across renders rather than creating renderer instances repeatedly.
- Frozen suite copy: `C:\Users\steve\AppData\Local\Temp\nsa-annotation-tests\stage-3-20261018-145234-6969225c\repo`. Vitest **470 passed, 3 skipped**, 37 files. Stage-3 Python tests **405 passed**; the full working-copy run additionally checked future exporter tests (24 passed, two section-reader numeric-dtype failures, assigned to Stage 5 and subsequently corrected there). Playwright remains **3 passed, same 5 baseline failures**. Copied source unchanged.
- Full-size static benchmark, **ghosts all**: startup median 13,651 ms, render **121.00 ms** versus baseline 57.25 ms (+111.4%), export 6.80 ms. No page errors. Four times as many meter/region bands are drawn; all-ghost mode is measurably slower, and is optional. The default remains selected-only. Measurements/screenshots: `docs/evaluation/stage-3/benchmark/`.
- The next HTML-panel stage will avoid redundant overlay writes on note-only changes; the above is the honest pre-optimization checkpoint.
