# Master Review of `/plans` Recommendations

**Date:** 2026-05-05  
**Scope:** Review and synthesis of `plans/Deepseek.md`, `plans/GLM5_1.md`, `plans/gemini3_1.md`, and `plans/KimiK2_6`, cross-checked against `AGENTS.md`, `README.md`, `TODO.txt`, and selected current code paths.

---

## 1. Ground Rules From Project Guidance

The implementation plan below is constrained by these project rules and gotchas:

- **Redux-style frontend architecture:** UI state belongs in `app.store`; updates go through event handler -> thunk -> action -> reducer -> selector/renderer.
- **Layer responsibilities:** event handlers stay thin; thunks hold orchestration/business logic; reducers stay pure; renderers do not dispatch or perform business logic.
- **Data cache split:** large arrays stay in mutable `dataCache`; lightweight UI/configuration state stays in immutable Redux-style state.
- **Bokeh image invariant:** spectrogram `source.data.image[0]` must keep the same fixed-size buffer after initialization. Do not change image dimensions in JavaScript updates.
- **Hybrid static/live architecture:** live server streams high-resolution visible slices; static export remains lightweight/offline and may use overview/downsampled data.
- **Google Drive test gotcha:** Node/Vitest/Playwright tests should be run from a local non-synced copy, not directly from `G:\My Drive\...`.
- **Current README reality:** annotation CSV import/export, workspace save/load, region average spectrum display, and some region drag-handle workflow support are already documented/implemented, so review suggestions that describe these as wholly missing are stale or need reframing.

---

## 2. Scores for Each Review File

Scores are split into:

- **Usefulness of ideas:** whether the suggestions would materially improve correctness, reliability, performance, or analysis workflow.
- **Review quality:** specificity, evidence, prioritisation, current-code awareness, and avoidance of stale or speculative claims.

| Review file | Usefulness of ideas | Review quality | Overall | Verdict |
|---|---:|---:|---:|---|
| `KimiK2_6` | **8.5/10** | **8.0/10** | **8.3/10** | Best practical frontend/data-integrity review. Strong on current JS workflow issues, comparison metrics, status chips, offsets, and test gaps. Some items are inferred or stale. |
| `GLM5_1.md` | **8.0/10** | **7.8/10** | **7.9/10** | Best broad backend/config/deployment review. Strong on hardcoded paths/timezone, cache risks, VLC import, logging, and session singleton. Some prioritisation over-emphasises low-value cleanup and some UX items are stale. |
| `Deepseek.md` | **7.0/10** | **6.5/10** | **6.8/10** | Concise and useful as a checklist. Correctly identifies several real backend/cache/performance issues. Too terse, with several speculative or expensive recommendations lacking enough implementation detail. |
| `gemini3_1.md` | **5.8/10** | **5.2/10** | **5.5/10** | Good high-level UX direction, but least grounded. Several claims are stale against current README/code; fewer precise files, fewer validated bugs, and some broad refactor ideas are high-risk. |

### 2.1 `KimiK2_6` assessment

**Strengths**

- Correctly identifies confirmed production leftovers: `DEBUG_POSITION` and `debugSpectrogram` in `data-processors.js`, `chart-classes.js`, and `server_data_handler.py`.
- Strong data-integrity findings around region offset handling and comparison metrics.
- Good alignment with `AGENTS.md`: it respects Bokeh fixed-image-buffer concerns and distinguishes render/state/data-cache risks.
- Excellent practical implementation order: hot fixes, reliability/performance, then analysis features.
- Good test-gap awareness: offsets, control widgets, streaming edge cases, generic parser.

**Weaknesses / stale points**

- Treats structured region metric/spectrum export as missing, but `sessionManager.js` already exports annotations CSV with metric columns and band columns. The remaining issue is more specific: include offset provenance and verify metric correctness.
- Treats region spectrum display as a missing feature in parts, but `regionPanelRenderer.js` and `regionUtils.js` already render average spectrum/frequency tables.
- Some lifecycle/memory-leak claims are plausible but not proven urgent for Bokeh page/session lifecycles.
- Some recommendations are inferred from TODOs rather than fully verified.

### 2.2 `GLM5_1.md` assessment

**Strengths**

