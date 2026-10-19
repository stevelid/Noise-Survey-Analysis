# Manual Test Checklist — Noise Survey Analysis Dashboard

**Purpose:** This checklist ensures all user interactions work correctly in the Bokeh environment. Run this checklist before each release or after significant changes to interaction logic.

**Last Updated:** 2026-10-19
**Version:** 1.8.0

---

## Test Environment Legend

**🟢 STATIC** - Can be tested with static HTML (no Python server required)  
**🔴 SERVER** - Requires active Python server connection  
**🟡 PARTIAL** - Some aspects work in static, some require server

---

## Pre-Test Setup

### For Static HTML Testing
- [ ] Generate static HTML: `python -m noise_survey_analysis.main --generate-static .\config.json`
- [ ] Open generated HTML file in browser
- [ ] Browser DevTools console is open to catch errors
- [ ] Run tests marked with 🟢 STATIC or 🟡 PARTIAL

### For Full Server Testing
- [ ] Bokeh server is running (`python -m noise_survey_analysis.main`)
- [ ] Dashboard loads without console errors
- [ ] Test data is loaded (at least 2 positions with log and overview data)
- [ ] Audio files are available (if testing audio features)
- [ ] Browser DevTools console is open to catch errors
- [ ] Run all tests including 🔴 SERVER

---

## 1. Chart Interactions 🟢 STATIC

### 1.1 Single Click (Tap) 🟢
- [ ] **Action:** Click on time series chart
- [ ] **Expected:** Red tap line appears at clicked timestamp
- [ ] **Expected:** Summary table updates with values at that timestamp
- [ ] **Expected:** Frequency bar updates with spectral data
- [ ] **Expected:** Tap line appears on all charts at same timestamp

### 1.2 Double Click 🟢
- [ ] **Action:** Double-click on time series chart
- [ ] **Expected:** New marker is created at clicked timestamp
- [ ] **Expected:** Marker appears as a vertical line in its chosen colour on all charts
- [ ] **Expected:** Marker panel is displayed
- [ ] **Expected:** New marker is the active selected marker
- [ ] **Expected:** Marker appears in Markers list

### 1.3 Shift + Click (Create Region) 🟢
- [ ] **Action:** Click to place tap line, then Shift+click at different location
- [ ] **Expected:** Region is created spanning from first to second click
- [ ] **Expected:** Region appears as colored box on the charts
- [ ] **Expected:** Region appears in Regions list
- [ ] **Expected:** Region side panel is active
- [ ] **Expected:** New region is the active selected region
- [ ] **Expected:** Region details (timestamps, metrics) load in the side panel
- [ ] **Expected:** Works in both directions (left-to-right and right-to-left)

### 1.4 Ctrl + Click (Delete Region) 🟢
- [ ] **Action:** Create a region, then Ctrl+click inside it
- [ ] **Expected:** Region is deleted immediately
- [ ] **Expected:** Region disappears from charts
- [ ] **Expected:** Region disappears from Regions panel

### 1.5 Box Selection (Drag) 🟢
- [ ] **Action:** Hold Shift, click and drag on chart to select time range
- [ ] **Expected:** Selection box appears during drag
- [ ] **Expected:** Region is created when mouse is released
- [ ] **Expected:** Region spans the selected time range
- [ ] **Expected:** Region side panel is active
- [ ] **Expected:** New region is the active selected region
- [ ] **Expected:** Region details (timestamps, metrics) load in the side panel.
- [ ] **Test:** Try very small selections (< 1 second)
- [ ] **Test:** Try very large selections (> 1 day)

### 1.6 Hover Over Chart 🟢
- [ ] **Action:** Move mouse over time series chart (with Hover Enabled)
- [ ] **Expected:** Gray dashed hover line appears on all charts
- [ ] **Expected:** Value labels appear showing data at hover position
- [ ] **Expected:** Frequency bar updates to show spectrum at hover point
- [ ] **Expected:** Hover line disappears when mouse leaves chart
- [ ] **Test:** Disable "Hover Enabled" toggle - hover line should not appear

### 1.7 Range Selector 🟢
- [ ] **Action:** Drag left handle of range selector
- [ ] **Expected:** All main charts zoom to match selected range
- [ ] **Expected:** Data updates after ~200ms debounce
- [ ] **Action:** Drag right handle of range selector
- [ ] **Expected:** Charts zoom accordingly
- [ ] **Action:** Drag center of range selector
- [ ] **Expected:** Charts pan without changing zoom level

---

## 2. Keyboard Shortcuts 🟡 PARTIAL

### 2.1 Space Bar (Play/Pause Audio) 🔴 SERVER
- [ ] **Action:** Click on chart, press Space
- [ ] **Expected:** Audio starts playing from tap line position
- [ ] **Expected:** Play toggle button activates
- [ ] **Action:** Press Space again
- [ ] **Expected:** Audio pauses
- [ ] **Expected:** Play toggle button deactivates

### 2.2 M Key (Create Marker) 🟢
- [ ] **Action:** Click on chart to place tap line, press M
- [ ] **Expected:** Marker is created at tap line position
- [ ] **Expected:** Marker appears on all charts
- [ ] **Expected:** Marker appears in Markers panel
- [ ] **Expected:** Newly created marker is automatically selected
- [ ] **Expected:** Side panel switches to Markers tab

### 2.3 R Key (Two-Step Region Creation) 🟢
- [ ] **Action:** Click on chart to place tap line, press R
- [ ] **Expected:** Region creation mode activates
- [ ] **Expected:** Side panel switches to Regions tab
- [ ] **Expected:** Regions panel shows a “Region start” status with the pinned timestamp
- [ ] **Expected:** Status explains that R finishes the region and Esc cancels it
- [ ] **Action:** Move tap line to different location, press R again
- [ ] **Expected:** Region is created spanning from first to second tap position
- [ ] **Expected:** Newly created region is automatically selected
- [ ] **Expected:** Region details appear in panel
- [ ] **Expected:** Creation banner disappears
- [ ] **Test:** Press R, then press R again at same location - no region created (too small)
- [ ] **Test:** Press R, then press Escape - creation mode cancels, no region created

### 2.4 Escape Key (Exit Modes) 🟢
- [ ] **Action:** Press R to enter region creation mode, then press Escape
- [ ] **Expected:** Region creation mode exits
- [ ] **Expected:** Creation banner disappears
- [ ] **Expected:** No region is created
- [ ] **Action:** Select a region, press Escape
- [ ] **Expected:** Region selection clears (if implemented)
- [ ] **Action:** Enter comparison mode, press Escape
- [ ] **Expected:** Comparison mode exits (if implemented)

### 2.5 Arrow Keys (Nudge Tap Line) 🟡 PARTIAL
- [ ] **Action:** Place tap line, press Right Arrow
- [ ] **Expected:** Tap line moves to next data point
- [ ] **Expected:** When the time series is displaying **log** data, the step matches the log cadence (can be sub-second)
- [ ] **Expected:** When the time series is displaying **overview** data (including when Log View is enabled but zoomed out), the step matches the overview cadence
- [ ] **Expected:** Summary table updates
- [ ] **Expected:** If audio is playing, it jumps to new position
- [ ] **Action:** Press Left Arrow
- [ ] **Expected:** Tap line moves to previous data point (matching the currently displayed dataset cadence)
- [ ] **Test:** Press and hold arrow key - should move continuously

