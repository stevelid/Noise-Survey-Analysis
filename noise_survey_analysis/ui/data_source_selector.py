# noise_survey_analysis/ui/data_source_selector.py

import os
import glob
import logging
import json
from collections import defaultdict
from datetime import datetime
from bokeh.plotting import figure
from bokeh.layouts import column, row, layout, grid
from bokeh.models import (
    ColumnDataSource, DataTable, TableColumn, StringEditor, CheckboxEditor,
    TextInput, Button, Div, Spacer, Select, MultiSelect, CustomJS, Panel, Tabs,
    HTMLTemplateFormatter, SelectEditor, NumberFormatter
)
from bokeh.events import ButtonClick, ValueSubmit
import os.path

from ..core.data_loaders import scan_directory_for_sources, summarize_scanned_sources
from ..core.config import DEFAULT_BASE_JOB_DIR

logger = logging.getLogger(__name__)

# --- Default Base Directory ---
if not os.path.isdir(DEFAULT_BASE_JOB_DIR):
    DEFAULT_BASE_JOB_DIR = os.path.expanduser("~")
    logger.warning(f"Default base job directory not found. Falling back to: {DEFAULT_BASE_JOB_DIR}")


CSV_PRIORITY_KEYWORDS = ("log", "summary")
PRIORITY_HIGHLIGHT_COLOR = "#1f3c88"  # Deep accent for likely valid sources
PRIORITY_HIGHLIGHT_TEXT_COLOR = "#f8f9fa"  # Light text for dark background
SECONDARY_HIGHLIGHT_COLOR = "#f1f3f5"  # Muted backdrop for other files
SECONDARY_HIGHLIGHT_TEXT_COLOR = "#212529"
NTI_DEFAULT_PRIORITY_THRESHOLD_BYTES = 0.1 * 1024 * 1024  # 3 MB default, tune per file type below
NTI_SIZE_HINTS_BYTES = {
    "rta_rpt": 0.1 * 1024 * 1024,
    "rpt_report": 0.1 * 1024 * 1024,
    "rta_log": 1 * 1024 * 1024,
    "log": 0.5 * 1024 * 1024,
    "spectral": 0.5 * 1024 * 1024,
}

VALIDITY_STATUS_DISPLAY = {
    "likely_valid": {
        "label": "Likely valid",
        "text_color": "#0f5132",
        "bg_color": "rgba(25, 135, 84, 0.18)",
        "highlight_color": "",
    },
    "needs_review": {
        "label": "Check header",
        "text_color": "#664d03",
        "bg_color": "rgba(255, 193, 7, 0.2)",
        "highlight_color": "rgba(255, 193, 7, 0.25)",
    },
    "unlikely_valid": {
        "label": "Header mismatch",
        "text_color": "#842029",
        "bg_color": "rgba(220, 53, 69, 0.18)",
        "highlight_color": "rgba(220, 53, 69, 0.28)",
    },
    "unknown": {
        "label": "Unknown",
        "text_color": "#495057",
        "bg_color": "rgba(108, 117, 125, 0.12)",
        "highlight_color": "",
    },
}


