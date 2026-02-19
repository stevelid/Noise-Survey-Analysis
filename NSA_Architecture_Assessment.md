Noise Survey Analysis Tool
Architecture Assessment & Clean-Sheet Alternatives
# 1. What Exists Today
The Noise Survey Analysis tool is a mature, interactive data viewer and explorer for noise survey data. It enables simultaneous viewing of data from multiple instruments on synchronised axes, with annotation, audio playback, and export capabilities. It runs as a local Bokeh server application with a browser-based frontend.
## 1.1 Technology Stack
## 1.2 Complete UX Feature Inventory
### Data Import
Data Source Selector UI with drag-and-drop file/folder import
Job directory scanning by job number
Auto-detection of file types: NTi (.txt), Svan (.csv/.xlsx), Noise Sentry (.csv), Generic tabular
Dual-pane transfer interface (available files -> included files) with editable position names and parser selection
Portable JSON configuration files (v1.2) with relative paths for sharing
Bulk edit positions dialog for batch renaming
Generic parser for arbitrary CSV/TXT/XLSX with datetime + numeric columns (line charts only, no spectra)
### Time History Views
One chart per measurement position with selectable parameters (LAeq, LAF90, LAF10, LAFmax, etc.)
Synchronised pan, zoom, and cursor across all charts
Toggle between overview (summary) and high-resolution log data
Reservoir streaming architecture with lazy loading for large log files
Red tap line (persistent cursor) and grey hover line (live following)
Chart visibility toggles per position to manage screen real estate
### Spectrogram Views
Colour-coded frequency-time heatmaps per position (LZeq, LZF90, LZFmax)
Fixed-size Bokeh Image glyph with in-place buffer updates for performance
Frequency range 31 Hz - 2 kHz visible (configurable)
Synchronised with time-series charts (same pan/zoom/cursor)
### Frequency Analysis
1/3 octave bar chart (20 Hz - 10 kHz) updates on tap or hover
Summary table showing parameter values at current cursor position
Region-averaged spectrum display when a region is selected
### Markers & Annotations
Double-click to place markers; press M at current tap position
Ctrl+click to delete nearest marker
Ctrl+Arrow to fine-tune marker position to adjacent data points
Colour picker and notes per marker
Press R to convert two most recent markers into a region
### Regions & Metrics
Shift+drag to create regions; boundary adjustment via keyboard (Shift+Arrow for right edge, Alt+Arrow for left)
Multi-area regions: Add Area mode to stitch non-contiguous segments
Auto Day & Night button (07:00-23:00 green / 23:00-07:00 purple)
Merge regions with automatic note history
Split multi-area regions back into separate regions
Live metrics: LAeq, LAFmax, LAF90, average spectrum per region
Copy Summary and Copy Spectrum Values to clipboard (paste to Excel)
Side panel with tabbed interface (Regions tab / Markers tab)
### Audio Playback (Live Server Only)
Synchronised WAV/FLAC/OGG playback with chart timeline
Click-to-seek: clicking charts seeks audio to that timestamp
Play/pause, variable speed (0.5x-2.0x), +20dB volume boost
Per-position audio with chart and audio time offset controls (+-300s)
Audio anchoring across disjoint survey segments
### Navigation & Range Selection
Full-survey range selector at bottom with drag handles for zoom window
Mouse wheel zoom, click-drag pan (all synchronised)
Arrow keys for stepping through data points
Double-click range selector to reset full view
### Session Persistence & Export
Save/Load Workspace (full UI state + source configs as JSON)
Export/Import Annotations as CSV (markers + regions with timestamps, notes, colours)
Static HTML export: single self-contained file for sharing (no audio)
Launch with --config and --state flags for instant workspace restoration
DataManager pickle cache to avoid re-parsing on reload
### Keyboard Shortcut Summary
## 1.3 Existing Roadmap Items (from TODO.txt)
Comparison mode - compare events within/across positions
Undo/redo - state history for annotation changes
UI polish - dropdown menus, cleaner audio controls, chart offset menus
Playback improvements - global speed/boost controls across positions
Region CSV import/export improvements with offset awareness
Offset handling - labels, spectrum, frequency outputs align with chart offsets
Side panel redesign - interactive region list, tabbed metrics/spectrum views
Dedicated comparison mode - position selector, time slice, overlaid spectra, metrics table
# 2. Strengths & Limitations of Current Architecture
## 2.1 What Works Well
## 2.2 Architectural Limitations
The core issue is that Bokeh is excellent for data visualisation but limited as an application framework. The project has effectively built a custom SPA framework on top of Bokeh's widget system, which creates friction for every UI improvement.
# 3. Clean-Sheet Architecture Alternatives
Given the requirements - local-only, responsive, large data, multi-instrument, extensible, easy team deployment - here are three distinct approaches considered from scratch.
## Option A: Electron + React + DuckDB
Desktop application with web technologies
Strengths:
Full access to NPM ecosystem, modern UI components, virtual scrolling, rich interactions
DuckDB handles GB-scale analytical queries directly in the app - no server needed
Native file system access means zero server overhead for data loading
Web Audio API replaces VLC dependency entirely
Single installable .exe - team just runs the app
TypeScript provides type safety across the entire codebase
Weaknesses:
Electron apps are large (~150MB installer) and resource-hungry
Significant learning curve if team wants to modify (React + TypeScript + DuckDB)
Rewriting Python parsers in TypeScript is substantial work (or adds Python subprocess complexity)
Auto-update mechanism needed for team distribution
## Option B: Python Backend + React SPA (Hybrid)
Keep Python for data, modernise the frontend
Strengths:
Preserves all existing Python parsers and data processing - minimal rewrite
Modern React frontend with full component library access (shadcn/ui, Radix, etc.)
FastAPI is fast, well-documented, has excellent TypeScript-compatible OpenAPI generation
Hot module replacement during development; Vite build for production
Arrow IPC transfer is ~10x faster than JSON for large datasets
CLI tools (like Claude Code) can interact via the REST API
Same deployment model as today (python command + browser)
Weaknesses:
Still requires Python installed + pip dependencies
Two language surfaces (Python + TypeScript) increases maintenance complexity
Frontend rewrite is significant even if backend is preserved
## Option C: Enhanced Bokeh (Incremental Evolution)
Modernise within the current framework
Strengths:
Lowest risk - incremental changes to working system
No rewrite required - all existing features continue working
Fastest time to delivering the roadmap items
Team already knows the codebase
Weaknesses:
UI ceiling remains - Bokeh widgets cannot match modern UI libraries
Bokeh custom extensions are complex to build and maintain
WebSocket bridge latency remains for server-side operations
Technical debt in components.py persists unless addressed
# 4. Comparison Matrix
# 5. Recommendation: Option B (Python Backend + React SPA)
## 5.1 Why Not A or C?
Option A (Electron) is architecturally the cleanest but requires rewriting all parsers in TypeScript or managing a Python subprocess - a large cost for marginal benefit over Option B. The .exe deployment advantage matters less for a 4-person team that already has Python installed.
Option C (Bokeh evolution) is the safest short-term path and is the right choice if the primary goal is shipping the existing roadmap items quickly. However, it does not resolve the fundamental UI ceiling that will increasingly constrain the tool as features like comparison mode, correlation analysis, and event detection are added.
## 5.2 Recommended Migration Strategy
A phased approach avoids the risk of a full rewrite while delivering incremental value:
Phase 1: API Layer (2-3 weeks)
Wrap the existing Python data pipeline with FastAPI endpoints. Keep the Bokeh frontend working in parallel. This creates zero user disruption while establishing the API contract.
Phase 2: Core Viewer (4-6 weeks)
Build the React frontend with time-series charts, spectrograms, and navigation. Use the API from Phase 1. This is the bulk of the work but can be developed alongside the existing tool.
Phase 3: Annotations & Audio (2-3 weeks)
Port the marker/region system and audio playback (Web Audio API) to the new frontend. The Redux state pattern can transfer almost directly to Zustand.
Phase 4: Polish & Transition (2-3 weeks)
Session persistence, static export, comparison mode, and the new features from the roadmap. Switch the team over.
# 6. Nice-to-Have Features (Beyond Current Roadmap)
Features that would add significant value and are easier to implement with a modern frontend:
### Analysis Features
Cross-meter correlation: Scatter plots and correlation coefficients between positions. Helps identify shared vs. localised noise sources.
Event detection: Pattern matching or threshold-based detection to automatically flag anomalous events. Configurable rules per project (e.g., 'LAFmax exceeds background by 10dB for >2 seconds').
Statistical summary dashboards: Percentile distributions, time-of-day heat maps, weekday vs. weekend comparisons calculated across full survey.
Background noise curve fitting: Automated LA90 trend analysis with confidence intervals. Flag measurement periods with atypical background.
Spectral fingerprinting: Save characteristic spectra (e.g., 'road traffic', 'plant noise') and overlay for comparison against measured data.
### Workflow Features
Report template generation: Export region metrics, spectra, and annotations directly into a structured report skeleton (Word/markdown).
Multi-survey overlay: Load data from different survey dates at the same site and overlay for trend analysis or before/after comparison.
Weather data integration: Already possible via generic parser, but a dedicated weather panel showing wind speed/direction alongside noise data would help identify wind-contaminated periods.
Collaborative annotations: Shared annotation files on the team drive. One person marks up, another reviews. Diff-merge for conflicting edits.
Measurement quality indicators: Automatic flagging of potential issues: wind noise, clipping, battery drops, gaps in logging, instrument overloads.
### Performance & UX Features
Progressive data loading with preview: Show a low-resolution overview within 2 seconds, progressively fill in detail. Users can start navigating immediately.
Minimap with annotations: Replace range selector with a richer minimap showing region locations, marker clusters, and data quality indicators.
Customisable chart layouts: Drag to reorder positions, resize chart heights, toggle between stacked and overlay modes.
Dark mode: Reduce eye strain during extended analysis sessions. Spectrograms particularly benefit from dark backgrounds.
Searchable event timeline: Filterable log of all user actions and detected events. Click to navigate to any point in the survey.