### 2.6 Ctrl + Arrow Keys (Adjust Region Start) 🟢
- [ ] **Action:** Select a region, press Ctrl+Right Arrow
- [ ] **Expected:** Region start edge moves forward (~5 minutes)
- [ ] **Expected:** Region updates on all charts immediately
- [ ] **Action:** Press Ctrl+Left Arrow
- [ ] **Expected:** Region start edge moves backward
- [ ] **Test:** If region has multiple areas and tap/hover is over one area, only that area's start adjusts
- [ ] **Test:** If no tap/hover over region, first area's start adjusts
- [ ] **Test:** Cannot move start past end (minimum 1ms width enforced)
- [ ] **Test:** Cannot move start before viewport minimum or past previous area's end

### 2.7 Alt + Arrow Keys (Adjust Region End) 🟢
- [ ] **Action:** Select a region, press Alt+Right Arrow
- [ ] **Expected:** Region end edge moves forward (~5 minutes)
- [ ] **Expected:** Region updates on all charts immediately
- [ ] **Action:** Press Alt+Left Arrow
- [ ] **Expected:** Region end edge moves backward
- [ ] **Test:** If region has multiple areas and tap/hover is over one area, only that area's end adjusts
- [ ] **Test:** If no tap/hover over region, last area's end adjusts
- [ ] **Test:** Cannot move end before start (minimum 1ms width enforced)
- [ ] **Test:** Cannot move end past viewport maximum or before next area's start

### 2.8 Ctrl + Arrow Keys with Selected Marker 🟢
- [ ] **Action:** Select a marker, press Ctrl+Right Arrow
- [ ] **Expected:** Marker timestamp moves forward (~5 minutes)
- [ ] **Expected:** Marker updates on all charts immediately
- [ ] **Expected:** Marker list updates with the new timestamp
- [ ] **Action:** Press Ctrl+Left Arrow
- [ ] **Expected:** Marker timestamp moves backward
- [ ] **Test:** Marker nudging takes priority over region adjustment when marker is selected

### 2.9 Shift Key (Switch Drag Tool) 🟢
- [ ] **Action:** Hold Shift key
- [ ] **Expected:** Cursor changes to indicate box select mode
- [ ] **Expected:** Dragging creates selection box instead of panning
- [ ] **Action:** Release Shift key
- [ ] **Expected:** Cursor returns to normal
- [ ] **Expected:** Dragging pans the chart

---

## 3. Control Panel Widgets 🟡 PARTIAL

### 3.1 Parameter Selector 🟢
- [ ] **Action:** Change parameter from LZeq to LAeq
- [ ] **Expected:** All spectrograms update to show LAeq data
- [ ] **Expected:** Frequency bar updates to show LAeq spectrum
- [ ] **Test:** Cycle through all available parameters
- [ ] **Test:** Verify each parameter displays different data

### 3.2 Log View Toggle 🟢
- [ ] **Expected:** On initial load, charts show overview data and the toggle reads "Log View Disabled"
- [ ] **Action:** Click "Log View Disabled" to enable
- [ ] **Expected:** All charts switch to log data
- [ ] **Expected:** Chart data becomes more granular
- [ ] **Action:** Click "Log View Enabled" to disable
- [ ] **Expected:** All charts switch to overview data
- [ ] **Expected:** Chart data becomes less granular

### 3.3 Hover Enabled Toggle 🟢
- [ ] **Action:** Click "Hover Enabled" to disable
- [ ] **Expected:** Hover lines no longer appear when moving mouse
- [ ] **Expected:** Value labels no longer appear on hover
- [ ] **Action:** Click to enable again
- [ ] **Expected:** Hover functionality restores

### 3.4 Confirmed Marker Clearing 🟢
- [ ] **Action:** Create 2–3 markers, open the Markers tab and choose “Clear all markers…”
- [ ] **Expected:** A confirmation appears; every marker, note and snapshot remains until confirmed
- [ ] **Action:** Choose Cancel
- [ ] **Expected:** All markers remain on charts and in the list
- [ ] **Action:** Request clearing again, then choose “Clear all markers” in the confirmation
- [ ] **Expected:** Marker lines disappear, the marker list empties and selection clears
- [ ] **Expected:** No separate Clear All Markers control appears in the top toolbar
- [ ] **Test:** Create markers again with M and double-click; selection, notes and snapshots still work

### 3.5 Chart Visibility Menu 🟢
- [ ] **Action:** Open Plots and disable a time-series chart
- [ ] **Expected:** That time series chart becomes hidden
- [ ] **Action:** Enable that chart again
- [ ] **Expected:** Chart becomes visible again
- [ ] **Test:** Hide and show spectrogram charts
- [ ] **Test:** Hide all charts, then show them all

### 3.6 Session Menu 🟡 PARTIAL
- [ ] **Action:** Choose Menu → Save Workspace
- [ ] **Expected:** A version-2 workspace JSON file downloads
- [ ] **Action:** Change annotations, then choose Menu → Load Workspace and select the saved file
- [ ] **Expected:** Regions, meter states, categories, markers and saved review settings restore
- [ ] **Action:** Choose Menu → Export Annotations — Quick (CSV)
- [ ] **Expected:** REGIONS, MARKERS and NOTES download quickly, with readable notes/times/categories/states/provenance, blank region metric fields and an annotations-only mode note; no per-meter metrics are calculated
- [ ] **Action:** Choose Menu → Export Annotations + Analysis (Browser CSV)
- [ ] **Expected:** OVERALL and SPECTRAL are added, REGIONS headline levels populate where data exists, and every analysis row identifies its data resolution
- [ ] **Test:** Import both exports into fresh annotation state; each restores the same regions, states, categories and marker snapshots
- [ ] **Action:** Choose Menu → Import Annotations (CSV) and select the export
- [ ] **Expected:** Annotations, states, categories and marker snapshots restore; analysis sections do not create annotations
- [ ] **Test:** Import an old unsectioned annotation CSV; matching cross-meter copies consolidate and the merge count appears
- [ ] **Test:** Select an imported region; on-demand metrics populate without console errors
- [ ] **SERVER:** Menu → Export Annotations — Full Resolution produces a file using the source logs and reports completion or a useful error
- [ ] **STATIC:** The full-resolution server command is absent; browser CSV import/export remains available

---

## 4. Region Panel Interactions 🟡 PARTIAL

### 4.1 Region List Selection and Filters 🟢
- [ ] **Action:** Create 2–3 regions and select a compact row in the Regions list
- [ ] **Expected:** The row and chart region highlight; selected-region details appear above the list
- [ ] **Expected:** Marker selection clears and the Regions tab is active
- [ ] **Action:** Select another row
- [ ] **Expected:** Selection and details switch to that region
- [ ] **Test:** Expand Filters, then filter by category, Present at meter, Present at one meter only and Has unchecked meters
- [ ] **Expected:** The list count and rows match each filter; annotations are retained when hidden by a filter
- [ ] **Test:** Reset the filters and confirm all rows return

### 4.2 Region Band Visibility 🟢
- [ ] **Action:** Expand Annotation visibility and untick Region bands
- [ ] **Expected:** Region bands disappear from charts; the region list, selection and details remain available
- [ ] **Action:** Tick Region bands again
- [ ] **Expected:** Present, absent and currently enabled unchecked bands return

