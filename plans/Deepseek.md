# Noise Survey Analysis — Deep Dive Codebase Review

**Date:** 2026-05-05 | **Scope:** Full-stack — Python, JS, UI, architecture, tests

---

## Priority 1 — Critical Bugs & Stability

### 1.1 Duplicate `import os` in `data_processors.py`
**File:** `noise_survey_analysis/core/data_processors.py:1-2` — `import os` appears twice. Remove duplicate.

### 1.2 `load_js_file` defined twice in `dashBuilder.py`
**File:** `noise_survey_analysis/visualization/dashBuilder.py:54-60` — Module-level definition shadows the import from `js.loader` (line 48). Path resolution differs between them. Remove the module-level duplicate.

### 1.3 Hardcoded `Europe/London` timezone in datetime parsing
**File:** `noise_survey_analysis/core/data_parsers.py:154-164` — `_normalize_datetime_column` hardcodes `tz_localize('Europe/London')`. Incorrect for non-UK surveys. Make timezone configurable per source.

### 1.4 `ParsedDataCache.get()` ignores `return_all_columns` parameter
**File:** `noise_survey_analysis/core/parsed_data_cache.py:138-141` — Comment admits the bug. If a file is first cached with `return_all_columns=False`, subsequent requests with `True` get the truncated result. Include in cache key.

### 1.5 `_get_cache_key` — fragile set/list normalization
**File:** `noise_survey_analysis/main.py:198-207` — `file_paths` can be `set` or `list` depending on code path. Normalize at creation point, not at key generation.

### 1.6 `onStateChange` — `previousState` capture pattern is fragile
**File:** `noise_survey_analysis/static/js/app.js:269-274` — If a renderer synchronously triggers a Bokeh callback that dispatches, the nested dispatch sees the wrong `previousState`. Use a stack or clone.

---

## Priority 2 — Performance & Memory

### 2.1 `deepClone` via `JSON.parse(JSON.stringify())` on every init
**File:** `noise_survey_analysis/static/js/core/rootReducer.js:24-26` — Called in `createInitialState()` on every `STATE_REHYDRATED`. Create template once, shallow-copy.

### 2.2 `dataCache` never prunes entries
**File:** `noise_survey_analysis/static/js/app.js:23-28` — Accumulates data per position indefinitely. Add cleanup for non-visible positions.

### 2.3 Spectrogram buffer updates lack dirty checking
**File:** `noise_survey_analysis/static/js/data-processors.js:74-91` — `updateBokehImageData` always overwrites full buffer. Add checksum/timestamp skip.

### 2.4 Python-level loop in `_rasterize_spectrogram_to_fixed_canvas`
**File:** `noise_survey_analysis/core/data_processors.py:262-270` — O(n_freqs × n_times) Python loop. Vectorize with `np.searchsorted`/`np.maximum.at` or use Numba.

### 2.5 Server streaming sends full buffer on every pan
**File:** `noise_survey_analysis/core/server_data_handler.py:131-232` — ~90% overlapping data resent on pan. Implement delta/incremental updates.

---

## Priority 3 — Architecture & Code Quality

### 3.1 Two competing cache layers
`DataManagerCache` (main.py) and `ParsedDataCache` (parsed_data_cache.py) overlap. Consolidate into `ParsedDataCache`; remove `DataManagerCache`.

### 3.2 `PositionData` — inconsistent lazy-load state flags
**File:** `noise_survey_analysis/core/data_manager.py:89-103` — Has `_log_data_loaded` but no spectral equivalent. Add explicit flags for both totals and spectral.

### 3.3 `DashBuilder` — 900+ lines, too many responsibilities
**File:** `noise_survey_analysis/visualization/dashBuilder.py` — Extract data prep into separate class, JS init into `js/loader.py`.

### 3.4 `components.py` — 3,169 lines, monolithic
**File:** `noise_survey_analysis/ui/components.py` — Split into `ui/components/` subdirectory with one file per component.

### 3.5 Inconsistent action type naming
**File:** `noise_survey_analysis/static/js/core/actions.js` — Mix of `domain/actionName` (e.g. `'markers/markerAdded'`) and bare `UPPER_CASE` (e.g. `'TAP'`). Standardize to `domain/actionName`.

