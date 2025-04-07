"""
data_source_selector.py

Browser-based UI for selecting data sources for the Noise Survey Analysis application.
"""

import os
import glob
import logging
from collections import defaultdict
from bokeh.plotting import figure
from bokeh.layouts import column, row, layout
from bokeh.models import (
    ColumnDataSource, DataTable, TableColumn, StringEditor, CheckboxEditor,
    TextInput, Button, Div, Spacer # Added Spacer
)
from bokeh.events import ButtonClick
import os.path

from ..core.data_loaders import scan_directory_for_sources, summarize_scanned_sources
from ..core.config import DEFAULT_BASE_JOB_DIR

logger = logging.getLogger(__name__)

# --- Default Base Directory ---
# You might want to make this configurable via environment variable or config file
# For testing if the default path doesn't exist on your system:
if not os.path.isdir(DEFAULT_BASE_JOB_DIR):
    DEFAULT_BASE_JOB_DIR = os.path.expanduser("~") # Fallback to home directory
    logger.warning(f"Default base job directory not found. Falling back to: {DEFAULT_BASE_JOB_DIR}")


class DataSourceSelector:
    """
    Bokeh UI component for selecting data sources using Job Number and Base Directory.
    """

    def __init__(self, doc, on_data_sources_selected):
        """
        Initialize the data source selector.

        Parameters:
        -----------
        doc : bokeh.document.Document
            The Bokeh document to attach the UI components to.
        on_data_sources_selected : callable
            Callback function to call when data sources are selected.
            Should accept a list of data source dictionaries.
        """
        self.doc = doc
        self.on_data_sources_selected = on_data_sources_selected
        self.scanned_sources = []
        # Added 'original_position' to potentially help with renaming logic if needed later
        # Added 'file_size' to display file sizes in the table
        self.source_table_data = ColumnDataSource({'index': [], 'position': [], 'path': [], 'type': [], 'include': [], 'original_position': [], 'file_size': []})
        self.current_job_directory = None

        # Create UI components
        self._create_ui_components()

    def _create_ui_components(self):
        """Create all UI components for the data source selector."""
        # Title
        self.title_div = Div(
            text="<h1>Noise Survey Analysis - Data Source Selection</h1>",
            width=800
        )

        # --- Directory/Job Input ---
        self.base_dir_label = Div(text="<b>Base Directory:</b>")
        self.base_directory_input = TextInput(
            value=DEFAULT_BASE_JOB_DIR, # Pre-filled
            width=500,
            name="base_directory_input" # Added name for easier reference
        )

        self.job_number_label = Div(text="<b>Job Number:</b>")
        self.job_number_input = TextInput(
            placeholder="e.g., 5852",
            width=150,
            name="job_number_input" # Added name
        )

        self.scan_button = Button(
            label="Scan Job Directory", # Updated label
            button_type="primary",
            width=150 # Adjusted width
        )

        # Input Row Layout
        self.input_row = row(
            column(self.base_dir_label, self.base_directory_input),
            column(self.job_number_label, self.job_number_input),
            column(Spacer(height=20), self.scan_button), # Add spacer for alignment
            sizing_mode="scale_width" # Allow row elements to adjust width
        )
        # --- End Directory/Job Input ---


        # Status
        self.status_div = Div(
            text="Enter Base Directory and Job Number, then click 'Scan Job Directory'.",
            width=800,
            styles={'color': 'blue', 'font-style': 'italic', 'margin-top': '10px'} # Added margin
        )

        # --- Table Controls (Select/Deselect All) ---
        self.select_all_button = Button(label="Select All", width=120, button_type="default", disabled=True)
        self.deselect_all_button = Button(label="Deselect All", width=120, button_type="default", disabled=True)
        self.table_controls_row = row(self.select_all_button, self.deselect_all_button)
        # --- End Table Controls ---

        # Results table
        self.table_columns = [
            TableColumn(field="include", title="Include", editor=CheckboxEditor(), width=60), # Adjusted width
            TableColumn(field="position", title="Position", editor=StringEditor(), width=150), # Adjusted width
            TableColumn(field="type", title="Type", width=100),
            TableColumn(field="file_size", title="Size", width=80), # New column for file size
            TableColumn(field="path", title="File/Directory Path", width=450) # Adjusted width
        ]
        self.data_table = DataTable(
            source=self.source_table_data,
            columns=self.table_columns,
            width=1200, # Increased width by 1.5x from 800
            height=350, # Adjusted height
            editable=True,
            index_position=None,
            autosize_mode="force_fit" # Try to fit columns
        )

        # --- Rename Group Controls ---
        self.rename_info_div = Div(text="<b>Rename Position Group:</b>", width=800)
        self.old_position_input = TextInput(placeholder="Current Position Name", width=200)
        self.new_position_input = TextInput(placeholder="New Position Name", width=200)
        self.rename_button = Button(label="Rename Group", width=150, button_type="warning", disabled=True)
        self.rename_controls_row = row(
            self.old_position_input,
            self.new_position_input,
            self.rename_button
        )
        # --- End Rename Group Controls ---


        # Information display (Scan Summary)
        self.info_div = Div(
            text="Scan results summary will appear here.", # Updated initial text
            width=800,
            styles={'background-color': '#f0f0f0', 'padding': '10px', 'border-radius': '5px', 'margin-top': '10px'} # Added margin
        )

        # Action buttons
        self.load_button = Button(
            label="Load Selected Data",
            button_type="success",
            width=200,
            disabled=True
        )
        self.cancel_button = Button(
            label="Cancel",
            button_type="default", # Keep default, less prominent
            width=200
        )
        self.action_button_row = row(
            self.load_button,
            self.cancel_button
        )

        # --- Main Layout ---
        self.main_layout = column(
            self.title_div,
            self.input_row,
            self.status_div,
            Spacer(height=10), # Add spacing
            self.table_controls_row, # Add select/deselect buttons
            self.data_table,
            Spacer(height=10), # Add spacing
            self.rename_info_div, # Add rename controls title
            self.rename_controls_row, # Add rename controls
            Spacer(height=10), # Add spacing
            self.info_div, # Scan summary
            Spacer(height=20), # Add spacing
            self.action_button_row, # Load/Cancel buttons
            width=1250 # Increased width to accommodate wider table
        )

        # --- Event Handlers ---
        self.scan_button.on_click(self._scan_directory)
        self.load_button.on_click(self._load_selected_data)
        self.cancel_button.on_click(self._cancel_selection)
        self.select_all_button.on_click(self._select_all)
        self.deselect_all_button.on_click(self._deselect_all)
        self.rename_button.on_click(self._rename_position_group)

        # Optional: Update rename fields when a position cell is edited
        # This requires more complex handling of Bokeh events if desired
        # self.source_table_data.on_change('patching', self._handle_table_edit)

    # --- Callback Methods ---

    def _scan_directory(self, event=None):
        """Handle the scan directory button click event using Base Dir and Job Number."""
        base_dir = self.base_directory_input.value.strip()
        job_num = self.job_number_input.value.strip()

        # --- Input Validation ---
        if not base_dir:
            self._update_status("Please enter a Base Directory path.", 'red')
            return
        if not job_num:
            self._update_status("Please enter a Job Number.", 'red')
            return
        if not os.path.isdir(base_dir):
            self._update_status(f"Base Directory not found: {base_dir}", 'red')
            return
        # --- End Input Validation ---

        self._update_status(f"Scanning for job '{job_num}' in '{base_dir}'...", 'blue')
        self.load_button.disabled = True # Disable buttons during scan
        self.rename_button.disabled = True
        self.select_all_button.disabled = True
        self.deselect_all_button.disabled = True

        # --- Find Job Directory ---
        try:
            search_pattern = os.path.join(base_dir, f"{job_num}*") # Pattern like G:\...\Jobs\5852*
            logger.info(f"Searching for job directory with pattern: {search_pattern}")
            possible_dirs = [d for d in glob.glob(search_pattern) if os.path.isdir(d)]
            logger.info(f"Found potential matches: {possible_dirs}")

            if not possible_dirs:
                self._update_status(f"No directory found for job number '{job_num}' in '{base_dir}'.", 'orange')
                self._clear_table()
                return
            elif len(possible_dirs) > 1:
                self._update_status(f"Multiple directories found for job '{job_num}': {possible_dirs}. Please refine.", 'red')
                self._clear_table()
                return
            else:
                job_dir = possible_dirs[0]
                self._update_status(f"Found job directory: {job_dir}", 'blue')
        except Exception as e:
            logger.exception("Error finding job directory")
            self._update_status(f"Error searching for job directory: {e}", 'red')
            self._clear_table()
            return
        # --- End Find Job Directory ---


        # --- Find 'surveys' Subdirectory ---
        survey_dir_name = f"{job_num} surveys"
        surveys_dir = os.path.join(job_dir, survey_dir_name)
        if os.path.isdir(surveys_dir):
            scan_target_dir = surveys_dir
            self._update_status(f"Found '{survey_dir_name}' subdirectory. Scanning: {scan_target_dir}", 'blue')
        else:
            # Fall back to searching the job directory recursively
            scan_target_dir = job_dir
            self._update_status(f"'{survey_dir_name}' subdirectory not found. Falling back to recursive search of job directory.", 'blue')
        # --- End Find 'surveys' Subdirectory ---


        # --- Scan Target Directory ---
        self.current_job_directory = scan_target_dir # Store for reference
        try:
            # Assuming scan_directory_for_sources handles recursion and file identification
            self.scanned_sources = scan_directory_for_sources(scan_target_dir)

            if not self.scanned_sources:
                self._update_status(f"No valid data files found in {scan_target_dir}", 'orange')
                self._clear_table()
                return

            # --- Populate Table ---
            summary = summarize_scanned_sources(self.scanned_sources)
            indices = list(range(len(self.scanned_sources)))
            positions = [src["position_name"] for src in self.scanned_sources]
            # Store original position separately in case needed for complex rename logic later
            original_positions = [src["position_name"] for src in self.scanned_sources]
            paths = [src["file_path"] for src in self.scanned_sources]
            types = [src.get("data_type", "unknown") for src in self.scanned_sources]
            # Default to included, user can deselect
            include = [src.get("enabled", True) for src in self.scanned_sources]
            
            # Get file sizes
            file_sizes = []
            for src in self.scanned_sources:
                path = src["file_path"]
                if os.path.isfile(path):
                    size_bytes = os.path.getsize(path)
                    # Format size to human-readable format
                    if size_bytes < 1024:
                        size_str = f"{size_bytes} B"
                    elif size_bytes < 1024 * 1024:
                        size_str = f"{size_bytes/1024:.1f} KB"
                    else:
                        size_str = f"{size_bytes/(1024*1024):.1f} MB"
                    file_sizes.append(size_str)
                else:
                    file_sizes.append("Dir")  # For directories

            new_data = {
                'index': indices,
                'position': positions,
                'path': paths,
                'type': types,
                'include': include,
                'original_position': original_positions, # Keep track if needed
                'file_size': file_sizes # Add file sizes
            }
            self.source_table_data.data = new_data # Update table data
            # --- End Populate Table ---

            # Enable buttons
            self.load_button.disabled = False
            self.rename_button.disabled = False
            self.select_all_button.disabled = False
            self.deselect_all_button.disabled = False

            # Update status and summary info
            summary_text = "<b>Scan Results Summary:</b><br>"
            for position, types_counts in summary.items():
                type_strings = [f"{count} {t}" for t, count in types_counts.items()]
                summary_text += f"• Position '{position}': {', '.join(type_strings)}<br>"
            self.info_div.text = summary_text
            self._update_status(f"Scan complete. Found {len(self.scanned_sources)} data sources/groups across {len(summary)} position(s).", 'green')

        except Exception as e:
            logger.exception(f"Error scanning directory: {e}")
            self._update_status(f"Error during scanning: {str(e)}", 'red')
            self._clear_table()
        # --- End Scan Target Directory ---


    def _load_selected_data(self, event=None):
        """Handle the load selected data button click event."""
        if not self.scanned_sources:
            self._update_status("No data sources to load.", 'orange')
            return

        table_data = self.source_table_data.data
        selected_sources = []
        included_count = 0

        for i in range(len(table_data['index'])):
            if table_data['include'][i]:
                included_count += 1
                # Find the original source using the index stored in the table
                original_source_index = table_data['index'][i]
                # Ensure index is valid
                if 0 <= original_source_index < len(self.scanned_sources):
                    source = self.scanned_sources[original_source_index].copy()
                    # Update with potentially edited position name from the table
                    source['position_name'] = table_data['position'][i]
                    source['enabled'] = True # Mark as enabled for loading
                    selected_sources.append(source)
                else:
                    logger.error(f"Invalid index {original_source_index} found in table data.")
                    self._update_status(f"Internal error: Invalid data index encountered.", 'red')
                    return # Stop processing on error


        if included_count == 0:
            self._update_status("No data sources selected. Check the 'Include' column.", 'orange')
            return

        if not selected_sources:
             # This case might happen if indices were invalid
            self._update_status("Could not prepare selected sources. Internal error likely.", 'red')
            return

        # Call the callback with the selected sources
        self._update_status(f"Loading {len(selected_sources)} selected data sources...", 'blue')
        self.on_data_sources_selected(selected_sources)


    def _cancel_selection(self, event=None):
        """Handle the cancel button click event."""
        self._update_status("Selection cancelled.", 'blue')
        # Call the callback with an empty list to indicate cancellation
        self.on_data_sources_selected([])


    def _select_all(self, event=None):
        """Set all 'include' checkboxes to True."""
        if not self.source_table_data.data['index']: return # No data
        current_data = self.source_table_data.data.copy()
        current_data['include'] = [True] * len(current_data['index'])
        self.source_table_data.data = current_data # Assign new dict to trigger update
        self._update_status("All sources selected.", 'blue')


    def _deselect_all(self, event=None):
        """Set all 'include' checkboxes to False."""
        if not self.source_table_data.data['index']: return # No data
        current_data = self.source_table_data.data.copy()
        current_data['include'] = [False] * len(current_data['index'])
        self.source_table_data.data = current_data # Assign new dict to trigger update
        self._update_status("All sources deselected.", 'blue')


    def _rename_position_group(self, event=None):
        """Rename all entries matching the 'Current Position Name'."""
        old_name = self.old_position_input.value.strip()
        new_name = self.new_position_input.value.strip()

        if not old_name or not new_name:
            self._update_status("Please enter both Current and New position names to rename.", 'orange')
            return

        if not self.source_table_data.data['index']:
            self._update_status("No data in table to rename.", 'orange')
            return

        current_data = self.source_table_data.data.copy() # Work on a copy
        positions = current_data['position'] # Get the list of positions
        renamed_count = 0

        # Create a new list for updated positions
        updated_positions = []
        for pos in positions:
            if pos == old_name:
                updated_positions.append(new_name)
                renamed_count += 1
            else:
                updated_positions.append(pos) # Keep original name

        if renamed_count > 0:
            current_data['position'] = updated_positions # Update the list in the copied dict
            self.source_table_data.data = current_data # Assign the modified dict back
            self._update_status(f"Renamed {renamed_count} entries from '{old_name}' to '{new_name}'.", 'green')
            # Clear the input fields after successful rename
            self.old_position_input.value = ""
            self.new_position_input.value = ""
        else:
            self._update_status(f"No entries found with position name '{old_name}'.", 'orange')


    def _update_status(self, message, color='blue'):
        """Helper method to update the status Div with message and color."""
        self.status_div.text = message
        self.status_div.styles = {'color': color, 'font-style': 'italic', 'margin-top': '10px'}
        logger.info(f"Status update: {message}")


    def _clear_table(self):
         """Clears the data table and disables relevant buttons."""
         self.source_table_data.data = {'index': [], 'position': [], 'path': [], 'type': [], 'include': [], 'original_position': [], 'file_size': []}
         self.load_button.disabled = True
         self.rename_button.disabled = True
         self.select_all_button.disabled = True
         self.deselect_all_button.disabled = True
         self.info_div.text = "Scan results summary will appear here." # Reset summary


    def get_layout(self):
        """Get the main layout for the data source selector."""
        return self.main_layout

# --- Function to integrate into Bokeh app ---

def create_data_source_selector(doc, on_data_sources_selected):
    """
    Create a data source selector UI in the given Bokeh document.

    Parameters:
    -----------
    doc : bokeh.document.Document
        The Bokeh document to attach the UI components to.
    on_data_sources_selected : callable
        Callback function to call when data sources are selected.
        Should accept a list of data source dictionaries.

    Returns:
    --------
    DataSourceSelector
        The created data source selector object.
    """
    # Configure logging if not already done (useful for standalone testing)
    if not logging.getLogger().hasHandlers():
         logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    selector = DataSourceSelector(doc, on_data_sources_selected)
    doc.add_root(selector.get_layout())
    # Set title for the browser tab
    doc.title = "Noise Survey - Select Data"
    return selector