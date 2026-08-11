# Classification Review UI — Implementation Plan

## Purpose

Improve the audio-classification review workflow in the Noise Survey Analysis dashboard without changing the existing distinction between:

- **classifications**: machine-generated candidate intervals; and
- **regions**: user-created analysis intervals.

The priority is fast review of classifier results directly against the time history and audio. The implementation should build on the existing Redux-style classification state, Bokeh `Quad` overlays, classification table, audio seek/play workflow and import/export format.

This work is a dashboard/UI enhancement. Event detection and frame-to-event merging remain external Python processing responsibilities.

---

## Current behaviour and relevant architecture

The existing classification feature already provides:

- imported classification intervals with `positionId`, `sourceId`, `sourceLabel`, `start`, `end`, `state`, `confidence`, `description`, `audioFile` and `color`;
- stable colours by `sourceId`;
- one chart lane per classification source;
- chart overlays using Bokeh `Quad` glyphs;
- selected-classification styling;
- a classification table and selected-item detail panel;
- import/export;
- conversion of a classification to a normal region.

The chart overlay source already includes `classification_id`, so the principal missing interaction is connecting a hit on a classification box back to `selectClassificationIntent(id)`.

Likely files to inspect and modify include:

```text
static/js/core/actions.js
static/js/features/classifications/classificationReducer.js
static/js/features/classifications/classificationSelectors.js
static/js/features/classifications/classificationThunks.js
static/js/features/classifications/classificationUtils.js
static/js/services/classifications/classificationPanelRenderer.js
static/js/services/renderers.js
static/js/services/eventHandlers.js
static/js/chart-classes.js
static/js/registry.js
static/js/init.js
static/js/app.js
static/css/theme.css
```

Also inspect the Python/Bokeh UI construction code that creates and registers models such as:

```text
classificationPanelSource
classificationPanelTable
classificationPanelDetailDiv
classificationVisibilityToggle
classification overlay renderers
```

Do not assume all necessary model construction is in the packed static-JavaScript context.

---

## Agreed UX principles

1. **Selecting a classification must be passive.**
   Clicking a box or table row selects it, highlights it and shows its details. It must not move the current seek cursor, change the viewport or start/stop audio.

2. **Preview is an explicit action.**
   Pressing `P` previews the selected classification: jump to one second before it, centre the viewport on it and play. This is the only new keyboard action required at this stage.

3. **Do not add arrow-key classifier navigation.**
   Up/down movement through a long list risks unintended jumps and is not needed for the initial workflow.

4. **Model score is not a calibrated probability.**
   Label the control and detail field as `Score` or `Match score`, not `Confidence`, unless preserving the existing CSV field name internally.

5. **Category identity and score strength must remain visually distinguishable.**
   Category is primarily encoded by hue/lane/label. Score must not replace category colouring.

6. **Supporting detections are diagnostic, not standard output.**
   Normal parser output should contain direct target detections only. Supporting vehicle/engine classifications may remain available as a separate optional diagnostic export/import, but the dashboard must not assume they are normally present.

---

# Phase 1 — Classification selection from chart overlays

## Required interaction

When a user clicks a classification box:

1. Select that classification in application state.
2. Switch the side panel to the **Classifications** tab.
3. Highlight the selected chart box.
4. Highlight the matching table row.
5. Scroll the table to that row where supported.
6. Populate the existing detail panel.
7. Do **not**:
   - move the tap/seek cursor;
   - change the viewport;
   - start, pause or restart audio;
   - create or elevate a region.

## Implementation approach

The overlay `ColumnDataSource` already contains `classification_id`. Add a renderer-specific selection/tap path for the classification `Quad` glyphs.

Preferred approach:

- attach a dedicated Bokeh selection/tap interaction to the classification renderer;
- when its selected indices change, obtain the relevant `classification_id`;
- dispatch the existing `selectClassificationIntent(classificationId)` thunk.

The classification tap must not also trigger the ordinary chart tap/seek interaction. Inspect the existing tap tool and event-handler setup and implement the least invasive conflict prevention. Possible approaches include:

- a renderer-restricted `TapTool`;
- checking whether the classification renderer handled the event before dispatching the ordinary chart tap;
- a short-lived interaction flag scoped to the current tap event.

Do not globally disable ordinary chart tapping.

## Table synchronisation

Set the classification table’s `scroll_to_selection` property explicitly to `true`.

Verify that:

- programmatic selection after a chart-box click highlights the correct row;
- the table scrolls when the selected row is outside the current viewport;
- the selected row remains correct after sorting and filtering.

If the current Bokeh version has any problem scrolling a sorted view, document it and implement a small JavaScript fallback using the table view only if necessary.

