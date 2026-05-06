# Noise Survey Analysis — Deep Dive Review (GLM5_1)

**Date**: 2026-05-05  
**Scope**: Full codebase review — Python backend, JavaScript frontend, UI/UX, architecture, testing, configuration  

---

## Executive Summary

The Noise Survey Analysis dashboard is a sophisticated Bokeh-based application with a well-structured Redux-inspired frontend and a hybrid streaming/static architecture. The codebase demonstrates strong architectural discipline in its state management layer (store → reducers → selectors → renderers). However, there are several categories of issues: **hardcoded configuration that blocks portability**, **security and robustness gaps in the cache/persistence layer**, **performance bottlenecks in the JS data-processing pipeline**, **incomplete UI features**, and **significant technical debt in the Python backend**.

Below is a prioritized list of 30 findings organized by recommended implementation order.

---

## Priority 1 — Bugs & Correctness (Implement Immediately)

### 1. Duplicate `import os` in `data_processors.py`
**File**: `noise_survey_analysis/core/data_processors.py:1-2`  
**Issue**: `import os` appears twice at the top of the file.  
**Fix**: Remove the duplicate line.  
**Impact**: No runtime effect, but signals copy-paste drift and confuses linters.

### 2. Duplicate `load_js_file` function in `dashBuilder.py`
**File**: `noise_survey_analysis/visualization/dashBuilder.py:48,54-60`  
**Issue**: `load_js_file` is imported from `noise_survey_analysis.js.loader` on line 48, then redefined locally on lines 54-60. The local definition shadows the import.  
**Fix**: Remove the local `load_js_file` function definition (lines 54-60).  
**Impact**: If the local version diverges from the imported one, JS loading may break silently.

### 3. Hardcoded `Europe/London` timezone in `_normalize_datetime_column`
**File**: `noise_survey_analysis/core/data_parsers.py:158-161`  
**Issue**: All datetime parsing assumes `Europe/London` timezone with `ambiguous='infer'`. This will silently produce wrong UTC offsets for surveys conducted in other time zones or during DST transitions in regions that don't observe BST/GMT.  
**Fix**: Make the timezone configurable via `config.json` or a per-source `timezone` field. Fall back to `Europe/London` only as a default.  
**Impact**: **Data correctness** — surveys from non-UK locations will have incorrect timestamps.