### 4.3 Auto Day & Night 🟢
- [ ] **Action:** Expand Actions and settings, then choose Auto Day & Night
- [ ] **Expected:** One region per day/night period spans the survey's civil-time boundaries: 07:00–23:00 and 23:00–07:00
- [ ] **Expected:** Every meter is present in each generated region; no duplicate row is created per meter
- [ ] **Expected:** Day and night colours remain distinguishable
- [ ] **Test:** Check clipped first/last periods and a survey crossing a daylight-saving change

### 4.4 Categories and Colour Overrides 🟢
- [ ] **Action:** Select a region and change Category
- [ ] **Expected:** Category colour becomes its default band and list-swatch colour
- [ ] **Action:** Open the native Colour override picker, choose a colour, then leave the control
- [ ] **Expected:** The override applies to that region without changing the category colour
- [ ] **Test:** Open and cancel the picker with no override: the category colour remains inherited, with no new override
- [ ] **Action:** Choose Use category
- [ ] **Expected:** The override clears and category colouring returns
- [ ] **Test:** Under Actions and settings → Categories, create, rename and recolour a category
- [ ] **Test:** Delete a category in use; affected regions move to Other, and Other itself cannot be deleted
- [ ] **Expected:** Undo restores category/state/colour edits appropriately

### 4.5 Region Notes 🟢
- [ ] **Action:** Edit the selected region's Notes, then leave the field or press Ctrl+Enter
- [ ] **Expected:** The note saves and persists after selecting another region and returning
- [ ] **Test:** With a dirty note, click Category and choose with the keyboard, then repeat with Colour override and choose in its native dialog: each control works on the first click and the note saves
- [ ] **Test:** Click Category after editing a note, dismiss it without changing the category, then click outside: the saved note appears in the list without leaving rendering paused
- [ ] **Test:** Repeat that unchanged-category flow but click another region or Actions and settings: the first click selects/opens it; repeat after choosing a colour override and verify both the colour save and selection complete
- [ ] **Action:** Edit a draft, then press Esc
- [ ] **Expected:** The draft cancels and the saved note returns
- [ ] **Test:** While a draft has focus, change an unrelated annotation field
- [ ] **Expected:** Draft text, caret position, expanded sections and panel scroll position survive
- [ ] **Expected:** Chart shortcuts do not trigger while typing; special characters, HTML-like text and emojis display literally

### 4.6 Copy Summary 🟡 PARTIAL
- [ ] **Action:** Select a region with metrics; expand Actions and settings and choose Copy summary
- [ ] **Action:** Paste into a text editor
- [ ] **Expected:** The summary identifies the region, origin meter, time span, duration and available levels

### 4.7 Delete Region 🟢
- [ ] **Action:** Select a region and choose Delete in its selected-region details
- [ ] **Expected:** That region disappears from charts and the list; no stale selection remains
- [ ] **Test:** Delete all regions, then create several new ones
- [ ] **Expected:** Every new region appears once; selection, states, categories, notes and editing still work

### 4.8 Add Area 🟢
- [ ] **Action:** Select a region; expand Actions and settings and choose Add area
- [ ] **Expected:** A status message identifies add-area mode
- [ ] **Action:** Shift+drag another time span
- [ ] **Expected:** The same region gains a non-contiguous area; its note, category and meter states remain shared across all areas
- [ ] **Action:** Choose Finish adding areas
- [ ] **Expected:** Subsequent new selections create independent regions again

### 4.9 Merge Regions 🟢
- [ ] **Action:** Select the destination region, then choose another region under Actions and settings → Merge into selected region
- [ ] **Expected:** Only other regions with the same origin meter are offered
- [ ] **Expected:** The two regions become one with their combined areas
- [ ] **Expected:** Unchecked defers to the other state; matching states remain; present/absent conflicts become unchecked and are named for re-check
- [ ] **Test:** One undo restores both original regions

### 4.10 Split Areas 🟢
- [ ] **Action:** Select a multi-area region and choose Actions and settings → Split areas
- [ ] **Expected:** One region per area replaces the original; each preserves its category, note, colour override and meter states
- [ ] **Test:** One undo restores the original multi-area region

### 4.11 Per-Meter State Strip 🟢
- [ ] **Action:** Create a region with at least three meters loaded
- [ ] **Expected:** Its origin is present (●); other meters start unchecked (○), using their display titles
- [ ] **Action:** Click another meter in the state strip repeatedly
- [ ] **Expected:** Its state cycles unchecked → present → absent (✕) → unchecked without creating another region row
- [ ] **Expected:** The origin remains present; tap/seek time and audio do not move
- [ ] **Test:** Number keys 1–9 address meters in display order; they do nothing inside editable fields or with modifiers/key-repeat
- [ ] **Expected:** There is no Copy Region To selector or copy-to-all control; undo restores state edits

### 4.12 Per-Meter Metrics and Resolution 🟢
- [ ] **Expected:** Per-meter metrics start collapsed in a new workspace; selecting regions does not calculate hidden metrics
- [ ] **Action:** Select a region and choose Show per-meter metrics
- [ ] **Expected:** One row per meter shows LAeq, LAFmax, LAF90 and the actual data resolution, including absent/unchecked meters
- [ ] **Expected:** Missing values remain unavailable; overview and 1 s LAF90 are identified as indicative
- [ ] **Test:** Hide per-meter metrics, change selection, then choose Show per-meter metrics; save/reload a workspace with each choice and verify it is remembered
- [ ] **Expected:** The region list does not calculate metrics for every row; it fills the remaining panel space with several review rows visible alongside selected details
- [ ] **Test:** Zoom or stream log data, then recalculate; resolution and levels update without recreating annotations

### 4.13 Centre, Back and Recalculate 🟢
- [ ] **Action:** Select an off-screen region and choose Centre
- [ ] **Expected:** The viewport centres on the complete region, using a useful width that includes all its areas
- [ ] **Action:** Choose Back (B), or press B
- [ ] **Expected:** The earlier view returns; a useful message appears if no prior view exists
- [ ] **Action:** Show overview data, then choose Actions and settings → Recalculate
- [ ] **Expected:** Selected metrics identify overview resolution
- [ ] **Action:** Display log data and recalculate again
- [ ] **Expected:** Selected metrics identify log resolution when the requested areas are fully covered; incomplete buffers do not masquerade as full log data
- [ ] **Test:** Check export resolution columns separately: standard analysis exports choose the best available resolution, and optional dual-resolution export includes both

