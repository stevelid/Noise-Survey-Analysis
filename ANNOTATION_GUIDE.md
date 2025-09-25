# Annotation Guide

The Noise Survey Analysis app provides two complementary annotation tools—**markers** and **regions**—that help analysts flag
important timestamps and build repeatable measurement windows. Both tools follow the same Redux-style data flow: user input is
normalised by the event handlers, dispatched as thunks, and reducers maintain a normalised state shape with `byId` and `allIds`
collections.

## Marker workflow

Markers capture a single moment in time and are ideal for noting complaints, interesting acoustic events, or points you wish to
revisit later.

- **Create:** Double-click anywhere on a time-series chart or press **M** to drop a marker at the active tap timestamp. The most
  recent marker is automatically selected and the metrics thunk computes broadband and spectral snapshots for all visible
  positions.
- **Select:** Click a marker entry in the side panel or dispatch `markerSelect(id)` programmatically to focus on its details.
- **Delete:** Hold **Ctrl** and click near the marker on a chart. The closest marker within the current viewport is removed, so
  precision clicking is not required.
- **Notes & colour:** Use `markerUpdate`/`markerSetNote`/`markerSetColor` to capture free-form context or colour-code related
  events. The reducer normalises whitespace and guards against duplicate timestamps.
- **CSV interchange:** The `features/markers/markerUtils` helpers expose `formatMarkersCsv(state)` and
  `parseMarkersCsv(csvText)` for exporting and reloading marker sets. Each row stores the timestamp, note, colour, metrics JSON
  payload, and optional selection flag.

## Region workflow

Regions describe a span of time and power the analysis panel. Each region can contain multiple areas (segments) and supports a
full metrics pipeline.

- **Create:** Hold **Shift** while dragging horizontally on a chart. Alternatively, press **R** to convert the two most recent
  markers into a new region on the active position.
- **Select:** Click the overlay on the chart or choose a region in the side panel. Only one region can be active at any time.
- **Refine:** Use **Shift + ←/→** to extend or shrink the right edge and **Alt + ←/→** for the left edge. Each press nudges by
  ~10 % of the current keyboard navigation step size.
- **Delete:** Hold **Ctrl** and click inside the region (or a specific segment). Multi-area regions will remove only the segment
  you clicked; single-area regions are removed entirely.
- **Merge & add area:** Toggle Add Area mode to append segments to the selected region, or use the Merge Region workflow to
  combine adjacent selections.
- **Metrics:** LAeq, LAFmax, LAF90, duration, and average spectrum are recomputed automatically whenever bounds change or new
  data loads. The clipboard utilities (`formatRegionSummary`, `formatSpectrumClipboardText`) provide ready-to-share outputs.

## Keyboard shortcuts overview

| Shortcut | Action |
|----------|--------|
| **M**    | Create a marker at the current tap timestamp and fetch metrics. |
| **R**    | Build a new region from the two most recent markers. |
| **Ctrl + Click** | Remove the active marker or the region segment under the cursor. |
| **Shift + Drag** | Draw a new region directly on the chart. |
| **Shift + ←/→** | Nudge the right edge of the selected region. |
| **Alt + ←/→** | Nudge the left edge of the selected region. |

By treating markers and regions as first-class entities with predictable state transitions, analysts can annotate surveys quickly
while the UI remains responsive and easy to reason about.