| Date: | 13 February 2026 | 
| --- | --- |
| Purpose: | Comprehensive review of current implementation with clean-sheet architecture recommendations | 
| Codebase: | ~12,000 LOC (Python + JavaScript), 30+ test files | 

| Layer | Technology | 
| --- | --- |
| Backend | Python 3.8+ with Bokeh 3.x server | 
| Frontend | Bokeh JS widgets + custom Redux-style JavaScript (~4,100 LOC) | 
| Data Layer | Pandas DataFrames, ColumnDataSource bridge to browser | 
| Visualisation | Bokeh figures (line glyphs, Image glyphs for spectrograms) | 
| Audio | python-vlc for playback, soundfile for metadata | 
| State | Custom Redux store (JS) + mutable data cache | 
| Testing | Vitest (unit), Playwright (E2E), pytest (backend) | 
| Deployment | Batch script sync to shared drive; team runs bokeh serve locally | 

| Shortcut | Action | 
| --- | --- |
| Double-click | Place marker at timestamp | 
| M | Place marker at tap position | 
| R | Convert two most recent markers to region | 
| Shift + Drag | Create region | 
| Ctrl + Click | Delete nearest marker/region | 
| Ctrl + Left/Right | Nudge selected marker | 
| Shift + Left/Right | Move region right boundary | 
| Alt + Left/Right | Move region left boundary | 
| Arrow Left/Right | Step tap line through data | 
| Spacebar | Play/pause audio | 
| Escape | Clear selection / exit mode | 

