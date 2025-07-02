
# Architectural Blueprint for Refactoring

This refactoring effort is guided by three core software design principles to ensure a robust, maintainable, and scalable application.

## 1. Guiding Principles

* **Separation of Concerns (SoC):** Each part of the application will have a single, well-defined responsibility. This means a strict separation between data loading, data processing, visual display, and user interaction.
* **Component-Based UI:** The user interface will be constructed from self-contained, reusable components. Each component (e.g., a chart, a set of controls) will manage its own creation and internal state.
* **State-Driven Frontend:** User interactions will not directly modify the JavaScript UI. Instead, interactions will update a central "state" object, and the UI will automatically "render" itself to reflect this new state, establishing a predictable, one-way data flow.

---

## 2. The Python Framework: A Three-Layer System

The Python application will follow OOP principles and be structured into three distinct layers:

### Layer 1: The Data Layer

* **Key Class:** `DataManager`
* **Responsibilities:**
    * Serve as the single point of contact for all data loading and parsing operations.
    * Utilize a `ParserFactory` to select the appropriate parser (e.g., `SvanParser`) for a given file.
    * Call the parser to obtain standardized pandas DataFrames.
    * Aggregate data from multiple files for the same position (e.g., combining log and summary files).
* **Output:** A single, clean Python dictionary (`app_data`) containing all organized, raw data for the application, with no knowledge of Bokeh or charts.

### Layer 2: The Presentation Layer (The View)

* **Key Classes:** `DashboardBuilder`, `TimeSeriesComponent`, `SpectrogramComponent`, `ControlsComponent`, etc.
* **Responsibilities:**
    * **Component Classes (`TimeSeriesComponent`, etc.):** Each component is an expert in building one specific piece of the UI. It receives data, creates its own Bokeh `Figure`, `Glyphs`, and `ColumnDataSource` models, and provides a `.layout()` method that returns the finished Bokeh object.
    * **`DashboardBuilder` (The "Assembler"):** This class orchestrates the entire presentation.
        * It instantiates all necessary components.
        * It performs critical "wiring" between components (e.g., linking the `x_range` of two charts).
        * It assembles the final page layout by calling the `.layout()` method on each component.

### Layer 3: The Control Layer

* **Key Classes:** `AppCallbacks` (Python), `GlyphDataProcessor` (Python), `app.js` (JavaScript)
* **Responsibilities:**
    * **`GlyphDataProcessor`:** A specialized tool used by the `DashboardBuilder`. Its sole purpose is to transform DataFrames into the specific dictionary formats required by complex glyphs, such as the spectrogram's `Image` glyph.
    * **`AppCallbacks`:** Handles backend events sent from the browser (like play/pause requests) and manages server-side processes, such as the `AudioHandler`.
    * **`app.js`:** The frontend controller that responds to user interactions in the browser. The `DashboardBuilder` is responsible for setting up the `CustomJS` callbacks that communicate with this file.

---

## 3. The JavaScript Framework: State-Driven UI

The `app.js` file will be refactored to adhere to a clear, state-driven pattern.

* `_state` **Object:** A single JavaScript object that serves as the **single source of truth** for what the UI should be displaying. It holds information such as:
    * `selectedParameter`: The currently chosen spectral parameter.
    * `viewType`: An object mapping each position to its current view (`'overview'` or `'log'`).
    * `activeSpectralData`: The pre-prepared glyph data for the currently active spectrogram view.
    * `verticalLinePosition`: The timestamp of the red tap line.
* **Controller Functions (`handle...`):** Functions triggered by user events. Their only job is to update the `_state` object. They do **not** directly manipulate the UI.
* **Renderer Functions (`render...`):** Functions whose only job is to read from the `_state` object and update the Bokeh models to match. For example, `renderSpectrogram()` reads from `_state.activeSpectralData` and updates the spectrogram glyph, while `renderFrequencyBar()` reads the active data and updates the bar chart.

the principle will be that the controller is smart with the renderers being dumb. on an action, the controller will update the state from the user action and then call the state updater to do data lookup and update the state. the controller will then call the renderers to update the UI based on the state. the renderers are dumb and only look to the state, with no handling data structures etc. state. The State Updater (_updateActiveData) sits in the middle and handles looking up data from the app_data dictionary and updating the state.

---

## 4. The Flow of Information: Creating a Spectrogram

This section illustrates how all the pieces work together, from start to finish:

1.  **Startup (`main.py`):** The application initiates. `main.py` instantiates the `DataManager` and `DashboardBuilder`.
2.  **Data Loading (`DataManager`):** `main.py` instructs the `DataManager` to load all source files. The `DataManager` parses them and produces the `app_data` dictionary containing raw, but clean, DataFrames.
3.  **Pre-processing (`DashboardBuilder` -> `GlyphDataProcessor`):** The `DashboardBuilder` receives `app_data`. Before building the UI, it instantiates a `GlyphDataProcessor` and calls it to transform the raw spectral DataFrames into the pre-prepared dictionaries needed for the `Image` glyphs.
4.  **Component Creation (`DashboardBuilder` -> `SpectrogramComponent`):** The `DashboardBuilder` instantiates a `SpectrogramComponent`, passing it the pre-prepared glyph data dictionary received from the processor.
5.  **Model Creation (`SpectrogramComponent`):** The `SpectrogramComponent` creates its `Figure`, `ColumnDataSource`, and `Image` glyph, configured with the default view data from the dictionary it was given.
6.  **JS Initialization (`DashboardBuilder`):** After all components are created and wired up, the `DashboardBuilder` assembles the "bridge dictionary." This dictionary contains:
    * References to the Bokeh models (`Figure`, `ColumnDataSource`, etc.).
    * The entire collection of pre-prepared glyph data for all parameters and views.
