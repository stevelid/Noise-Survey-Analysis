# Noise Survey Analysis Tool

An interactive Bokeh application for loading, analyzing, and visualizing noise survey data from various sound level meters.

## Overview

This tool provides a powerful, interactive dashboard for analyzing noise survey data from multiple measurement positions and file types simultaneously. It is designed for performance and interactivity, even with large datasets from manufacturers like Svan, NTi, and Noise Sentry.

## Key Features

*   **Unified Dashboard:** View time history, spectrograms, and frequency data for multiple positions in a single, synchronized view.
*   **Multi-Source Data Import:** Automatically parses and aggregates data from various formats, including NTi `.txt`, Svan `.csv`/`.xlsx`, and Noise Sentry `.csv`.
*   **High-Performance Spectrograms:** Utilizes an efficient rendering strategy for smooth, interactive spectrograms, even with millions of data points.
*   **Synchronized Chart Interaction:**
    *   Pan and zoom on one chart updates all other time-based charts simultaneously.
    *   A global range selector provides a full survey overview for easy navigation.
    *   Hovering over charts shows live data details and a synchronized vertical line.
    *   Clicking on a chart sets a persistent cursor and updates a detailed "Frequency Slice" bar chart.
*   **Synchronized Audio Playback (Live Server Only):**
    *   Listen to `.wav` audio recordings synchronized with the visualization timeline.
    *   Playback seeks automatically when you click on the charts.
    *   Clear visual indicators show which position is currently playing.
    *   Controls for play/pause, playback speed, and a +20dB volume boost for quiet recordings.
*   **Audio File Scanning (Wider Format Support):**
    *   The audio directory scanner now uses `soundfile` (libsndfile) to read durations, enabling support for common formats like WAV, FLAC, OGG, etc. WAV remains supported even without `soundfile`.
*   **Keyboard Navigation:** Use arrow keys for fine-grained time-stepping.
*   **Static HTML Export:** Generate a single, self-contained HTML file of the dashboard for easy sharing and reporting (audio playback is disabled in static mode).

## Getting Started

### 1. Prerequisites

*   Python 3.8+
*   **VLC Media Player:** Must be installed on your system for audio playback to function in the live server mode.
*   `soundfile` Python package (included in `requirements.txt`) to read audio durations for multiple formats. On most platforms, wheels include `libsndfile`.
    *   If you build from source or encounter installation issues, install `libsndfile` via your OS package manager (e.g., `brew install libsndfile` on macOS, `apt-get install libsndfile1` on Debian/Ubuntu). Windows wheels typically bundle it.
*   Install the required Python packages:
    ```bash
    pip install -r requirements.txt
    ```

### 2. Run the Application

You can run the tool in three ways from your terminal:

**A) Live Interactive Server (Recommended)**

This is the primary mode for analysis. It starts a local web server and opens the interactive data source selector.

```bash
bokeh serve noise_survey_analysis --show
```

Your browser will open to the **Data Source Selector**, where you can:
*   **Scan a job directory** by providing a base path and job number.
*   **Drag and drop** data files or folders directly onto the window.
*   Select the files you want to include, assign position names, and load the dashboard.
*   **Save the selection** as a portable configuration file (`.json`) for quick reloading later.

**B) Live Server with a Configuration File**

If you have a previously saved configuration file, you can bypass the selector and load the dashboard directly. This is ideal for quickly revisiting a specific analysis.

```bash
bokeh serve noise_survey_analysis --show --args --config /path/to/your/config.json
```

**C) Generate a Static HTML File**

This mode processes data from a specified configuration file and packages the dashboard into a single `.html` file that you can easily email or archive. Audio playback is disabled in this mode.

```bash
python -m noise_survey_analysis.main --generate-static /path/to/your/config.json
```

This will generate a dashboard HTML file in the same directory as your configuration file.

### 4. Configuration File Format (`.json`)

Configuration files are the most robust way to manage your data selections. They are generated automatically when you click "Save Config" in the Data Source Selector, but you can also edit them manually.

The format is designed to be portable, meaning you can move the config file along with its data, and the application will still be able to find the files.

Here is an example of the `v1.2` format:

```json
{
  "version": "1.2",
  "created_at": "2023-10-27T15:00:00.000000",
  "config_base_path": "C:/Users/YourUser/Documents/NoiseSurveys/Job1234",
  "sources": [
    {
      "path": "Svan/Logs/Position1_data.csv",
      "position": "North",
      "type": "svan_log",
      "parser_type": "svan"
    },
    {
      "path": "Audio/Position1/",
      "position": "North",
      "type": "audio_dir",
      "parser_type": "audio"
    },
    {
      "path": "NTi/Position2_data.txt",
      "position": "East",
      "type": "nti_log",
      "parser_type": "nti"
    }
  ]
}
```

**Key Fields:**

*   `"config_base_path"`: The absolute path to the directory that serves as the root for all relative paths below. This is the key to portability.
*   `"sources"`: A list of data source entries.
*   `"path"`: The path to the data file or directory, relative to the `config_base_path`. The application combines these two paths to find the data.
*   `"position"`: The name for the measurement position that appears in the dashboard.
*   `"parser_type"`: The specific parser to use (`svan`, `nti`, `sentry`, `audio`, or `auto`).