- Strong backend/config coverage that other reviews missed.
- Confirmed important issues:
  - hardcoded `Europe/London` in `data_parsers.py`,
  - hardcoded Venta paths/media/default sources in `config.py`,
  - `DataManagerCache` pickle in fixed temp path,
  - unconditional `import vlc`,
  - unconditional `logging.basicConfig(level=logging.DEBUG)`,
  - duplicate `load_js_file`,
  - duplicate `_to_bokeh_ms`,
  - process-level `_session_bridge` concerns.
- Good distinction between correctness, performance, UX, and architecture.

**Weaknesses / stale points**

- Prioritises duplicate imports and small DRY issues too high relative to data-integrity bugs.
- Says region import/export CSV is missing, but README and `sessionManager.js` show annotation CSV import/export is implemented. The remaining task is offset-aware/provenance-complete export.
- Says no spectral bar chart in region side panel, but current `regionPanelRenderer.js` contains spectrum/frequency rendering.
- Suggests broad middleware and TypeScript/JSDoc work before some more targeted data correctness issues.

### 2.3 `Deepseek.md` assessment

**Strengths**

- Efficiently identifies several real issues:
  - `ParsedDataCache.get()` ignoring `return_all_columns`,
  - hardcoded timezone,
  - duplicate JS loader,
  - duplicate imports,
  - `DataManagerCache` vs `ParsedDataCache` overlap,
  - stale debug/logging and expensive timestamp collection.
- Useful as a triage checklist.
- Includes some good feature ideas: statistical panel, weather overlay, audio clip export.

**Weaknesses**

- Too terse to implement from directly.
- Some recommendations are expensive architecture changes without enough migration strategy.
- Some ideas are lower value for the immediate reliability/data-integrity phase.
- Does not sufficiently account for already-implemented annotation CSV/spectrum workflow.

### 2.4 `gemini3_1.md` assessment

**Strengths**

- Good UX framing: side-panel redesign, top-bar consolidation, comparison mode workflow, offset synchronization.
- Correctly identifies undo/redo as high-value and architecture-compatible.
- Mentions graceful fallback for spectrogram streaming failures, which aligns with the hybrid architecture.

**Weaknesses / stale points**

- Least code-grounded and least specific.
- Says hover wiring noise was fixed; current `TODO.txt` still lists it as a manual-test finding, so this needs verification before closing.
- Region average spectrum and drag-handle claims are partly stale against `README.md` and current region renderer code.
- Broad refactor recommendations are valid long-term but should not drive the near-term order.

---

## 3. Confirmed High-Value Findings

These are the findings I would act on first because they are either confirmed in current code or have strong data-integrity/reliability implications.

### 3.1 Region metrics and exports are not offset-aware enough

**Status:** Confirmed/high risk.

Current region metrics are calculated in `static/js/features/regions/regionUtils.js`. `computeRegionMetrics()` uses raw region `areas` directly against source `Datetime` arrays. Displayed line/spectrogram data can be shifted by `positionChartOffsets` in `data-processors.js`, and audio uses `positionEffectiveOffsets` in `app.js`. That creates a real risk that a region drawn on a visually shifted chart is measured/exported against the wrong raw time window.

**Do first because:** this can silently produce incorrect LAeq/LAFmax/LA90/spectrum values in reports.

**Suggested fix approach**

- Add a small selector/helper for offset-aware region areas:
  - input: full `state`, `region`, and mode/purpose,
  - output: display areas and source-query areas,
  - source-query areas should subtract the relevant chart offset from display timestamps.
- Use this helper in:
  - `regionUtils.computeRegionMetrics()`,
  - `computeSpectrumAverage()` calls,
  - annotation CSV export in `sessionManager.js`,
  - clipboard/summary generation if it includes computed values.
- Add export columns showing offset provenance, e.g. `chart_offset_ms`, `source_start_utc`, `source_end_utc`, and keep current `start_utc`/`end_utc` as displayed region times.
- Invalidate region metric cache when chart offsets change. Current cache key is `${regionId}_${parameter}`; it should include at least offset and data resolution/source identity.

**Tests**

- Unit-test `computeRegionMetrics()` with a known source and a non-zero chart offset.
- Unit-test CSV export to confirm both display and source-query timestamps are explicit.
- Add a regression for cache invalidation when `positionChartOffsets` changes.

