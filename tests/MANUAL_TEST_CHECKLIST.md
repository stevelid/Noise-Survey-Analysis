# Manual Test Checklist — Noise Survey Analysis Dashboard

**Purpose:** This checklist ensures all user interactions work correctly in the Bokeh environment. Run this checklist before each release or after significant changes to interaction logic.

**Last Updated:** 2025-10-10
**Version:** 1.3.1

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
- [ ] **Expected:** Tap line moves to next data point (~5 minutes forward)
- [ ] **Expected:** Summary table updates
- [ ] **Expected:** If audio is playing, it jumps to new position
- [ ] **Action:** Press Left Arrow
- [ ] **Expected:** Tap line moves to previous data point (~5 minutes backward)
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
- [ ] **Action:** Click "Log View Enabled" to disable
- [ ] **Expected:** All charts switch to overview data
- [ ] **Expected:** Chart data becomes less granular
- [ ] **Action:** Click to enable again
- [ ] **Expected:** All charts switch back to log data
- [ ] **Expected:** Chart data becomes more granular

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

## 11. Data Source Selector Panel 🔴 SERVER

### 11.1 Highlighting Rules 🟢
- [ ] **Setup:** Scan a job directory that contains CSV log/summary files and unrelated files
- [ ] **Expected:** Only CSV/TXT files with expected naming and size bounds show highlighted styling
- [ ] **Expected:** Other file types display without the old validity column or highlight badges
- [ ] **Test:** Confirm log and summary CSVs highlight independently when their sizes meet expectations

### 11.2 Config Auto-Detection 🔴
- [ ] **Setup:** Scan a directory containing a single valid `noise_survey_config_*.json`
- [ ] **Expected:** "Load Config" button enables automatically
- [ ] **Expected:** Config loads immediately into the Included Files table without manual selection
- [ ] **Expected:** Status banner reports the auto-loaded config and warns if referenced files are missing

### 11.3 Multiple Config Prompt 🔴
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