## Project Structure

```
├── noise_survey_analysis/
│   ├── core/                 # Core backend logic
│   │   ├── __init__.py
│   │   ├── app_callbacks.py  # Python-side server callbacks
│   │   ├── app_setup.py      # Logic for loading and preparing configurations
│   │   ├── audio_handler.py  # VLC audio playback logic
│   │   ├── config.py         # Default configuration values
│   │   ├── data_manager.py   # Orchestrates data loading and aggregation
│   │   ├── data_parsers.py   # Parsers for different file formats (Svan, NTi, etc.)
│   │   ├── data_processors.py# Prepares data for complex Bokeh glyphs
│   │   └── utils.py          # Utility functions
│   ├── js/                   # Helper for loading JS code
│   │   └── loader.py
│   ├── static/js/            # Client-side JavaScript for interactivity
│   │   ├── app.js            # Main JS entry point
│   │   ├── core/             # Redux-style primitives (actions, root reducer)
│   │   │   ├── actions.js
│   │   │   └── rootReducer.js
│   │   ├── features/         # Feature-specific reducers, thunks, selectors, utils
│   │   │   ├── audio/
│   │   │   │   ├── audioReducer.js
│   │   │   │   └── audioThunks.js
│   │   │   ├── interaction/
│   │   │   │   ├── interactionReducer.js
│   │   │   │   └── interactionThunks.js
│   │   │   ├── markers/
│   │   │   │   ├── markersReducer.js
│   │   │   │   └── markersSelectors.js
│   │   │   ├── regions/
│   │   │   │   ├── regionReducer.js
│   │   │   │   ├── regionSelectors.js
│   │   │   │   ├── regionThunks.js
│   │   │   │   └── regionUtils.js
│   │   │   └── view/
│   │   │       ├── viewReducer.js
│   │   │       └── viewSelectors.js
│   │   ├── services/         # App-wide services and handlers
│   │   │   ├── eventHandlers.js
│   │   │   └── renderers.js
│   │   ├── chart-classes.js  # OO classes for charts
│   │   ├── data-processors.js# JS data processing (slicing, filtering)
│   │   ├── registry.js       # Registry wiring between models/controllers
│   │   ├── store.js          # Redux-like store implementation
│   │   ├── thunks.js         # Aggregated thunks facade
│   │   └── utils.js          # JS utility functions
│   ├── ui/                   # UI Widget and Component creation
│   │   ├── __init__.py
│   │   ├── components.py
│   │   └── data_source_selector.py # The interactive UI for selecting data
│   ├── visualization/        # Dashboard assembly and orchestration
│   │   ├── __init__.py
│   │   └── dashBuilder.py
│   ├── __init__.py
│   └── main.py               # Main application entry point
├── config.json               # User configuration for data sources
├── README.md                 # This file
└── requirements.txt          # Python dependencies
```

## Core Architectural Concepts

### Data Flow

The application follows a clear, structured data flow:

*   **Application Start (main.py):** The app starts. If a `--config` argument is provided, it loads that file directly. Otherwise, it displays the interactive **Data Source Selector**.
*   **Data Selection (ui/data_source_selector.py):** The user selects files, which generates a source configuration in memory.
*   **Configuration Loading (core/app_setup.py):** The `load_config_and_prepare_sources` function parses the configuration (from file or the selector), resolves file paths, and groups data by position.
*   **Data Management (data_manager.py):** DataManager iterates through the configs. For each file path, it uses NoiseParserFactory to get the correct parser.
*   **Parsing (data_parsers.py):** The appropriate parser (e.g., NTiFileParser) reads a file and converts it into a standardized ParsedData object, separating broadband (totals_df) and spectral (spectral_df) data.
*   **Aggregation (data_manager.py):** DataManager adds the ParsedData to a PositionData object, which aggregates all data for a single measurement position (e.g., merging a log file and a summary file for the same site).
*   **Processing (data_processors.py):** Before visualization, GlyphDataProcessor transforms the raw spectral DataFrames into the specific, pre-padded data structures required by Bokeh's high-performance Image glyph.
*   **Component Creation (components.py):** Classes like TimeSeriesComponent and SpectrogramComponent create the individual Bokeh figures and their ColumnDataSources.
*   **Dashboard Assembly (dashBuilder.py):** DashBuilder orchestrates the entire process: it calls the data processor, instantiates all UI components, assembles them into a final layout, and sets up the JavaScript bridge.

### JavaScript State Management

The front-end interactivity is managed by a self-contained JavaScript application architecture (in `static/js/`). It follows a modern state management pattern similar to Redux:

*   **core/actions.js** defines the global action vocabulary and creators. `store.js` uses **core/rootReducer.js** to combine the feature reducers into the application state tree.
*   **features/** contains isolated slices for each domain (view, interaction, markers, regions, audio). Each feature provides its own reducer, selectors, and thunks so business logic stays modular.
*   **services/eventHandlers.js** listens for Bokeh UI events (e.g., tap, zoom), translates them into semantic thunks, and dispatches them.
*   **data-processors.js** computes derived data (e.g., slicing spectrogram buffers) whenever state changes.
*   **services/renderers.js** consumes the latest state plus derived data to update the visible Bokeh models.

This pattern keeps the code organized, predictable, and easier to debug and extend.