| Strength | Detail | 
| --- | --- |
| Redux pattern | Clean unidirectional data flow. Predictable state, easy debugging, testable. The AGENTS.md handbook is excellent for maintaining conventions. | 
| Parser extensibility | NoiseParserFactory pattern makes adding new instrument parsers straightforward. Generic parser enables arbitrary data. | 
| Streaming architecture | Reservoir streaming with lazy loading handles large log files well. Overview/log toggle avoids loading gigabytes upfront. | 
| Annotation system | Regions with multi-area support, automatic metrics, clipboard export - genuinely useful workflow for report writing. | 
| Audio integration | Synchronised audio playback with chart interaction is a significant differentiator over SVANPC. | 
| Session persistence | Workspace save/load and annotation CSV export make analysis recoverable and shareable. | 
| Test coverage | 30+ test files across unit, integration, and E2E layers. Comprehensive for a small-team project. | 

| Limitation | Impact | Severity | 
| --- | --- | --- |
| Bokeh widget system | UI components are limited to Bokeh's widget set. No modern component library, no virtual scrolling, no rich dropdowns. Side panel is particularly constrained. | HIGH | 
| Python-JS bridge latency | Every server callback round-trips through WebSocket. Audio commands, data requests, and UI state changes all transit the bridge. Adds perceptible latency. | MEDIUM | 
| components.py size | 3,062 lines in a single file building all UI widgets. Difficult to navigate, modify, and test. Tightly coupled to Bokeh internals. | MEDIUM | 
| No bundler/transpiler | JavaScript is served as raw ES modules through Bokeh's static file mechanism. No TypeScript, no tree-shaking, no minification, no NPM ecosystem. | MEDIUM | 
| VLC dependency | Audio playback requires VLC installed. Fragile on different machines, version-sensitive, harder to deploy consistently. | LOW | 
| Spectrogram buffer | Fixed-size Image glyph constraint means pre-padding data. Works but requires careful dimension management and limits dynamic resolution. | LOW | 