### 3.2 Comparison metrics use the wrong broadband parameter and misleading fallbacks

**Status:** Confirmed.

`static/js/comparison-metrics.js` hardcodes `LAeq` in `chooseDatasetForSlice()` and uses `selectedParameter` only for the spectral path. It also falls back to using `LAeq` values for `LAFmax` if the `LAFmax` column is missing.

**Suggested fix approach**

- Change dataset selection to accept a broadband parameter, using `selectedParameter` where appropriate and falling back clearly to `LAeq` only when intended.
- Do not label max of `LAeq` as `LAFmax`. If `LAFmax` is missing, output `null`/`N/A` and a `lafmaxAvailable` flag.
- Consider computing `LA90` for overview data where appropriate, matching `regionUtils.js` behaviour.
- Add tests for:
  - selected `LZeq` or other available parameter,
  - missing `LAFmax`,
  - overview-only datasets,
  - no standard columns for generic parser sources.

### 3.3 `ParsedDataCache` ignores `return_all_columns`

**Status:** Confirmed.

`core/parsed_data_cache.py` accepts `return_all_columns` but `_get_cache_key()` only uses file path, and comments note this is not part of the key. A file parsed first in filtered mode can later be served in truncated form even when all columns are requested.

**Suggested fix approach**

- Include `return_all_columns` in the cache key or maintain separate entries per parse profile.
- Prefer an explicit parse-profile key so future parser options can be added without repeating this bug.
- Add a Python test that parses the same fixture first with `False`, then `True`, and verifies extra columns are present.

### 3.4 Hardcoded timezone in parser pipeline

**Status:** Confirmed.

`BaseNoiseParser._normalize_datetime_column()` localizes all naive datetimes as `Europe/London`.

**Suggested fix approach**

- Add optional `timezone` to source config.
- Default to `Europe/London` for existing Venta/UK workflows, preserving current behaviour.
- Store resolved timezone in `ParsedData.metadata`.
- Add tests for:
  - default UK behaviour,
  - explicit non-UK timezone,
  - DST ambiguous/nonexistent times.

### 3.5 Production debug leakage and excessive logging

**Status:** Confirmed.

Current code contains:

- hardcoded `DEBUG_POSITION` in `data-processors.js`, `chart-classes.js`, and `server_data_handler.py`,
- verbose `console.log` calls in `collectPositionTimestamps()`,
- `logging.basicConfig(level=logging.DEBUG)` in `main.py`.

**Suggested fix approach**

- Replace job-specific debug constants with runtime debug flags:
  - JS: localStorage/query flag such as `nsa_debug=1`,
  - Python: environment/config log level and optional position filter.
- Default Python logging to `INFO`, configurable via `NOISE_SURVEY_LOG_LEVEL`.
- Remove ungated `collectPositionTimestamps()` logs.

### 3.6 Cache architecture and pickle persistence risk

**Status:** Confirmed/medium-high.

`DataManagerCache` in `main.py` stores pickled whole DataManagers in a predictable temp path. `ParsedDataCache` also stores per-file pickles. This creates overlapping cache responsibilities and possible stale/concurrent/security issues.

**Suggested fix approach**

- Short term:
  - include file mtimes/sizes and source options in any whole-DataManager cache key,
  - make cache location/session identity explicit,
  - avoid loading pickle files if not created by the current app version/profile.
- Medium term:
  - consolidate around `ParsedDataCache` plus deterministic in-memory assembly of `DataManager`,
  - avoid process-global whole-dashboard cache unless there is a measured need.

### 3.7 VLC import prevents non-audio/static use on machines without VLC bindings

**Status:** Confirmed.

`core/audio_handler.py` imports `vlc` at module import time.

**Suggested fix approach**

- Lazy import `vlc` only when live audio is actually initialized.
- Provide a clear disabled-audio state when VLC/python-vlc is unavailable.
- Ensure static generation does not require VLC.

### 3.8 Spectrogram streamed payload validation

**Status:** Valid/high-value defensive improvement.

Because Bokeh image buffers must keep fixed dimensions, streamed `initial_glyph_data.image` or reservoir payloads should be validated before touching `source.data.image[0]`.

