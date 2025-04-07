# Noise Survey Analysis - Development & Refactoring Plan

## Project Overview

This document outlines the plan for refactoring the Noise Survey Analysis codebase to improve maintainability, enhance functionality, and support both Jupyter notebook-style cell execution and full application execution modes.

## Current System Analysis

### Core Components

1. **plot_analysis.py**: Main orchestration file with data loading, processing, and visualization functions
2. **js_callbacks.py**: JavaScript callback functions for interactive visualization features
3. **visualization_components.py**: Chart creation and configuration components

### Existing Functionality

- Data import from multiple source formats (Noise Sentry, NTi, Svan)
- Time series visualization of sound levels
- Spectral analysis with spectrograms and frequency distribution charts
- Interactive navigation with synchronized charts
- Audio playback integration with visualization synchronization
- Support for both cell-by-cell and full application execution

## Detailed Component Analysis

### Data Import and Parsing
- **Purpose**: Loads noise survey data from different file formats
- **Key Functions**: 
  - `read_in_noise_sentry_file()` - Parses Noise Sentry CSV files
  - `read_in_Svan_file()` - Parses Svan XLSX files
  - `read_NTi()` - Parses NTi audio data files
- **Current Implementation**: Invoked through `load_data()` function with file type selection

### Data Processing
- **Purpose**: Prepares and aligns data from different sources
- **Key Functions**:
  - `get_common_time_range()` - Identifies time overlaps between different data sources
  - `filter_by_time_range()` - Filters data to focus on specific time periods
  - `synchronize_time_range()` - Ensures all visualizations use the same time scale

### Visualization Components
- **Purpose**: Creates interactive charts for data exploration
- **Key Functions**:
  - `create_TH_chart()` - Creates time-history charts for sound level metrics
  - `create_log_chart()` - Creates logging data charts
  - `make_spectrogram()` / `make_rec_spectrogram()` - Creates spectral visualizations
  - `create_frequency_bar_chart()` - Shows frequency distribution at selected points

### Interactive Features
- **Purpose**: Enables user interaction with visualizations
- **Key Components**:
  - JavaScript callbacks for hover, click, and keyboard navigation
  - Vertical line synchronization between charts
  - Chart visibility toggles via checkboxes
  - Parameter selection for spectrograms

### Audio Integration
- **Purpose**: Syncs audio playback with visualizations
- **Key Components**:
  - `AudioPlaybackHandler` class manages VLC-based audio playback
  - Tap events on charts for time-based navigation
  - Periodic callback to update UI during playback

## Identified Issues and Improvement Areas

1. **Code Structure and Maintainability**
   - Cell-based structure makes code flow difficult to follow
   - Function responsibilities overlap between files
   - Configuration settings are scattered throughout the code

2. **JavaScript Integration**
   - `get_common_utility_functions()` initialization timing issues
   - Lack of clear documentation for JavaScript callback interactions
   - Global variables in JavaScript may cause issues with multiple instances

3. **User Interface**
   - Need for file selection functionality
   - Layout improvements for better usability
   - More intuitive chart selection and configuration

4. **Data Handling**
   - Support for additional data types and formats
   - Better synchronization between different data sources
   - More efficient processing of large datasets

## Proposed Architecture

### New Module Structure

```
noise_survey_analysis/
├── __init__.py
├── core/
│   ├── __init__.py
│   ├── config.py              # Centralized configuration
│   ├── data_loaders.py        # Data import functions
│   ├── data_processors.py     # Data processing utilities
│   └── audio_handler.py       # Audio playback functionality
├── visualization/
│   ├── __init__.py
│   ├── chart_factory.py       # Chart creation functions
│   ├── interactive.py         # Interactive feature implementation
│   └── layouts.py             # Layout management
├── ui/
│   ├── __init__.py
│   ├── file_selector.py       # File selection UI
│   ├── chart_controls.py      # UI for manipulating charts
│   └── playback_controls.py   # Audio playback UI
├── js/
│   ├── common.js              # Common utility functions
│   ├── hover.js               # Hover interaction code
│   ├── navigation.js          # Keyboard navigation
│   └── update.js              # Chart update functionality
└── app.py                     # Main application entry point
```

### Key Architectural Improvements

1. **Separation of Concerns**:
   - Clear distinction between data handling, visualization, and UI
   - Configuration centralized in one location
   - JavaScript isolated in separate files for better maintainability

