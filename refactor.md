# Noise Survey Analysis - Hybrid Lite + Live Streaming Refactor Plan

## Summary

The dashboard can be slow or unresponsive with high-resolution log data spanning multiple days. We want to keep a standalone, offline HTML export for review, while using local streaming to keep the live app responsive. The server and viewer run on the same machine as a single-user tool.

This refactor introduces a **Hybrid Local-Only architecture** for the Noise Survey Analysis dashboard:

- **Initial live view** uses existing **summary/overview data** (already low resolution).
- **Log data** is the only dataset that is **downsampled/streamed**.
- **Live Mode streaming** pulls high-resolution **log** slices from the **local Python backend** when the user zooms or pans.
- **Single-machine workflow:** server + viewer are always used together; no cloud or remote streaming required.

The goal is **smooth performance for large surveys** without a massive rewrite.

---

## Goals
1. **Fast initial load** for multi-day high-resolution data.
2. **Responsive zoom/pan** by streaming high-res data from backend on demand.
3. **Retain existing UI/JS architecture** with minimal changes.
4. **Static HTML export** remains functional with Lite data.
5. **Never lose original high-resolution log data** in the backend.

## Non-Goals
- No cloud streaming
- No distributed multi-user system
- No large refactor of JS state architecture

---

## Current Bottleneck
The current app uses a **heavy client model**:
- Full datasets are serialized into the browser.
- JS slices large arrays on every viewport change.

This breaks down with large datasets and causes UI freezes.

---

## Proposed Hybrid Architecture
### A) Lite Data
Use existing **summary/overview data** for initial live view. For log data, generate a downsampled
version (e.g. 2,000-5,000 points across the survey). This is:
- Used for **static HTML export** when a log view is needed offline
- Optional fallback when streaming is disabled
- Small and fast to render

### B) Live Streaming (Local)
When the user zooms/pans (log view only):
- Python backend slices the **full resolution log** data
- Downsamples to match the viewport pixel width
- Updates the `ColumnDataSource` directly

---

## Implementation Phases

### Phase 1 - Config + Downsample Helpers
**Files:** `core/config.py`, `core/data_processors.py`

**Add config flags:**
- `LITE_TARGET_POINTS` (e.g. 2000 or 5000)
- `STREAMING_ENABLED` (bool)
- `STREAMING_DEBOUNCE_MS` (e.g. 150–250ms)
- `STREAMING_VIEWPOINT_MULTIPLIER` (e.g. 3x width)

**Downsampling helper (log only):**
- Use `resample().max()` to preserve peak noise events.
- Ensure output matches the expected glyph structure (`prepare_single_spectrogram_data`).

> NOTE: The Lite data must conform to existing Bokeh structures so UI components don't change.

---

### Phase 2 - Initial Render (Summary + Optional Lite Log)
**Files:** `visualization/dashBuilder.py`, `core/data_processors.py`

**Add `server_mode` flag** to `DashBuilder.build_layout`.

Logic:
- **Live Mode:** render **summary/overview** data initially.
- **Log View (Live Mode):** stream high-resolution log slices on demand.
- **Static Export:** include summary data and (optionally) downsampled log data.
- Full resolution log data remains in `DataManager` only.

**Implementation detail:**
- `DashBuilder._prepare_glyph_data` should always use summary/overview data for initial render.
- For log data, choose between:
  - `prepare_downsampled_spectral_data` (static/offline or fallback)
  - streaming via backend (live mode)

---

### Phase 3 - Server-Side Streaming (Log Only)
**Files:** `core/server_data_handler.py`, `core/app_callbacks.py`

**ServerDataHandler responsibilities:**
- Hold full-resolution `DataManager`
- Slice log data by time window
- Downsample log data to viewport width
- Push updates to `ColumnDataSource`

**Core method:**
`handle_range_update(position_id, start_ms, end_ms, plot_width_px)`

Steps:
1. Slice full DataFrame between start/end times.
2. Downsample to `max(LITE_TARGET_POINTS, width * STREAMING_VIEWPOINT_MULTIPLIER)`
3. Convert to glyph format via `prepare_single_spectrogram_data`
4. `source.data = prepared_data['initial_glyph_data']`

**Attach callbacks:**
- Use `x_range.on_change` in `AppCallbacks.attach_non_audio_callbacks`.
- Debounce using `STREAMING_DEBOUNCE_MS`.

---

### Phase 4 - JS Integration (Minimal Changes)
**Files:** `static/js/app.js`, `static/js/data-processors.js`

**Add `server_mode` flag to JS models** (passed from Python).

If `server_mode=true`:
- Skip heavy client slicing for **log** mode in `updateActiveData`.
- Avoid overwriting server-updated log sources in renderers.

**Optional:**
If frequency bar depends on spectral arrays in JS, ensure it can still read from the updated source or add a metadata patch.

---

### Phase 5 - Static Export + Entry Points
**Files:** `main.py`, `export/static_export.py`

- `main.py` should pass `server_mode=True` for live execution.
- `static_export.py` should pass `server_mode=False` + Lite dataset.

---

## Testing Strategy

### Unit Tests
- **Downsampling correctness (log only):**
  - Ensure `resample().max()` preserves peaks
  - Output structure is valid for UI rendering

- **ServerDataHandler slicing:**
  - Proper slicing by time
  - Downsampling scales with viewport width

### Integration Tests (Manual)
1. **Static HTML**
   - Load file quickly
   - View Lite data correctly

2. **Live Mode**
   - Initial load uses summary/overview data
   - Log zoom in triggers high-res updates
   - Log pan updates follow smoothly

### Performance Validation
- Initial load time under 3s
- Smooth zoom/pan (<250ms update)

---

## Acceptance Criteria
- Initial load is fast even for multi-day logs
- Log zooming reveals higher detail
- No freezing or memory spikes
- Static export remains functional
- No major JS refactor

---

## Key Files to Modify

**Python:**
- `core/config.py` (new flags)
- `core/data_processors.py` (Lite downsample method)
- `visualization/dashBuilder.py` (server_mode + summary-first init)
- `core/server_data_handler.py` (streaming handler)
- `core/app_callbacks.py` (x_range hooks)
- `main.py`, `export/static_export.py`

**JavaScript:**
- `static/js/app.js` (skip heavy updates in server mode)
- `static/js/data-processors.js` (server_mode awareness)

---

## Notes for Implementer LLM
- jealously keep the programming ideology and principles such as soc, ddd, and kaa as already implimented. read the readmen, agent files etc to understand what is required. 
- Keep changes minimal; reuse existing structures.
- Avoid large UI refactor.
- Streaming should update only the relevant `ColumnDataSource`.
- Ensure spectrogram image buffers respect Bokeh’s fixed image array size rules.
- Debounce to avoid flooding the backend.

---




