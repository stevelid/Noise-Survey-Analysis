# Noise Survey Analysis - Development & Refactoring Plan

**(Updated: 2025-03-29)**

## Project Overview

This document outlines the plan for refactoring and enhancing the Noise Survey Analysis codebase. The goals are to improve maintainability, enhance functionality (including easier file input, annotations, data selection/stats, and export), stabilize interactive features, and support both standalone execution and potential future extensions.

## Current System Analysis (Based on Provided Code)

### Core Components

1.  **`core/`**: Handles backend logic.
    * `config.py`: Centralized configuration for file paths, types, metrics, and chart settings.
    * `data_loaders.py`: Manages loading data based on config, calling appropriate parsers, and aggregating results by position. Includes initial directory scanning logic.
    * `data_parsers.py`: Contains parser classes (`NoiseSentryParser`, `SvanParser`, `NTiParser`) for different file formats.
    * `data_processors.py`: Utilities for data manipulation, primarily time range synchronization.
    * `audio_handler.py`: Manages audio playback using `python-vlc`, including synchronization logic and callbacks.
2.  **`visualization/`**: Creates Bokeh visualization objects.
    * `visualization_components.py`: Functions to create specific chart types (time history, log, spectrogram, frequency bar).
    * `interactive.py`: Functions to add interactive elements (range selector, vertical lines, labels) and initialize JavaScript callbacks.
3.  **`js/` & `static/js/`**: Client-side JavaScript for interactivity.
    * `js/loader.py`: Utility to load JS files (potentially simplify/remove).
    * `static/js/*.js`: Actual JavaScript files (`core.js`, `charts.js`, `frequency.js`, `audio.js`) containing logic for hover, tap, keyboard navigation, frequency updates, etc. Relies on global `window` variables and initialization via `DocumentReady`.
4.  **`app.py`**: Main Bokeh application file. Orchestrates data loading, visualization creation, UI widget setup (buttons, dropdown), audio handler integration, and Python/JS callback definitions.
5.  **`run_app.py`**: Simple script to launch the Bokeh server for `app.py`.

### Existing Functionality

* Data import from configured sources (Noise Sentry, NTi, Svan).
* Time series and spectral visualization (image spectrograms, frequency slice bar chart).
* Interactive vertical line linked across charts via hover/tap.
* Basic keyboard navigation (left/right arrows).
* Synchronized audio playback via VLC, linked to visualization time.
* Support for Bokeh server execution.

## Identified Issues and Improvement Areas

1.  **JavaScript Fragility:** The current JS initialization (`initialize_global_js`, `DocumentReady`, `window` variables) is complex and prone to timing issues. Global state management needs improvement.
2.  **Callback Complexity:** Synchronization between Python audio state and JS interactions involves multiple layers of callbacks (`add_next_tick_callback`, `js_on_change`, `on_change`, periodic updates, Python seek handler), making debugging difficult.
3.  **Limited UI/UX:** File input relies on editing `config.py`. No UI for adding annotations or selecting data ranges for analysis exists. Layout is functional but basic.
4.  **State Management:** Application state (current time, active chart, potentially future notes/selections) is handled implicitly, which can become problematic as features grow.
5.  **Lack of Testing:** No automated test suite, increasing the risk of regressions during refactoring or feature additions.
6.  **Hardcoded Paths/Values:** ~~Some values (e.g., `media_path`) are still hardcoded in `app.py`.~~ (Resolved)

## Proposed Architecture (Refinement) -> Implemented Architecture

The application now follows a more modular structure:

1.  **`core/`**: Handles backend logic.
    * `config.py`: Centralized configuration (includes `GENERAL_SETTINGS` with `media_path`).
    * `data_loaders.py`, `data_parsers.py`, `data_processors.py`: Data handling (Largely unchanged structure).
    * `audio_handler.py`: Audio playback class (Unchanged structure).
    * **`app_callbacks.py`**: **NEW:** Defines the `AppCallbacks` class, responsible for handling Bokeh model events (button clicks, source changes) and interacting with `audio_handler`. Includes session cleanup logic.
2.  **`visualization/`**: Creates Bokeh visualization objects.
    * **`components.py`**: **RENAMED** (from `visualization_components.py`): Functions to create individual chart figures/sources.
    * `interactive.py`: Adds interactive elements (lines, hover), sets up JS initialization.
    * **`dashboard.py`**: **NEW:** Contains the `DashboardBuilder` class, orchestrating visualization creation by calling `components.py` and `ui/controls.py`, assembling the layout (Tabs, controls), and managing Bokeh models.
3.  **`ui/`**: **NEW:** Contains UI widget creation logic.
    * `controls.py`: Functions (`create_playback_controls`, `create_parameter_selector`, `create_hover_info_div`) to generate Bokeh widgets.
