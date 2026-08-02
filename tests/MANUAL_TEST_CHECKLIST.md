# Manual Test Checklist — Noise Survey Analysis Dashboard

**Purpose:** This checklist ensures all user interactions work correctly in the Bokeh environment. Run this checklist before each release or after significant changes to interaction logic.

**Last Updated:** 2026-08-02
**Version:** 1.7.0

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
- [ ] **Expected:** Marker appears as orange vertical line on all charts
- [ ] **Expected:** Marker panel is displayed
- [ ] **Expected:** New marker is the active selected marker
- [ ] **Expected:** Marker appears in Markers panel table

### 1.3 Shift + Click (Create Region) 🟢
- [ ] **Action:** Click to place tap line, then Shift+click at different location
- [ ] **Expected:** Region is created spanning from first to second click
- [ ] **Expected:** Region appears as colored box on the charts
- [ ] **Expected:** Region appears in Regions panel table
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

### 1.7 

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
- [ ] **Expected:** Regions panel shows "Create Region mode active" banner with timestamp and position
- [ ] **Expected:** Banner shows instructions: "Move tap line and press R again to finish, or Escape to cancel"
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
- [ ] **Expected:** Marker table updates with new timestamp
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

### 3.4 Clear All Markers Button 🟢
- [ ] **Action:** Create 2-3 markers, click "Clear All Markers"
- [ ] **Expected:** All markers disappear from charts
- [ ] **Expected:** Markers panel table becomes empty
- [ ] **Expected:** Marker selection clears
- [ ] **Test:** After clearing, create new markers - should work normally
- [ ] **Expected:** Newly created markers repopulate the table with every marker visible
- [ ] **Test:** After clearing, all marker functionality still works (double-click, M key, etc.)

### 3.5 Chart Visibility Checkboxes 🟢
- [ ] **Action:** Uncheck a time series visibility checkbox
- [ ] **Expected:** That time series chart becomes hidden
- [ ] **Action:** Check it again
- [ ] **Expected:** Chart becomes visible again
- [ ] **Test:** Hide and show spectrogram charts
- [ ] **Test:** Hide all charts, then show them all

### 3.6 Session Menu 🟡 PARTIAL
- [ ] **Action:** Click Menu → "Save Workspace"
- [ ] **Expected:** Workspace state saves to localStorage
- [ ] **Expected:** Success message appears (if implemented)
- [ ] **Action:** Make changes, click Menu → "Load Workspace"
- [ ] **Expected:** Previous workspace state restores
- [ ] **Action:** Click Menu → "Export Annotations (CSV)"
- [ ] **Expected:** CSV file downloads with all regions and markers
- [ ] **Action:** Click Menu → "Import Annotations (CSV)"
- [ ] **Expected:** File picker opens
- [ ] **Expected:** Annotations load from selected CSV
- [ ] **Expected:** Imported regions show overlays on all relevant charts
- [ ] **Test:** Select an imported region and confirm metrics (duration, LAeq) populate without console errors

---

## 4. Region Panel Interactions 🟡 PARTIAL

### 4.1 Region Table Selection 🟢
- [ ] **Action:** Create 2-3 regions, click on one in the table
- [ ] **Expected:** Region becomes selected (highlighted in table)
- [ ] **Expected:** Region details appear in panel
- [ ] **Expected:** Region highlights on charts
- [ ] **Expected:** Marker selection clears (if any marker was selected)
- [ ] **Expected:** Side panel shows Regions tab
- [ ] **Action:** Click on a different region
- [ ] **Expected:** Selection switches to new region
- [ ] **Expected:** Previous region unhighlights

### 4.2 Region Visibility Toggle 🟢
- [ ] **Action:** Click "Regions" toggle to disable
- [ ] **Expected:** All region overlays disappear from charts
- [ ] **Expected:** Region panel details hide
- [ ] **Action:** Click to enable again
- [ ] **Expected:** Region overlays reappear
- [ ] **Expected:** Region panel details show

### 4.3 Auto Day & Night Button 🟢
- [ ] **Action:** Click "Auto Day & Night" button
- [ ] **Expected:** Regions are automatically created for day periods (7am-11pm)
- [ ] **Expected:** Regions are automatically created for night periods (11pm-7am)
- [ ] **Expected:** Day regions have green color
- [ ] **Expected:** Night regions have purple color
- [ ] **Test:** Verify regions span entire dataset

### 4.4 Region Color Picker 🟢
- [ ] **Action:** Select a region, change its color
- [ ] **Expected:** Region color updates on all charts immediately
- [ ] **Expected:** Region color updates in table
- [ ] **Test:** Try multiple different colors

### 4.5 Region Notes Input 🟢
- [ ] **Action:** Select a region, type notes in text area
- [ ] **Expected:** Notes save automatically as you type
- [ ] **Expected:** Notes persist when switching to another region and back
- [ ] **Expected:** Keyboard shortcuts (Space, R, M) do not trigger while typing
- [ ] **Test:** Type special characters and emojis

### 4.6 Copy Summary Button 🟡 PARTIAL
- [ ] **Action:** Select a region with metrics, click "Copy Summary"
- [ ] **Expected:** Region summary copies to clipboard
- [ ] **Action:** Paste into text editor
- [ ] **Expected:** Summary includes region name, timestamps, duration, metrics, notes

