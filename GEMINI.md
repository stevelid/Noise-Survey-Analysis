# Gemini Development Notes

This file contains important notes and reminders for the Gemini agent to ensure consistency and adherence to key architectural decisions during future development.

## Spectrogram Data Handling for Bokeh `Image` Glyphs

**Core Constraint:** The data source for a Bokeh `Image` glyph (`source.data.image`) is a fixed-size buffer in the browser. You **cannot** change the size of this array after it has been initialized. Any new data sent to update the glyph in JavaScript **must** be the exact same size as the original data array.

### Implementation Details

1.  **Python (`data_processors.py`):**
    *   The `prepare_single_spectrogram_data` function is responsible for creating the initial data for the spectrogram.
    *   It uses a `MAX_DATA_SIZE` constant to define a fixed `chunk_time_length`.
    *   **Crucially, all spectral data (both low-resolution 'overview' and high-resolution 'log' data) is padded to this `chunk_time_length` before being sent to the browser.** This ensures that the JavaScript `ColumnDataSource` is always initialized with a data array of a consistent, predictable size.

2.  **JavaScript (`app.js`):**
    *   The `_updateActiveSpectralData` function handles the dynamic display of data based on zoom level.
    *   When a smaller, high-resolution chunk of data needs to be displayed, it does **not** create a new data source.
    *   It uses `_getTimeChunkFromSerialData` to extract a slice from the full dataset.
    *   It then uses `MatrixUtils.updateBokehImageData` to **overwrite the contents of the existing `source.data.image[0]` array in-place**.
    *   Finally, it calls `source.change.emit()` to trigger a redraw.

**Reminder for Future Changes:** When modifying any part of the spectrogram data pipeline, you must respect this fixed-size buffer constraint. Any changes to the data chunking logic must ensure that the data passed to the `Image` glyph in JavaScript always has the same dimensions as the data it was initialized with.

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