4.  **`static/js/`**: Client-side JavaScript for interactivity (Structure unchanged, internal logic may need refinement).
5.  **`app.py`**: Main Bokeh application *entry point* and *orchestrator*. Significantly simplified, delegates tasks to `DashboardBuilder` and `AppCallbacks`. Handles initial setup, data loading calls, and connects the main components.
6.  **`run_app.py`**: Script to launch the Bokeh server (Updated to target the `noise_survey_analysis` directory).

Focus areas achieved/in progress:

1.  **Simplifying JS Interaction:** Foundation laid by centralizing model creation in `DashboardBuilder` and callback logic in `AppCallbacks`. Further JS refinement needed.
2.  **Introducing a UI Layer:** Achieved with the `ui/controls.py` module for widget creation.
3.  **Clearer State Handling:** Improved by separating concerns. `AppCallbacks` manages interaction state, `DashboardBuilder` manages visualization models. Explicit `playback_source` and `param_holder` used.
4.  **Robust Callbacks:** Centralized in `AppCallbacks` class, simplifying `app.py`. Includes session cleanup.

## wanted features: 
1. Enhanced File/Directory Input:

-Allow selecting a parent directory instead of manually listing each file path in the config.
Scan the selected directory (and subdirectories) for relevant noise survey files (based on configurable criteria like filename patterns, file types: .csv, .txt, .xlsx, etc., potentially size).
-Present the identified files to the user.
-Allow the user to select which files to include in the analysis.
-Automatically suggest or allow user assignment of "position names" (e.g., based on subfolder names where files are located).

2. Chart Annotation / Note-Taking System:

-Ability to add notes directly linked to specific points in time on the charts.
-Display unobtrusive visual markers on the charts indicating where notes exist.
-Provide an easy-to-use interface for taking notes (e.g., a popup dialog or side panel).
-When creating a note, automatically pre-populate it with relevant context from the chart at the selected time (e.g., timestamp, position name, key sound levels like LAeq, LAF90).
-Define a clear UI trigger to initiate note creation (e.g., button click when the red vertical line is active, right-click menu option on the line, dedicated key press).
-Save the notes persistently, associated with the specific survey data/job folder (e.g., in a JSON or CSV file within that folder).
-Automatically load existing notes for a survey when the data is loaded in a new session.

3. Data Range Selection and Statistical Analysis:

Al-low users to select a specific range of data directly on the time-history charts (e.g., by dragging handles on the range selector, using a box select tool).
-Calculate and display statistical results for the selected data range (e.g., overall LAeq, L10, L90, Lmax for the period).
-Calculate and display the average frequency spectrum for the selected time range.
-Provide an easy way to copy the calculated statistics and spectral data (e.g., formatted text in a display area or <textarea> for easy pasting into reports).
-Potentially integrate the display/copying of these statistics within the note-taking feature for the selected range.

4. Export and Session Management:

-Option to save the current view (charts and layout) as a standalone HTML file (understanding this will be static, without audio or server-side interactivity).
-Explore saving the configuration of a specific analysis session (selected files, chosen views, possibly notes) associated with the job folder.
-Explore functionality to reload a saved session configuration, automatically setting up the Bokeh server with the previously selected files and settings for that specific job.


## Refactoring & Enhancement Plan

### Phase 0: Core Refactoring & Foundation (Completed/In Progress)

1.  **Refactor `app.py`:** Orchestration role achieved. **(Done)**
2.  **Create `DashboardBuilder` (`visualization/dashboard.py`):** Centralized layout and model creation. **(Done)**
3.  **Create `AppCallbacks` (`core/app_callbacks.py`):** Centralized callback logic and state management. **(Done)**
4.  **Create `ui/controls.py`:** Centralized widget creation. **(Done)**
5.  **Configuration Cleanup:** Moved `media_path` to `GENERAL_SETTINGS` in `config.py`. **(Done)**
6.  **Update `run_app.py`:** Targets the application directory. **(Done)**
7.  **Update `DEVELOPMENT_PLAN.md` & `README.md`:** Reflect refactoring. **(Done)**
8.  **JS Management Refinement:** (Ongoing / Next Step)
    * Review `initialize_global_js` and JS files (`static/js/*.js`).
    * Simplify initialization flow. Pass models/data via `args` more explicitly where possible. Reduce `window.*` usage.
    * Improve JS error handling and logging. Verify interactions with refactored Python structure.
9.  **Implement Testing:** (Next Step)
    * Set up `pytest`.
    * Write unit tests for `data_parsers.py`, `data_processors.py`, `audio_handler.py`, `ui/controls.py`.
    * Write integration tests for `DashboardBuilder` and `AppCallbacks`.
    * Write basic integration tests for `app.py` orchestration.

### Phase 1: UI Structure & Enhanced File Input (Addresses New Feature: Directory Input)