---

# Phase 2 — Hover details on classification boxes

Add a `HoverTool` restricted to the classification overlay renderer only.

## Overlay source fields

Extend `_emptyClassificationOverlayData()` and `_buildClassificationOverlayData()` so each rendered box also carries:

```text
classification_id
source_id
label
start
end
score
state
description
audio_file
role
```

`role` should support at least:

```text
direct
supporting
```

For backwards-compatible imports where no role exists:

- infer `supporting` only where the imported source/description clearly marks it as supporting;
- otherwise default to `direct`;
- do not rely on this inference for newly generated files.

## Tooltip content

Show:

```text
<Category label>
Start – End
Score: 0.xx
Direct / Supporting
State
Description, if present
```

Use a renderer-specific hover configuration so the classifier tooltip appears only when the pointer is over a classification box. It should not disable the existing line/spectrogram hover behaviour elsewhere.

Test boxes that occupy the lower portion of the time-series plot and confirm the hover hit area does not prevent normal interaction with the data outside the boxes.

---

# Phase 3 — Explicit preview with the `P` key

## Behaviour

When `P` is pressed and a classification is selected:

1. Determine the selected classification’s position and times.
2. Set the seek/tap timestamp to:

```text
classification.start - 1.0 second
```

Clamp this to available audio/data bounds where necessary.

3. Centre the time-series viewport on the classification interval.
4. Start playback at the selected classification’s position.
5. Leave playback running normally until the user pauses it.

## Viewport rule

Use a useful review window rather than retaining an extremely wide overview:

- if the existing viewport width is **120 seconds or less**, preserve that width;
- if it is wider, use a **60-second preview window**;
- centre the window on the midpoint of the selected classification;
- clamp to the available data range.

Put these values in named constants so they can be adjusted later:

```javascript
CLASSIFICATION_PRE_ROLL_MS = 1000
CLASSIFICATION_PREVIEW_MAX_PRESERVE_MS = 120000
CLASSIFICATION_PREVIEW_WINDOW_MS = 60000
```

## Interaction safeguards

- Ordinary selection must not invoke preview.
- `P` must do nothing when no classification is selected.
- Ignore `P` while focus is in an input, textarea, select, editable table cell or other text-editing control.
- Reuse the existing tap/seek, viewport and audio-play actions/thunks rather than writing directly to Bokeh audio-control models.
- Verify behaviour when audio is:
  - paused;
  - already playing at the same position;
  - playing at another position;
  - playing later in the same file.

A visible **Preview** button in the detail panel may call the same thunk, but keyboard `P` is the required interaction.

---

# Phase 4 — Filtering and compact source controls

## Minimum-score filter

Add a classification filter state field:

```javascript
minimumScore: 0.0
```

Provide a compact slider or numeric slider labelled:

```text
Minimum score
```

Suggested initial range and step:

```text
0.00 to 1.00
step 0.01
```

Filtering must be applied to a derived visible-classification list. Do not delete or mutate imported classifications when the slider changes.

Display:

```text
Showing N of M
```

where:

- `M` is the number imported after source/role inclusion rules;
- `N` is the number passing the current visible filters.

Entries with no finite score should either:

- remain visible by default; or
- be controlled by a clearly named `Include unscored` option.

Use the first behaviour initially for backwards compatibility.

## Source/category visibility

Avoid a permanently expanded checkbox list in the narrow panel.

Add a compact control:

```text
Sources (n/m)
```

Clicking it should reveal/collapse a `CheckboxGroup` or equivalent list showing:

```text
☑ Motorcycle       count
☑ Dog bark         count
☑ Music            count
```

Each entry should include the same category colour swatch used in the chart.

Include compact:

```text
All
None
```

actions.

The expanded source list should be collapsible and should not materially increase panel clutter when closed.

## Direct/supporting role

Normal classifier files will generally contain direct detections only. Still support role filtering for diagnostic imports:

```text
☑ Direct
☐ Supporting
```

Default:

```text
Direct = on
Supporting = off
```

If no supporting items are present, hide this control entirely.

Longer term, add a structured `role` column to classification CSV/JSON. Preserve backwards compatibility with the current CSV schema.

## Derived selector

Add a selector such as:

```javascript
selectVisibleClassifications(state)
```

It should apply:

1. enabled source IDs;
2. direct/supporting role;
3. minimum score;
4. any review-state filter added later;
5. configured sort order if sorting is performed in application state.

Use the same derived list for:

- chart overlays;
- table rows;
- visible counts;
- right-side lane labels.

The underlying imported list remains unchanged.

---

