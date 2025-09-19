# Development Notes

This file contains important notes and reminders for future development.

## JavaScript Architecture: State vs. Data Cache

The front-end application is architected around a clear separation between **UI State** and a **Data Cache**. This design is critical for maintaining performance, especially when handling large datasets like time series and spectrograms. It should avoid changes to the shape of the data to feed into the glyph (See below).

### principles

**Handlers** (router-only): may normalise the raw event (preventDefault, extract keys, coerce timestamps) but must not read state or branch on business rules.

**Thunks** (feature logic only): no DOM reads/writes, no chart API calls, no heavy number crunching. They read state, make decisions, and dispatch semantic actions.

**Reducers** (accountants): pure, synchronous, immutable, no derived computation beyond simple field changes.

**Selectors** (derive data from state): when data is derived from different state objects, use selectors. Not needed for direct state access.

### Naming Conventions
* Selectors: select<DerivedDataDescription> (e.g. selectRegionsOverTimestamp)
* Thunks / Intents: <Verb><Noun>Intent (e.g. resizeSelectedRegionIntent, handleTapIntent) 
* Action Types: "feature/nounVerb" (e.g. "interaction/tapOccurred", "region/replaceAll"). n.b past tense for handled events
* Action Creators: <noun><Verb> (e.g. tapOccurred(payload), regionUpdateBounds(payload))
* Event Handlers: handle<UIEventDescription> (e.g. handleKeyPress(e))

### UI State (`app.store`)

*   **Purpose:** To be the single, immutable source of truth for the *UI's configuration and interaction status*.
*   **Contents:** Lightweight, serializable data. This includes things like:
    *   Current viewport (zoom level).
    *   Selected parameters (e.g., 'LZeq').
    *   UI toggles (e.g., Log/Overview view, chart visibility).
    *   User interaction status (tap timestamp, hover position).
    *   Audio playback status.
*   **Management:** Handled by a Redux-style pattern.
    *   **`store.js`:** Creates the store.
    *   **`actions.js`:** Defines all possible state changes.
    *   **`reducers.js`:** Pure functions that compute the next state.
*   **Key Principle:** The state object is considered **immutable**. It is never modified directly. Actions produce a new state object, ensuring predictable state transitions. This makes debugging straightforward.

### Data Cache (`dataCache`)

*   **Purpose:** To hold large, non-serializable data arrays that are derived from the original source data and are ready for rendering.
*   **Contents:** Heavy data structures that are expensive to copy. This includes:
    *   `activeLineData`: The currently visible slice of time series data.
    *   `activeSpectralData`: The currently visible slice of spectrogram data.
    *   `_spectrogramCanvasBuffers`: Reusable buffers for efficient spectrogram rendering.
*   **Management:**
    *   The `dataCache` is a single, **mutable** JavaScript object.
    *   It is initialized and "owned" by the main `app.js` orchestrator.
    *   It is passed by reference to `data-processors.js` (which mutates it with new data slices) and `renderers.js` (which reads from it to update the charts).
*   **Key Principle:** The `dataCache` is intentionally **mutable** to avoid the massive performance overhead of copying large arrays on every state change (e.g., every pan or zoom). By mutating the contents of the cache directly, we achieve high performance and a responsive UI.

### The Application Loop (`app.js: onStateChange`)

The core application loop demonstrates how these two concepts work together:
1.  A user interaction (e.g., zoom) dispatches an **action**.
2.  The **reducer** creates a new, lightweight **UI State** object reflecting the new zoom level.
3.  The `onStateChange` subscriber in `app.js` is triggered by the state update.
4.  `onStateChange` passes the new `state` object and the persistent `dataCache` object to the `data_processors`.
5.  The `data_processors` read the new viewport from the `state` and use it to calculate the correct data slice, which they then write into the **mutable `dataCache`**.
6.  `onStateChange` then passes the `state` and the now-updated `dataCache` to the `renderers`.
7.  The `renderers` read from both sources: they use the `state` to configure UI elements (like titles and visibility) and the `dataCache` to update the data in the chart sources.

This separation provides the best of both worlds: the predictability of immutable state for UI logic and the high performance of mutable data handling for large datasets.

## Spectrogram Data Handling for Bokeh `Image` Glyphs

**Core Constraint:** The data source for a Bokeh `Image` glyph (`source.data.image`) is a fixed-size buffer in the browser. You **cannot** change the size of this array after it has been initialized. Any new data sent to update the glyph in JavaScript **must** be the exact same size as the original data array.

### Implementation Details

1.  **Python (`data_processors.py`):**
    *   The `prepare_single_spectrogram_data` function is responsible for creating the initial data for the spectrogram.
    *   It uses a `MAX_DATA_SIZE` constant to define a fixed `chunk_time_length`.
    *   **Crucially, all spectral data (both low-resolution 'overview' and high-resolution 'log' data) is padded to this `chunk_time_length` before being sent to the browser.** This ensures that the JavaScript `ColumnDataSource` is always initialized with a data array of a consistent, predictable size.

