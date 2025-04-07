# Noise Survey Analysis Tool

An interactive Bokeh application for loading, analyzing, and visualizing noise survey data from various sound level meters.

## Overview

This tool provides a dashboard for analyzing noise survey data, featuring:

* Data import from multiple source formats (currently Noise Sentry CSV, NTi TXT, Svan XLSX).
* Configuration via `noise_survey_analysis/core/config.py`.
* Time series visualization of broadband sound levels (e.g., LAeq, LAF90).
* Spectral analysis including image-based spectrograms and interactive frequency slice bar charts.
* Interactive chart navigation: synchronized zooming/panning, hover/tap to inspect data points.
* Keyboard navigation (arrow keys for time stepping, spacebar for play/pause).
* Synchronized audio playback (requires VLC) linked to the visualization timeline.

## Project Structure (Post-Refactoring Target)

├── noise_survey_analysis/
│   ├── core/                 # Core functionality (config, loading, parsing, processing, audio, callbacks)
│   │   ├── __init__.py
│   │   ├── config.py
│   │   ├── data_loaders.py
│   │   ├── data_parsers.py
│   │   ├── data_processors.py
│   │   ├── audio_handler.py
│   │   └── app_callbacks.py    # NEW: Handles Python-side callbacks
│   ├── visualization/        # Bokeh visualization components & orchestration
│   │   ├── __init__.py
│   │   ├── components.py       # RENAMED: Creates individual chart figures/sources
│   │   ├── interactive.py      # Adds interactive elements (lines, hover), JS init setup
│   │   └── dashboard.py        # NEW: Orchestrates viz creation, builds layout
│   ├── ui/                   # NEW: UI Widget Creation
│   │   ├── __init__.py
│   │   └── controls.py         # Functions to create Bokeh widget sets
│   ├── static/js/            # Client-side JavaScript files for interactivity
│   │   ├── core.js
│   │   ├── charts.js
│   │   ├── frequency.js
│   │   └── audio.js
│   ├── __init__.py
│   └── app.py                # Main Bokeh application *entry point* and *orchestrator*
├── tests/                      # Pytest tests (mirroring structure)
│   ├── core/
│   ├── visualization/
│   ├── ui/
│   └── test_app.py
├── DEVELOPMENT_PLAN.md       # Refactoring and enhancement plan
├── README.md                 # This file
└── run_app.py                # Script to run the Bokeh server

## Requirements

* Python 3.8+
* Bokeh (`pip install bokeh`)
* Pandas (`pip install pandas`)
* NumPy (`pip install numpy`)
* python-vlc (`pip install python-vlc`)
* VLC media player (must be installed separately on your system for audio playback)
* `openpyxl` (for reading Svan `.xlsx` files: `pip install openpyxl`)

## Usage

1.  **Configure Data:** Edit `noise_survey_analysis/core/config.py` to define your `DEFAULT_DATA_SOURCES`, specifying the `position_name`, `file_path`, `parser_type`, and `enabled` status for each data file. **TODO:** Move the `media_path` definition from `noise_survey_analysis/app.py` into `config.py`.
2.  **Run the Application:** Execute the `run_app.py` script from your terminal in the project's root directory:
    ```bash
    python run_app.py
    ```
    This will start the Bokeh server and open the application in your default web browser.
3.  **Interact:**
    * Use checkboxes to toggle chart visibility.
    * Use the range selector at the bottom to zoom into specific time periods.
    * Hover over charts to see a vertical line and details (in spectrogram hover div).
    * Click on a chart to set the red vertical line and update the frequency slice chart.
    * Use the playback controls (Play, Pause, Stop, Speed) to listen to audio synchronized with the red line.
    * Use keyboard arrow keys (Left/Right) to step the red line through time.
    * Use the Spacebar to toggle Play/Pause.
    * Use the "Parameter" dropdown (if spectral data is present) to change the spectrogram display.

## Development Plan

This project is undergoing refactoring and enhancement according to the [Development Plan](DEVELOPMENT_PLAN.md). Key goals include:

* Improved code structure and maintainability.
* Improved JavaScript stability and state handling.
* Enhanced file/directory input UI.
* Annotation/note-taking features.
* Data range selection for statistical analysis.
* Static HTML export options.
* Addition of automated tests.

## License

This project is intended for internal use.