**Suggested fix approach**

- Validate presence and size of typed arrays against `n_freqs * chunk_time_length`.
- On invalid payload, retain current image/overview fallback and show a status label rather than white/crashed spectrogram.
- Add tests around reservoir payload shape and fallback path.

### 3.9 `onStateChange` error/nested-dispatch resilience

**Status:** Confirmed concern; implement cautiously.

`app.js` advances `previousState` before rendering to reduce nested-dispatch issues. That is intentional, but the main render loop lacks a broad error boundary.

**Suggested fix approach**

- Add a top-level guarded render cycle that logs contextual information (`lastActionType`, heavy/light update, affected position) without swallowing repeat errors silently.
- Avoid introducing dispatch-from-render patterns.
- Treat action buffering/middleware as a later refactor unless a reproducible nested-dispatch bug exists.

### 3.10 Auto-region timestamp collection is expensive and noisy

**Status:** Confirmed.

`collectPositionTimestamps()` materializes, sorts, and deduplicates all overview and log timestamps and logs heavily.

**Suggested fix approach**

- Remove/gate logs immediately.
- Cache min/max and/or deduped timestamps per position and source update generation.
- Prefer min/max + day-bound calculations where possible rather than materializing all timestamps.

---

## 4. Stale or Partly Stale Recommendations

These should not be implemented as written.

### 4.1 “Region import/export CSV is missing”

**Reality:** `README.md` documents annotation CSV import/export, and `sessionManager.js` implements `Export Annotations (CSV)` / `Import Annotations (CSV)` including markers and regions.

**Reframe:** improve the existing export by adding offset provenance and verifying metric/spectrum correctness.

### 4.2 “Region average spectrum is missing”

**Reality:** `regionUtils.js` computes average spectrum and `regionPanelRenderer.js` renders spectrum/frequency output.

**Reframe:** verify it is using the selected parameter and offset-correct source timestamps. Current code appears to hardcode `LZeq` for region spectrum (`prepared_params?.['LZeq']`) even when `state.view.selectedParameter` differs.

### 4.3 “Region drag handles are missing”

**Reality:** `README.md` says drag handles respond to direct manipulation. `TODO.txt` still includes older grab-handle notes, so this may be partially implemented or documentation may be ahead of behaviour.

**Reframe:** manually test handle UX and only then decide whether to improve visuals/direct manipulation.

### 4.4 “Hover wiring noise fixed”

**Reality:** `TODO.txt` still lists startup hover wiring noise as a manual-test finding.

**Reframe:** verify current browser console behaviour before closing.

### 4.5 “Use Web Workers / major orchestration refactor now”

**Reality:** this may eventually help, but current architecture already has a deliberate state/data-cache split and Bokeh fixed-buffer constraints.

**Reframe:** only pursue after profiling proves JS processing is the bottleneck and after correctness fixes are complete.

---

## 5. Recommended Implementation Order

### Phase 0 — Baseline verification and safety net (half day)

1. **Create a local non-Google-Drive test copy**
   - Use the existing sync script or manual local clone.
   - Run Python tests from the repo and Node/Vitest/Playwright from the local non-synced path.

2. **Record current high-risk behaviours**
   - Comparison metrics with non-`LAeq` selected parameter.
   - Region metrics/export with non-zero chart offset.
   - Startup console noise.
   - Static HTML generation without VLC.

3. **Add/identify minimal fixtures**
   - Small time series with predictable LAeq/LAFmax/LA90.
   - Small spectral matrix with predictable average spectrum.
   - Parser fixture with extra columns for `return_all_columns` cache test.

### Phase 1 — Data correctness hot fixes (1-3 days)

1. **Fix offset-aware region metrics and export**
   - Highest priority due to silent report error risk.
   - Implement a shared offset-aware region-area helper.
   - Include offset/source timestamp columns in annotation CSV export.
   - Update metrics cache key/invalidation.

2. **Fix comparison metric parameter handling**
   - Use selected/current parameter for broadband where valid.
   - Remove misleading `LAFmax` fallback to max `LAeq`.
   - Add availability flags and tests.

3. **Fix region spectrum parameter handling**
   - `regionUtils.computeRegionMetrics()` currently uses `prepared_params?.['LZeq']`; switch to selected parameter with fallback and label the fallback.
   - Combine with offset-aware source-query areas.