### 4.13a Region Review Keyboard Flow 🟢
- [ ] **Action:** With several regions, press ] repeatedly, then [
- [ ] **Expected:** Selection steps through regions and brings them into view; first/last messages appear at the ends
- [ ] **Action:** After several steps, press B once
- [ ] **Expected:** The view returns to where it was before the first jump
- [ ] **Action:** Press N, type a note and press Ctrl+Enter
- [ ] **Expected:** The note field receives focus and the saved text persists after switching regions
- [ ] **Action:** Clear selection, place the tap line inside a region and press N
- [ ] **Expected:** That region is selected and its note is focused; a tap outside regions produces a useful selection message

### 4.14 Average Spectrum and Clipboard 🟡 PARTIAL
- [ ] **Action:** Keep per-meter metrics collapsed; expand Actions and settings → Average spectrum
- [ ] **Expected:** The origin meter spectrum loads independently; the all-meter metrics table stays collapsed
- [ ] **Expected:** The table identifies its parameter/resolution and lists frequency bands in order
- [ ] **Action:** Choose Copy spectrum and paste into a spreadsheet
- [ ] **Expected:** Frequency bands and levels occupy separate columns

---

## 5. Marker Panel Interactions 🟡 PARTIAL

### 5.1 Marker List Selection 🟡 PARTIAL
- [ ] **Action:** Create 2–3 markers and select a row in the Markers list
- [ ] **Expected:** The row highlights, saved snapshot/details appear, and the tap line moves to its timestamp
- [ ] **Expected:** Region selection clears and the Markers tab is active
- [ ] **Action:** Select another marker
- [ ] **Expected:** Selection, timestamp and saved details switch correctly

### 5.2 Marker Line Visibility 🟢
- [ ] **Action:** Expand Annotation visibility and untick Marker lines
- [ ] **Expected:** Lines disappear from charts; all markers, notes and snapshots remain in the list
- [ ] **Action:** Tick Marker lines again
- [ ] **Expected:** The lines reappear at their original timestamps

### 5.3 Marker Colour 🟢
- [ ] **Action:** Change the selected marker's Colour field, then leave it
- [ ] **Expected:** The chart lines and list swatch update; the saved metric snapshot is preserved

### 5.4 Marker Notes 🟢
- [ ] **Action:** Edit Notes and leave the field, or press Ctrl+Enter
- [ ] **Expected:** Saved notes persist when switching markers
- [ ] **Test:** Esc cancels an unsaved draft; chart shortcuts do not fire while editing

### 5.5 Copy Snapshot 🟡 PARTIAL
- [ ] **Action:** Select a marker and choose Copy snapshot
- [ ] **Action:** Paste into a text editor
- [ ] **Expected:** Timestamp, note and saved per-meter broadband/spectral metrics are included

### 5.6 Delete Marker 🟢
- [ ] **Action:** Select a marker and choose Delete marker
- [ ] **Expected:** It disappears from charts and the list; selection clears
- [ ] **Test:** Delete all markers, then create new ones; selection, notes, colours and snapshots still work
- [ ] **Test:** Clear all markers through the confirmed flow in section 3.4

### 5.7 Create Marker with M 🟢
- [ ] **Action:** Place the tap line on a chart, then press M
- [ ] **Expected:** A marker appears on every chart and in the Markers list, is selected, and has a saved metrics snapshot
- [ ] **Test:** Double-click creates a marker through the same workflow
- [ ] **Expected:** No Add Marker at Tap button is present

---

## 6. Audio Control Interactions 🔴 SERVER

**Note:** Audio controls are now global (at top of dashboard) and work with the currently tapped position. Position title and offset controls appear above each chart.

### 6.1 Global Play/Pause Toggle 🔴
- [ ] **Action:** Click on a chart to place tap line, then click global Play toggle
- [ ] **Expected:** Audio starts playing from tap line position for that position
- [ ] **Expected:** Global toggle button shows "Pause" state (blue)
- [ ] **Expected:** Active position display shows "▶ [Position Name]" in blue
- [ ] **Expected:** Position title shows "▶ [Position Name]" in blue
- [ ] **Expected:** Chart background turns light blue
- [ ] **Action:** Click global toggle again
- [ ] **Expected:** Audio pauses
- [ ] **Expected:** Toggle returns to "Play" state (green)
- [ ] **Test:** Click on different position chart while audio is playing
- [ ] **Expected:** Audio switches to new position automatically

### 6.2 Global Playback Rate Button 🔴
- [ ] **Action:** Start audio playback, click global playback rate button
- [ ] **Expected:** Rate cycles: 1.0x → 1.5x → 2.0x → 0.5x → 1.0x
- [ ] **Expected:** Button label updates to show current rate
- [ ] **Expected:** Audio speed changes immediately
- [ ] **Test:** Verify audio pitch remains constant (time-stretching)
- [ ] **Test:** Rate persists when switching between positions

### 6.3 Global Volume Boost Toggle 🔴
- [ ] **Action:** Start audio playback, click global volume boost toggle
- [ ] **Expected:** Audio volume increases significantly
- [ ] **Expected:** Toggle button shows active state (orange)
- [ ] **Action:** Click toggle again
- [ ] **Expected:** Audio volume returns to normal
- [ ] **Expected:** Toggle button shows inactive state (gray)
- [ ] **Test:** Boost persists when switching between positions

### 6.4 Position Title Display 🟢
- [ ] **Action:** Observe position titles above each chart
- [ ] **Expected:** All positions show their title (even without audio)
- [ ] **Action:** Start audio playback for a position
- [ ] **Expected:** Active position title shows "▶ [Name]" in blue
- [ ] **Expected:** Other position titles remain black
- [ ] **Action:** Stop audio
- [ ] **Expected:** Position title returns to normal (black)

### 6.5 Chart Offset Spinner (Per-Position) 🟢
- [ ] **Action:** Change chart offset value for a position (e.g., +5 seconds)
- [ ] **Expected:** Chart data for that position shifts forward in time by 5 seconds
- [ ] **Expected:** Effective offset display for that position updates
- [ ] **Expected:** Other positions are not affected
- [ ] **Test:** Try negative offsets
- [ ] **Test:** Try large offsets (> 60 seconds)
- [ ] **Test:** Verify each position can have independent chart offsets

### 6.6 Audio Offset Spinner (Per-Position) 🔴
- [ ] **Action:** Change audio offset value for a position (e.g., -3 seconds)
- [ ] **Expected:** Audio playback shifts backward by 3 seconds
- [ ] **Expected:** Effective offset display updates
- [ ] **Test:** Combine chart and audio offsets

### 6.7 Effective Offset Display (Per-Position) 🟢
- [ ] **Action:** Set chart offset to +5s and audio offset to -3s
- [ ] **Expected:** Effective offset shows +2s (or appropriate calculation)
- [ ] **Expected:** Display updates immediately when either spinner changes

---

## 7. Comparison Mode Interactions 🟡 PARTIAL

### 7.1 Enter Comparison Mode 🟢
- [ ] **Action:** Click button to enter comparison mode
- [ ] **Expected:** Comparison panel appears
- [ ] **Expected:** The HTML sidebar displays its Comparison view in place of the annotation-tab content
- [ ] **Expected:** Box select tool becomes active
- [ ] **Expected:** Instructions appear in comparison panel

### 7.2 Position Selector 🟢
- [ ] **Action:** Uncheck a position in comparison selector
- [ ] **Expected:** That position is excluded from comparison
- [ ] **Expected:** Metrics update to exclude that position
- [ ] **Action:** Tick that meter again in the Comparison view
- [ ] **Expected:** Position is included again

### 7.3 Box Select Time Slice 🟡 PARTIAL
- [ ] **Action:** In comparison mode, drag to select time range on chart
- [ ] **Expected:** Selection box appears during drag
- [ ] **Expected:** Slice info updates when released
- [ ] **Expected:** Metrics table populates with data for selected slice
- [ ] **Expected:** Comparison frequency chart shows spectra for all positions

### 7.4 Metrics Table 🟡 PARTIAL
- [ ] **Action:** Select a time slice in comparison mode
- [ ] **Expected:** Table shows one row per included position
- [ ] **Expected:** Each row shows meter, LAeq, LAFmax, LAF90 and resolution; the slice times appear above
- [ ] **Expected:** Values are accurate for selected time slice

### 7.5 Make Region 🟢
- [ ] **Action:** Select a comparison time slice and choose Make Region
- [ ] **Expected:** One region is created for the slice, with included meters marked present and other meters unchecked
- [ ] **Expected:** The origin is the first included meter in display order
- [ ] **Action:** Finish comparison and open Regions
- [ ] **Expected:** The new annotation appears once, with its full meter-state strip

### 7.6 Finish Comparison Button 🟢
- [ ] **Action:** Choose Finish comparison
- [ ] **Expected:** Comparison mode exits
- [ ] **Expected:** Comparison panel hides
- [ ] **Expected:** The annotation-tab content returns in the same sidebar
- [ ] **Expected:** Pan tool becomes active again

---

## 8. Side Panel Tab Switching 🟢 STATIC

### 8.1 Switch to Markers Tab 🟢
- [ ] **Action:** Click "Markers" tab
- [ ] **Expected:** Markers panel content displays
- [ ] **Expected:** Regions panel content hides
- [ ] **Expected:** Tab appears active

### 8.2 Switch to Regions Tab 🟢
- [ ] **Action:** Click "Regions" tab
- [ ] **Expected:** Regions panel content displays
- [ ] **Expected:** Markers panel content hides
- [ ] **Expected:** Tab appears active

---

## 9. Edge Cases & Error Handling 🟢 STATIC

### 9.1 Empty Data Sets 🟢
- [ ] **Test:** Load dashboard with no data
- [ ] **Expected:** Charts show empty state or placeholder
- [ ] **Expected:** No console errors
- [ ] **Expected:** Interactions gracefully handle missing data

### 9.2 Single Data Point 🟢
- [ ] **Test:** Load position with only one data point
- [ ] **Expected:** Charts render without errors
- [ ] **Expected:** Range selector handles single point
- [ ] **Expected:** Hover and tap work on single point

### 9.3 Very Large Time Ranges 🟢
- [ ] **Test:** Load data spanning > 30 days
- [ ] **Expected:** Charts render without performance issues
- [ ] **Expected:** Zoom and pan remain responsive
- [ ] **Expected:** Data downsampling works correctly

### 9.4 Rapid Interaction Sequences 🟢
- [ ] **Test:** Click rapidly on chart (10+ clicks in 2 seconds)
- [ ] **Expected:** App remains responsive
- [ ] **Expected:** No console errors
- [ ] **Expected:** Tap line updates correctly
- [ ] **Test:** Rapidly toggle visibility checkboxes
- [ ] **Expected:** Charts show/hide without errors

### 9.5 Position Switching During Playback 🔴
- [ ] **Test:** Start audio playback for one position
- [ ] **Action:** Click on a different position's chart
- [ ] **Expected:** Audio automatically switches to new position
- [ ] **Expected:** Global controls update to show new position
- [ ] **Expected:** Previous position's title returns to normal
- [ ] **Expected:** New position's title shows playing indicator

### 9.6 Invalid Region Operations 🟢
- [ ] **Test:** Try to create region with start > end (Shift+click)
- [ ] **Expected:** Region is created with corrected bounds (start/end swapped)
- [ ] **Test:** Try to create region with start === end
- [ ] **Expected:** Region is not created (minimum 1ms width required)
- [ ] **Test:** Try to merge region with itself
- [ ] **Expected:** Operation is prevented or handled gracefully
- [ ] **Test:** Try to split single-area region
- [ ] **Expected:** Split button is disabled or operation is prevented
- [ ] **Test:** Press R twice at same location
- [ ] **Expected:** No region created, creation mode exits

### 9.7 Delete and Recreate All Annotations 🟢
- [ ] **Test:** Create 3-4 regions and 3-4 markers
- [ ] **Action:** Delete all regions one by one
- [ ] **Action:** Open Markers → Clear all markers… and confirm
- [ ] **Action:** Create new regions using Shift+click and R key
- [ ] **Action:** Create new markers using double-click and M key
- [ ] **Expected:** All region functionality works (selection, editing, notes, colors)
- [ ] **Expected:** All marker functionality works (selection, editing, notes, colors)
- [ ] **Expected:** Side panel switches correctly between Markers and Regions tabs
- [ ] **Expected:** Newly created annotations are automatically selected
- [ ] **Expected:** No console errors appear
- [ ] **Test:** Verify region edge adjustments work (Ctrl/Alt + arrows)
- [ ] **Test:** Verify marker nudging works (Ctrl + arrows)

### 9.8 Browser Compatibility 🟢
- [ ] **Test:** Chrome/Edge (Chromium)
- [ ] **Test:** Firefox
- [ ] **Test:** Safari (if available)
- [ ] **Expected:** All interactions work consistently across browsers

### 9.9 Console Error Check 🟢
- [ ] **Test:** Complete entire checklist while monitoring console
- [ ] **Expected:** No JavaScript errors appear
- [ ] **Expected:** No Bokeh warnings appear
- [ ] **Expected:** Only expected debug logs appear

---

## 10. Performance Checks 🟢 STATIC

### 10.1 Initial Load Time 🟢
- [ ] **Test:** Measure time from page load to interactive
- [ ] **Expected:** < 5 seconds for typical dataset
- [ ] **Expected:** Progress indicator shows during load

### 10.2 Interaction Responsiveness 🟢
- [ ] **Test:** Click on chart
- [ ] **Expected:** Tap line appears within 100ms
- [ ] **Test:** Hover over chart
- [ ] **Expected:** Hover line follows cursor smoothly (60fps)
- [ ] **Test:** Zoom with range selector
- [ ] **Expected:** Charts update within 500ms

### 10.3 Memory Usage 🟢
- [ ] **Test:** Open browser task manager
- [ ] **Test:** Perform 50+ interactions (clicks, zooms, region creates/deletes)
- [ ] **Expected:** Memory usage remains stable (< 500MB growth)
- [ ] **Expected:** No memory leaks detected

---

## 11. Reservoir Streaming (Log Data) 🔴 SERVER

**Note:** These tests verify the reservoir streaming architecture where the server pushes log data to the frontend as the user pans/zooms.

### 11.1 Log Data Streaming on Zoom 🔴
- [ ] **Setup:** Enable Log View, zoom in to < 5 minute viewport
- [ ] **Expected:** Log data displays (chart title shows "Log Data")
- [ ] **Expected:** Data appears within ~500ms of zoom completing
- [ ] **Test:** Zoom out past 5 minute threshold
- [ ] **Expected:** Chart switches to overview data automatically
- [ ] **Expected:** Chart title shows zoom threshold message

### 11.2 Buffer Edge Detection 🔴
- [ ] **Setup:** Enable Log View, zoom to ~2 minute viewport
- [ ] **Action:** Pan slowly to the right
- [ ] **Expected:** Data remains smooth during pan (no flickering)
- [ ] **Expected:** New data loads when approaching buffer edge (~20% margin)
- [ ] **Test:** Pan rapidly back and forth
- [ ] **Expected:** App remains responsive, no console errors

### 11.3 Spectrogram Streaming 🔴
- [ ] **Setup:** Enable Log View, zoom to < 5 minute viewport
- [ ] **Expected:** Spectrogram shows log data (higher resolution)
- [ ] **Action:** Pan to new time range
- [ ] **Expected:** Spectrogram updates with new data
- [ ] **Expected:** Frequency bar updates correctly at tap location

### 11.4 Data Refresh Trigger 🔴
- [ ] **Setup:** Enable Log View, zoom in, place tap line
- [ ] **Action:** Pan to new time range (triggering server data push)
- [ ] **Expected:** Summary table updates with new values
- [ ] **Expected:** Frequency bar updates with new spectrum
- [ ] **Expected:** No console errors about missing data

### 11.5 Mixed View Transitions 🔴
- [ ] **Action:** Toggle Log View on/off rapidly (5+ times)
- [ ] **Expected:** Charts switch correctly each time
- [ ] **Expected:** No stale data displayed
- [ ] **Expected:** No console errors
- [ ] **Test:** Zoom in (log view), toggle to overview, toggle back to log
- [ ] **Expected:** Log data reloads correctly

### 11.6 Spectrogram Buffer Width Is Pinned 🔴
**Why:** The Image glyph buffer is fixed-size after init (AGENTS.md §6). The streamed
chunk width is now pinned to the initialized display buffer instead of being re-derived
from each slice's cadence, which drifted across gaps and file boundaries.
- [ ] **Setup:** Load a position whose log data contains a gap or spans multiple files
- [ ] **Action:** Enable Log View and pan so the viewport starts inside the gap
- [ ] **Expected:** Spectrogram keeps updating; it does not freeze while the time history moves
- [ ] **Expected:** Console shows no `Image size mismatch` or `replacement image shape` warnings
- [ ] **Expected:** Server log shows `[SPEC PIN] ... pinned to N bins` once per position
- [ ] **Expected:** Server log shows **no** `[SPEC PIN] ... does not match pinned buffer width` warnings

### 11.7 Large Survey Responsiveness 🔴
**Why:** Streamed slices are cut by row before column selection, and refreshes are
batched per frame.
- [ ] **Setup:** Load 3+ positions with 1 s log data over 3–4 days, spectral where available
- [ ] **Action:** Pan and zoom repeatedly in Log View
- [ ] **Expected:** UI stays responsive; charts settle within ~1 s of the gesture ending
- [ ] **Expected:** Server `[SPEC PERF]` lines show `slice_ms` in single-digit ms, not hundreds
- [ ] **Expected:** One heavy update per pan, not one per streamed source

---

### 11.8 Deferred Log Files Load In The Background 🔴
**Why:** The first zoom into a position used to parse its whole log file on the document
thread, freezing the dashboard for seconds. It now loads on a worker.
- [ ] **Setup:** Start with a config whose log files are large (multi-day, 1 s or faster)
- [ ] **Action:** Enable Log View and zoom in on a position for the first time
- [ ] **Expected:** The UI stays interactive throughout — hover, pan and the range selector all keep responding
- [ ] **Expected:** That position shows a "waiting for log data" status rather than freezing
- [ ] **Expected:** Log data appears by itself when the load finishes, with no further interaction
- [ ] **Expected:** Server log shows `[LAZY LOAD] Starting background load` then `[LAZY LOAD] Completed`

### 11.9 Panning During A Background Load 🔴
- [ ] **Action:** Zoom into an unloaded position, then immediately pan somewhere else while it loads
- [ ] **Expected:** Data appears for **where you ended up**, not where you started
- [ ] **Expected:** Server log shows `[LAZY LOAD] Refreshing ... at viewport` with the later range
- [ ] **Test:** Pan back and forth repeatedly during the load
- [ ] **Expected:** Only one load runs per position (one `Starting background load` line each)

### 11.10 Unreadable Log File Recovers 🔴
- [ ] **Setup:** Point a config at a log file on a disconnected network drive, or rename it after load
- [ ] **Action:** Zoom into that position
- [ ] **Expected:** `[LAZY LOAD] Failed` is logged once; the dashboard stays usable on overview data
- [ ] **Expected:** No repeated retry storm in the log
- [ ] **Action:** Restore the file, then navigate away and back
- [ ] **Expected:** The load is retried and the data appears

---

## 11b. Audio Seek Responsiveness 🔴 SERVER

**Note:** Seeking inside the recording already loaded no longer reloads media, and
control commands run off the Bokeh document thread.

### 11b.1 Seek Within The Current Recording 🔴
- [ ] **Setup:** Start playback on a position with audio
- [ ] **Action:** Click a new time inside the same audio file
- [ ] **Expected:** Audio jumps effectively immediately (no ~0.5 s stall)
- [ ] **Expected:** Playback continues without an audible stop/restart
- [ ] **Expected:** Server log shows `Seeking within already-loaded media`, not `Now playing:`

### 11b.2 Seek Across A File Boundary 🔴
- [ ] **Action:** Click a time that falls in a different audio file
- [ ] **Expected:** Playback switches to the new file and continues
- [ ] **Expected:** Server log shows `Now playing: <new file>`
- [ ] **Expected:** Position indicator and file name update

### 11b.3 Seeking Does Not Freeze The Dashboard 🔴
- [ ] **Setup:** Load a large survey (3+ positions, multi-day 1 s log data)
- [ ] **Action:** Click rapidly between distant times and across positions
- [ ] **Expected:** Charts, hover and range selector stay responsive throughout
- [ ] **Expected:** Commands apply in the order clicked; final position is the last clicked
- [ ] **Expected:** No console or server errors

### 11b.4 Closing The Tab Mid-Playback 🔴
**Why:** Session teardown releases VLC. A command still running on the worker would be
calling into freed resources.
- [ ] **Action:** Start playback, then close the browser tab while audio is playing
- [ ] **Expected:** Server logs `Audio handler released.` and `AppCallbacks cleaned up.`
- [ ] **Expected:** No VLC crash, segfault, or `RuntimeError: cannot schedule new futures after shutdown`
- [ ] **Test:** Repeat while rapidly clicking to seek, so a command is genuinely in flight
- [ ] **Expected:** Teardown completes promptly; no `Audio command still running after` warning

### 11b.5 Playback Rolls Over Between Files 🔴
- [ ] **Setup:** Start playback shortly before the end of an audio file
- [ ] **Action:** Let it play through the boundary without interacting
- [ ] **Expected:** Playback continues into the next file automatically
- [ ] **Expected:** Server log shows no `cannot join current thread` error

---

## 12. Data Source Selector Panel 🔴 SERVER

### 12.1 Survey Folder Is The Scan Boundary 🔴
**Why:** Scanning the whole job folder dredged in Admin, Corres and Report material.
A structural survey found `<job> Surveys` isolates ~99% of data files.
- [ ] **Setup:** Scan a job that has a `<job> Surveys` folder alongside Admin/Corres/Report
- [ ] **Expected:** No PDFs, quotes, letters or report documents appear as candidates
- [ ] **Expected:** Server log shows `Survey root for '<job>': <job> Surveys`
- [ ] **Test:** Scan a job with **no** Surveys folder (e.g. an older job)
- [ ] **Expected:** Falls back to the job folder and still finds data — nothing is hidden

### 12.2 Positions, Not Files 🔴
- [ ] **Setup:** Scan a job with a Svan position (log + summary, ideally with audio)
- [ ] **Expected:** The position appears as **one row**, not one row per file
- [ ] **Expected:** "Contains" reads e.g. `log + summary + audio`; Meter, Period, Duration and Files are populated
- [ ] **Action:** Select that row and press "Add ▶"
- [ ] **Expected:** All of its files appear in Included Files, sharing one position name
- [ ] **Test:** Press "Add ▶" again with the same row selected
- [ ] **Expected:** No duplicate rows are added

### 12.3 NTi Sessions Stay Distinct 🔴
- [ ] **Setup:** Scan a job with an NTi folder of several `SLM_nnn` sessions
- [ ] **Expected:** Each session is **one row**, not ~5.5 rows of its individual files
- [ ] **Expected:** Sessions are not merged together into a single position
- [ ] **Expected:** Rows whose files are `RTA_3rd` are identified as having spectral content

### 12.4 Visit Selection 🔴
**Why:** Several visits per job is the norm — 16 of 20 in the folder survey.
- [ ] **Setup:** Scan a job with more than one visit (e.g. a main survey plus "Verification Monitoring")
- [ ] **Expected:** The Visit dropdown lists each visit with its position count and dates, plus "All visits"
- [ ] **Expected:** A fresh scan lands on the **newest** visit, not on everything
- [ ] **Expected:** The status line states how many positions are shown of the total
- [ ] **Action:** Choose a different visit
- [ ] **Expected:** The position list changes to that visit only
- [ ] **Action:** Choose "All visits"
- [ ] **Expected:** Every position from every visit is listed

### 12.5 The Unnamed Visit Is Selectable 🔴
**Why:** Files sitting loose in the Surveys folder form a visit with an empty name;
it must not be conflated with "All visits".
- [ ] **Setup:** Scan a job with data both loose in `<job> Surveys` and inside a visit subfolder
- [ ] **Expected:** The dropdown offers "Main survey" separately from "All visits"
- [ ] **Action:** Select "Main survey"
- [ ] **Expected:** Only the loose-file positions are listed — **not** everything

### 12.6 Short Manual Readings 🔴
**Why:** Spot readings are not the usual dashboard use case, and one folder of them can
otherwise dominate the list.
- [ ] **Setup:** Scan a job containing a manual-measurement folder (many short sessions)
- [ ] **Expected:** Those readings are **not** listed by default and **not** pre-selected
- [ ] **Expected:** The status line says how many were hidden
- [ ] **Action:** Tick "Include short manual readings"
- [ ] **Expected:** They appear, one row per session, unticked
- [ ] **Test:** A position with a long log plus short extras
- [ ] **Expected:** It is treated as a real measurement, not hidden

### 12.7 Recommendations And Position Names 🔴
- [ ] **Expected:** Real measurements are pre-selected on scan, so "Add ▶" needs one click
- [ ] **Expected:** Position names match the folder/meter exactly, including capitals and digits
      (e.g. `5882 Warbrook House 971-2`, `6145-3 - front` — shown in full)
- [ ] **Test:** Rename a position in Included Files, then check it again
- [ ] **Expected:** Your capitalisation is preserved; only a leading lowercase letter is capitalised
- [ ] **Test:** A position folder whose name contains "log" (e.g. "Catalogue Road")
- [ ] **Expected:** The name is intact, not corrupted to "Cataue Road"

### 12.8 Time Span Probing 🔴
**Why:** Periods come from an ~8 KB read at each end of every candidate — about 4.5 ms
per file on local storage, against ~2.5 s to parse a 71 MB log. Files are assumed to be
available locally.
- [ ] **Setup:** Scan a job with many candidate files
- [ ] **Expected:** The scan completes promptly and Period/Duration are populated
- [ ] **Note:** If a job is ever scanned while its files are online-only rather than
      cached, probing may pull them down. `scan_directory_for_sources(..., probe_time_spans=False)`
      disables it; Period, Duration and short-reading detection are then unavailable.

### 12.9 Config Auto-Detection 🔴
- [ ] **Setup:** Scan a directory containing a single valid `noise_survey_config_*.json`
- [ ] **Expected:** "Load Config" button enables automatically
- [ ] **Expected:** Config loads immediately into the Included Files table without manual selection
- [ ] **Expected:** Status banner reports the auto-loaded config and warns if referenced files are missing

### 12.10 Multiple Config Prompt 🔴
- [ ] **Setup:** Scan a directory containing two or more valid config JSON files
- [ ] **Expected:** Status banner prompts to select a config before loading
- [ ] **Action:** Select one config in Available Files and press "Load Config"
- [ ] **Expected:** Selected config populates the Included Files table while other configs remain available
- [ ] **Test:** With multiple configs present, pressing "Load Config" without a selection keeps the prompt visible

---

## 13. Classification Review 🟡 PARTIAL

**Setup:** Import a classifier CSV via Menu → Import Classifications (CSV/JSON), then open Classifications.
A job 6461 motorcycle export is available at
`G:\My Drive\Venta AI\skills\classify-survey-audio\references\manual-test\6461_motorcycle_classifications.csv`
(85 events, mixed `on`/`uncertain` states, single source).
Audio-dependent steps (13.4) need 🔴 SERVER plus loaded audio.

### 13.1 Chart Box Selection 🟢
- [ ] **Action:** Click a classification box on the time series chart
- [ ] **Expected:** That classification becomes selected (box gains a thick white outline)
- [ ] **Expected:** Side panel switches to the Classifications tab
- [ ] **Expected:** The matching compact list row highlights
- [ ] **Expected:** The list brings the selected row into view if it was off-screen
- [ ] **Expected:** Selected-classification details above the list populate
- [ ] **Expected:** Tap/seek line does **NOT** move
- [ ] **Expected:** Viewport does **NOT** change
- [ ] **Expected:** Audio does **NOT** start, stop or restart
- [ ] **Test:** Clicking empty chart space still performs the normal tap/seek

### 13.2 Hover Tooltip 🟢
- [ ] **Action:** Hover the pointer over a classification box
- [ ] **Expected:** Tooltip shows Category, Start, End, Score, Role, State, Description
- [ ] **Expected:** Tooltip appears **only** over classification boxes
- [ ] **Test:** Normal line/spectrogram hover elsewhere on the chart still works

### 13.3 Classification List Sorting 🟢
- [ ] **Action:** Choose Start from the Sort selector
- [ ] **Expected:** Entries sort chronologically across midnight
- [ ] **Action:** Choose Score (highest first)
- [ ] **Expected:** Scores sort numerically; unscored entries follow scored entries
- [ ] **Action:** Try Source, State and Meter ordering
- [ ] **Expected:** List order matches the chosen field
- [ ] **Action:** After sorting, select a chart box, then select a different list row
- [ ] **Expected:** The correct annotation highlights in each direction without moving the seek cursor or starting audio
- [ ] **Expected:** List timestamps and selected details use the same display timezone

### 13.4 Preview with `P` Key 🔴 SERVER
- [ ] **Action:** Select a classification, then press `P`
- [ ] **Expected:** Seek jumps to 1 second before the event start
- [ ] **Expected:** Viewport centres on the event
- [ ] **Expected:** If the viewport was wider than 120 s it becomes a 60 s window
- [ ] **Expected:** If the viewport was already ≤ 120 s its width is preserved
- [ ] **Expected:** Audio starts playing at that position
- [ ] **Test:** `P` with no classification selected does nothing
- [ ] **Test:** `P` while typing in a notes/text field does nothing (no preview, text types normally)
- [ ] **Test:** `P` while audio is already playing the **same** position does not restart it
- [ ] **Test:** `P` while audio is playing a **different** position switches to this one
- [ ] **Test:** The "Preview (P)" button in the detail panel does the same thing
- [ ] **Test:** Preview is absent when nothing is selected; a selected-but-filtered classification remains available for explicit preview

### 13.5 Minimum Score Filter 🟢
- [ ] **Action:** Drag the "Minimum score" slider up
- [ ] **Expected:** Low-scoring boxes disappear from the chart
- [ ] **Expected:** List rows reduce to match
- [ ] **Expected:** "Showing N of M" caption updates
- [ ] **Expected:** Imported data is **not** deleted — reducing the slider restores them
- [ ] **Test:** Entries with no score remain visible at any slider value

### 13.6 Source Visibility 🟢
- [ ] **Action:** Expand Sources (n/m)
- [ ] **Expected:** Checkbox list expands showing each source with its event count
- [ ] **Action:** Untick a source
- [ ] **Expected:** That source's boxes, list rows and right-hand lane label all disappear
- [ ] **Expected:** "Sources (n/m)" count updates
- [ ] **Action:** Press "None" then "All"
- [ ] **Expected:** All sources hide, then all reappear
- [ ] **Test:** Collapsing Sources hides its controls without changing the filter

### 13.7 Direct / Supporting Roles 🟢
- [ ] **Setup:** Import a file containing supporting events, e.g.
      `G:\My Drive\Venta AI\skills\classify-survey-audio\references\manual-test\6461_supporting_vehicle_classifications.csv`
- [ ] **Expected:** Direct/Supporting checkboxes appear, with Supporting **off** by default
- [ ] **Action:** Tick Supporting
- [ ] **Expected:** Supporting events appear on the chart and in the list
- [ ] **Test:** With a direct-only file imported, the Direct/Supporting control is hidden entirely

### 13.8 Selected-but-Hidden Handling 🟢
- [ ] **Action:** Select a classification, then filter it out (raise the score slider above it)
- [ ] **Expected:** Message "Selected classification is hidden by current filters"
- [ ] **Expected:** No misleading highlighted list row remains
- [ ] **Action:** Restore the filter
- [ ] **Expected:** The classification is still selected and its details return

### 13.9 Right-Hand Lane Labels 🟢
- [ ] **Expected:** One "● Source" label per visible classification lane at the right edge
- [ ] **Expected:** Label colour matches the category colour used for the boxes
- [ ] **Action:** Pan and zoom the x-axis
- [ ] **Expected:** Labels stay pinned to the right edge
- [ ] **Expected:** Labels do not appear on the spectrogram

### 13.10 Score Shading 🟢
- [ ] **Expected:** Boxes use three discrete shades of the category colour
      (light < 0.20, base 0.20–0.50, dark ≥ 0.50)
- [ ] **Expected:** Category remains identifiable by hue at every shade
- [ ] **Expected:** The selected box's outline stays clearly visible on all three shades

### 13.11 Regression 🟡 PARTIAL
- [ ] **Test:** Existing classification CSV import still works
- [ ] **Test:** Classification JSON import still works
- [ ] **Test:** Classification export still works
- [ ] **Test:** "Elevate to Region" still creates a region with the classification's note
- [ ] **Test:** Save a workspace with filters set, reload it — filters restore
- [ ] **Test:** Load a workspace saved **before** filters existed — it loads with default filters
- [ ] **Test:** A dashboard with no classifications imported behaves exactly as before
- [ ] **Test:** Marker, region, chart and audio interactions are unaffected

---

## Test Results Template

**Date:** ___________  
**Tester:** ___________  
**Browser:** ___________  
**Dataset:** ___________  

**Summary:**
- Total Tests: ___
- Passed: ___
- Failed: ___
- Skipped: ___

**Failed Tests:**
1. Test ID: _____ | Issue: _____________________
2. Test ID: _____ | Issue: _____________________

**Notes:**
_____________________________________________
_____________________________________________

---

## Maintenance Notes

**When to Update This Checklist:**
- After adding new user interactions
- After modifying existing interaction behavior
- After discovering bugs not covered by existing tests
- After adding new UI components or controls

**How to Update:**
1. Add new test cases in appropriate section
2. Update section numbering if needed
3. Update "Last Updated" date at top
4. Increment version number
5. Document changes in git commit message

**Related Files:**
- `AGENTS.md` - Contains instructions for LLMs to maintain this checklist
- `tests/e2e/` - Automated E2E tests (limited coverage)
- `tests/*.test.js` - Unit and integration tests for JS logic
# Annotation model v2 checkpoints

- [ ] Create a region: origin is present, every other meter is unchecked.
- [ ] Comparison Make Region creates one object with all included meters present.
- [ ] Meter-state strips mark presence without creating another region row; copy-to-meter controls are retired.
- [ ] Merge same-origin regions: unchecked defers; present/absent conflicts become unchecked and are named for re-check. One undo restores both originals.
- [ ] Split multi-area regions: each output preserves meter states and category; one undo restores the original.
- [ ] Import a v1 workspace/legacy CSV containing matching cross-meter copies: consolidation count appears and originals on disk remain unchanged.
- [ ] Save/reload v2: category catalog, overrides and states survive. An unsupported future version leaves current annotations intact.
- [ ] Unchecked bands default to selected-only; Off hides them and All shows every ghost. Present/absent bands remain visible.
- [ ] Plain click on the selected region at another meter cycles unchecked/present/absent without moving the seek cursor or audio.
- [ ] Keys 1–9 address meter display order; typing in notes/categories, modified keys and key-repeat never change meter states.
- [ ] With a nonzero chart offset, bands stay on the shared displayed times and metrics query each meter's own source times once.
- [ ] Undoing an annotation edit preserves the current ghost visibility preference.

### HTML annotation sidebar (server and standalone HTML)

- [ ] Default HTML sidebar fits inside the viewport alongside charts; page and chart ancestors have no clipping overflow that prevents sticky positioning.
- [ ] Scroll charts several meters down: the sidebar stays visible and its content scrolls independently. Repeat after resizing the browser.
- [ ] Regions/Markers/Classifications tabs retain their selection and work offline. Comparison shows its meter selector, metrics, Make Region and Finish controls.
- [ ] Meter strips use display titles and cycle unchecked/present/absent without seeking audio; the origin remains present.
- [ ] Meter-state chips have legible labels and distinct high-contrast solid/dashed states, including the disabled origin; native colour picker cancellation never changes inherited category colour.
- [ ] Edit notes, move the caret, expand a section and scroll the panel. Another annotation update preserves the draft, caret, open section and scroll position.
- [ ] Ctrl+Enter saves a note; Esc cancels a draft; N focuses the selected region note. Existing chart shortcuts do nothing while editing.
- [ ] Category, present-at-meter, single-meter and unchecked filters narrow the list without altering annotations. Category edits and colour overrides support undo.
- [ ] Only the selected region calculates per-meter metrics; hide metrics to defer those calculations. Each row shows resolution and unavailable values remain blank.
- [ ] Marker notes, colours and saved snapshots survive tab switches. Clear all markers requires its second confirmation action.
- [ ] Classification selection is passive; Preview/P explicitly seeks and plays. Verify score/source/role filters, numeric score sorting, hidden selection message and elevation.
- [ ] Notes, meter titles and category labels containing HTML-like text display literally and never create elements.
- [ ] Export settings retain context window, minimum usable context and optional both-resolution rows across workspace save/load; default remains best available resolution.
- [ ] Server menu offers full-resolution annotation export; static menu offers browser export only.
- [ ] Open an older config containing `ui.side_panel: legacy`: the current HTML sidebar opens normally; the temporary comparison flag has retired.
- [ ] No copy-to-meter selector or Add Marker at Tap button remains. Shift+drag, R twice, M and double-click still provide the quick annotation routes.
- [ ] Collapsed Annotation visibility settings hide region bands, marker lines and classification bands independently; annotations remain in their lists and reappear when enabled.

