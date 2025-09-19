# Region Marker & Analysis Panel Guide

The Region Markers feature lets analysts highlight time ranges directly on the charts and review calculated metrics in a dedicated side panel. All computations happen in the browser, so the metrics update instantly while you refine a region.

## Creating & Managing Regions
- **Create:** Hold **Shift** and drag horizontally on either the time-series or spectrogram view. A blue band appears across both charts for that position.
- **Select:** Click inside a region or choose it from the list in the side panel. Only one region can be active at a time; the active band is highlighted.
- **Nudge:** While a region is selected, use **Shift + ←/→** to move the right edge or **Alt + ←/→** to move the left edge. Each press nudges by roughly three seconds (10% of the current keyboard navigation step).
- **Delete:** Hold **Ctrl** and click inside the region, or use the Delete button in the side panel list.
- **Notes:** Add comments in the Notes box inside the detail view; changes are saved instantly.

## Analysis Side Panel
- **Region List:** Shows every region with its position, time span, and duration. Click a row to activate it. The Delete button removes the region everywhere.
- **Detail View:** Displays the active region’s metrics—LAeq, LAFmax, and LAF90 (greyed out if only overview data is available). The Average Spectrum mini-chart shows band-by-band energy averages for the selected parameter. Use **Copy line** to send a formatted summary to the clipboard.
- **Metrics Refresh:** Metrics recalc automatically whenever you resize or import a region.

## Export & Import
- **Export Regions:** Click **Export Regions** to download a JSON file containing all bounds, notes, and the latest metrics snapshot.
- **Import Regions:** Click **Import Regions** and choose a previously exported JSON file. Regions are recreated and metrics are recomputed against the currently loaded dataset for consistency.

Tip: Regions are stored per position, so create separate bands for each site you need to report on.