class DataSourceSelector:
    """
    Bokeh UI component for selecting data sources using Job Number and Base Directory.
    Features a dual-pane transfer list UI for selecting files, and also supports drag-and-drop.
    """

    def __init__(self, doc, on_data_sources_selected):
        """
        Initialize the data source selector.
        """
        self.doc = doc
        self.on_data_sources_selected = on_data_sources_selected
        self.scanned_sources = []
        self.current_config_path = None
        
        # Data sources for the dual-pane interface
        self.available_files_source = ColumnDataSource({
            'index': [], 'position': [], 'relpath': [], 'display_path': [],
            'fullpath': [], 'type': [], 'file_size': [],
            'group': [], 'parser_type': [], 'file_size_bytes': [],
            'highlight_color': [], 'highlight_text_color': [], 'highlight_reason': [],
            'validity_status': [], 'validity_reason': [], 'header_preview': [],
            'validity_label': [], 'validity_text_color': [], 'validity_bg_color': [],
            'validity_tooltip': []
        })

        self.included_files_source = ColumnDataSource({
            'index': [], 'position': [], 'relpath': [], 'display_path': [],
            'fullpath': [], 'type': [], 'file_size': [],
            'group': [], 'parser_type': [], 'file_size_bytes': [],
            'validity_status': [], 'validity_reason': [], 'header_preview': [],
            'validity_label': [], 'validity_text_color': [], 'validity_bg_color': [],
            'validity_tooltip': []
        })
        
        self.source_table_data = ColumnDataSource({
            'index': [], 'position': [], 'path': [], 'type': [], 'include': [], 
            'original_position': [], 'file_size': []
        })
        
        self.current_job_directory = None
        
        self.dropped_files_source = ColumnDataSource(data={'paths': []}, name='dropped_files_source')

        self._create_ui_components()
        self._attach_dnd_handlers()


    def _resolve_validity_fields(self, status, reason, header_preview):
        normalized_status = (status or "unknown").lower()
        display = VALIDITY_STATUS_DISPLAY.get(normalized_status, VALIDITY_STATUS_DISPLAY["unknown"])
        safe_reason = reason or ""
        safe_preview = header_preview or ""
        tooltip_parts = [part for part in (safe_reason.strip(), safe_preview.strip()) if part]
        tooltip = "\n".join(tooltip_parts)

        return {
            'status': normalized_status,
            'reason': safe_reason,
            'header': safe_preview,
            'label': display["label"],
            'text_color': display["text_color"],
            'bg_color': display["bg_color"],
            'tooltip': tooltip,
            'highlight_color': display.get("highlight_color", "")
        }


    def _create_ui_components(self):
        """Create all UI components for the data source selector."""
        self.title_div = Div(text="<h1>Noise Survey Analysis - Data Source Selection</h1>", width=800)

        self.base_dir_label = Div(text="<b>Base Directory:</b>")
        self.base_directory_input = TextInput(value=DEFAULT_BASE_JOB_DIR, width=500, name="base_directory_input")
        self.job_number_label = Div(text="<b>Job Number:</b>")
        self.job_number_input = TextInput(placeholder="e.g., 5852", width=150, name="job_number_input")
        self.scan_button = Button(label="Scan Job Directory", button_type="primary", width=150)

        self.input_row = row(
            column(self.base_dir_label, self.base_directory_input),
            column(self.job_number_label, self.job_number_input),
            column(Spacer(height=20), self.scan_button),
            sizing_mode="scale_width"
        )
        
        self.status_div = Div(
            text="Enter Base Directory and Job Number, then click 'Scan Job Directory'. Or drag and drop files/folders anywhere on this panel.",
            width=800, styles={'color': 'blue', 'font-style': 'italic', 'margin-top': '10px'} 
        )

        self.available_files_label = Div(
            text="<b>Available Files:</b> <i>(Highlights flag heuristics; Validity column shows header checks)</i>",
            width=400
        )

        highlight_template = """
        <div style="background-color:<% if (highlight_color) { %><%= highlight_color %><% } else { %>transparent<% } %>; color:<%= highlight_text_color %>;
                    padding:4px 6px; border-radius:4px;">
            <span title="<%= highlight_reason %>"><%= value %></span>
        </div>
        """

        validity_template = """
        <div style=\"padding:4px 6px; border-radius:4px; background-color:<%= validity_bg_color %>;\">
            <span style=\"color:<%= validity_text_color %>; font-weight:600;\" <% if (validity_tooltip) { %>title=\"<%- validity_tooltip %>\"<% } %>>
                <%= validity_label %>
            </span>
        </div>
        """

        self.available_files_columns = [
            TableColumn(field="group", title="Folder", width=120),
            TableColumn(field="display_path", title="File Path", width=250,
                        formatter=HTMLTemplateFormatter(template=highlight_template)),
            TableColumn(field="type", title="Type", width=80),
            TableColumn(field="position", title="Position", width=120),
            TableColumn(field="file_size", title="Size", width=80),
            TableColumn(field="validity_label", title="Validity", width=140,
                        formatter=HTMLTemplateFormatter(template=validity_template))
        ]
        
        self.available_files_table = DataTable(
            source=self.available_files_source, columns=self.available_files_columns,
            width=650, height=350, editable=False, index_position=None,
            autosize_mode="force_fit", selectable=True, sortable=True
        )
        
        self.add_button = Button(label="Add ▶", width=100, button_type="success", disabled=True)
        self.remove_button = Button(label="◀ Remove", width=100, button_type="danger", disabled=True)
        self.bulk_edit_button = Button(label="Bulk Edit Positions", width=120, button_type="warning", disabled=True)
        self.transfer_buttons = column(Spacer(height=100), self.add_button, Spacer(height=10), self.remove_button, Spacer(height=10), self.bulk_edit_button, Spacer(height=100), width=120)
        
        self.included_files_label = Div(text="<b>Included Files:</b> <i>(Click position names to edit)</i>", width=500)
        
        parser_options = ['auto', 'svan', 'sentry', 'nti', 'audio']
        self.included_files_columns = [
            TableColumn(field="display_path", title="File Path", width=250),
            TableColumn(field="type", title="Type", width=80),
            TableColumn(field="position", title="Position ✏️", editor=StringEditor(), width=120),
            TableColumn(field="parser_type", title="Parser", editor=SelectEditor(options=parser_options), width=100), 
            TableColumn(field="file_size", title="Size", width=80)
        ]
        
        self.included_files_table = DataTable(
            source=self.included_files_source, columns=self.included_files_columns,
            width=650, height=350, editable=True, index_position=None,
            autosize_mode="force_fit", selectable=True, sortable=True
        )
        
        self.dual_pane_layout = row(
            column(self.available_files_label, self.available_files_table),
            self.transfer_buttons,
            column(self.included_files_label, self.included_files_table)
        )
        
        self.info_div = Div(
            text="Scan results summary will appear here.", width=800,
            styles={'background-color': '#f0f0f0', 'padding': '10px', 'border-radius': '5px', 'margin-top': '10px'}
        )

        self.save_config_button = Button(label="Save Config", button_type="warning", width=120, disabled=True)
        self.load_config_button = Button(label="Load Config", button_type="default", width=120)
        self.load_button = Button(label="Load Selected Data", button_type="success", width=200, disabled=True)
        self.cancel_button = Button(label="Cancel", button_type="default", width=200)
        
        self.config_controls_row = row(self.save_config_button, self.load_config_button, Spacer(width=20), self.load_button, self.cancel_button)

        self.main_layout = column(
            self.title_div, self.input_row, self.status_div, Spacer(height=10), 
            self.dual_pane_layout, Spacer(height=20), self.config_controls_row, 
            name="data_source_selector_main_layout", width=1450,
        )

        self.job_number_input.on_event(ValueSubmit, self._scan_directory)
        self.scan_button.on_click(self._scan_directory)
        self.load_button.on_click(self._load_selected_data)
        self.cancel_button.on_click(self._cancel_selection)
        self.save_config_button.on_click(self._save_config)
        self.load_config_button.on_click(self._load_config)
        self.add_button.on_click(self._add_selected_files)
        self.remove_button.on_click(self._remove_selected_files)
        self.bulk_edit_button.on_click(self._bulk_edit_positions)
        self.available_files_table.source.selected.on_change('indices', self._on_available_selection_change)
        self.included_files_table.source.selected.on_change('indices', self._on_included_selection_change)
        self.included_files_source.on_change('data', self._validate_positions)
        self.dropped_files_source.on_change('data', self._handle_dropped_files)

    def _attach_dnd_handlers(self):
        js_code = """
        setTimeout(() => {
            const layoutElement = document.querySelector('[name="data_source_selector_main_layout"]');
            if (!layoutElement) return;
            const droppedFilesSource = Bokeh.documents[0].get_model_by_name('dropped_files_source');
            if (!droppedFilesSource) return;

            layoutElement.addEventListener('dragover', (e) => { e.preventDefault(); e.stopPropagation(); layoutElement.style.border = '2px dashed #007bff'; layoutElement.style.backgroundColor = '#f0f8ff'; e.dataTransfer.dropEffect = 'copy'; });
            layoutElement.addEventListener('dragleave', (e) => { e.stopPropagation(); layoutElement.style.border = ''; layoutElement.style.backgroundColor = ''; });
            layoutElement.addEventListener('drop', (e) => {
                e.preventDefault(); e.stopPropagation(); layoutElement.style.border = ''; layoutElement.style.backgroundColor = '';
                const files = e.dataTransfer.files; const droppedPaths = [];
                for (let i = 0; i < files.length; i++) { droppedPaths.push(files[i].path || files[i].name); }
                if (droppedPaths.length > 0) { droppedFilesSource.data = {paths: droppedPaths}; droppedFilesSource.change.emit(); }
            });
        }, 1000);
        """
        self.doc.add_root(CustomJS(code=js_code))

    def _handle_dropped_files(self, attr, old, new):
        dropped_paths = new.get('paths', [])
        if not dropped_paths: return
        self._update_status(f"Processing {len(dropped_paths)} dropped items...", 'blue')
        
        newly_scanned_sources = []
        for path in dropped_paths:
            if os.path.exists(path):
                if os.path.isdir(path):
                    newly_scanned_sources.extend(scan_directory_for_sources(path))
                elif os.path.isfile(path):
                    newly_scanned_sources.extend(scan_directory_for_sources(os.path.dirname(path)))
        
        existing_full_paths = {s['file_path'] for s in self.scanned_sources}
        unique_new_sources = [s for s in newly_scanned_sources if s['file_path'] not in existing_full_paths]
        
        if unique_new_sources:
            self.scanned_sources.extend(unique_new_sources)
            self._update_available_files_table()
            self._update_status(f"Added {len(unique_new_sources)} new file(s) from drag and drop.", 'green')
            self.load_button.disabled = False
        else:
            self._update_status("No new unique files were added from drag and drop.", 'orange')
        
        self.dropped_files_source.data = {'paths': []}

    def _update_available_files_table(self):
        if not self.scanned_sources:
            self.available_files_source.data = {k: [] for k in self.available_files_source.data.keys()}
            return

        indices = list(range(len(self.scanned_sources)))
        positions = [src.get("position_name", "") for src in self.scanned_sources]
        fullpaths = [src.get("file_path", "") for src in self.scanned_sources]
        types = [src.get("data_type", "unknown") for src in self.scanned_sources]
        parsers = [src.get("parser_type", "auto") for src in self.scanned_sources]
        file_sizes = [src.get("file_size", "N/A") for src in self.scanned_sources]
        file_sizes_bytes = [src.get("file_size_bytes", 0) for src in self.scanned_sources]

        display_paths, groups, highlight_colors, highlight_text_colors, highlight_reasons = [], [], [], [], []
        validity_statuses, validity_reasons, header_previews = [], [], []
        validity_labels, validity_text_colors, validity_bg_colors, validity_tooltips = [], [], [], []

        for source in self.scanned_sources:
            path = source.get("file_path", "")
            display_path = source.get("display_path", os.path.basename(path))
            display_paths.append(display_path)

            folder = os.path.dirname(display_path)
            groups.append(folder if folder else "Root")

            color, text_color, reason = self._determine_highlight(source)
            highlight_colors.append(color)
            highlight_text_colors.append(text_color)
            highlight_reasons.append(reason)

            validity = self._resolve_validity_fields(
                source.get("validity_status"),
                source.get("validity_reason"),
                source.get("header_preview")
            )
            validity_statuses.append(validity['status'])
            validity_reasons.append(validity['reason'])
            header_previews.append(validity['header'])
            validity_labels.append(validity['label'])
            validity_text_colors.append(validity['text_color'])
            validity_bg_colors.append(validity['bg_color'])
            validity_tooltips.append(validity['tooltip'])

        sorted_indices = sorted(range(len(indices)), key=lambda idx: groups[idx])

        self.available_files_source.data = {
            'index': [indices[i] for i in sorted_indices],
            'position': [positions[i] for i in sorted_indices],
            'display_path': [display_paths[i] for i in sorted_indices],
            'fullpath': [fullpaths[i] for i in sorted_indices],
            'type': [types[i] for i in sorted_indices],
            'file_size': [file_sizes[i] for i in sorted_indices],
            'group': [groups[i] for i in sorted_indices],
            'parser_type': [parsers[i] for i in sorted_indices],
            'relpath': [display_paths[i] for i in sorted_indices],
            'file_size_bytes': [file_sizes_bytes[i] for i in sorted_indices],
            'highlight_color': [highlight_colors[i] for i in sorted_indices],
            'highlight_text_color': [highlight_text_colors[i] for i in sorted_indices],
            'highlight_reason': [highlight_reasons[i] for i in sorted_indices],
            'validity_status': [validity_statuses[i] for i in sorted_indices],
            'validity_reason': [validity_reasons[i] for i in sorted_indices],
            'header_preview': [header_previews[i] for i in sorted_indices],
            'validity_label': [validity_labels[i] for i in sorted_indices],
            'validity_text_color': [validity_text_colors[i] for i in sorted_indices],
            'validity_bg_color': [validity_bg_colors[i] for i in sorted_indices],
            'validity_tooltip': [validity_tooltips[i] for i in sorted_indices],
        }

    def _determine_highlight(self, source):
        """Determine if a file should be visually highlighted in the available list."""
        filename = (source.get("display_path") or source.get("file_path") or "").split('/')[-1]
        filename_lower = filename.lower()
        parser_type = (source.get("parser_type") or "").lower()
        file_size_bytes = source.get("file_size_bytes") or 0
        validity_status = (source.get("validity_status") or "").lower()

        reasons = []
        has_priority = False

        if filename_lower.endswith('.csv') and all(keyword in filename_lower for keyword in CSV_PRIORITY_KEYWORDS):
            has_priority = True
            reasons.append("CSV includes log & summary keywords")

        if parser_type == 'nti':
            threshold = NTI_DEFAULT_PRIORITY_THRESHOLD_BYTES
            for keyword, size_threshold in NTI_SIZE_HINTS_BYTES.items():
                if keyword in filename_lower:
                    threshold = max(threshold, size_threshold)

            if file_size_bytes >= threshold > 0:
                has_priority = True
                approx_mb = file_size_bytes / (1024 * 1024)
                reasons.append(f"NTi file ~{approx_mb:.1f} MB")

        if parser_type == 'audio':
            has_priority = True
            audio_reason = source.get("validity_reason") or "Audio capture folder"
            reasons.append(audio_reason)

        if has_priority and validity_status not in ("likely_valid", ""):
            has_priority = False
            reasons.append("Header check needs review")

        if has_priority:
            highlight_color = PRIORITY_HIGHLIGHT_COLOR
            text_color = PRIORITY_HIGHLIGHT_TEXT_COLOR
        else:
            highlight_color = SECONDARY_HIGHLIGHT_COLOR
            text_color = SECONDARY_HIGHLIGHT_TEXT_COLOR

        reason_text = "; ".join(reasons)
        return highlight_color, text_color, reason_text

    def _scan_directory(self, event=None):
        base_dir, job_num = self.base_directory_input.value.strip(), self.job_number_input.value.strip()
        if not (base_dir and job_num and os.path.isdir(base_dir)):
            self._update_status("Please provide a valid Base Directory and Job Number.", 'red')
            return
        
        self._update_status(f"Scanning for job '{job_num}' in '{base_dir}'...", 'blue')
        self.load_button.disabled = True

        try:
            search_pattern = os.path.join(base_dir, f"{job_num}*")
            possible_dirs = [d for d in glob.glob(search_pattern) if os.path.isdir(d)]
            
            if not possible_dirs:
                self._update_status(f"No directory found for job '{job_num}' in '{base_dir}'.", 'orange')
                return self._clear_table()
            
            job_dir = possible_dirs[0]
            survey_dir_name = f"{job_num} surveys"
            scan_target_dir = os.path.join(job_dir, survey_dir_name) if os.path.isdir(os.path.join(job_dir, survey_dir_name)) else job_dir
            
            self.current_job_directory = scan_target_dir
            self.scanned_sources = scan_directory_for_sources(scan_target_dir)

            if not self.scanned_sources:
                self._update_status(f"No valid data files found in {scan_target_dir}", 'orange')
                return self._clear_table()
            
            self._update_available_files_table()
            self.included_files_source.data = {k: [] for k in self.included_files_source.data.keys()}
            self.load_button.disabled = False
            self._update_status(f"Scan complete. Found {len(self.scanned_sources)} data source(s).", 'green')
        except Exception as e:
            logger.exception(f"Error scanning directory: {e}")
            self._update_status(f"Error during scanning: {e}", 'red')
            self._clear_table()

    def _on_available_selection_change(self, attr, old, new): self.add_button.disabled = len(new) == 0
    def _on_included_selection_change(self, attr, old, new): self.remove_button.disabled = len(new) == 0
    
    def _validate_positions(self, attr, old, new):
        """Validate and auto-format position names when data changes."""
        if 'position' not in new:
            return
            
        positions = new['position']
        cleaned_positions = []
        
        for pos in positions:
            if isinstance(pos, str):
                # Clean up position name: strip whitespace, capitalize first letter
                cleaned = pos.strip()
                if cleaned and not cleaned[0].isupper():
                    cleaned = cleaned.capitalize()
                cleaned_positions.append(cleaned)
            else:
                cleaned_positions.append(str(pos) if pos is not None else "")
        
        # Only update if there were actual changes to avoid infinite loops
        if cleaned_positions != positions:
            new_data = new.copy()
            new_data['position'] = cleaned_positions
            self.included_files_source.data = new_data
    
    def _add_selected_files(self, event=None):
        selected_indices = self.available_files_table.source.selected.indices
        if not selected_indices: return
        
        available_data = self.available_files_source.data
        included_data = {key: list(values) for key, values in self.included_files_source.data.items()}

        # Create a set of existing fullpaths for efficient lookup
        existing_fullpaths = set(included_data.get('fullpath', []))

        for i in selected_indices:
            file_path = available_data['fullpath'][i]
            if file_path not in existing_fullpaths:
                for key in included_data.keys():
                    if key in available_data:
                        included_data[key].append(available_data[key][i])
                existing_fullpaths.add(file_path)
            else:
                logger.debug(f"File already included, skipping duplicate add: {file_path}")

        # Refresh indices to remain sequential inside the included table
        included_count = len(included_data.get('fullpath', []))
        included_data['index'] = list(range(included_count))

        self.included_files_source.data = included_data
        self.available_files_table.source.selected.indices = []
        self._update_button_states()

    def _remove_selected_files(self, event=None):
        selected_indices = self.included_files_table.source.selected.indices
        if not selected_indices: return
        
        included_data = {key: list(values) for key, values in self.included_files_source.data.items()}
        new_included_data = {
            key: [value for i, value in enumerate(values) if i not in selected_indices]
            for key, values in included_data.items()
        }

        new_included_data['index'] = list(range(len(new_included_data.get('fullpath', []))))

        self.included_files_source.data = new_included_data
        self.included_files_table.source.selected.indices = []
        self._update_button_states()
    
    def _bulk_edit_positions(self, event=None):
        """Open a dialog for bulk editing position names."""
        included_data = self.included_files_source.data
        if not included_data.get('position'):
            return self._update_status("No files available for position editing.", 'orange')
        
        # Create a simple bulk edit interface using JavaScript
        js_code = f"""
        const positions = {included_data['position']};
        const filePaths = {[path.split('/')[-1] for path in included_data['display_path']]};
        
        let editDialog = `
        <div style="position: fixed; top: 50%; left: 50%; transform: translate(-50%, -50%); 
                    background: white; border: 2px solid #ccc; border-radius: 8px; 
                    padding: 20px; z-index: 1000; box-shadow: 0 4px 8px rgba(0,0,0,0.3);
                    max-height: 80vh; overflow-y: auto; min-width: 500px;">
            <h3>Bulk Edit Position Names</h3>
            <div style="margin-bottom: 15px;">
                <label>Apply to all: <input type="text" id="bulk-position-all" placeholder="Enter position name for all files" style="width: 200px; margin-left: 10px;"></label>
                <button onclick="applyToAll()" style="margin-left: 10px; padding: 5px 10px; background: #007bff; color: white; border: none; border-radius: 3px;">Apply to All</button>
            </div>
            <hr>
            <div style="margin-bottom: 15px;"><strong>Individual Positions:</strong></div>
            <div id="position-inputs">`;
        
        for (let i = 0; i < positions.length; i++) {{
            editDialog += `
                <div style="margin-bottom: 8px; display: flex; align-items: center;">
                    <span style="width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${{filePaths[i]}}">${{filePaths[i]}}</span>
                    <input type="text" id="pos-${{i}}" value="${{positions[i]}}" style="width: 150px; margin-left: 10px; padding: 3px;">
                </div>`;
        }}
        
        editDialog += `
            </div>
            <div style="margin-top: 20px; text-align: right;">
                <button onclick="cancelEdit()" style="margin-right: 10px; padding: 8px 15px; background: #6c757d; color: white; border: none; border-radius: 3px;">Cancel</button>
                <button onclick="savePositions()" style="padding: 8px 15px; background: #28a745; color: white; border: none; border-radius: 3px;">Save Changes</button>
            </div>
        </div>
        <div id="dialog-overlay" style="position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.5); z-index: 999;"></div>
        `;
        
        document.body.insertAdjacentHTML('beforeend', editDialog);
        
        window.applyToAll = function() {{
            const allValue = document.getElementById('bulk-position-all').value.trim();
            if (allValue) {{
                for (let i = 0; i < positions.length; i++) {{
                    document.getElementById(`pos-${{i}}`).value = allValue;
                }}
            }}
        }};
        
        window.cancelEdit = function() {{
            document.querySelector('#dialog-overlay').remove();
            document.querySelector('#dialog-overlay').nextElementSibling.remove();
        }};
        
        window.savePositions = function() {{
            const newPositions = [];
            for (let i = 0; i < positions.length; i++) {{
                newPositions.push(document.getElementById(`pos-${{i}}`).value.trim() || positions[i]);
            }}
            
            // Update the Bokeh data source
            const includedSource = Bokeh.documents[0].get_model_by_name('{self.included_files_source.name}');
            if (includedSource) {{
                const data = includedSource.data;
                data['position'] = newPositions;
                includedSource.change.emit();
            }}
            
            cancelEdit();
        }};
        """
        
        self.doc.add_root(CustomJS(code=js_code))
        self._update_status("Bulk position editor opened. Edit positions and click 'Save Changes'.", 'blue')
    
    def _load_selected_data(self, event=None):
        if not self.included_files_source.data['index']:
            return self._update_status("No files are included for loading.", 'orange')
        
        included_data = self.included_files_source.data
        selected_sources = []
        
        for i in range(len(included_data['fullpath'])):
            source = {
                'position_name': included_data['position'][i],
                'file_path': included_data['fullpath'][i],
                'enabled': True,
                'data_type': included_data['type'][i],
                'parser_type': included_data['parser_type'][i]
            }
            selected_sources.append(source)

        self._update_status(f"Loading {len(selected_sources)} selected data sources...", 'blue')
        self.on_data_sources_selected(selected_sources)

    def _cancel_selection(self, event=None):
        self._update_status("Selection cancelled.", 'blue')
        self.on_data_sources_selected([])

    def _save_config(self):
        try:
            included_data = self.included_files_source.data
            if not included_data['fullpath']:
                return self._update_status("No files selected to save in configuration.", 'orange')

            file_paths = included_data['fullpath']
            # The base path for the config is the common parent of all included files.
            config_base_path = self._find_common_parent_directory(file_paths) or self.current_job_directory or os.getcwd()

            config_data = {
                "version": "1.2",
                "created_at": datetime.now().isoformat(),
                "config_base_path": config_base_path.replace('\\', '/'),
                "sources": []
            }

            for i in range(len(included_data['fullpath'])):
                full_path = included_data['fullpath'][i]
                try:
                    # Make path relative to the config's future location
                    relative_path = os.path.relpath(full_path, config_base_path)
                except ValueError:
                    # This occurs if paths are on different drives (e.g., C: vs D:)
                    # In this case, we store the absolute path as a fallback.
                    relative_path = os.path.abspath(full_path)

                config_data["sources"].append({
                    "path": relative_path.replace('\\', '/'),
                    "position": included_data['position'][i],
                    "type": included_data['type'][i],
                    "parser_type": included_data['parser_type'][i],
                    "validity_status": included_data['validity_status'][i],
                    "validity_reason": included_data['validity_reason'][i],
                    "header_preview": included_data['header_preview'][i],
                })

            job_num_str = self.job_number_input.value or 'custom_selection'
            config_filename = f"noise_survey_config_{job_num_str}.json"
            config_path = os.path.join(config_base_path, config_filename)

            with open(config_path, 'w') as f:
                json.dump(config_data, f, indent=2)

            self.current_config_path = config_path
            self._update_status(f"Configuration saved to: {config_path}", 'green')

        except Exception as e:
            self._update_status(f"Error saving configuration: {e}", 'red')
            logger.error(f"Error saving config: {e}", exc_info=True)

    def _load_config(self):
        try:
            selected_indices = self.available_files_table.source.selected.indices
            if not selected_indices:
                return self._update_status("Please select a config file from the 'Available Files' list.", 'orange')

            available_data = self.available_files_source.data
            config_path = next((available_data['fullpath'][i] for i in selected_indices if available_data['parser_type'][i] == 'config'), None)

            if not config_path:
                return self._update_status("The selected file is not a valid config file.", 'orange')

            with open(config_path, 'r') as f:
                config_data = json.load(f)

            if "sources" not in config_data:
                return self._update_status("Invalid configuration file format.", 'red')

            self._clear_table()

            # Determine the base path for resolving relative paths
            # New format uses 'config_base_path', old format relies on the config file's directory
            base_path = config_data.get('config_base_path', os.path.dirname(config_path))

            included_data = defaultdict(list)
            files_not_found = 0

            for i, source in enumerate(config_data["sources"]):
                stored_path = source["path"]
                # If stored_path is absolute, join will use it directly. Otherwise, it's joined with base_path.
                full_path = os.path.abspath(os.path.join(base_path, stored_path))

                if not os.path.exists(full_path):
                    logger.warning(f"File from config not found: {full_path} (resolved from base '{base_path}' and path '{stored_path}')")
                    files_not_found += 1
                    continue

                display_path = os.path.relpath(full_path, base_path) if base_path in full_path else stored_path

                included_data['index'].append(i)
                included_data['position'].append(source.get("position", ""))
                included_data['relpath'].append(stored_path)
                included_data['display_path'].append(display_path.replace('\\', '/'))
                included_data['fullpath'].append(full_path)
                included_data['type'].append(source.get("type", "unknown"))
                included_data['file_size'].append(self._format_file_size(os.path.getsize(full_path)) if os.path.isfile(full_path) else "Dir")
                included_data['group'].append(os.path.dirname(display_path) or ".")
                included_data['parser_type'].append(source.get("parser_type", "auto"))
                included_data['file_size_bytes'].append(os.path.getsize(full_path) if os.path.isfile(full_path) else 0)
                validity = self._resolve_validity_fields(
                    source.get("validity_status"),
                    source.get("validity_reason"),
                    source.get("header_preview")
                )
                included_data['validity_status'].append(validity['status'])
                included_data['validity_reason'].append(validity['reason'])
                included_data['header_preview'].append(validity['header'])
                included_data['validity_label'].append(validity['label'])
                included_data['validity_text_color'].append(validity['text_color'])
                included_data['validity_bg_color'].append(validity['bg_color'])
                included_data['validity_tooltip'].append(validity['tooltip'])

            self.included_files_source.data = dict(included_data)
            if included_data['index']: self._update_button_states()

            status_msg = f"Config loaded from: {os.path.basename(config_path)}"
            if files_not_found:
                status_msg += f". Warning: {files_not_found} file(s) not found."
            self._update_status(status_msg, 'green' if not files_not_found else 'orange')

        except Exception as e:
            self._update_status(f"Error loading configuration: {e}", 'red')
            logger.error(f"Error loading config: {e}", exc_info=True)

    def _find_common_parent_directory(self, file_paths):
        if not file_paths: return None
        try:
            common_path = os.path.commonpath([os.path.abspath(p) for p in file_paths])
            return os.path.dirname(common_path) if os.path.isfile(common_path) else common_path
        except ValueError: return None
    
    def _update_status(self, message, color='blue'):
        self.status_div.text = message
        self.status_div.styles = {'color': color, 'font-style': 'italic', 'margin-top': '10px'}
        logger.info(f"Status: {message}")

    def _update_button_states(self):
        has_included = bool(self.included_files_source.data.get('index'))
        self.load_button.disabled = not has_included
        self.save_config_button.disabled = not has_included
        self.bulk_edit_button.disabled = not has_included

    def _format_file_size(self, size_bytes):
        if size_bytes >= 1048576: return f"{size_bytes / 1048576:.1f} MB"
        if size_bytes >= 1024: return f"{size_bytes / 1024:.1f} KB"
        return f"{size_bytes} B"

    def _clear_table(self):
          self.scanned_sources = []
          self.current_job_directory = None
          
          # Use a dictionary comprehension to create new lists for each key
          self.available_files_source.data = {k: [] for k in self.available_files_source.data.keys()}
          self.included_files_source.data = {k: [] for k in self.included_files_source.data.keys()}
          
          # Also clear any selections to prevent out-of-bounds errors
          self.available_files_table.source.selected.indices = []
          self.included_files_table.source.selected.indices = []
          
          self.load_button.disabled = True
          self.save_config_button.disabled = True
          self.add_button.disabled = True
          self.remove_button.disabled = True
          self.info_div.text = "Scan results summary will appear here."

    def get_layout(self):
        return self.main_layout

def create_data_source_selector(doc, on_data_sources_selected):
    if not logging.getLogger().hasHandlers():
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    selector = DataSourceSelector(doc, on_data_sources_selected)
    doc.add_root(selector.get_layout())
    doc.title = "Noise Survey - Select Data"
    return selector