### 4. Hardcoded paths in `config.py` and `config.json`
**File**: `noise_survey_analysis/core/config.py:128,136,159-188`  
**Issue**: `DEFAULT_BASE_JOB_DIR`, `media_path`, and `DEFAULT_DATA_SOURCES` all contain hardcoded Venta-specific Windows paths (`G:\Shared drives\Venta\...`). These break on any other machine or OS.  
**Fix**:  
- Remove `DEFAULT_DATA_SOURCES` entirely (it's only used as a fallback; the selector/config file is the proper path).  
- Make `DEFAULT_BASE_JOB_DIR` configurable via environment variable or `config.json`.  
- Remove the hardcoded `media_path` — it should come from the source config.  
**Impact**: **Portability** — the app cannot be used by anyone outside Venta's Google Drive setup.

### 5. `DataManagerCache` uses insecure pickle in a predictable temp path
**File**: `noise_survey_analysis/main.py:127-175`  
**Issue**: The `DataManagerCache` singleton writes pickled Python objects to a fixed temp file path (`noise_survey_datamanager_cache.pkl`). This is:  
- **A security risk**: any user on the machine can read/replace the pickle.  
- **A concurrency risk**: multiple Bokeh server processes will collide on the same file.  
- **A staleness risk**: there is no cache invalidation when source files change on disk.  
**Fix**:  
- Use `tempfile.mkstemp()` with a unique suffix per process.  
- Add an mtime/size check on source files before trusting cached data.  
- Consider using `sqlite3` or `shelve` instead of pickle for safer persistence.  
**Impact**: **Security and correctness** — stale or corrupted cache produces wrong dashboards.

### 6. `deepClone` uses `JSON.parse(JSON.stringify())` — loses non-JSON types
**File**: `noise_survey_analysis/static/js/core/rootReducer.js:24-26`  
**Issue**: `deepClone` via `JSON.parse(JSON.stringify())` drops `undefined` values, `NaN`, `Infinity`, `Date` objects, and functions. Since the initial state contains `null` viewport values and numeric fields, this is mostly safe today, but any future state field containing `undefined` will be silently stripped.  
**Fix**: Use `structuredClone()` (available in all modern browsers) or a proper deep-clone utility that preserves `undefined`.  
**Impact**: Silent state corruption if new fields are added that contain `undefined`.

### 7. `onStateChange` may dispatch during rendering (nested dispatch)
**File**: `noise_survey_analysis/static/js/app.js:262-429`  
**Issue**: `onStateChange` calls `app.data_processors.updateActiveData()` and `app.renderers.renderPrimaryCharts()`, which may trigger Bokeh callbacks that dispatch actions (e.g., `VIEWPORT_CHANGE` from range sync). The comment on line 273 acknowledges this risk, and `previousState` is captured early, but the store's listener list is iterated during dispatch, which can cause index corruption in the `listeners` array.  
**Fix**: Buffer dispatched actions during `onStateChange` and flush them after the render cycle completes (similar to Redux batched updates).  
**Impact**: Potential infinite loops or skipped state updates under heavy interaction.

### 8. `collectPositionTimestamps` has verbose `console.log` calls left in production code
**File**: `noise_survey_analysis/static/js/features/regions/regionThunks.js:63-96`  
**Issue**: Six `console.log` / `console.warn` calls with `[collectPositionTimestamps]` prefix are left in production code. These fire on every region creation and will flood the console.  
**Fix**: Remove or gate behind a debug flag.  
**Impact**: Console noise; minor performance impact from string formatting.

### 9. `DEBUG_POSITION` constant left in production JS
**Files**: `data-processors.js:16`, `chart-classes.js:13`  
**Issue**: `const DEBUG_POSITION = 'Residential boundary (971-2, 440 m)'` is a job-specific debug constant that gates `debugSpectrogram()` calls. This is a real job reference leaking into the codebase.  
**Fix**: Remove `DEBUG_POSITION` and `debugSpectrogram()` entirely, or replace with a generic `__DEV__` flag.  
**Impact**: Information leakage; dead code in production.

### 10. `_to_bokeh_ms` is defined identically in three files
**Files**: `core/data_processors.py:23-27`, `core/server_data_handler.py:30-34`, `ui/components.py:63-68`  
**Issue**: The same `_to_bokeh_ms` function is copy-pasted across three modules. Any bug fix or behavior change must be applied three times.  
**Fix**: Move to `core/utils.py` and import from there.  
**Impact**: DRY violation; maintenance burden.

---

## Priority 2 — Performance & Robustness (Implement Soon)

### 11. `downsample_dataframe_max` uses naive binning — can miss peaks
**File**: `noise_survey_analysis/core/data_processors.py:275-299`  
**Issue**: The downsampling function bins rows by time interval and takes the max within each bin. However, for the "Lite" overview data, this means short-duration peaks that straddle a bin boundary may be assigned to the wrong bin or lost. For acoustic data where LAFmax peaks are critical, this is a correctness concern.  
**Fix**: Use a "LTTB" (Largest Triangle Three Buckots) or "min-max" downsampling algorithm that preserves visual peaks. At minimum, ensure the bin alignment is deterministic and document the trade-off.  
**Impact**: **Data accuracy** — peaks may be visually underrepresented in overview mode.

### 12. `updateActiveData` in JS processes all positions even when only one changed
**File**: `noise_survey_analysis/static/js/app.js:330-332`  
**Issue**: On every heavy update, `updateActiveData` reprocesses data for all positions. When only one position's data source has changed (e.g., server pushed a log update for position A), positions B, C, D are also reprocessed unnecessarily.  
**Fix**: Pass the `lastActionType` and `positionId` to `updateActiveData` so it can skip unchanged positions.  
**Impact**: Unnecessary CPU work, especially with 3+ positions at high log rates.

### 13. No requestAnimationFrame batching for renderer calls
**File**: `noise_survey_analysis/static/js/app.js:372-411`  
**Issue**: `renderPrimaryCharts`, `renderFrequencyBar`, `renderOverlays`, `renderControlWidgets`, `renderSidePanel`, `renderMarkers`, `renderRegions` are all called synchronously in sequence within `onStateChange`. Each may trigger Bokeh's internal layout recalculation.  
**Fix**: Batch renderer calls into a single `requestAnimationFrame` callback so Bokeh only recalculates layout once.  
**Impact**: Jank during rapid zooming/panning.

### 14. `store.js` has no middleware support — thunks are handled inline
**File**: `noise_survey_analysis/static/js/store.js:49-56`  
**Issue**: The `dispatch` function has a single special case for function actions (thunks), but there's no middleware pipeline for logging, crash reporting, or debouncing. This makes it hard to add cross-cutting concerns.  
**Fix**: Implement a `applyMiddleware` pattern (like Redux) so thunk support, logging, and crash reporting are composable.  
**Impact**: Extensibility; debugging difficulty.

### 15. `PositionData.__getitem__` uses if/elif chain instead of `getattr`
**File**: `noise_survey_analysis/core/data_manager.py:120-140`  
**Issue**: Dictionary-style access (`position_data['overview_totals']`) goes through a 6-branch if/elif chain. This is fragile — adding a new data attribute requires updating both the `__init__` and `__getitem__`.  
**Fix**: Use `getattr(self, key, None)` with a whitelist, or store data in an internal dict.  
**Impact**: Maintenance burden; easy to forget to update `__getitem__` when adding fields.

### 16. No error boundary around Bokeh model creation in `components.py`
**File**: `noise_survey_analysis/ui/components.py` (3169 lines)  
**Issue**: The 3169-line `components.py` monolith creates Bokeh figures, sources, and widgets. If any single model creation fails (e.g., bad data shape), the entire dashboard build crashes with an unhelpful traceback.  
**Fix**: Wrap each component's `__init__` in try/except with position-specific error messages. Create a fallback "error" Div for failed positions instead of crashing the whole layout.  
**Impact**: Resilience — one bad position shouldn't kill the entire dashboard.

### 17. VLC import is unconditional in `audio_handler.py`
**File**: `noise_survey_analysis/core/audio_handler.py:15`  
**Issue**: `import vlc` at module level will raise `ImportError` on any machine without `python-vlc` installed, even if audio is never used.  
**Fix**: Move to a lazy import inside `__init__` or use a try/except at module level that sets a flag.  
**Impact**: Deployment — the app cannot even generate static HTML on a machine without VLC.

### 18. `SessionBridge` is a process-level singleton but Bokeh creates per-session docs
**File**: `noise_survey_analysis/main.py:32`, `noise_survey_analysis/control/session_bridge.py:22-42`  
**Issue**: `_session_bridge` is a module-level singleton, but `create_app` is called per Bokeh session. When multiple sessions connect, `register()` overwrites the previous session's references. Only the last session is controllable.  
**Fix**: Either make `SessionBridge` session-aware (keyed by session ID), or document that the control server only works with a single active session.  
**Impact**: Multi-session control is broken silently.

---

## Priority 3 — UI/UX Improvements (High Value for Data Review)

### 19. No undo/redo support
**Issue**: Listed in `TODO.txt:18`. Markers, regions, and offset changes are all destructive with no way to revert. For a data review tool, this is a significant usability gap.  
**Fix**: Implement an undo stack in the store. Snapshot state on marker/region add/remove and offset changes. Add keyboard shortcuts (Ctrl+Z / Ctrl+Shift+Z).  
**Impact**: **High UX value** — reduces anxiety about accidental deletions during review.

### 20. Region import/export via CSV
**Issue**: Listed in `TODO.txt:21`. Currently regions exist only in workspace state JSON. Reviewers need to share region definitions (with notes, offsets) across sessions and with colleagues.  
**Fix**: Add "Export Regions" and "Import Regions" buttons. CSV format: `region_id, position_id, start_ms, end_ms, note, color, chart_offset, audio_offset`. Support JSON import for backward compatibility.  
**Impact**: **High workflow value** — enables collaborative review and audit trails.

### 21. No spectral bar chart in the region side panel
**Issue**: Listed in `TODO.txt:62`. When a region is selected, the side panel shows metrics (LAeq, LA90, etc.) but not the average spectrum for that time slice. Reviewers currently have to mentally compare the frequency bar chart at a single timestamp against the region's broadband levels.  
**Fix**: Add a small embedded bar chart (using Bokeh's `figure` with `vbar`) inside the region detail panel that shows the averaged 1/3-octave spectrum for the selected region. The `computeSpectrumAverage` function already exists in `comparison-metrics.js`.  
**Impact**: **Very high UX value** — this is the single most impactful improvement for acoustic analysis workflow.

### 22. Comparison mode spectrum table is nearly empty
**File**: `noise_survey_analysis/static/js/services/renderers.js:146-170`  
**Issue**: `buildComparisonSpectrumTable` only shows "Position" and "Dataset" columns — no actual frequency data. The comparison frequency chart exists but the table below it is a placeholder.  
**Fix**: Populate the table with per-band level differences between positions, or at minimum show the numeric values for each position at key frequencies (e.g., 63 Hz, 250 Hz, 1 kHz, 4 kHz).  
**Impact**: Comparison mode is currently half-functional; this completes it.

### 23. Audio playback speed and boost controls need global application
**Issue**: Listed in `TODO.txt:20`. Currently playback rate and volume boost are per-position controls. During multi-position review, the user has to set these independently for each position.  
**Fix**: Add a "Apply to All" button or a global control that sets rate/boost across all positions simultaneously. Remember the last-used boost state per position.  
**Impact**: Reduces repetitive configuration during multi-position review.

### 24. No visual "grab handles" on regions for resizing
**Issue**: Listed in `TODO.txt:50`. Regions can only be resized by editing start/end values in the side panel. There are no drag handles on the chart overlay.  
**Fix**: Add small triangular/diamond handles at the left and right edges of selected region BoxAnnotations. Use Bokeh's `CustomJS` on drag to dispatch `REGION_UPDATED` actions.  
**Impact**: **High UX value** — direct manipulation is far more intuitive than numeric editing.

### 25. Chart offset controls are buried in audio controls
**Issue**: Listed in `TODO.txt:8`. Chart time offsets (to align positions) are currently in the audio control bar. Users who want to visually align charts without audio still need to interact with audio controls.  
**Fix**: Move chart offset spinner to a per-position header/toolbar above the charts, independent of audio controls.  
**Impact**: Decouples visual alignment from audio workflow.

---

## Priority 4 — Code Quality & Architecture (Medium-Term)

### 26. `components.py` is a 3169-line monolith
**File**: `noise_survey_analysis/ui/components.py`  
**Issue**: All UI component classes (TimeSeriesComponent, SpectrogramComponent, FrequencyBarComponent, ControlsComponent, RangeSelectorComponent, SummaryTableComponent, ComparisonPanelComponent, RegionPanelComponent, MarkerPanelComponent, SidePanelComponent, plus helpers) are in one file.  
**Fix**: Split into `ui/components/` directory with one class per file. Use `__init__.py` to re-export.  
**Impact**: Maintainability; merge conflicts; code navigation.

### 27. `data-processors.js` is a 1515-line monolith
**File**: `noise_survey_analysis/static/js/data-processors.js`  
**Issue**: All data processing logic (line chart updates, spectrogram updates, frequency bar, step size calculation, threshold resolution, offset handling, MatrixUtils) is in one file.  
**Fix**: Split into `data-processors/` directory: `lineProcessor.js`, `spectrogramProcessor.js`, `freqBarProcessor.js`, `matrixUtils.js`, `thresholdResolution.js`.  
**Impact**: Maintainability; testability.

### 28. No TypeScript or JSDoc type definitions for JS modules
**Issue**: The JavaScript codebase uses no type system. Function signatures are documented with JSDoc in some files but not consistently. The `app` global namespace is dynamically assembled, making it impossible for IDEs to provide autocomplete.  
**Fix**: Add `// @ts-check` to key files and maintain a `types.d.ts` that declares the `NoiseSurveyApp` namespace shape. This doesn't require a build step.  
**Impact**: Developer experience; reduces bugs from typos and wrong parameter types.

### 29. Test infrastructure requires non-Google-Drive path
**Issue**: Per `AGENTS.md`, Node-based tests (Vitest, Playwright) must be run from a local non-synced path because Google Drive's file watcher interferes with Node. The `sync_to_dev.ps1` script exists but there's no CI integration.  
**Fix**:  
- Add a `package.json` script that syncs and runs tests in one step.  
- Add a GitHub Actions workflow that checks out the repo and runs both Python and JS tests.  
**Impact**: Test reliability; CI readiness.

### 30. `logging.basicConfig(level=logging.DEBUG)` in `main.py` is too verbose for production
**File**: `noise_survey_analysis/main.py:116`  
**Issue**: The root logger is set to `DEBUG` level unconditionally. This produces massive log output including every cache key comparison (lines 346-386). In production with multiple sessions, this will fill disks.  
**Fix**: Make log level configurable via environment variable (`NOISE_SURVEY_LOG_LEVEL`) or config file. Default to `INFO`.  
**Impact**: Operational — log volume in production.

---

## Summary Table

| # | Category | Title | Impact | Effort |
|---|----------|-------|--------|--------|
| 1 | Bug | Duplicate `import os` | Low | Trivial |
| 2 | Bug | Duplicate `load_js_file` | Medium | Trivial |
| 3 | Bug | Hardcoded Europe/London timezone | High | Medium |
| 4 | Bug | Hardcoded Venta paths | High | Medium |
| 5 | Bug | Insecure pickle cache | High | Medium |
| 6 | Bug | `deepClone` loses undefined | Medium | Low |
| 7 | Bug | Nested dispatch risk | Medium | Medium |
| 8 | Bug | Leftover console.log in regionThunks | Low | Trivial |
| 9 | Bug | DEBUG_POSITION in production JS | Low | Trivial |
| 10 | Bug | `_to_bokeh_ms` triple-defined | Low | Low |
| 11 | Perf | Downsampling misses peaks | High | Medium |
| 12 | Perf | Unnecessary reprocessing of all positions | Medium | Low |
| 13 | Perf | No RAF batching for renderers | Medium | Low |
| 14 | Arch | No store middleware | Medium | Medium |
| 15 | Code | PositionData if/elif chain | Low | Low |
| 16 | Robust | No error boundary in components.py | High | Medium |
| 17 | Bug | Unconditional VLC import | Medium | Trivial |
| 18 | Bug | SessionBridge singleton vs multi-session | Medium | Medium |
| 19 | UX | Undo/redo support | Very High | High |
| 20 | UX | Region import/export CSV | High | Medium |
| 21 | UX | Spectral bar chart in region panel | Very High | Medium |
| 22 | UX | Comparison spectrum table incomplete | High | Low |
| 23 | UX | Global audio rate/boost controls | Medium | Low |
| 24 | UX | Region grab handles for resizing | High | Medium |
| 25 | UX | Chart offsets decoupled from audio | Medium | Low |
| 26 | Code | components.py 3169-line monolith | Medium | Medium |
| 27 | Code | data-processors.js 1515-line monolith | Medium | Medium |
| 28 | Code | No TypeScript/JSDoc types | Medium | Medium |
| 29 | Infra | Test path / CI issues | Medium | Medium |
| 30 | Ops | DEBUG logging in production | Medium | Trivial |

---

## Recommended Implementation Order

**Phase 1 — Quick Wins (1-2 days)**: Items 1, 2, 8, 9, 10, 17, 30  
**Phase 2 — Correctness (3-5 days)**: Items 3, 4, 5, 6, 7, 18  
**Phase 3 — Performance (3-5 days)**: Items 11, 12, 13, 16  
**Phase 4 — High-Value UX (5-8 days)**: Items 19, 20, 21, 22, 24  
**Phase 5 — Architecture (5-8 days)**: Items 14, 15, 26, 27, 28, 29  

Items 23 and 25 can be done at any point as they are self-contained.
