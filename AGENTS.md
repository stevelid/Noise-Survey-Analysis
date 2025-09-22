# Noise Survey Analysis — LLM Developer Handbook

This handbook combines all project guidance to help contributors (especially LLMs) quickly understand the Noise Survey Analysis codebase and follow its conventions. The application follows a unidirectional data flow inspired by Redux: the UI is always a function of a central state object.

## 1. Core Architectural Principles
- **Single Source of Truth:** `app.store` is the sole, immutable source of truth for all UI state.
- **State Is Read-Only:** State changes only occur via dispatched actions.
- **Pure State Transitions:** Reducers are pure functions that take the previous state plus an action and return the next state.
- **Strict Separation of Concerns:** Logic is split into distinct layers; each file type has exactly one responsibility.
- **UI State vs. Data Cache:** Maintain the clear separation between lightweight immutable UI state and the mutable, performance-oriented data cache described below.

## 2. Architectural Layers & Responsibilities
All new features must place logic in the correct layer. The flow is: event handler → thunk → actions → reducer → selectors/renderers.

### Event Handlers (`services/eventHandlers.js`) — “Dumb Routers”
- Translate raw UI events into a single, high-level intent (thunk).
- Must be as thin as possible and may normalize events (e.g., `preventDefault`, extracting keys, coercing timestamps) or contain simple, state-free logic (e.g., `if (event.shiftKey)`).
- Must not read application state, branch on business rules, or contain business logic.
- Must dispatch a thunk for any complex logic.

### Thunks (`features/*/*Thunks.js`, aggregated via `thunks.js`) — “Smart Controllers”
- Primary home of business logic and orchestration of complex actions.
- Required for asynchronous logic or logic that reads multiple state slices.
- May perform lightweight reads from `getState()` directly for single values; when coordinating multiple slices or deriving data (e.g., finding a region for a timestamp), use selectors to keep logic reusable and testable.
- Must dispatch simple, semantic actions to reducers. No DOM reads/writes, no chart API calls, and no heavy number crunching here.

### Actions & Action Creators (`core/actions.js`) — “Vocabulary”
- Actions are plain JavaScript objects with a `type` property describing discrete events.
- Action creators are pure functions returning action objects.

### Reducers (`core/rootReducer.js`, `features/.../reducer.js`) — “Pure Accountants”
- Pure `(state, action) => newState` functions with no side effects (no API calls, no nested dispatches).
- Perform immutable updates only (spread syntax, non-mutating helpers) and depend solely on their state slice plus the action payload.
- Contain no derived computation beyond simple field changes.

### Selectors (`selectors.js`, `features/.../selectors.js`) — “Librarians”
- The canonical way to read data from state, returning direct or derived data.
- Must be pure functions that take the full state; thunks and renderers use selectors instead of reaching into the state tree directly.
- Use selectors when data must be derived from multiple state objects.

### Renderers (`services/renderers.js`) — “Dumb Painters”
- Synchronize Bokeh models with the current state by reading data via selectors and updating the UI.
- Must remain dumb: no business logic, no dispatching actions.

## 3. Naming Conventions
Follow consistent naming to make intent obvious:

| Type | Convention | Example |
| --- | --- | --- |
| Selectors | `select<Description>` | `selectSelectedRegion(state)`; `selectRegionsOverTimestamp` |
| Thunks / Intents | `<Verb><Noun>Intent` | `resizeSelectedRegionIntent(payload)`; `handleTapIntent` |
| Action Types | `feature/nounVerb` (past tense for handled events) | `'markers/regionRemoved'`; `'interaction/tapOccurred'`; `'region/replaceAll'` |
| Action Creators | `<noun><Verb>` (past tense) | `regionAdded(payload)`; `regionUpdateBounds(payload)` |
| Event Handlers | `handle<Event>` | `handleKeyPress(e)` |

## 4. UI State (`app.store`) vs. Data Cache (`dataCache`)
### UI State (`app.store`)
- **Purpose:** Single, immutable source of truth for UI configuration and interaction status.
- **Contents:** Lightweight, serializable data (e.g., viewport/zoom, selected parameters such as `LZeq`, UI toggles, user interaction status, audio playback state).
- **Management:** Redux-style pattern handled by `store.js`, `core/actions.js`, and `core/rootReducer.js` plus feature reducers.
- **Key Principle:** State objects are immutable—never mutate them directly; actions produce new state objects for predictability and easy debugging.