7.  **Hand-off to Frontend (`app.js`):** This bridge dictionary is passed to the `NoiseSurveyApp.init()` function. `app.js` now possesses all the necessary information to handle future interactions without needing to communicate with the Python backend.

---

## 5. Refactoring Priorities: A Safe, Phased Approach

To implement this new architecture, we will proceed in the following order:

### Phase 1: Solidify the Data Layer (Python) - `COMPLETE`

*   **Status:** The `DataManager` and `PositionData` classes are fully implemented in `noise_survey_analysis/core/data_manager.py`, successfully separating data loading from the rest of the application.

### Phase 2: Implement the Presentation Layer (Python) - `COMPLETE`

*   **Status:** The `DashboardBuilder` in `noise_survey_analysis/visualization/dashBuilder.py` now orchestrates the creation of the UI using a component-based approach as planned. It correctly assembles the layout from individual components.

### Phase 3: Refactor the Control Layer (JavaScript) - `SUBSTANTIALLY COMPLETE`

*   **Status:** `noise_survey_analysis/static/js/app.js` has been successfully restructured to use the state-driven (`_state`, `handle...`, `render...`) pattern. The core client-side logic for interactivity is in place.

### Phase 4: Final Wiring and Server Integration - `NEXT`

*   **Status:** The application currently generates a standalone HTML file (`noise_survey_analysis.html`) from `main.py`. The final step is to transition from this static output to a live Bokeh server.
*   **Next Steps:**
    *   Update `run_app.py` to use the new `DashBuilder` architecture.
    *   Connect the `AppCallbacks` class to handle server-side interactions like audio playback.
    *   Ensure all `CustomJS` callbacks are correctly wired for the live server environment.

---
### JS Example

Here is a detailed, conceptual breakdown of what happens in the JavaScript when a user clicks the toggle to switch from "Overview" to "Log" data for a specific position (e.g., "SW").

The Paradigm: One-Way Data Flow
The core principle is a one-way flow of information:
User Action → Controller → State Update → Renderers → UI Change

Let's trace a single click through this pipeline.

Stage 1: The Event (The Trigger)
Action: The user clicks the toggle button for the "SW" position. It currently says "Switch to Log".
Mechanism: A CustomJS callback, which was attached to that specific button in Python, immediately fires in the browser.
Logic: This callback's only job is to be a bridge. It calls the main application's designated controller function, passing the necessary context.
JavaScript

// The CustomJS call from Python would conceptually be:
window.NoiseSurveyApp.handleToggleClick(true, 'SW', toggle_widget_model);
Stage 2: The Controller (handleToggleClick)
Responsibility: To interpret the user's intent and update the application's central state. It does not directly change any charts.
Logic:
The handleToggleClick(isActive, position, ...) function in app.js is executed.
It sees that isActive is true, so it determines the desired new view is 'log'.
It updates the application's memory of the current view for that position: _state.viewType['SW'] = 'log';
It delegates the complex task of finding the correct data to the central state updater: _updateActiveData('SW', 'log', _state.selectedParameter);
Once the state is updated, it calls the functions responsible for drawing the UI: renderLineChart('SW'); renderSpectrogram('SW');
Stage 3: The State Updater (_updateActiveData)
Responsibility: To be the single source of truth for synchronizing the active data sets with the current state.

Logic:

Line Chart Data: It looks into the master data store (_models.sources) for the key 'SW_log_raw_data' and places that raw data object into the active state holder: _state.activeLineChartData['SW'] = { ...log data... };.
Spectral Data: It looks deep inside the master spectral store (_models.spectralParamCharts) for the data corresponding to position 'SW', view 'spectral_log', and the currently selected parameter (e.g., 'LZeq'). It places this pre-prepared glyph data object into the active state holder: _state.activeSpectralData['SW'] = { ...prepared log data for LZeq... };.
Outcome of this stage: The central _state object is now fully consistent and represents the new desired view. The UI on the screen has not yet changed.

Stage 4: The Renderers (Updating the UI)
Responsibility: These "dumb" functions have one job: read the current _state and make their specific UI component match it.

renderLineChart('SW') is called:

Logic: It reads the new data from _state.activeLineChartData['SW']. It then updates its ColumnDataSource's .data property. It also updates its title to "SW - Log Data".
Mechanism: Setting the .data property on the Bokeh model automatically tells Bokeh to redraw the line chart.
renderSpectrogram('SW') is called:

Logic: It reads the new pre-prepared glyph data from _state.activeSpectralData['SW']. It updates its Image glyph's properties (x, y, dw, dh), its ColumnDataSource's image data, its color mapper, and its title to "SW - LZeq (Spectral Log)".
Mechanism: Updating these properties on the Bokeh models triggers a redraw of the spectrogram.
Stage 5: The Final Result
Within milliseconds of the user's click, they see the fully updated interface:

The time series chart for "SW" now displays the detailed log data.
The spectrogram for "SW" now displays the spectral log data.
The titles for both charts are updated to reflect their new content.
The toggle button's label is updated by its controller to read "Switch to Overview".
This entire process is predictable and easy to debug. If a chart isn't updating correctly, you know the problem is either in its specific render... function or that the central _state wasn't updated correctly by the Controller.