| Component | Choice | 
| --- | --- |
| Shell | Electron (Chromium + Node.js runtime) | 
| Frontend | React + TypeScript with Zustand state management | 
| Charts | Apache ECharts or Plotly.js (WebGL-accelerated) | 
| Data Engine | DuckDB-WASM for in-browser SQL analytics on large files | 
| Audio | Web Audio API (native browser, no VLC needed) | 
| File Access | Node.js fs module for direct local file access | 
| Parsers | TypeScript parsers (or Python child process for complex formats) | 

| Component | Choice | 
| --- | --- |
| Backend | FastAPI (Python) serving REST + WebSocket endpoints | 
| Frontend | React + TypeScript SPA with Vite build | 
| Charts | Apache ECharts, Plotly.js, or uPlot (lightweight, fast timeseries) | 
| Data | Pandas on backend; JSON/Arrow IPC transfer; optional DuckDB-WASM for client-side drill-down | 
| Audio | Backend streams audio chunks via HTTP range requests; Web Audio API in browser | 
| State | Zustand or Redux Toolkit (TypeScript) on frontend | 
| Launch | Single Python command starts backend + opens browser (like current bokeh serve) | 

| Component | Change | 
| --- | --- |
| Backend | Keep Bokeh server, refactor components.py into smaller modules | 
| Frontend JS | Add esbuild/Vite for bundling; migrate to TypeScript gradually | 
| Custom Widgets | Build Bokeh extensions for side panel, dropdowns, comparison mode | 
| Audio | Move to Web Audio API via Bokeh JS callback (remove VLC) | 
| Data | Improve streaming, add server-side DuckDB for analytical queries | 
| State | Keep Redux pattern; add undo/redo middleware | 

| Criterion | A: Electron | B: FastAPI+React | C: Bokeh Evolution | 
| --- | --- | --- | --- |
| UI quality ceiling | Excellent | Excellent | Limited | 
| Reuse of existing parsers | Low | High | Full | 
| Data performance (1GB files) | Excellent (DuckDB) | Very Good (Arrow) | Good (streaming) | 
| Audio without VLC | Yes (Web Audio) | Yes (Web Audio) | Possible (complex) | 
| Team deployment ease | Best (.exe) | Good (pip install) | Good (pip install) | 
| CLI/API controllability | Moderate (IPC) | Excellent (REST) | Limited (WebSocket) | 
| Time to feature parity | 6-9 months | 3-5 months | 1-2 months | 
| Future extensibility | Excellent | Excellent | Moderate | 
| Maintenance complexity | Medium | Medium | Low-Medium | 
| Learning curve for team | Steep | Moderate | Low | 

| Option B is the recommended path because it maximises reuse of existing work while removing the architectural ceiling.
The Python parsers, data pipeline, and domain logic are the hardest-won parts of this project. Option B preserves them entirely while replacing only the constrained presentation layer (Bokeh widgets) with a modern React frontend. The REST API also opens the door to CLI tooling and future automation. | 
| --- |

| Summary: The existing tool has strong foundations - the data pipeline, parser system, annotation workflow, and audio integration are genuinely good. The main constraint is the Bokeh widget layer limiting UI quality and extensibility. Option B (FastAPI + React) preserves the valuable Python backend while unlocking a modern frontend that can grow with the tool's ambitions. | 
| --- |