# Phase 5 — Table layout and sorting

Bokeh `DataTable` supports sortable columns. Enable sorting on useful columns and verify it works correctly with selection and scroll-to-selection.

## Recommended visible columns

For a single-position dashboard:

```text
Source
Start
Score
State
```

Hide `Position` where every row belongs to the same position. Retain it where multiple positions are displayed together.

The current long combined time-span text and source labels produce unnecessary horizontal scrolling. Use narrower, purpose-specific fields.

## Important implementation detail

Do not sort formatted text values for time or score.

The `ColumnDataSource` should contain raw fields such as:

```text
start_ms
end_ms
score_value
```

Use appropriate Bokeh formatters to display:

```text
HH:MM:SS
0.00
```

This ensures numeric/date sorting rather than lexicographic sorting.

Suggested sortable columns:

- Source;
- Start;
- Score;
- State.

Suggested initial ordering:

```text
Start ascending
```

Do not add a separate sort dropdown unless built-in header sorting proves unreliable with the installed Bokeh version.

## Selection after sorting

Test explicitly:

- sort by score descending;
- click a chart box;
- confirm the matching sorted row highlights and scrolls into view;
- click a sorted row;
- confirm the correct chart interval highlights;
- change filters and ensure selection is retained only if the selected item remains visible.

If the selected item becomes hidden by a filter, keep it selected in underlying state but:

- clear the visible table selection;
- show a small message such as `Selected classification is hidden by current filters`; or
- clear selection if that is materially simpler.

Prefer retaining the underlying selection so pressing `P` remains deterministic, but do not leave a misleading highlighted row.

---

# Phase 6 — Right-hand category labels

Add one label per visible classification lane at the right-hand side of the main time-series plot.

Example:

```text
● Motorcycle
● Dog bark
● Music
```

## Requirements

- Labels align vertically with their corresponding classification lanes.
- Labels use the source colour.
- Labels show only enabled/visible source categories.
- Do not repeat the labels on the spectrogram.
- Labels remain at the right edge while the x-axis pans or zooms.
- Keep labels concise: use `sourceLabel`, with sensible shortening only if required.

## Suggested implementation

Start with a Bokeh `LabelSet` or individual `Label` models anchored just inside the current `x_range.end`, right-aligned with a small inset.

Update their x position when the viewport range changes.

Only introduce a separate narrow side figure if the in-plot labels prove unreliable or interfere with glyph hit testing.

---

# Phase 7 — Score styling

Do not use opacity as the main score encoding because low-score boxes become difficult to see against the noise traces.

## Initial styling

Keep:

- **hue** = source/category;
- **outline width** = selected;
- **greyed styling** = rejected/off, if retained.

Add three discrete shade bands within each category hue:

```text
low score       light shade
medium score    base shade
high score      dark shade
```

Do not use a continuous rainbow or global heat-map palette.

## Thresholds

Because model scores are not directly comparable between categories, allow the renderer to accept source-specific display breakpoints later.

For the first implementation, use configurable global breakpoints such as:

```javascript
LOW_SCORE_MAX = 0.20
MEDIUM_SCORE_MAX = 0.50
```

Keep them as named constants and document that they are visual bands, not probability thresholds.

Selected styling must remain obvious across every shade, for example:

- 2–3 px high-contrast outline;
- slightly increased lane height;
- or both.

Do not allow score shading to obscure source identity.

Treat score shading as lower priority than click selection, preview, hover, filtering and right-side labels. It may be implemented after those interactions are stable.

---

# External parser responsibilities

## Standard output

The normal audio classifier parser should export only the direct target categories requested for that run, for example:

```text
Motorcycle
Dog bark
Music
Cattle
```

Do not automatically export every related AudioSet class as a separate visible classification.

## Supporting information

Supporting classes may be used internally when calculating or describing a direct detection, for example:

```text
Vehicle
Motor vehicle (road)
Engine
Accelerating, revving, vroom
```

Preferred treatment:

- attach the strongest supporting classes to the direct event’s `description` or structured metadata;
- do not produce thousands of separate supporting intervals in the standard dashboard import.

If a diagnostic supporting-event export is retained:

- create it as a separate optional output;
- mark every event with `role=supporting`;
- give it a separate source ID;
- default it to hidden in the dashboard.

## Event merging

Frame-to-event merging must remain in the external Python parser.

For each target category:

1. apply a low screening score;
2. merge overlapping positive frames;
3. bridge short gaps using a category-specific gap;
4. apply any category-specific minimum duration;
5. optionally add short pre/post padding;
6. export one candidate episode.

Suggested starting points:

