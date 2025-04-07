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
6.  **Hardcoded Paths/Values:** Some values (e.g., `media_path`) are still hardcoded in `app.py`.

## Proposed Architecture (Refinement)

Maintain the modular structure (`core`, `visualization`, `static/js`) but focus on:

1.  **Simplifying JS Interaction:** Reduce reliance on global JS variables and complex initialization. Pass necessary data/models directly via `CustomJS` args where possible. Improve error handling.
2.  **Introducing a UI Layer:** Gradually add UI components for new features (file selection, notes panel, stats display) possibly within `app.py` initially, or a dedicated `ui/` module later if complexity warrants it.
3.  **Clearer State Handling:** Make application state (like selected files, current time, active notes) more explicit, possibly using dedicated Bokeh models or simple Python state variables managed within `app.py`.
4.  **Robust Callbacks:** Simplify the Python <-> JS callback chain where possible, potentially using `CustomJS` more for client-side actions to avoid unnecessary Python round-trips.

## Refactoring & Enhancement Plan

### Phase 0: Stabilization & Foundation (Update/Refine Existing Plan's Phase 1)

1.  **Update `DEVELOPMENT_PLAN.md`:** (This document) Reflect current code state, integrate new features, adjust phases.
2.  **Implement Testing:**
    * Set up `pytest`.
    * Write unit tests for `data_parsers.py`.
    * Write unit tests for key functions in `data_processors.py`, `audio_handler.py`.
    * Write basic integration tests for `app.py` loading default data.
3.  **JS Management Refinement:**
    * Consolidate all JS code into `static/js/` files.
    * Simplify `initialize_global_js` and initialization flow. Pass models/data via `args` more explicitly. Reduce `window.*` usage.
    * Improve JS error handling and logging.
4.  **Configuration Cleanup:** Move any remaining hardcoded paths/values from `app.py` to `config.py` or handle dynamically.

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
3.  **Documentation:** Update `README.md`, add code comments.
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

1.  **Phase 0:** Stabilization, Testing Setup, JS Cleanup.
2.  **Phase 1:** File Input UI & Logic.
3.  **Phase 2/3 (Can be parallel):** Notes System / Range Selection & Stats (depending on user need).
4.  **Phase 4:** Export & Polish.

## Development Approach

* **Incremental:** Apply changes phase by phase.
* **Test-Driven:** Write tests before or alongside code changes where practical.
* **Version Control:** Use Git with feature branches.
* **Focus:** Prioritize stability and the requested new features.

## Next Steps

1.  Create development branch.
2.  Set up `pytest` infrastructure.
3.  Begin implementing Phase 0 tasks (JS cleanup, testing, config review).