4. **Fix `ParsedDataCache` parse profile key**
   - Include `return_all_columns` and future parse options in cache key.
   - Add Python regression test.

### Phase 2 — Reliability and production hygiene (1-2 days)

5. **Remove/gate job-specific debug code**
   - Remove `DEBUG_POSITION` constants or replace with generic runtime debug filters.
   - Remove ungated `collectPositionTimestamps()` logging.

6. **Make logging configurable**
   - `NOISE_SURVEY_LOG_LEVEL`, default `INFO`.
   - Keep targeted streaming diagnostics available behind debug flags.

7. **Make VLC optional/lazy**
   - Static/no-audio paths must run without `python-vlc`.
   - UI should show audio unavailable rather than crashing imports.

8. **Add spectrogram payload validation and graceful fallback**
   - Validate typed-array shape before updating Bokeh image buffers.
   - Preserve existing overview image if streamed data is invalid/missing.

9. **Wrap main render cycle with contextual error handling**
   - Catch and log render-cycle errors with action/update context.
   - Do not dispatch from renderers.

### Phase 3 — Performance fixes with clear ROI (1-3 days)

10. **Optimize auto-region timestamp collection**
    - Remove logs immediately.
    - Cache min/max/deduped timestamps per position/source generation.
    - Prefer min/max interval creation for day/night regions.

11. **Avoid unnecessary frequency-bar work**
    - Gate `updateActiveFreqBarData()` and `renderFrequencyBar()` to hover/tap/parameter/active-position changes where safe.

12. **Memoize heavy control widget rendering**
    - Skip unchanged per-position DOM/model updates in `controlWidgetsRenderer.js`.

13. **Profile before large buffer/delta streaming changes**
    - Do not implement server delta streaming or Web Workers until profiling shows current full-buffer path is a real bottleneck.

### Phase 4 — Configuration, portability, and cache architecture (2-5 days)

14. **Configurable parser timezone**
    - Add per-source timezone, default `Europe/London`.
    - Store resolved timezone in metadata.

15. **Remove hardcoded Venta defaults from core paths**
    - Keep Venta convenience defaults behind config/env.
    - Avoid hardcoded `media_path`/`DEFAULT_DATA_SOURCES` in production path.

16. **Rationalize cache layers**
    - Short term: make whole-DataManager cache safer.
    - Medium term: consolidate around per-file `ParsedDataCache` and remove persistent whole-dashboard pickle if not necessary.

17. **Clarify `SessionBridge` multi-session behaviour**
    - Either document single-session control or make bridge keyed by Bokeh session ID.

### Phase 5 — High-value workflow features (after correctness)

18. **Undo/redo for annotations and offsets**
    - Use the Redux-style architecture.
    - Track only meaningful actions: region/marker create/update/delete, offset changes, import/replace operations.
    - Exclude hover, transient tap, playback status, step-size calculation.
    - Use bounded history.

19. **Comparison mode completion**
    - Finish numeric spectrum table and differences.
    - Allow multiple named slices only after the single-slice data path is correct.
    - Add “copy/sync region to all positions” workflow if not already sufficient.

20. **Offset workflow improvements**
    - Add global/link offsets option.
    - Decouple chart offsets from audio controls where still confusing.
    - Ensure offsets can be applied without audio loaded.

21. **Keyboard shortcut help overlay**
    - Low effort, good usability.
    - Implement as UI state + renderer, not ad-hoc DOM mutation in event handlers.

22. **Report-oriented exports**
    - Existing annotation CSV already has metrics/spectrum columns.
    - Add a clearer “Region Report CSV” preset if current annotation CSV is too broad.
    - Include offset provenance and data source/resolution.

23. **Spectrogram color legend and fixed scale**
    - Useful for side-by-side comparison.
    - Must respect fixed Bokeh image buffer invariant; changing color mapper/range is safe, changing image shape is not.

24. **Statistical overlays / panel**
    - High analysis value but more design work.
    - Prefer region/statistics panel first, then optional chart overlays.

### Phase 6 — Larger refactors only after tests are strong