```text
Motorcycle    merge gap 1–2 s
Dog barking   merge gap 3 s
Music         merge gap 5–10 s
```

Each exported event should retain:

```text
start
end
peak score
mean score
positive frame count
top supporting classes
model name/version
audio filename
direct/supporting role
```

Use `confidence` in the current schema for the event’s peak model score until the schema is renamed or expanded.

The dashboard score slider filters completed candidate episodes. It does not rerun YAMNet or recompute event boundaries.

---

# State and persistence

Add filter settings to classification state, for example:

```javascript
filters: {
    minimumScore: 0.0,
    enabledSourceIds: null,
    showDirect: true,
    showSupporting: false,
    sourceFilterExpanded: false
}
```

`enabledSourceIds: null` should mean all currently available direct sources enabled, allowing newly imported sources to appear without a migration.

Decide whether purely presentational controls such as `sourceFilterExpanded` need to be saved. Persist meaningful review settings such as:

```text
minimumScore
enabledSourceIds
showDirect
showSupporting
```

Ensure rehydration remains backwards compatible with saved workspaces created before these fields existed.

Filter changes should not enter undo/redo history unless there is already an established pattern for view settings being undoable.

---

# Suggested action and selector additions

Possible action types:

```text
classifications/minimumScoreSet
classifications/sourceVisibilitySet
classifications/allSourcesVisibilitySet
classifications/roleVisibilitySet
```

Possible actions:

```javascript
classificationMinimumScoreSet(value)
classificationSourceVisibilitySet(sourceId, visible)
classificationAllSourcesVisibilitySet(visible)
classificationRoleVisibilitySet({ direct, supporting })
```

Possible selectors:

```javascript
selectClassificationSources(state)
selectVisibleClassifications(state)
selectClassificationCounts(state)
selectIsSelectedClassificationVisible(state)
```

Add a thunk:

```javascript
previewSelectedClassificationIntent()
```

This thunk should own the `P` behaviour and be callable from both keyboard handling and an optional Preview button.

---

# Tests and acceptance criteria

## Selection

- Clicking a classification box selects exactly that classification.
- The Classifications tab opens.
- The correct table row highlights.
- The table scrolls to the row where necessary.
- The detail panel updates.
- Cursor, viewport and playback remain unchanged.
- Clicking empty chart space continues to perform the existing tap/seek behaviour.

## Preview

- Selecting an item alone does nothing to audio or viewport.
- Pressing `P` seeks to one second before the selected start.
- The selected interval is centred in a useful viewport.
- Playback starts at the correct position.
- `P` is ignored in editable controls.
- `P` with no selection has no effect.

## Hover

- Tooltip appears only over classification boxes.
- Tooltip fields match the imported event.
- Existing line/spectrogram hover remains usable.

## Filters

- Score changes update chart, table and visible counts without changing imported data.
- Source checkboxes affect chart, table and right-side labels consistently.
- Supporting events are hidden by default.
- Unscored legacy events remain visible.
- Selected hidden items are handled consistently.

## Sorting

- Start sorts chronologically.
- Score sorts numerically.
- Selection and scroll-to-selection remain correct after sorting.
- Filtering after sorting does not select the wrong ID.

## Labels and styling

- Right-side labels align with lanes.
- Labels remain at the plot edge during pan/zoom.
- Category hue remains consistent in label, table and boxes.
- Score shading is discrete and selected styling remains obvious.

## Regression

- Existing classification CSV and JSON imports still work.
- Existing classification export still works.
- Existing region elevation still works.
- Existing marker/region/chart/audio interactions remain unchanged.
- Saved workspaces without filter state still load.
- Standard dashboards with no classifications behave exactly as before.

---

# Implementation sequence

Implement and test in this order:

1. Chart-box click selection and table scroll.
2. Renderer-specific hover.
3. `previewSelectedClassificationIntent()` and `P`.
4. Derived visible-classification selector and minimum-score filter.
5. Compact source and direct/supporting controls.
6. Table column cleanup and built-in sorting.
7. Right-hand lane labels.
8. Discrete score shading.
9. Optional parser/schema improvements for structured `role` and richer metadata.

Commit each phase separately where practical. Do not combine parser/model work with the first UI interaction commit.

---

# Deliverables

Provide:

1. The implemented code.
2. Tests for reducer/selectors/thunks where test infrastructure exists.
3. A short manual test checklist covering chart click, table scroll, `P`, hover, filters and sorting.
4. Before/after screenshots.
5. A brief note identifying:
   - any Bokeh-version limitations encountered;
   - whether built-in DataTable sorting and `scroll_to_selection` worked reliably;
   - any deliberate deviation from this plan and why.
