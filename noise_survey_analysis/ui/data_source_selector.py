# noise_survey_analysis/ui/data_source_selector.py

import os
import glob
import logging
import json
import os.path
import re
from datetime import datetime

from bokeh.layouts import column, row
from bokeh.models import (
    ColumnDataSource, DataTable, TableColumn, StringEditor,
    TextInput, Button, Div, Spacer, Select, CustomJS, CheckboxGroup,
    HTMLTemplateFormatter, SelectEditor
)
from bokeh.events import ButtonClick, ValueSubmit

from ..core.data_loaders import scan_directory_for_sources, summarize_scanned_sources
from ..core.config import DEFAULT_BASE_JOB_DIR
from ..core import survey_layout

logger = logging.getLogger(__name__)

# --- Default Base Directory ---
if not os.path.isdir(DEFAULT_BASE_JOB_DIR):
    DEFAULT_BASE_JOB_DIR = os.path.expanduser("~")
    logger.warning(f"Default base job directory not found. Falling back to: {DEFAULT_BASE_JOB_DIR}")


# Sentinel for the "no visit filter" option.
ALL_VISITS = "\x00all"

PRIORITY_HIGHLIGHT_COLOR = "#1f3c88"
PRIORITY_HIGHLIGHT_TEXT_COLOR = "#f8f9fa"
DEFAULT_TEXT_COLOR = "#212529"


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
        self.valid_config_paths = []
        # Candidate positions built from the scan, and the subset currently on screen.
        self.survey_groups = []
        self.visible_groups = []

        # Data sources for the dual-pane interface
        # One row per candidate position rather than per file: a Svan position is 2-3
        # files and an NTi session about 5.5, so file rows make the user do the
        # grouping by hand.
        self.available_files_source = ColumnDataSource({
            'index': [], 'position': [], 'contents': [], 'instrument': [],
            'period': [], 'duration': [], 'file_count': [], 'file_size': [],
            'visit': [], 'spectral': [], 'recommended': [],
            'highlight_color': [], 'highlight_text_color': [], 'highlight_reason': []
        })

        self.included_files_source = ColumnDataSource({
            'index': [], 'position': [], 'relpath': [], 'display_path': [],
            'fullpath': [], 'type': [], 'file_size': [],
            'group': [], 'parser_type': [], 'file_size_bytes': []
        })
        
        self.source_table_data = ColumnDataSource({
            'index': [], 'position': [], 'path': [], 'type': [], 'include': [], 
            'original_position': [], 'file_size': []
        })
        
        self.current_job_directory = None
        
        self.dropped_files_source = ColumnDataSource(data={'paths': []}, name='dropped_files_source')

        self._create_ui_components()
        self._attach_dnd_handlers()


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
            column(Spacer(height=25), self.scan_button),
            sizing_mode="scale_width"
        )
        
        self.status_div = Div(
            text="Enter Base Directory and Job Number, then click 'Scan Job Directory'. Or drag and drop files/folders anywhere on this panel.",
            width=800, styles={'color': 'blue', 'font-style': 'italic', 'margin-top': '10px'} 
        )

        # Multiple visits per job are the norm - a structural survey found 16 of 20
        # jobs had several - so which visit comes first, before any file question.
        self.visit_label = Div(text="<b>Visit:</b>")
        # A distinct sentinel: the unnamed visit (files loose in the Surveys folder)
        # legitimately has an empty name, so "" cannot also mean "no filter".
        self.visit_select = Select(value=ALL_VISITS, options=[(ALL_VISITS, "All visits")],
                                   width=300, name="visit_select")
        self.show_spot_checkbox = CheckboxGroup(
            labels=["Include short manual readings"], active=[], width=250,
            name="show_spot_measurements",
        )
        self.config_label = Div(text="<b>Saved selection:</b>")
        self.config_select = Select(value="", options=[], width=320, name="config_select",
                                    visible=False)
        self.visit_row = row(
            column(self.visit_label, self.visit_select),
            column(Spacer(height=18), self.show_spot_checkbox),
            column(self.config_label, self.config_select),
            sizing_mode="scale_width",
        )

        self.available_files_label = Div(
            text="<b>Available Positions:</b> <i>(recommended positions are pre-selected)</i>",
            width=400
        )

        highlight_template = """
        <div style="background-color:<% if (highlight_color) { %><%= highlight_color %><% } else { %>transparent<% } %>; color:<%= highlight_text_color %>;
                    padding:4px 6px; border-radius:4px;">
            <span title="<%= highlight_reason %>"><%= value %></span>
        </div>
        """

        self.available_files_columns = [
            TableColumn(field="position", title="Position", width=180,
                        formatter=HTMLTemplateFormatter(template=highlight_template)),
            TableColumn(field="contents", title="Contains", width=150),
            TableColumn(field="instrument", title="Meter", width=70),
            TableColumn(field="period", title="Period", width=170),
            TableColumn(field="duration", title="Duration", width=80),
            TableColumn(field="file_count", title="Files", width=55),
            TableColumn(field="file_size", title="Size", width=80),
        ]
        
        self.available_files_table = DataTable(
            source=self.available_files_source, columns=self.available_files_columns,
            width=650, height=350, editable=False, index_position=None,
            autosize_mode="force_fit", selectable=True, sortable=True
        )
        
        self.add_button = Button(label="Add ▶", width=100, button_type="success", disabled=True)  # adds every file in the selected positions
        self.remove_button = Button(label="◀ Remove", width=100, button_type="danger", disabled=True)
        self.bulk_edit_button = Button(label="Bulk Edit Positions", width=120, button_type="warning", disabled=True)
        self.transfer_buttons = column(Spacer(height=100), self.add_button, Spacer(height=10), self.remove_button, Spacer(height=10), self.bulk_edit_button, Spacer(height=100), width=120)
        
        self.included_files_label = Div(text="<b>Included Files:</b> <i>(Click position names to edit)</i>", width=500)
        
        parser_options = ['auto', 'svan', 'sentry', 'nti', 'audio', 'generic']
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
        self.load_config_button = Button(label="Load Config", button_type="default", width=120, disabled=True)
        self.load_button = Button(label="Load Selected Data", button_type="success", width=200, disabled=True)
        self.cancel_button = Button(label="Cancel", button_type="default", width=200)
        
        self.config_controls_row = row(self.save_config_button, self.load_config_button, Spacer(width=20), self.load_button, self.cancel_button)

        self.main_layout = column(
            self.title_div, self.input_row, self.status_div, Spacer(height=10),
            self.visit_row, Spacer(height=5),
            self.dual_pane_layout, Spacer(height=25), self.config_controls_row,
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
        self.visit_select.on_change('value', self._on_visit_change)
        self.show_spot_checkbox.on_change('active', self._on_visit_change)

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
            self._update_status(*self._status_with_filter_notice(
                f"Added {len(unique_new_sources)} new file(s) from drag and drop."))
            self._update_button_states()
        else:
            self._update_status("No new unique files were added from drag and drop.", 'orange')
        
        self.dropped_files_source.data = {'paths': []}

    def _update_available_files_table(self):
        """Rebuild the position list from the current scan, visit and filters."""
        if not self.scanned_sources:
            self.survey_groups = []
            self.visible_groups = []
            self.available_files_source.data = {k: [] for k in self.available_files_source.data.keys()}
            self._refresh_visit_options()
            return

        self.survey_groups = survey_layout.build_groups(self.scanned_sources)
        self._refresh_visit_options(reset_selection=True)
        self._render_visible_groups()
        self._detect_and_handle_configs()

    def _refresh_visit_options(self, reset_selection=False):
        """
        Offer the visits found, newest first, with an 'all' escape hatch.

        A fresh scan lands on the newest visit, which is usually the one being opened,
        rather than on every visit a job has ever had. Nothing is hidden silently: the
        dropdown names each visit with its position count and dates.
        """
        visits = survey_layout.list_visits(self.survey_groups)
        options = [(ALL_VISITS, "All visits")]
        for visit in visits:
            period = self._format_period(visit.get('start_time'), visit.get('end_time'))
            suffix = f" - {period}" if period else ""
            options.append((
                visit['visit'],
                f"{visit['label']} ({visit['recommended_count']} of {visit['position_count']}){suffix}",
            ))

        self.visit_select.options = options
        valid_values = [value for value, _ in options]
        if reset_selection or self.visit_select.value not in valid_values:
            # More than one visit means a choice worth making; a single visit needs no
            # filter at all.
            self.visit_select.value = visits[0]['visit'] if len(visits) > 1 else ALL_VISITS

    def _render_visible_groups(self):
        """Apply the visit and spot-reading filters, then paint the table."""
        include_spot = 0 in (self.show_spot_checkbox.active or [])
        selected_visit = self.visit_select.value

        groups = [
            group for group in self.survey_groups
            if (selected_visit == ALL_VISITS or group.visit == selected_visit)
            and (include_spot or not group.is_spot_measurement)
        ]
        self.visible_groups = groups

        highlight, highlight_text, reasons = [], [], []
        for group in groups:
            if group.recommended:
                highlight.append(PRIORITY_HIGHLIGHT_COLOR)
                highlight_text.append(PRIORITY_HIGHLIGHT_TEXT_COLOR)
                reasons.append(
                    f"{group.describe_contents()} over {survey_layout.format_duration(group.duration_seconds)}"
                )
            else:
                highlight.append("")
                highlight_text.append(DEFAULT_TEXT_COLOR)
                reasons.append("Short manual reading" if group.is_spot_measurement else "")

        self.available_files_source.data = {
            'index': list(range(len(groups))),
            'position': [g.label for g in groups],
            'contents': [g.describe_contents() for g in groups],
            'instrument': [g.instrument for g in groups],
            'period': [self._format_period(g.start_time, g.end_time) for g in groups],
            'duration': [survey_layout.format_duration(g.duration_seconds) for g in groups],
            'file_count': [g.file_count for g in groups],
            'file_size': [self._format_file_size(g.total_size_bytes) for g in groups],
            'visit': [g.visit for g in groups],
            'spectral': ["yes" if g.has_spectral else "" for g in groups],
            'recommended': [g.recommended for g in groups],
            'highlight_color': highlight,
            'highlight_text_color': highlight_text,
            'highlight_reason': reasons,
        }

        # Pre-select what we would recommend, so the common case is one click on Add.
        self.available_files_table.source.selected.indices = [
            index for index, group in enumerate(groups) if group.recommended
        ]
        self._update_button_states()

        notice = self.current_filter_notice()
        if notice:
            self._update_status(notice, 'blue')

    def current_filter_notice(self):
        """
        Describe what the current filters are hiding, or '' when nothing is.

        Returned rather than written straight to the status line, because the scan and
        drag-and-drop paths set their own message afterwards; if this wrote directly it
        would be overwritten and positions would be hidden silently.
        """
        total = len(self.survey_groups)
        shown = len(self.visible_groups)
        if not total or shown >= total:
            return ''

        parts = [f"Showing {shown} of {total} position(s)"]
        if self.visit_select.value != ALL_VISITS:
            selected = next((label for value, label in self.visit_select.options
                             if value == self.visit_select.value), '')
            parts.append(f"visit '{selected.split(' (')[0]}'")
        spot_hidden = sum(1 for g in self.survey_groups if g.is_spot_measurement)
        if spot_hidden and 0 not in (self.show_spot_checkbox.active or []):
            parts.append(f"{spot_hidden} short manual reading(s) hidden")
        return ' - '.join(parts) + ". Use the Visit list to see the rest."

    def _status_with_filter_notice(self, message):
        """Append the filter notice to a caller's own message, so neither is lost."""
        notice = self.current_filter_notice()
        return (f"{message} {notice}".strip(), 'blue' if notice else 'green')

    def _on_visit_change(self, attr, old, new):
        if self.survey_groups:
            self._render_visible_groups()

    @staticmethod
    def _format_period(start_iso, end_iso):
        """e.g. '13-17 Jul 2026'. Empty when the span could not be probed."""
        if not start_iso and not end_iso:
            return ""
        try:
            import pandas as pd
            start = pd.Timestamp(start_iso) if start_iso else None
            end = pd.Timestamp(end_iso) if end_iso else None
        except (ValueError, TypeError):
            return ""

        if start is not None and end is not None:
            if start.date() == end.date():
                return start.strftime("%d %b %Y")
            if (start.year, start.month) == (end.year, end.month):
                return f"{start.day}-{end.strftime('%d %b %Y')}"
            return f"{start.strftime('%d %b')} - {end.strftime('%d %b %Y')}"
        only = start or end
        return only.strftime("%d %b %Y") if only is not None else ""

    def _detect_and_handle_configs(self):
        valid_configs = []

        for source in self.scanned_sources:
            if source.get("parser_type") != 'config':
                continue

            config_path = source.get("file_path")
            if not config_path:
                continue

            try:
                with open(config_path, 'r') as f:
                    config_data = json.load(f)
                if isinstance(config_data.get("sources"), list):
                    valid_configs.append(config_path)
                else:
                    logger.warning(f"Config file missing 'sources' list: {config_path}")
            except Exception as exc:
                logger.warning(f"Unable to validate config {config_path}: {exc}")

        previous_paths = set(self.valid_config_paths)
        self.valid_config_paths = valid_configs
        self.load_config_button.disabled = not bool(valid_configs)

        # Configs are chosen here rather than from the position table: they are not
        # positions, and the table no longer carries per-file columns to index into.
        self.config_select.options = [(path, os.path.basename(path)) for path in valid_configs]
        self.config_select.visible = bool(valid_configs)
        self.config_label.visible = bool(valid_configs)
        if valid_configs and self.config_select.value not in valid_configs:
            self.config_select.value = valid_configs[0]
        elif not valid_configs:
            self.config_select.value = ""

        if len(valid_configs) == 1:
            config_path = valid_configs[0]
            if (
                self.current_config_path != config_path
                or not self.included_files_source.data.get('index')
            ):
                success, files_not_found = self._load_config_from_path(config_path)
                if success:
                    status_msg = f"Loaded saved configuration: {os.path.basename(config_path)}"
                    if files_not_found:
                        status_msg += f". Warning: {files_not_found} file(s) not found."
                    color = 'green' if not files_not_found else 'orange'
                    self._update_status(status_msg, color)
        elif len(valid_configs) > 1:
            if set(valid_configs) != previous_paths:
                file_names = ', '.join(os.path.basename(path) for path in valid_configs)
                self._update_status(
                    f"Multiple configs found ({file_names}). Choose one under 'Saved selection' "
                    f"and click 'Load Config'.",
                    'blue'
                )

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
            # Resolve via find_survey_root rather than matching an exact
            # "<job> surveys" name: real folders are capitalised ("5882 Surveys"), and
            # os.path.isdir is case-sensitive off Windows, so the exact-name check
            # silently fell back to scanning the whole job folder.
            scan_target_dir = survey_layout.find_survey_root(job_dir)
            
            self.current_job_directory = scan_target_dir
            self.scanned_sources = scan_directory_for_sources(scan_target_dir)

            if not self.scanned_sources:
                self._update_status(f"No valid data files found in {scan_target_dir}", 'orange')
                return self._clear_table()
            
            self._update_available_files_table()
            self.included_files_source.data = {k: [] for k in self.included_files_source.data.keys()}
            self._update_button_states()
            self._update_status(*self._status_with_filter_notice(
                f"Scan complete. Found {len(self.scanned_sources)} data source(s)."))
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
                # Strip whitespace and capitalise a leading lowercase letter.
                # str.capitalize() would also lowercase the remainder, which mangles
                # the meter names these labels come from: most start with a digit, so
                # "5882 Warbrook House 971-2" came back as "5882 warbrook house 971-2".
                cleaned = pos.strip()
                if cleaned and cleaned[0].islower():
                    cleaned = cleaned[0].upper() + cleaned[1:]
                cleaned_positions.append(cleaned)
            else:
                cleaned_positions.append(str(pos) if pos is not None else "")
        
        # Only update if there were actual changes to avoid infinite loops
        if cleaned_positions != positions:
            new_data = new.copy()
            new_data['position'] = cleaned_positions
            self.included_files_source.data = new_data
    
    def _add_selected_files(self, event=None):
        """Add every file belonging to the selected positions."""
        selected_indices = self.available_files_table.source.selected.indices
        if not selected_indices:
            return

        included_data = {key: list(values) for key, values in self.included_files_source.data.items()}
        existing_fullpaths = set(included_data.get('fullpath', []))

        added = 0
        for index in selected_indices:
            if index >= len(self.visible_groups):
                continue
            group = self.visible_groups[index]
            for source in group.sources:
                file_path = source.get('file_path')
                if not file_path or file_path in existing_fullpaths:
                    continue
                included_data['fullpath'].append(file_path)
                included_data['position'].append(group.label)
                included_data['display_path'].append(source.get('display_path', ''))
                included_data['relpath'].append(source.get('display_path', ''))
                included_data['type'].append(source.get('data_type', ''))
                included_data['parser_type'].append(source.get('parser_type', 'auto'))
                included_data['file_size'].append(source.get('file_size', ''))
                included_data['file_size_bytes'].append(source.get('file_size_bytes', 0))
                included_data['group'].append(group.visit or '')
                existing_fullpaths.add(file_path)
                added += 1

        included_data['index'] = list(range(len(included_data.get('fullpath', []))))
        self.included_files_source.data = included_data
        self.available_files_table.source.selected.indices = []
        self._update_button_states()
        if added:
            self._update_status(f"Added {added} file(s) from {len(selected_indices)} position(s).", 'green')

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

            job_num_str = self.job_number_input.value.strip() or 'custom_selection'
            config_data = {
                "version": "1.3",
                "created_at": datetime.now().isoformat(),
                "config_base_path": config_base_path.replace('\\', '/'),
                "job_number": job_num_str,
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
            config_path = self.config_select.value or None
            if config_path is None and len(self.valid_config_paths) == 1:
                config_path = self.valid_config_paths[0]

            if not config_path:
                return self._update_status(
                    "Please choose a config under 'Saved selection'.", 'orange')

            success, files_not_found = self._load_config_from_path(config_path)
            if success:
                status_msg = f"Config loaded from: {os.path.basename(config_path)}"
                if files_not_found:
                    status_msg += f". Warning: {files_not_found} file(s) not found."
                self._update_status(status_msg, 'green' if not files_not_found else 'orange')

        except Exception as e:
            self._update_status(f"Error loading configuration: {e}", 'red')
            logger.error(f"Error loading config: {e}", exc_info=True)

    def _load_config_from_path(self, config_path):
        try:
            with open(config_path, 'r') as f:
                config_data = json.load(f)
        except Exception as exc:
            self._update_status(f"Error reading configuration: {exc}", 'red')
            logger.error(f"Failed to read config {config_path}: {exc}")
            return False, 0

        sources = config_data.get("sources")
        if not isinstance(sources, list):
            self._update_status("Invalid configuration file format.", 'red')
            return False, 0

        base_path = config_data.get('config_base_path', os.path.dirname(config_path))

        included_data = {key: [] for key in self.included_files_source.data.keys()}
        files_not_found = 0

        for source in sources:
            stored_path = source.get("path")
            if not stored_path:
                continue

            full_path = os.path.abspath(os.path.join(base_path, stored_path))

            if not os.path.exists(full_path):
                logger.warning(
                    f"File from config not found: {full_path} (resolved from base '{base_path}' and path '{stored_path}')"
                )
                files_not_found += 1
                continue

            try:
                rel_path = os.path.relpath(full_path, base_path)
                display_path = rel_path if not rel_path.startswith('..') else stored_path
            except ValueError:
                display_path = stored_path

            included_data['index'].append(len(included_data['index']))
            included_data['position'].append(source.get("position", ""))
            included_data['relpath'].append(stored_path)
            included_data['display_path'].append(display_path.replace('\\', '/'))
            included_data['fullpath'].append(full_path)
            included_data['type'].append(source.get("type", "unknown"))

            if os.path.isdir(full_path):
                included_data['file_size'].append("Dir")
                included_data['file_size_bytes'].append(0)
            else:
                size_bytes = os.path.getsize(full_path)
                included_data['file_size'].append(self._format_file_size(size_bytes))
                included_data['file_size_bytes'].append(size_bytes)

            included_data['group'].append(os.path.dirname(display_path) or ".")
            included_data['parser_type'].append(source.get("parser_type", "auto"))

        self.included_files_source.data = included_data
        self._update_button_states()
        self.available_files_table.source.selected.indices = []
        self.current_config_path = config_path
        return True, files_not_found

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
        self.current_config_path = None
        self.valid_config_paths = []

        self.available_files_source.data = {k: [] for k in self.available_files_source.data.keys()}
        self.included_files_source.data = {k: [] for k in self.included_files_source.data.keys()}

        self.available_files_table.source.selected.indices = []
        self.included_files_table.source.selected.indices = []

        self.load_button.disabled = True
        self.save_config_button.disabled = True
        self.load_config_button.disabled = True
        self.bulk_edit_button.disabled = True
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
