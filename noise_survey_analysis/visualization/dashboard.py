"""
Visualization dashboard for noise survey analysis.

This module contains the DashboardBuilder class which orchestrates 
the creation and layout of visualization components for the dashboard.
"""

import logging
import pandas as pd
import numpy as np
import traceback
from bokeh.plotting import figure
from bokeh.io import curdoc
from bokeh.models import (
    ColumnDataSource, Button, Select, Div, Toggle, CheckboxGroup, Range1d,
    Slider, RangeSlider, CustomJS, Panel, Tabs, RadioButtonGroup, LayoutDOM,
    TableColumn, DataTable
)
from bokeh.layouts import column, row, gridplot
from ..core.data_loaders import extract_spectral_parameters
from ..core.data_processors import prepare_spectral_image_data
from .visualization_components import (
    create_TH_chart, create_log_chart, make_image_spectrogram, 
    create_frequency_bar_chart, create_range_selector
)
from .interactive import (
    link_x_ranges,
    add_hover_interaction,
    add_tap_interaction
)
from ..ui.controls import create_position_play_button, create_global_audio_controls, create_parameter_selector

# --- Setup Logger ---
logger = logging.getLogger(__name__)


class DashboardBuilder:
    """
    Builds the Bokeh dashboard layout, including charts, widgets, and interactions.
    Orchestrates the creation of visualization components and UI elements.
    """
    def __init__(self, position_data: dict, chart_settings: dict, visualization_settings: dict, audio_handler_available: bool):
        self.position_data = position_data
        self.chart_settings = chart_settings
        self.visualization_settings = visualization_settings
        self.audio_handler_available = audio_handler_available

        self.bokeh_models = {
            'charts': {'all': [], 'time_series': []},
            'sources': {
                'data': {},
                'playback': {'position': None, 'seek_command': None, 'play_request': None},
                'frequency': {'bar': None, 'table': None}
            },
            'ui': {
                'position_elements': {},
                'controls': {
                    'playback': {},
                    'parameter': {'select': None, 'holder': None},
                    'play_request': None,
                    'js_trigger': None, # For Python -> JS communication
                    'visibility': {}
                },
                'visualization': {'click_lines': {}, 'labels': {}, 'range_selectors': {}}
            },
            'frequency_analysis': {
                'bar_chart': {'figure': None, 'x_range': None},
                'table_div': None # Initialize key for frequency table
            },
            'spectral_data': {}
        }
        self._all_spectral_params = set()

    def build(self) -> LayoutDOM:
        """Builds and returns the complete dashboard layout."""
        logger.info("Building dashboard...")
        
        self._create_shared_components()
        
        title_div = Div(text="<h1>Noise Survey Dashboard</h1>", sizing_mode="stretch_width")
        
        chart_elements, time_series_charts, has_spectral = self._create_position_charts()
        
        self.bokeh_models['charts']['time_series'] = time_series_charts
        
        range_selector = self._create_shared_range_selector(time_series_charts) if time_series_charts else None
        
        controls_area = self._create_controls_area()
        
        freq_analysis_section = self._create_frequency_analysis_section() if has_spectral else None
        freq_data_table = self._create_frequency_data_table() if has_spectral else None # Create table if spectral data exists
        
        self._add_interactions()
        
        init_JS_button = self.bokeh_models['ui']['controls']['init_js']
        
        layout_components = [comp for comp in [
            title_div,
            controls_area,
            range_selector,
            *chart_elements,
            freq_analysis_section,
            freq_data_table,
            Div(text="<div style='margin-top: 20px;'></div>", sizing_mode="stretch_width"),
            init_JS_button
        ] if comp is not None]

        main_layout = column(*layout_components, sizing_mode="stretch_width")
        
        from .interactive import initialize_global_js
        js_init_callback = initialize_global_js(bokeh_models=self.bokeh_models)
        
        if js_init_callback:
            trigger_source = ColumnDataSource(data={'trigger': [0]}, name='js_init_trigger')
            trigger_source.js_on_change('data', js_init_callback)
            curdoc().add_root(trigger_source)
            curdoc().add_timeout_callback(lambda: trigger_source.data.update({'trigger': [1]}), 1000)
            if init_JS_button:
                init_JS_button.js_on_click(js_init_callback)
        
        logger.info("Dashboard build complete.")
        return main_layout

    def _create_shared_components(self):
        """Creates components shared across all positions."""
        self.bokeh_models['sources']['playback']['position'] = ColumnDataSource(data={'current_time': [0]}, name='playback_source')
        self.bokeh_models['sources']['playback']['seek_command'] = ColumnDataSource(data={'target_time': [None]}, name='seek_command_source')
        self.bokeh_models['sources']['playback']['play_request'] = ColumnDataSource(data={'position': [None], 'time': [None]}, name='play_request_source')
        self.bokeh_models['sources']['playback']['js_trigger'] = ColumnDataSource(data={'event': [None]}, name='js_trigger_source')
        self.bokeh_models['sources']['playback']['status'] = ColumnDataSource(data={'is_playing': [False], 'active_position': [None]}, name='playback_status_source')
        self.bokeh_models['ui']['controls']['init_js'] = Button(label="Initialize JS (Manual)", button_type="primary", name="init_js_button", width=150)
        
        (self.bokeh_models['frequency_analysis']['bar_chart']['figure'],
         self.bokeh_models['sources']['frequency']['bar'],
         self.bokeh_models['frequency_analysis']['bar_chart']['x_range']) = create_frequency_bar_chart()
        self.bokeh_models['sources']['data']["frequency_bar"] = self.bokeh_models['sources']['frequency']['bar']
    
    def _create_frequency_data_table(self) -> LayoutDOM:
        """Creates a container Div for the frequency data table."""
        html_table_div = Div(text="<p>Click on a chart to see frequency data...</p>", name="frequency_html_table_div", width=800, styles={'min-height': '100px'})
        self.bokeh_models['frequency_analysis']['table_div'] = html_table_div
        help_text = Div(text="<p style='font-size: 0.9em; color: #666;'>Click and drag to select values, then copy (Ctrl+C).</p>", width=800)
        return column(html_table_div, help_text, css_classes=["freq-data-table-container"])

    def _create_position_charts(self) -> tuple[list, list, bool]:
        """
        Creates charts for each position, combining overview and log data into a single
        time-series chart that can be dynamically switched.
        """
        all_elements = []
        all_position_time_series_charts = []
        has_any_spectral_data = False

        default_combined_metrics = ['LAeq', 'LAF90', 'LAF10', 'LAFmax']
               
        for position, data_dict in self.position_data.items():
            position_charts = []
            current_position_time_series_charts = []
            
            # Initialize the UI elements container for the position
            if position not in self.bokeh_models['ui']['position_elements']:
                self.bokeh_models['ui']['position_elements'][position] = {'charts': {}}

            overview_df = data_dict.get('overview')
            log_df = data_dict.get('log')

            primary_df_for_chart = None
            chart_display_type_label = None
            initial_metrics_for_chart = None

            #prioritise overview data if available
            if isinstance(overview_df, pd.DataFrame) and not overview_df.empty:
                primary_df_for_chart = overview_df.copy()
                chart_display_type_label = "Overview Data"
                initial_metrics_for_chart = default_combined_metrics

            # Fallback to log data if overview is not available
            elif isinstance(log_df, pd.DataFrame) and not log_df.empty:
                primary_df_for_chart = log_df.copy()
                chart_display_type_label = "Log Data"
                initial_metrics_for_chart = None # if falling back to log, auto-detect metrics for log data (create_TH_chart handles None)
                
            #If no suitable time-serices data found, skip creating this chart
            if primary_df_for_chart is None or primary_df_for_chart.empty:
                logger.warning(f"No suitable time-series data found for position {position}. Skipping chart creation.")
                continue

            else:
                chart, source = create_TH_chart(
                    primary_df_for_chart,
                    title = f"{position} - {chart_display_type_label}",
                    metrics = initial_metrics_for_chart,
                )
                if chart and source:
                    chart.name = f"{position}_combined_time_series"
                    self.bokeh_models['sources']['data'][chart.name] = source
                    self.bokeh_models['charts']['all'].append(chart)
                    position_charts.append(chart)
                    current_position_time_series_charts.append(chart)
                    logger.info(f"Created combined time series chart for {position}.")

                    #store the raw dfs so JS can access them
                    #convert to dict(orient='list') for direct JS consumption
                    self.bokeh_models['sources']['data'][f"{position}_overview_raw_data"] = overview_df.to_dict(orient='list') if isinstance(overview_df, pd.DataFrame) else None
                    self.bokeh_models['sources']['data'][f"{position}_log_raw_data"] = log_df.to_dict(orient='list') if isinstance(log_df, pd.DataFrame) else None

                    # Store information about the combined chart's state
                    self.bokeh_models['sources']['data'][f"{position}_combined_state"] = ColumnDataSource(data={
                        'display_type': [chart_display_type_label], # "Overview Data" or "Log Data"
                        'enable_auto_switch': [False], # Initial state of auto-switch toggle (for later)
                        'min_overview_span': [self.chart_settings.get('min_overview_span', 3600000)], # For JS zoom threshold
                        'min_log_span': [self.chart_settings.get('min_log_span', 300000)], # For JS zoom threshold
                    }, name=f"{position}_combined_state") 

            # Create combined spectrograms for both overview and log data if available

            overview_spectral_df = data_dict.get('spectral')
            log_spectral_df = data_dict.get('spectral_log')
            
            #Determine which df to use for the initial chart (prioritise overview if available
            initial_spectral_df, initial_spec_key, initial_title_suffix = (None, None, None)
            if isinstance(overview_spectral_df, pd.DataFrame) and not overview_spectral_df.empty:
                initial_spectral_df = overview_spectral_df
                initial_spec_key = 'spectral'
                initial_title_suffix = 'Spectral Overview'
            elif isinstance(log_spectral_df, pd.DataFrame) and not log_spectral_df.empty:
                initial_spectral_df = log_spectral_df
                initial_spec_key = 'spectral_log'
                initial_title_suffix = 'Spectral Log'

            # If we have at least one type of spectral data, proceed
            if initial_spectral_df is not None:
                #Preprocess both datasets
                if isinstance(initial_spectral_df, pd.DataFrame) and not initial_spectral_df.empty:
                    self._create_single_spectrogram(position, overview_spectral_df, 'spectral', 'Spectral Overview')
                    
                if isinstance(log_spectral_df, pd.DataFrame) and not log_spectral_df.empty:    
                    self._create_single_spectrogram(position, log_spectral_df, 'spectral_log', 'Spectral Log')
                    
                 # A better refactor would be to have _prepare_spectral_data and _create_spectrogram_figure.
                 # Re-call with the initial data to get the figure for the layout
                spectral_chart, hover_div = self._create_single_spectrogram(
                    position, initial_spectral_df, initial_spec_key, initial_title_suffix
                )   
                
                if spectral_chart:
                    spectral_chart_name = f"{position}_combined_spectrogram"
                    if hover_div:
                        hover_div.name = f"{position}_combined_spectrogram_hover_div"

                    position_charts.append(spectral_chart)
                    current_position_time_series_charts.append(spectral_chart)
                    if hover_div:
                        position_charts.append(hover_div)
                        #store the hover_div for visibility toggling
                        self.bokeh_models['ui']['position_elements'][position]['charts']['hover_div_combined_spectrogram'] = hover_div

                    # Store the chart model itself for the toggle callback
                    self.bokeh_models['ui']['position_elements'][position]['charts']['combined_spectrogram'] = spectral_chart
                    has_any_spectral_data = True

                    spec_key = initial_spec_key
                    position_charts.append(spectral_chart)
                    current_position_time_series_charts.append(spectral_chart)
                    if hover_div:
                        position_charts.append(hover_div)
                        #store the hover_div for visibility toggling
                        self.bokeh_models['ui']['position_elements'][position]['charts'][f'hover_div_{spec_key}'] = hover_div
                    has_any_spectral_data = True
            
            # Assemble layout for the position if any charts were created
            if position_charts:
                # Store chart models for visibility controls
                for chart in position_charts:
                    if hasattr(chart, 'name') and chart.name:
                        if chart.name.endswith('_combined_time_series'):
                            chart_type = 'combined_time_series'
                        elif chart.name.endswith(f"{position}_spectral"):
                            chart_type = chart.name.replace(f"{position}_", "", 1)
                        else:
                            chart_type = chart.name.replace(f"{position}_", "", 1)
                        self.bokeh_models['ui']['position_elements'][position]['charts'][chart_type] = chart

                header_row = self._create_position_header(position, data_dict)
                all_elements.append(header_row)
                all_elements.extend(position_charts)
                all_position_time_series_charts.extend(current_position_time_series_charts)

        logger.info(f"Finished collecting charts. Total time series charts: {len(all_position_time_series_charts)}")
        return all_elements, all_position_time_series_charts, has_any_spectral_data

    def _create_position_header(self, position, data_dict):
        """Creates the header row for a position with play button if applicable."""
        header = Div(text=f"<h2 style='margin-top: 20px;'>{position}</h2>", sizing_mode="stretch_width")
        header_content = [header]
        if 'audio' in data_dict and data_dict['audio'] and self.audio_handler_available:
            play_button = create_position_play_button(position, self.audio_handler_available)
            if 'position_buttons' not in self.bokeh_models['ui']['controls']['playback']:
                self.bokeh_models['ui']['controls']['playback']['position_buttons'] = {}
            self.bokeh_models['ui']['controls']['playback']['position_buttons'][position] = play_button
            header_content.append(play_button)
        
        header_row = row(*header_content, css_classes=["position-header-row"], name=f"{position}_header_row")
        self.bokeh_models['ui']['position_elements'][position]['header_row'] = header_row
        return header_row

    def _create_single_spectrogram(self, position, spectral_df, data_key, title_suffix):
        """Creates one spectrogram chart."""
        source_key = f"{position}_{data_key}"
        chart_title = f"{position} - {title_suffix}"
        
        params = extract_spectral_parameters(spectral_df)
        if not params: return None, None
        self._all_spectral_params.update(params)

        if position not in self.bokeh_models['spectral_data']: self.bokeh_models['spectral_data'][position] = {}
        self.bokeh_models['spectral_data'][position][data_key] = {'prepared_data': {}}
        self.bokeh_models['spectral_data'][position]['available_params'] = sorted(list(self._all_spectral_params))

        default_param = self.chart_settings.get("default_spectral_param", params[0])
        
        for param in params:
            prepared = prepare_spectral_image_data(spectral_df, param, self.chart_settings)
            if prepared: self.bokeh_models['spectral_data'][position][data_key]['prepared_data'][param] = prepared
        
        initial_data = self.bokeh_models['spectral_data'][position][data_key]['prepared_data'].get(default_param)
        if not initial_data: return None, None

        chart, source, hover_div = make_image_spectrogram(
            param=default_param, df=None, bar_source=self.bokeh_models['sources']['frequency']['bar'],
            bar_x_range=self.bokeh_models['frequency_analysis']['bar_chart']['x_range'], position=position,
            title=chart_title, prepared_data=initial_data
        )

        if chart:
            chart.name = source_key
            self.bokeh_models['sources']['data'][source_key] = source
            self.bokeh_models['charts']['all'].append(chart)
            logger.info(f"Created spectrogram '{chart_title}'")
        return chart, hover_div

    def _create_chart_visibility_controls(self) -> LayoutDOM:
        """Creates checkboxes to toggle chart visibility."""

        if 'ui' not in self.bokeh_models: self.bokeh_models['ui'] = {}
        if 'controls' not in self.bokeh_models['ui']: self.bokeh_models['ui']['controls'] = {}
        if 'visibility' not in self.bokeh_models['ui']['controls']: self.bokeh_models['ui']['controls']['visibility'] = {}

        position_chart_types = {}
        for pos, data in self.position_data.items():
            types = []
 
            df_overview = data.get('overview')
            if isinstance(df_overview, pd.DataFrame) and not df_overview.empty: types.append('overview')
            df_log = data.get('log')
            if isinstance(df_log, pd.DataFrame) and not df_log.empty: types.append('log')
            df_spectral = data.get('spectral')
            if isinstance(df_spectral, pd.DataFrame) and not df_spectral.empty: types.append('spectral')
            df_spectral_log = data.get('spectral_log')
            if isinstance(df_spectral_log, pd.DataFrame) and not df_spectral_log.empty: types.append('spectral_log')
            
            if self.bokeh_models['sources']['data'].get(f"{pos}_combined_time_series"):
                types.insert(0, 'combined_time_series')
            
            if types:
                position_chart_types[pos] = types
        
        if not position_chart_types:
            return None
        
        position_controls = []
        for pos, types in sorted(position_chart_types.items()):
            # Use more descriptive labels for the checkboxes
            labels = [t.replace('_', ' ').title() for t in types]
            checkbox = CheckboxGroup(labels=labels, active=list(range(len(types))), name=f"{pos}_visibility_toggle")
            
            if pos not in self.bokeh_models['ui']['controls']['visibility']:
                self.bokeh_models['ui']['controls']['visibility'][pos] = {}
            self.bokeh_models['ui']['controls']['visibility'][pos] = {'widget': checkbox, 'chart_types': types}
            
            pos_label = Div(text=f"<b>{pos}</b>", width=80, styles={'margin-top': '5px'})

            combined_chart_toggle = None
            if 'combined_time_series' in types:
                #Determine initial label for the toffle based on whats currently displayed
                initial_display_type = self.bokeh_models['sources']['data'][f"{pos}_combined_state"].data['display_type'][0]
                toggle_button_label = f"Switch to {('Log Data' if initial_display_type == 'Overview Data' else 'Overview Data').replace(' Data', '')}"
            
                combined_chart_toggle = Toggle(label=toggle_button_label, button_type="primary", active=False, width=150)
                
                if combined_chart_toggle:
                    position_controls.append(row(pos_label, checkbox, combined_chart_toggle, spacing=5))
                    self._add_combined_chart_toggle_callback(pos, combined_chart_toggle)
                else:
                    position_controls.append(row(pos_label, checkbox, spacing=5))

            self._add_position_checkbox_callback(pos, checkbox, types)

        if not position_controls:
            return None

        header = Div(text="<b>Chart Visibility</b>", styles={'margin-bottom': '5px'})
        return column(header, row(*position_controls, spacing=20))

    def _add_combined_chart_toggle_callback(self, position, toggle_widget):
        """Adds JS callback to handle combined chart visibility toggling."""
        combined_source = self.bokeh_models['sources']['data'].get(f"{position}_combined_time_series")
        overview_raw_data = self.bokeh_models['sources']['data'].get(f"{position}_overview_raw_data")
        log_raw_data = self.bokeh_models['sources']['data'].get(f"{position}_log_raw_data")
        combined_chart_state_source = self.bokeh_models['sources']['data'].get(f"{position}_combined_state")
        
        combined_chart = None
        for chart in self.bokeh_models['charts']['all']:
            if hasattr(chart, 'name') and chart.name == f"{position}_combined_time_series":
                combined_chart = chart
                break

        combined_spectrogram = self.bokeh_models.get('ui', {}).get('position_elements', {}).get(position, {}).get('charts', {}).get('combined_spectrogram')
        spectral_prepared_data = self.bokeh_models.get('spectral_data', {}).get(position)

        if not combined_source or not combined_chart_state_source or not combined_chart:
            logger.warning(f"Missing essential models for combined chart toggle callback for position {position}. Skipping.")
            return

        callback_args  = dict(
            toggle_widget=toggle_widget, # Pass the toggle itself for label updates
            combined_source=combined_source,
            overview_raw_data=overview_raw_data,
            log_raw_data=log_raw_data,
            combined_chart_state_source=combined_chart_state_source,
            combined_chart=combined_chart,
            position=position, # Pass position name for logging/debugging in JS
            combined_spectrogram=combined_spectrogram,
            spectral_prepared_data=spectral_prepared_data
        )

        js_code = """
            console.log("Combined chart toggle callback triggered for position:", position);
            if (window.NoiseSurveyApp && window.NoiseSurveyApp.handleCombinedChartToggle) {
                window.NoiseSurveyApp.handleCombinedChartToggle(cb_obj.active, 
                                                            combined_source,
                                                            overview_raw_data,
                                                            log_raw_data,
                                                            combined_chart_state_source,
                                                            combined_chart,
                                                            position,
                                                            combined_spectrogram,
                                                            spectral_prepared_data,
                                                            toggle_widget); // Pass the toggle widget itself
            } else {
                console.error('window.NoiseSurveyApp.handleCombinedChartToggle function not found!');
            }
        """
        
        toggle_widget.js_on_change('active', CustomJS(args=callback_args, code=js_code))      
        
    
    def _add_position_checkbox_callback(self, position, checkbox_group, chart_types):
        """Adds JS callback to handle chart visibility toggling."""
        pos_elements = self.bokeh_models['ui']['position_elements'].get(position, {})
        
        charts_dict = {}
        hover_divs_dict = {}

        for chart_type in chart_types:
            chart = pos_elements.get('charts', {}).get(chart_type)
            if chart:
                charts_dict[chart_type] = chart
                # Correctly find the hover div associated with this position's charts
                if chart_type in ['spectral', 'spectral_log']:
                    hover_div = next((c for c in pos_elements.get('charts', {}).values() if isinstance(c, Div) and 'spectrogram_hover_div' in (c.name or '')), None)
                    if hover_div:
                        hover_divs_dict[chart_type] = hover_div
        
        callback_args = {
            'header_row': pos_elements.get('header_row'),
            'charts_dict': charts_dict,
            'hover_divs_dict': hover_divs_dict
        }
        
        js_code = """
            const active_indices = cb_obj.active;
            const chart_types = %s;
            
            chart_types.forEach((type, index) => {
                const chart = charts_dict[type];
                if (chart) {
                    chart.visible = active_indices.includes(index);
                }
            });

            if (header_row){
                header_row.visible = active_indices.length > 0;
            }

            chart_types.forEach((type, index) => {
                if (type.includes('spectral')) {
                    const hover_div = hover_divs_dict[type];
                    if (hover_div) {
                        hover_div.visible = active_indices.includes(index);
                    }
                }
            });
        """ % chart_types

        checkbox_group.js_on_change('active', CustomJS(args=callback_args, code=js_code))

    # Other builder methods (_create_shared_range_selector, _create_frequency_analysis_section, etc.)
    # have been omitted for brevity as they require less substantial changes.
    def _create_shared_range_selector(self, time_series_charts: list) -> LayoutDOM:
        if not time_series_charts: return None
        
        def get_chart_range(c):
            source = self.bokeh_models['sources']['data'].get(c.name)
            if source and 'Datetime' in source.data:
                df = pd.DataFrame(source.data)
                if not df.empty and pd.api.types.is_datetime64_any_dtype(df['Datetime']):
                    # Ensure there are at least two points to form a range
                    if len(df['Datetime']) > 1:
                        return (df['Datetime'].max() - df['Datetime'].min()).total_seconds()
            return 0

        # Prioritize summary/overview charts for the range selector
        summary_charts = [c for c in time_series_charts if c.name and 'overview' in c.name]

        # Determine the pool of charts to select from
        candidate_charts = summary_charts if summary_charts else time_series_charts
        
        if not candidate_charts:
            logger.warning("No candidate charts found for creating the range selector.")
            return None

        longest_chart = max(candidate_charts, key=get_chart_range, default=None)
        if not longest_chart: return None
        
        chart_source = self.bokeh_models['sources']['data'].get(longest_chart.name)
        if not chart_source: return None

        range_selector = create_range_selector(
            attached_chart=longest_chart, 
            source=chart_source,
        )
        range_selector.name = 'shared_range_selector'
        self.bokeh_models['charts']['shared_range_selector'] = range_selector

        return range_selector

    def _create_frequency_analysis_section(self):
        freq_header = Div(text="<h2>Frequency Analysis</h2>", sizing_mode="stretch_width")
        if self.bokeh_models['frequency_analysis']['bar_chart']['figure']:
            return column(freq_header, self.bokeh_models['frequency_analysis']['bar_chart']['figure'], sizing_mode="stretch_width")
        return None
        
    def _create_controls_area(self) -> LayoutDOM:
        playback_controls = create_global_audio_controls(self.audio_handler_available)
        self.bokeh_models['ui']['controls']['playback'].update(playback_controls)
        
        param_selector, param_holder = create_parameter_selector(sorted(list(self._all_spectral_params)), self.chart_settings.get("default_spectral_param"))
        if param_selector:
            self.bokeh_models['ui']['controls']['parameter']['select'] = param_selector
            self.bokeh_models['ui']['controls']['parameter']['holder'] = param_holder

        visibility_controls = self._create_chart_visibility_controls()
        
        controls_row = row(
            column(
                *[w for w in [Div(text="<b>Playback Speed:</b>"), playback_controls.get('speed_control')] if w is not None]
            ),
            column(
                *[w for w in [Div(text="<b>Amplification:</b>"), playback_controls.get('amp_control')] if w is not None]
            ),
            *( [param_selector] if param_selector is not None else [] ),
            sizing_mode="scale_width"
        )
        
        return column(controls_row, visibility_controls) if visibility_controls else controls_row

    def _add_interactions(self) -> None:
        """
        Adds hover and tap interactions to the charts using the centralized
        functions from the 'interactive' module.
        """
        logger.debug("Adding interactions (hover, tap)...")
        
        # Link x ranges if option is enabled
        if self.visualization_settings.get("link_x_ranges", True) and len(self.bokeh_models['charts']['time_series']) > 1:
            logger.debug("Linking x ranges of time series charts...")
            link_x_ranges(self.bokeh_models['charts']['time_series'])
        
        # Get all charts that should have interactions
        charts_to_interact = self.bokeh_models['charts']['time_series'] + [self.bokeh_models['charts']['shared_range_selector']]
        if not charts_to_interact:
            logger.warning("No time series charts available for interactions")
            return
        
        # Add tap interaction and get back the models to store for JS init
        click_lines_list, labels_list = add_tap_interaction(
            charts=charts_to_interact
        )
        
        # --- Call the NEW, refactored interaction functions ---
        
        # Add hover interaction, passing the labels created by the tap interaction
        add_hover_interaction(
            charts=charts_to_interact,
            labels=labels_list # Pass the labels to the hover function
        )
        
        # Store the created models for JS initialization
        self.bokeh_models['ui']['visualization']['click_lines'] = click_lines_list
        self.bokeh_models['ui']['visualization']['labels'] = labels_list
        
        logger.debug(f"Added interaction elements: {len(click_lines_list)} click lines, {len(labels_list)} labels")