### Data Cache (`dataCache`)
- **Purpose:** Store large, non-serializable arrays derived from source data and ready for rendering.
- **Contents:** Heavy structures such as `activeLineData`, `activeSpectralData`, and `_spectrogramCanvasBuffers`.
- **Management:** A single mutable JavaScript object initialized and owned by `app.js`, passed by reference to `data-processors.js` (which mutates it with new slices) and `renderers.js` (which reads it to update charts).
- **Key Principle:** The cache stays mutable to avoid copying large arrays on every state change, ensuring high performance and responsiveness.

## 5. Application Loop (`app.js: onStateChange`)
1. A user interaction dispatches an action.
2. Reducers create a new, lightweight UI state reflecting the change.
3. `onStateChange` triggers in `app.js` due to the state update.
4. `onStateChange` passes the new `state` and persistent `dataCache` to the `data_processors`.
5. `data_processors` read the new viewport from state, compute the correct data slice, and write it into the mutable `dataCache`.
6. `onStateChange` then passes the state plus updated `dataCache` to the renderers.
7. Renderers use state for UI configuration and `dataCache` for chart data updates.

## 6. Spectrogram Data Handling for Bokeh `Image` Glyphs
- **Core Constraint:** The `source.data.image` buffer is fixed-size in the browser—you cannot change its dimensions after initialization. All JavaScript updates must keep the exact same array size.

### Python (`data_processors.py`)
- `prepare_single_spectrogram_data` defines initial spectrogram data.
- Uses `MAX_DATA_SIZE` to set a fixed `chunk_time_length`.
- Pads all spectral data (overview and log) to this `chunk_time_length` before sending to the browser, ensuring consistent `ColumnDataSource` array sizes.

### JavaScript (`data-processors.js`)
- `getTimeChunkFromSerialData` manages zoom-dependent display.
- Extracts slices from the full dataset instead of creating new data sources.
- Uses `MatrixUtils.updateBokehImageData` to overwrite `source.data.image[0]` in place.
- Calls `source.change.emit()` to trigger redraws after in-place updates.

### ColumnDataSource Update Mechanisms in JavaScript
1. **Replacing `.data` entirely:** Use when column lengths (e.g., image dimensions) change. Assign a new object with all column names and matching lengths. `source.change.emit()` is unnecessary afterward.
2. **In-place modifications with `source.change.emit()`:** Use when values change but lengths stay constant. Modify arrays directly (e.g., `source.data['image'][0] = new_typed_array;`) and explicitly call `source.change.emit()`.

### Additional Bokeh Notes
- Bokeh 3.x+ requires 2D NumPy `ndarray` data (JS `TypedArray`s) for `Image`/`ImageRGBA`; older list-of-lists formats are no longer supported.
- `dw` and `dh` define image dimensions in data space; update them with image data changes if display size in data units must change.
- Even for single images, the `image` column remains a list containing the 2D array (e.g., `image=[img]`) to keep `ColumnDataSource` column lengths consistent.
- Common errors:
  - `expected a 2D array, not undefined`: indicates incorrect or missing 2D array (`TypedArray`) in `source.data.image`.
  - Size mismatch errors: occur when column lengths diverge; fix by replacing the entire `.data` dictionary with consistent-length arrays.

## 7. Example Workflow — Ctrl+Click to Delete a Region
1. **User Action:** User holds Ctrl and clicks a region.
2. **Event Handler (`handleTap`):** Normalizes tap event, packages context `{ timestamp, positionId, modifiers: { ctrl: true } }`, and dispatches `handleTapIntent(payload)`.
3. **Thunk (`handleTapIntent`):** Uses selectors (e.g., `selectRegionByTimestamp(state, ...)`) to find the region, checks `modifiers.ctrl`, and dispatches `regionRemoved({ id: region.id })`.
4. **Reducer (`regionsReducer`):** Handles `{ type: 'markers/regionRemoved', ... }`, performs a pure immutable update to remove the region from `state.regions`, and returns the new slice.
5. **Orchestrator (`onStateChange`):** Detects changes to `state.regions` and invokes `renderers.renderRegions(newState)`.
6. **Renderer (`renderRegions`):** Reads the updated region list via a selector, removes the corresponding `BoxAnnotation`, and updates the side panel UI.

By following this handbook, contributors maintain a clean, scalable, and predictable codebase that respects the project’s performance constraints and architectural conventions.