2. **Class-Based Design**:
   - `DataSource` classes for different data types
   - `ChartBuilder` class hierarchy for different visualization types
   - `VisualizationManager` to coordinate chart interactions

3. **Event-Driven Architecture**:
   - Publish-subscribe pattern for communication between components
   - Clear separation between UI events and data updates

4. **Support for Both Execution Modes**:
   - Factory functions that work in both notebook and application contexts
   - Jupyter notebook helpers for cell-by-cell execution
   - Application-level orchestration for full execution

## Refactoring Plan

### Phase 1: Foundation (Weeks 1-2)

#### Tasks:
1. Set up development environment and branching strategy
2. Create comprehensive tests for existing functionality
3. Implement new module structure
4. Move configuration to centralized location
5. Refactor JavaScript to ensure proper initialization

#### Deliverables:
- Basic test suite covering core functionality
- Initial reorganized codebase with clear separation of concerns
- Consistent configuration mechanism
- Properly scoped JavaScript with explicit initialization

### Phase 2: Core Functionality (Weeks 3-4)

#### Tasks:
1. Implement class-based design for data sources
2. Develop chart builders for different visualization types
3. Create visualization manager for chart coordination
4. Improve data processing pipeline
5. Add file selection UI

#### Deliverables:
- Refactored data handling components
- Improved visualization creation system
- Basic file selection interface
- Enhanced data processing capabilities

### Phase 3: Interactive Features (Weeks 5-6)

#### Tasks:
1. Refine JavaScript event handling
2. Improve chart synchronization
3. Enhance keyboard navigation
4. Optimize audio integration
5. Implement improved layouts

#### Deliverables:
- More robust interactive features
- Better chart coordination
- Enhanced audio-visual synchronization
- Improved UI layouts for better usability

### Phase 4: Advanced Features (Weeks 7-8)

#### Tasks:
1. Add support for additional data formats
2. Implement data export functionality
3. Create reporting tools
4. Optimize performance for large datasets
5. Add advanced analysis options

#### Deliverables:
- Expanded data format support
- Export and reporting capabilities
- Performance improvements for large datasets
- Advanced analysis tools

## Risk Analysis and Mitigation

### Risk: Breaking existing functionality
**Mitigation**: 
- Create comprehensive tests before refactoring
- Implement changes incrementally with frequent testing
- Maintain backward compatibility where possible

### Risk: JavaScript initialization issues
**Mitigation**: 
- Create clear initialization patterns
- Document JavaScript dependencies thoroughly
- Implement error handling for JavaScript components

### Risk: Disrupting notebook-style execution
**Mitigation**: 
- Maintain cell-compatible API
- Create wrapper functions for notebook use
- Test both execution modes throughout refactoring

### Risk: Performance regression
**Mitigation**: 
- Benchmark current performance
- Monitor performance during refactoring
- Optimize critical paths

## Testing Strategy

### Unit Tests
- Test individual parsers with sample files
- Test data processing functions with known inputs/outputs
- Test chart generation functions with mock data

### Integration Tests
- Test end-to-end data loading and visualization
- Test interaction between charts and data updates
- Test audio synchronization with visualizations

### UI Tests
- Test user interactions with charts
- Test file selection functionality
- Test chart control operations

### Performance Tests
- Test with large datasets to ensure responsiveness
- Test memory usage during extended operation
- Test JavaScript performance with many interactive elements

## Implementation Priorities

### High Priority
1. **Code Structure Reorganization**
2. **JavaScript Initialization Improvements**
3. **Data Loading Enhancement with File Selection**

### Medium Priority
1. **UI Layout Improvements**
2. **Documentation Enhancement**
3. **Additional Data Processing Options**

### Lower Priority
1. **Advanced Features (Export, Reports)**
2. **Performance Optimizations**
3. **Extended Format Support**

## Development Approach

This refactoring will follow a progressive enhancement approach:

1. Begin with structural improvements that don't change functionality
2. Add new capabilities incrementally without disrupting existing features
3. Maintain compatibility with both execution modes throughout
4. Continuously test to ensure quality and performance

## Next Steps

1. Create development branch and set up testing infrastructure
2. Document current API in detail
3. Implement initial module reorganization
4. Begin refactoring highest priority components 