2.  **JavaScript (`data-processors.js`):**
    *   The `getTimeChunkFromSerialData` function handles the dynamic display of data based on zoom level.
    *   When a smaller, high-resolution chunk of data needs to be displayed, it does **not** create a new data source.
    *   It extracts a slice from the full dataset.
    *   It then uses `MatrixUtils.updateBokehImageData` to **overwrite the contents of the existing `source.data.image[0]` array in-place**.
    *   Finally, it calls `source.change.emit()` to trigger a redraw.

**Reminder for Future Changes:** When modifying any part of the spectrogram data pipeline, you must respect this fixed-size buffer constraint. Any changes to the data chunking logic must ensure that the data passed to the `Image` glyph in JavaScript always has the same dimensions as the data it was initialized with.

## JavaScript State Management

The front-end interactivity is managed by a self-contained JavaScript application architecture (in static/js/). It follows a modern state management pattern similar to Redux:

*   **store.js:** Holds the single source of truth for the UI state. The `dispatch` function is the only way to modify the state.
*   **actions.js:** Defines the actions that can be dispatched to modify the state.
*   **reducers.js:** Specifies how the application's state changes in response to actions.
*   **event-handlers.js:** Listens for Bokeh UI events (e.g., tap, zoom), translates them into semantic actions (e.g., { type: 'TAP', payload: ... }), and dispatches them.
*   **data-processors.js:** When the state changes, these functions compute the derived data needed for the charts (e.g., slicing the correct chunk of spectrogram data).
*   **renderers.js:** These functions take the new state and derived data and update the Bokeh models to change what the user sees on screen.

This pattern keeps the code organized, predictable, and easier to debug and extend.

## Additional Notes on Bokeh Image Glyphs and ColumnDataSource

To further clarify the behavior and requirements of Bokeh's `Image` glyphs and `ColumnDataSource` when handling dynamic data, especially for spectrograms:

### Bokeh Image Data Format (Bokeh 3.x+)
-   Bokeh 3.x and later strictly require 2D NumPy `ndarray` data for `ImageGlyph` (and `ImageRGBA`). This translates to JavaScript `TypedArray`s (e.g., `Float64Array`, `Uint32Array`) on the client side.
-   The older "lists of lists" (e.g., `[[row1_pixel1, row1_pixel2], ...]`) format is no longer supported for dynamic updates. This is a critical breaking change from pre-3.x versions.

### ColumnDataSource Update Mechanisms in JavaScript
There are two primary methods for updating `ColumnDataSource` data via JavaScript, each suited for different scenarios:

1.  **Replacing the entire `.data` property:**
    -   **When to use:** When the underlying data for a glyph changes in a way that alters the *length* of its columns (e.g., an image changing from 100x100 pixels to 200x200 pixels, implying a new total number of pixels). This is necessary if the *dimensions* of the image data change.
    -   **How:** Assign an entirely new JavaScript object to its `.data` property (e.g., `source.data = new_dict;`). This `new_dict` must contain all original column names, and the arrays for each column must all have the same new length.
    -   **`source.change.emit()`:** *Not* required after this operation, as BokehJS automatically detects the change.

2.  **Modifying data in-place with `source.change.emit()`:**
    -   **When to use:** If modifications are made to the *values* within an existing data array in a `ColumnDataSource` *without changing its length* (e.g., updating pixel values of an image that retains its 100x100 dimensions). This is the method currently employed for spectrogram updates.
    -   **How:** Modify the array directly (e.g., `source.data['image'][0] = new_typed_array;`).
    -   **`source.change.emit()`:** *Essential* to explicitly notify BokehJS to redraw the plot after in-place modifications.

### `dw` and `dh`: Dimensions in Data Space
-   For `ImageGlyph` and `ImageRGBA`, the properties `dw` and `dh` define the width and height of the image in the plot's *data coordinates*, not in pixels.
-   `dw` and `dh` control how large the image appears on the plot relative to the plot's x and y axes ranges. They should be updated in conjunction with image data changes if the desired display size in data units changes.

### "List of Array" Convention for Single Images
-   Even when displaying a single image, the `image` column in `ColumnDataSource` is consistently represented as a list containing the 2D array (e.g., `image=[img]`).
-   This is a design choice to maintain the `ColumnDataSource`'s strict "all columns must have the same length" rule. By wrapping the 2D image array in a list, the `image` column itself becomes an array of length 1, aligning its length with `x`, `y`, `dw`, `dh` (which are also arrays of length 1 for a single image). Adhering to this convention is crucial to avoid "Size mismatch" errors.

### Common Errors
-   `'expected a 2D array, not undefined'`: Often indicates that the `image` field within `source.data` is not conforming to the expected 2D array format (i.e., a `TypedArray` representing a 2D array) or is missing.
-   `'Size mismatch errors'`: Occurs when violating the `ColumnDataSource`'s rule that all columns must have the same length. This typically happens when updating a subset of columns or when new data for one column has a different length than existing data in other columns. The solution is to replace the entire `source.data` dictionary with a new one where all columns have consistent lengths.