25. **Split `components.py` and `data-processors.js` gradually**
    - Do not big-bang refactor.
    - Extract tested pure helpers first:
      - region/metric utilities,
      - spectrogram threshold/payload validation,
      - line data slicing,
      - matrix utilities.

26. **Standardize action naming as touched**
    - Follow `feature/nounVerb` for new actions.
    - Avoid mass-renaming without migration tests.

27. **Add JS type checking incrementally**
    - Add JSDoc/`// @ts-check` to small pure modules first.
    - Do not introduce a build-step migration during correctness work.

---

## 6. Proposed Test Plan

### Python tests

- `ParsedDataCache` respects `return_all_columns` parse profiles.
- Parser timezone defaults to `Europe/London` and accepts explicit source timezone.
- Static generation path does not require VLC import.
- Spectrogram processor tests continue to enforce fixed buffer shape and `dw = chunk_time_length * time_step`.

### JavaScript unit tests

- Region metrics with chart offset use source-query timestamps correctly.
- Region metrics cache invalidates or differentiates by offset and selected parameter.
- Region spectrum uses selected parameter or explicit fallback label.
- Comparison metrics do not hardcode `LAeq` when another selected broadband column exists.
- `LAFmax` missing returns `N/A`, not max `LAeq`.
- `collectPositionTimestamps` caching/min-max behaviour.
- Control widget status chips do not regress to `Display: None` on light renders.

### E2E/manual tests

- Run static HTML export and open via `file://`.
- Live Bokeh server zooms into log mode and preserves spectrogram image on invalid/missing stream response.
- Compare two positions with offsets applied and verify exported rows document display/source timestamps.
- Verify hover startup console noise.
- Verify region drag-handle workflow matches README.

---

## 7. Final Ranked Backlog

| Rank | Item | Why now | Effort | Risk |
|---:|---|---|---:|---:|
| 1 | Offset-aware region metrics/export/cache | Silent report data error | Medium | Medium |
| 2 | Comparison selected-parameter and `LAFmax` fixes | Silent analysis error | Low-Medium | Low |
| 3 | Region spectrum selected-parameter fix | Analysis/report correctness | Low-Medium | Low |
| 4 | `ParsedDataCache` parse-profile key | Stale/truncated parsed data | Low | Low |
| 5 | Remove/gate debug constants/log spam | Production hygiene/support clarity | Low | Low |
| 6 | Configurable logging | Operational stability | Low | Low |
| 7 | Lazy/optional VLC | Portability/static reliability | Low | Low |
| 8 | Spectrogram payload validation/fallback | Prevent white/crashed spectrograms | Medium | Medium |
| 9 | Render-cycle error boundary | Better recoverability/debugging | Low-Medium | Medium |
| 10 | Auto-region timestamp optimization | Avoid large-data hangs | Medium | Low-Medium |
| 11 | Configurable timezone | Non-UK correctness | Medium | Medium |
| 12 | Hardcoded path cleanup | Portability | Medium | Low-Medium |
| 13 | Cache architecture simplification | Long-term robustness | Medium-Large | Medium |
| 14 | Undo/redo | Very high UX value | Medium | Medium |
| 15 | Comparison mode completion | Core workflow value | Medium | Medium |
| 16 | Offset workflow UI | Reduces repeated work/errors | Medium | Low-Medium |
| 17 | Shortcut help overlay | Cheap usability win | Low | Low |
| 18 | Spectrogram color legend/fixed scale | Comparison trust | Medium | Low-Medium |
| 19 | Statistical panel/overlays | Analysis value | Medium-Large | Medium |
| 20 | Modular refactors/type checking | Maintainability | Large | Medium-High |

---

## 8. Recommendation Summary

The most useful review is `KimiK2_6` for immediate frontend/data-integrity work, supplemented by `GLM5_1.md` for backend/config/cache/deployment risks. `Deepseek.md` is a useful condensed checklist. `gemini3_1.md` is mostly useful for UX direction but should not be treated as an authoritative bug review.

I would start with offset-aware region metrics/export and comparison metric correctness before any UI redesign or major refactor. Those fixes protect report accuracy. Then clean production debug/logging, make VLC optional, and add spectrogram validation. Only after those correctness and reliability fixes should undo/redo, comparison-mode expansion, offset workflow UI, and larger modular refactors be prioritised.
