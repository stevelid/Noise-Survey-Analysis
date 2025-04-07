# Noise Survey Analysis Tool

A tool for loading, analyzing, and visualizing noise survey data from different sound meter models (Noise Sentry, NTi, and Svan).

## Overview

This application provides an interactive dashboard for analyzing noise survey data, with features including:

- Data import from multiple source formats
- Time series visualization of sound levels
- Spectral analysis with spectrograms and frequency distribution charts
- Interactive navigation with synchronized charts
- Audio playback integration with visualization synchronization

## Project Structure

The project has been organized with a modular structure:

```
noise_survey_analysis/
├── core/                    # Core functionality
│   ├── config.py            # Centralized configuration
│   ├── data_loaders.py      # Data import functions
│   ├── data_processors.py   # Data processing utilities
│   └── audio_handler.py     # Audio playback functionality
├── visualization/           # Visualization components
│   ├── interactive.py       # Interactive feature implementation
│   └── ...                  # (More modules to be added in Phase 2)
├── js/                      # JavaScript components
│   ├── callbacks.py         # JavaScript callbacks for interactivity
│   └── ...                  # (More modules to be added in Phase 2)
└── app.py                   # Main application entry point
```

## Usage

### Running the Full Application

To run the application as a Bokeh server:

```
python run_app.py
```

Or use the Bokeh command directly:

```
bokeh serve --show noise_survey_analysis/app.py
```

### Using in Jupyter Notebook / Interactive Mode

The code is structured to support cell-by-cell execution in Jupyter notebooks or IDE cells (like VS Code with Python extension).

```python
# Import required modules
from noise_survey_analysis.core.config import CONFIG
from noise_survey_analysis.core.data_loaders import define_file_paths_and_types, load_data
from noise_survey_analysis.core.data_processors import synchronize_time_range

# Define data files
file_paths = {
    'Position1': 'path/to/file1.csv',
    'Position2': 'path/to/file2.csv'
}
file_types = {
    'Position1': 'sentry',
    'Position2': 'nti'
}

# Load data
file_paths, file_types = define_file_paths_and_types(file_paths, file_types)
position_data = load_data(file_paths, file_types)

# Process data
if CONFIG["chart_settings"]["sync_charts"]:
    position_data = synchronize_time_range(position_data)

# Create and display visualizations
from noise_survey_analysis.app import create_visualizations
from bokeh.io import output_notebook, show
output_notebook()  # For Jupyter notebooks
layout, _, _ = create_visualizations(position_data)
show(layout)
```

## Development Plan

This project is being refactored according to the [Development Plan](DEVELOPMENT_PLAN.md), which outlines:

- Current system analysis
- Identified issues and improvement areas
- Proposed architecture
- Phased refactoring plan
- Risk analysis and mitigation strategies

## Requirements

- Python 3.6+
- Bokeh
- pandas
- numpy
- vlc (for audio playback)

## License

This project is intended for internal use only.

## Acknowledgements

Original code developed for noise survey analysis by Venta Acoustics. 