### 3.6 `attach_js_callbacks` is a no-op
**File:** `noise_survey_analysis/core/app_callbacks.py:420-421` — Empty method. Implement or remove.

### 3.7 Duplicate `import sys` and `import logging` in `main.py`
Multiple redundant imports (lines 3, 122 for sys; lines 1, 11 in dashBuilder.py for logging). Clean up.

---

## Priority 4 — UI/UX Improvements

### 4.1 No loading progress during lazy data import
Large log files freeze the UI. Add a progress indicator driven by existing `[STREAM PERF]` timing data.

### 4.2 No undo/redo
Redux architecture is ideal for this but it's not implemented. Add undo stack with last N state snapshots.

### 4.3 No keyboard shortcut reference
Users must discover shortcuts (R, Shift+drag, Ctrl+click, arrows) by trial. Add "?" help modal.

### 4.4 No "Show All" / "Hide All" for chart visibility
Requires clicking each checkbox individually. Add bulk toggle buttons.

### 4.5 No dark mode
Light-theme only. Add theme toggle. Bokeh supports `curdoc().theme`.

### 4.6 Region notes — plain text only
No rich text or multi-line preview. Support Markdown with preview toggle.

### 4.7 Comparison mode — single slice only
Support multiple named comparison slices with individual colors.

---

## Priority 5 — Feature Opportunities

### 5.1 Statistical Analysis Panel
Compute L1/L5/L50/L95, exceedance percentages, time-above-curve, histograms for selected regions. **High value, medium effort.**

### 5.2 Automated Report Text Generation
Generate draft report sentences from regions/markers. Export region metrics as CSV. **High value, large effort.**

### 5.3 Audio Waveform View
Synchronized waveform visualization for audio-equipped surveys. **Medium value, medium effort.**

### 5.4 Multi-File Diff View
Load two configs side-by-side for before/after comparisons. **Medium value, medium effort.**

### 5.5 Export Region Audio Clips
Extract and export WAV clips corresponding to selected regions. **Medium value, medium effort.**

### 5.6 Weather Data Overlay
Overlay wind speed/direction, rain from external CSV on the time series. **Medium value, medium effort.**

### 5.7 Calibration Tone Detection
Auto-detect calibration tones in audio and mark them on the timeline. **Low value, large effort.**

### 5.8 Annotations Export/Import
Export markers and regions as JSON for sharing between team members. **Medium value, low effort.**

---

## Priority 6 — Testing Gaps

### 6.1 No Python unit tests for `data_parsers.py` (1,481 lines)
The largest and most critical module has no direct unit tests. Only integration-tested via `test_data_loaders.py`.

### 6.2 No tests for `data_processors.py` rasterization logic
`_rasterize_spectrogram_to_fixed_canvas` and `downsample_dataframe_max` are untested.

### 6.3 No tests for `ServerDataHandler` buffer calculation
`_calculate_buffer`, `_buffer_covers_viewport`, `_spectrogram_chunk_coverage_ratio` are untested.

### 6.4 No E2E tests for static HTML export
The static export path is only manually verified.

### 6.5 JS tests cannot run from Google Drive
Documented limitation. Consider CI/CD setup that copies to local path automatically.

---

## Summary — Recommended Implementation Order

| # | Item | Type | Effort |
|---|------|------|--------|
| 1 | Fix timezone hardcoding (1.3) | Bug | Small |
| 2 | Fix `ParsedDataCache` column bug (1.4) | Bug | Small |
| 3 | Remove duplicate `load_js_file` (1.2) | Bug | Small |
| 4 | Consolidate caches (3.1) | Architecture | Medium |
| 5 | Add loading progress indicator (4.1) | UX | Medium |
| 6 | Add undo/redo (4.2) | Feature | Medium |
| 7 | Split `components.py` (3.4) | Code Quality | Large |
| 8 | Standardize action types (3.5) | Code Quality | Medium |
| 9 | Add keyboard shortcut help (4.3) | UX | Small |
| 10 | Add dark mode (4.5) | UX | Medium |
| 11 | Vectorize rasterization (2.4) | Performance | Medium |
| 12 | Statistical analysis panel (5.1) | Feature | Medium |
| 13 | Report text generation (5.2) | Feature | Large |
| 14 | Multi-slice comparison (4.7) | Feature | Medium |
| 15 | Fill testing gaps (6.1-6.5) | Quality | Large |