1.  **Basic UI Layout:** Refine `app.py` layout (e.g., using `Tabs`, sidebar) for better organization.
2.  **Directory Scanning Logic:** Improve `scan_directory_for_sources` heuristics (subfolder names, file patterns). Add error handling.
3.  **File Selection UI:**
    * Implement UI elements (e.g., Button + `TextInput` or potentially more advanced method) to allow user selection of a survey directory.
    * Add UI to display scanned files/positions and allow user confirmation/selection.
    * Modify `load_and_process_data` to use user selection.

### Phase 2: Annotation / Notes System (Addresses New Feature: Notes)

1.  **Data Model & Storage:**
    * Define note structure (JSON: timestamp, position, text, levels).
    * Implement Python functions (`core/notes_handler.py`?) for saving/loading notes relative to the survey folder.
2.  **Bokeh Integration:**
    * Add `notes_source = ColumnDataSource(...)`.
    * Add glyphs (e.g., `Scatter`) to charts linked to `notes_source` for markers.
3.  **Note Taking UI:**
    * Implement "Make Note" button and associated Python callback.
    * Callback reads current time/position/levels.
    * Implement a modal dialog or panel (e.g., toggled `Div`) with `TextAreaInput`, pre-populated info, and Save/Cancel buttons.
4.  **Saving/Loading:** Implement save logic in callback, update `notes_source`. Load notes on startup.

### Phase 3: Data Range Selection & Statistics (Addresses New Feature: Range Stats)

1.  **Selection Mechanism:** Add `BoxSelectTool` (x-dimension) to time-history charts.
2.  **Callback on Selection:** Implement Python callback triggered by selection changes.
3.  **Statistics Calculation:** Python callback filters data for selected range, calculates overview stats and average spectrum.
4.  **Display Results:** Add a `Div` to layout. Update `Div.text` in callback with formatted stats and copyable spectral data (`<textarea>`).

### Phase 4: Export & Polish (Addresses New Feature: HTML Export & General)

1.  **HTML Export:** Add Button + Python callback using `bokeh.io.save` for static HTML snapshot. *Consider saving session config separately.*
2.  **Code Cleanup:** Refactor complex functions, ensure consistency, address TODOs, improve docstrings.
3.  **Documentation:** Update `README.md`, add code comments. **(Partially Done)**
4.  **UI Polish:** Improve layout, widget appearance, user feedback.
5.  **Performance:** Profile and optimize if needed for large datasets.

## Risk Analysis and Mitigation

### Risk: Breaking existing functionality during refactoring
**Mitigation**: Comprehensive testing (Phase 0). Incremental changes. Frequent commits.

### Risk: JavaScript interaction/timing issues persist
**Mitigation**: Simplify JS initialization (Phase 0). Pass data via `args`. Add robust JS error handling. Test thoroughly across browsers if applicable.

### Risk: UI complexity becomes hard to manage in `app.py`
**Mitigation**: Start simple. If needed, introduce dedicated `ui/` module later. Consider Panel library if advanced widgets are required.

### Risk: Performance bottlenecks with large files or complex interactions
**Mitigation**: Profile during/after feature additions (Phase 4). Optimize data loading (use efficient Pandas operations) and rendering (aggregation if needed).

## Testing Strategy

* **Unit Tests:** Use `pytest` for parsers, processors, core utilities. Mock external dependencies (like VLC).
* **Integration Tests:** Test data loading -> processing -> visualization generation flow. Test callback chains (e.g., button click -> audio handler -> playback source update -> JS update).
* **Manual UI Testing:** Verify chart interactions, file selection, note taking, stats display, audio sync behave as expected.

## Implementation Priorities

1.  **Phase 0:** Core Refactoring **(Largely Done)**, JS Refinement & Testing Setup **(Next)**.
2.  **Phase 1:** File Input UI & Logic.
3.  **Phase 2/3 (Can be parallel):** Notes System / Range Selection & Stats (depending on user need).
4.  **Phase 4:** Export & Polish.

## Development Approach

* **Incremental:** Apply changes phase by phase.
* **Test-Driven:** Write tests before or alongside code changes where practical.
* **Version Control:** Use Git with feature branches.
* **Focus:** Prioritize stability and the requested new features.

## Next Steps

1.  Create development branch (If not already done).
2.  **Review and Refine JS:** Adapt `static/js/*.js` and `visualization/interactive.py::initialize_global_js` to work reliably with the refactored Python structure (models passed via `args`, potentially simplified global state).
3.  **Set up `pytest` infrastructure.**
4.  **Begin implementing Phase 0 Testing tasks.**
5.  Proceed to Phase 1 (Enhanced File Input).

## Additoinal TODOs

- [ ] when selecting a file to load, give the option to ignor spectral data (if log and summary svan files are selected, the log spectral data appears to be prioritized and user may prefer summary spectral data)