### 4.7 Delete Region Button 🟢
- [ ] **Action:** Select a region, click "Delete Region"
- [ ] **Expected:** Region is deleted immediately
- [ ] **Expected:** Region disappears from charts and table
- [ ] **Expected:** Panel shows no selection
- [ ] **Test:** Delete all regions, then create new ones - should work normally
- [ ] **Test:** After deleting all regions and recreating them, all region functionality still works
- [ ] **Expected:** When recreating multiple regions, every region appears in the regions table

### 4.8 Add Area Button 🟢
- [ ] **Action:** Select a region, click "Add Area"
- [ ] **Expected:** Add-area mode activates
- [ ] **Action:** Shift+click to create another time span
- [ ] **Expected:** New area is added to the same region
- [ ] **Expected:** Region now spans multiple non-contiguous areas
- [ ] **Action:** Click "Add Area" again
- [ ] **Expected:** Add-area mode deactivates

### 4.9 Merge Regions Button 🟢
- [ ] **Action:** Create 2 regions, select one, click "Merge Regions"
- [ ] **Expected:** Merge mode activates
- [ ] **Expected:** Dropdown appears with other regions
- [ ] **Action:** Select a region from dropdown, click "Merge Regions" again
- [ ] **Expected:** Two regions merge into one
- [ ] **Expected:** Merged region spans all areas from both regions

### 4.10 Split Areas Button 🟢
- [ ] **Action:** Create a multi-area region, select it, click "Split Areas"
- [ ] **Expected:** Region splits into separate regions (one per area)
- [ ] **Expected:** Each new region appears in table
- [ ] **Expected:** Original region is deleted

### 4.11 Copy Spectrum Values Button 🟡 PARTIAL
- [ ] **Action:** Select a region with spectrum data, click "Copy Spectrum Values"
- [ ] **Expected:** Spectrum data copies to clipboard
- [ ] **Action:** Paste into spreadsheet
- [ ] **Expected:** Frequency bands and levels appear in columns

---

## 5. Marker Panel Interactions 🟡 PARTIAL

### 5.1 Marker Table Selection 🟡 PARTIAL
- [ ] **Action:** Create 2-3 markers, click on one in the table
- [ ] **Expected:** Marker becomes selected (highlighted in table)
- [ ] **Expected:** Marker details appear in panel
- [ ] **Expected:** Tap line jumps to marker timestamp
- [ ] **Expected:** Region selection clears (if any region was selected)
- [ ] **Expected:** Side panel shows Markers tab
- [ ] **Action:** Click on a different marker
- [ ] **Expected:** Selection switches to new marker
- [ ] **Expected:** Tap line jumps to new marker timestamp

### 5.2 Marker Visibility Toggle 🟢
- [ ] **Action:** Click "Markers" toggle to disable
- [ ] **Expected:** All marker lines disappear from charts
- [ ] **Action:** Click to enable again
- [ ] **Expected:** Marker lines reappear

### 5.3 Marker Color Picker 🟢
- [ ] **Action:** Select a marker, change its color
- [ ] **Expected:** Marker color updates on all charts immediately
- [ ] **Expected:** Marker color updates in table (if shown)

### 5.4 Marker Notes Input 🟢
- [ ] **Action:** Select a marker, type notes in text area
- [ ] **Expected:** Notes save automatically as you type
- [ ] **Expected:** Notes persist when switching markers
- [ ] **Expected:** Keyboard shortcuts (Space, R, M) do not trigger while typing

### 5.5 Copy Details Button 🟡 PARTIAL
- [ ] **Action:** Select a marker, click "Copy Details"
- [ ] **Expected:** Marker details copy to clipboard
- [ ] **Action:** Paste into text editor
- [ ] **Expected:** Details include timestamp, position, metrics, notes

### 5.6 Delete Marker Button 🟢
- [ ] **Action:** Select a marker, click "Delete Marker"
- [ ] **Expected:** Marker is deleted immediately
- [ ] **Expected:** Marker disappears from charts and table
- [ ] **Expected:** Marker selection clears
- [ ] **Test:** Delete all markers, then create new ones - should work normally
- [ ] **Test:** After deleting all markers and recreating them, all marker functionality still works

### 5.7 Add Marker at Tap Button 🟢
- [ ] **Action:** Click on chart to place tap line, click "Add Marker at Tap"
- [ ] **Expected:** New marker is created at tap line position
- [ ] **Expected:** Marker appears on charts and in table
- [ ] **Expected:** Newly created marker is automatically selected
- [ ] **Expected:** Marker details appear in panel

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
- [ ] **Expected:** Normal side panel hides
- [ ] **Expected:** Box select tool becomes active
- [ ] **Expected:** Instructions appear in comparison panel

### 7.2 Position Selector 🟢
- [ ] **Action:** Uncheck a position in comparison selector
- [ ] **Expected:** That position is excluded from comparison
- [ ] **Expected:** Metrics update to exclude that position
- [ ] **Action:** Check it again
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
- [ ] **Expected:** Each row shows duration, LAeq, LAFmax, LA90
- [ ] **Expected:** Values are accurate for selected time slice

### 7.5 Make Region(s) Button 🟢
- [ ] **Action:** Select a time slice, click "Make Region(s)"
- [ ] **Expected:** One region is created per included position
- [ ] **Expected:** Each region spans the selected time slice
- [ ] **Expected:** Regions appear in Regions panel after exiting comparison mode

### 7.6 Finish Comparison Button 🟢
- [ ] **Action:** Click "Finish Comparison"
- [ ] **Expected:** Comparison mode exits
- [ ] **Expected:** Comparison panel hides
- [ ] **Expected:** Normal side panel reappears
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
- [ ] **Action:** Delete all markers using "Clear All Markers"
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
