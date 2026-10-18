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
