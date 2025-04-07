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

## Data and Visualization Model Structures

### Data Loading Structure (`position_data`)

The application loads data through the `load_and_process_data()` function in `data_loaders.py`, which returns a dictionary with the following structure:

```
{
    'Position1': {
        'overview': DataFrame,    # Time series data for broadband metrics (LAeq, LAF90, etc.)
        'spectral': DataFrame,    # Spectral data with frequency bands
        'log': DataFrame,         # Detailed logging data with timestamps
        'spectral_log': DataFrame, # Logged spectral data
        'audio': '/path/to/audio.wav',  # Path to associated audio file
        'metadata': {
            'parser_type': 'sentry|nti|svan',
            'original_path': '/path/to/original/file.csv',
            'audio_path': '/path/to/audio/directory',
            'RPT': {...},         # Specific metadata from RPT parser
            'RTA': {...},         # Specific metadata from RTA parser
            'audio': {...}        # Audio file metadata
        }
    },
    'Position2': { ... }
}
```

### Bokeh Models Dictionary (`bokeh_models`)

The application has transitioned from a flat to a hierarchical structure for `bokeh_models` using an adapter pattern to maintain backward compatibility while encouraging better organization. The `DashboardBuilder` class maintains this dictionary for all Bokeh objects.

#### Legacy Flat Structure (Backward Compatible)

```
{
    # Charts and Sources
    'all_charts': [],                  # List of all Bokeh Figure objects
    'time_series_charts': [],          # Charts with a time-based x-axis 
    'all_sources': {},                 # Dictionary of {source_key: ColumnDataSource}
    'position_elements': {},           # UI elements organized by position
    
    # Interactive Elements
    'click_lines': {},                 # Vertical lines for clicked positions
    'labels': {},                      # Text labels for data at clicked positions
    'range_selectors': {},             # Range selectors for zooming time series
    'playback_source': None,           # Data source for playback position
    'seek_command_source': None,       # Source for sending seek commands
    'play_request_source': None,       # Source for play requests from JS
    
    # UI Controls
    'playback_controls': {},           # Play/pause buttons
    'param_select': None,              # Dropdown for spectral parameter selection
    'param_holder': None,              # Hidden Div holding selected parameter
    
    # Frequency Analysis
    'freq_bar_chart': None,            # Frequency bar chart
    'freq_bar_source': None,           # Data source for frequency bar chart
    'freq_bar_x_range': None,          # X range for frequency bar chart
    'freq_table_source': None,         # Source for frequency data table
    
    # Spectral Data
    'spectral_param_charts': {         # Position and parameter specific data
        'position': {
            'available_params': [...],  # List of available params
            'current_param': 'LZeq',    # Currently selected param
            'prepared_data': {          # Pre-processed data by param
                'LZeq': {
                    'frequencies': ndarray,     # Array of frequency values (e.g. [25, 31.5, 40, ...])
                    'frequency_labels': list,   # List of formatted frequency labels (e.g. ["25 Hz", "31.5 Hz", ...])
                    'times_ms': ndarray,        # Array of timestamps in milliseconds (epoch time)
                    'times_dt': ndarray,        # Array of datetime64 objects
                    'levels_matrix': ndarray,   # 2D matrix of sound levels in shape (n_times, n_freqs)
                    'levels_matrix_transposed': ndarray, # Transposed matrix (n_freqs, n_times) for Bokeh image glyph
                    'freq_indices': ndarray,    # Array of frequency indices [0, 1, 2, ...]
                    'min_val': float,           # Minimum level value for color mapping
                    'max_val': float,           # Maximum level value for color mapping
                    'n_times': int,             # Number of time points
                    'n_freqs': int,             # Number of frequency bands
                    'x': float,                 # X coordinate for Bokeh image glyph (start time)
                    'y': float,                 # Y coordinate for Bokeh image glyph (typically -0.5)
                    'dw': float,                # Width for Bokeh image glyph (time span)
                    'dh': float                 # Height for Bokeh image glyph (frequency span)
                },
                'LAF90': { ... }
            }
        }
    },
    
    # JavaScript Integration
    'charts_for_js': [],              # Charts that need JS interactions
    'init_js_button': None            # Button to manually initialize JS if needed
}
```

#### New Hierarchical Structure (Preferred)

```
{
    'charts': {
        'all': [],                    # All Bokeh Figure objects
        'time_series': [],            # Time-based charts for synchronization
        'for_js_interaction': []      # Charts requiring JS callbacks
    },
    
    'sources': {
        'data': {},                   # Main data sources by key
        'playback': {                 # Playback-related sources
            'position': None,         # Current playback position 
            'seek_command': None,     # For sending seek commands
            'play_request': None      # For play requests from JS
        },
        'frequency': {                # Frequency analysis sources
            'bar': None,              # For frequency bar chart
            'table': None             # For frequency data table
        }
    },
    
    'ui': {
        'position_elements': {},      # UI elements by position
        'controls': {                 # UI controls
            'playback': {},           # Play/pause buttons
            'parameter': {            # Parameter selection
                'select': None,       # Dropdown for parameter selection
                'holder': None        # Hidden div for selected parameter
            },
            'init_js': None           # Button to initialize JS
        },
        'visualization': {            # Visual elements
            'click_lines': {},        # Vertical lines for clicked positions
            'labels': {},             # Text labels for data points
            'range_selectors': {}     # Range selectors for zooming
        }
    },
    
    'frequency_analysis': {           # Frequency analysis components 
        'bar_chart': {                # Bar chart components
            'figure': None,           # The bar chart figure
            'x_range': None           # X range for the chart
        }
    },
    
    'spectral_data': {                # Spectral data by position
        'position': {
            'available_params': [],   # Available spectral parameters
            'current_param': 'LZeq',  # Currently selected parameter
            'prepared_data': {        # Pre-processed data by parameter
                'param_name': {       # Same detailed structure as shown in legacy version
                    'frequencies': ndarray,
                    // Additional fields as above
                }
            }
        }
    }
}
```

The `BokehModelsAdapter` class manages this transition, providing backward compatibility by logging warnings when legacy keys are accessed, helping identify code that needs updating to the new structure.

#### Using the Hierarchical Structure

The application includes adapter classes to support a gradual transition from the flat to hierarchical structure:

**Python Example**:
```python
# Access the data with the new structure
# These are equivalent:
old_style = builder.bokeh_models['all_charts']          # Legacy access
new_style = builder.bokeh_models['charts']['all']       # New hierarchical access

# Creating a frequency chart
chart, source = create_frequency_bar_chart()
builder.bokeh_models['frequency_analysis']['bar_chart']['figure'] = chart  # New way
builder.bokeh_models['freq_bar_source'] = source                           # Legacy way also works

# Access spectral data for a position 
param_data = builder.bokeh_models['spectral_data']['NE']['prepared_data']['LZeq']
```

**JavaScript Example**:
```javascript
// The JS initialization has been updated to handle both structures
function initializeApp(models, options) {
    // Check if using new structure
    const usingHierarchicalStructure = models.hierarchical === true;
    
    // Updated initialization logic for either structure
    _models.charts = models.charts || [];
    _models.sources = models.sources || {};
    _models.barChart = models.barChart || models.charts.find(c => c?.name === 'frequency_bar');
    
    console.log(`Using ${usingHierarchicalStructure ? 'hierarchical' : 'legacy'} structure`);
    // ... rest of initialization
}
```

The adapter class (`BokehModelsAdapter`) displays warning logs when legacy keys are accessed, helping identify code that needs updating while maintaining backward compatibility during the transition.

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