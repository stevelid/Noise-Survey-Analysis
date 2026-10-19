"""Controls components extracted without changing Bokeh wiring."""

from bokeh.models import (
    Button,
    CheckboxGroup,
    CustomJS,
    Div,
    Dropdown,
    Select,
    Spinner,
    Toggle,
)
from typing import Dict, List
from bokeh.layouts import Row, column

from .shared import logger


class ControlsComponent:
    """A component that provides global controls for the dashboard."""
    def __init__(self, available_params: List[str], server_mode: bool = False): # Would take DataManager to access all positions' info
        
        self.available_params = available_params
        self.server_mode = bool(server_mode)
        self.visibility_checkboxes: Dict[str, list] = {} # Key: position_name, Value: list of (chart_name, checkbox_widget) tuples
        self.position_order: List[str] = []  # Track order of positions as checkboxes are added
        self.plot_visibility_menu = self.add_plot_visibility_menu()
        
        self.session_menu = self.add_session_menu()
        self.view_toggle = self.add_view_type_selector()
        self.hover_toggle = self.add_hover_toggle()
        self.param_select = self.add_parameter_selector(available_params)
        self.global_audio_controls = self.add_global_audio_controls()
        self.log_threshold_spinner = self.add_log_threshold_spinner()
        self.status_chips = self.add_status_chips()

        logger.info("ControlsComponent initialized.")


    def add_view_type_selector(self):
        toggle = Toggle(
            label="Log View Enabled", 
            button_type="primary", 
            width=150,
            name="global_view_toggle",
            active=True
        )
        
        toggle.js_on_change("active", CustomJS(code="""if (window.NoiseSurveyApp && window.NoiseSurveyApp.eventHandlers && window.NoiseSurveyApp.eventHandlers.handleViewToggle) {
                window.NoiseSurveyApp.eventHandlers.handleViewToggle(cb_obj.active);
            } else {
                console.error('window.NoiseSurveyApp.eventHandlers.handleViewToggle function not found!');
            }"""))
        return toggle

    def add_hover_toggle(self):
        toggle = Toggle(
            label="Hover Enabled", 
            button_type="success", 
            width=130,
            height=30,
            name="global_hover_toggle",
            active=True
        )
        
        toggle.js_on_change("active", CustomJS(code="""if (window.NoiseSurveyApp && window.NoiseSurveyApp.eventHandlers && window.NoiseSurveyApp.eventHandlers.handleHoverToggle) {
                window.NoiseSurveyApp.eventHandlers.handleHoverToggle(cb_obj.active);
            } else {
                console.error('window.NoiseSurveyApp.eventHandlers.handleHoverToggle function not found!');
            }"""))
        return toggle
    
    def add_global_audio_controls(self):
        """Creates global audio playback controls that work with the active position."""
        # Play/Pause Toggle Button
        play_toggle = Toggle(
            label="Play", 
            button_type="success", 
            width=80,
            height=30,
            name="global_play_toggle"
        )
        play_toggle.js_on_change('active', CustomJS(
            args=dict(button=play_toggle),
            code="""
                if (window.NoiseSurveyApp && window.NoiseSurveyApp.eventHandlers && window.NoiseSurveyApp.eventHandlers.togglePlayPause) {
                    // Global control uses the active position from tap state
                    window.NoiseSurveyApp.eventHandlers.togglePlayPause({ positionId: null, isActive: button.active });
                } else {
                    console.error('NoiseSurveyApp.eventHandlers.togglePlayPause function not found!');
                }
            """
        ))

        # Playback Rate Button
        playback_rate_button = Button(
            label="1.0x",
            width=60,
            height=30,
            name="global_playback_rate"
        )
        playback_rate_button.js_on_click(CustomJS(
            code="""
                if (window.NoiseSurveyApp && window.NoiseSurveyApp.eventHandlers && window.NoiseSurveyApp.eventHandlers.handlePlaybackRateChange) {
                    window.NoiseSurveyApp.eventHandlers.handlePlaybackRateChange({ positionId: null });
                } else {
                    console.error('NoiseSurveyApp.eventHandlers.handlePlaybackRateChange function not found!');
                }
            """
        ))

        # Volume Boost Toggle Button
        volume_boost_button = Toggle(
            label="Boost",
            width=70,
            height=30,
            name="global_volume_boost",
            active=False
        )
        volume_boost_button.js_on_change('active', CustomJS(
            args=dict(button=volume_boost_button),
            code="""
                if (window.NoiseSurveyApp && window.NoiseSurveyApp.eventHandlers && window.NoiseSurveyApp.eventHandlers.handleVolumeBoostToggle) {
                    window.NoiseSurveyApp.eventHandlers.handleVolumeBoostToggle({ positionId: null, isBoostActive: button.active });
                } else {
                    console.error('NoiseSurveyApp.eventHandlers.handleVolumeBoostToggle function not found!');
                }
            """
        ))

        # Active position display
        active_position_display = Div(
            text="<span style='font-size: 11px; color: #64748b;'>Audio not available</span>",
            width=140,
            height=30,
            name="global_active_position_display",
            styles={"display": "flex", "align-items": "center", "padding-left": "8px"}
        )

        # Audio file info display (filename, position in file, file start time)
        audio_file_info_display = Div(
            text="",
            width=350,
            height=30,
            name="global_audio_file_info_display",
            styles={"display": "flex", "align-items": "center", "padding-left": "8px", "font-size": "10px", "color": "#64748b"}
        )

        controls_layout = Row(
            play_toggle,
            playback_rate_button,
            volume_boost_button,
            active_position_display,
            audio_file_info_display,
            name="global_audio_controls",
            styles={
                "gap": "4px",
                "padding": "4px 12px",
                "border": "1px solid #cbd5e1",
                "border-radius": "4px",
                "background-color": "#f8fafc",
                "margin-left": "16px"
            }
        )

        return {
            'layout': controls_layout,
            'play_toggle': play_toggle,
            'playback_rate_button': playback_rate_button,
            'volume_boost_button': volume_boost_button,
            'active_position_display': active_position_display,
            'audio_file_info_display': audio_file_info_display
        }

    def add_log_threshold_spinner(self):
        """Creates a spinner for adjusting the log view zoom threshold."""
        spinner = Spinner(
            title="",
            value=5,
            low=0.5,
            high=1440,
            step=0.5,
            width=70,
            height=30,
            name="log_view_threshold_spinner"
        )
        spinner.js_on_change("value", CustomJS(code="""
            if (window.NoiseSurveyApp && window.NoiseSurveyApp.eventHandlers && window.NoiseSurveyApp.eventHandlers.handleLogViewThresholdChange) {
                window.NoiseSurveyApp.eventHandlers.handleLogViewThresholdChange(cb_obj.value);
            }
        """))
        label = Div(
            text="Log max window (min):",
            width=145,
            height=30,
            styles={'line-height': '30px', 'font-size': '9pt', 'white-space': 'nowrap'}
        )
        self.log_threshold_spinner_widget = spinner
        return Row(label, spinner, name="log_threshold_group")

    def add_plot_visibility_menu(self):
        dropdown = Dropdown(
            label="Plots",
            button_type="default",
            width=120,
            height=30,
            name="plot_visibility_dropdown",
            menu=[],
        )
        dropdown.js_on_event("menu_item_click", CustomJS(code="""
            const chartName = cb_obj?.item;
            if (!chartName) {
                return;
            }
            const checkboxes = window.NoiseSurveyApp?.registry?.models?.visibilityCheckBoxes || [];
            const target = checkboxes.find(cb => cb?.name === `visibility_${chartName}`);
            if (!target) {
                console.error('[PlotVisibility]', `Checkbox not found for ${chartName}`);
                return;
            }
            const active = Array.isArray(target.active) ? target.active : [];
            target.active = active.includes(0) ? [] : [0];
            if (target.change && typeof target.change.emit === 'function') {
                target.change.emit();
            }
        """))
        return dropdown

    def add_status_chips(self):
        view_status = Div(
            text="<span style='font-size:11px;color:#0f172a;'>View: --</span>",
            width=170,
            height=28,
            name="view_status_chip",
            styles={
                "display": "flex",
                "align-items": "center",
                "padding": "0 8px",
                "border": "1px solid #cbd5e1",
                "border-radius": "999px",
                "background-color": "#f8fafc",
            },
        )
        focus_status = Div(
            text="<span style='font-size:11px;color:#0f172a;'>Focus: none</span>",
            width=200,
            height=28,
            name="focus_status_chip",
            styles={
                "display": "flex",
                "align-items": "center",
                "padding": "0 8px",
                "border": "1px solid #cbd5e1",
                "border-radius": "999px",
                "background-color": "#f8fafc",
            },
        )

        chip_row = Row(
            view_status,
            focus_status,
            name="status_chip_row",
            styles={
                "gap": "8px",
                "align-items": "center",
            }
        )

        return {
            "layout": chip_row,
            "view_status_chip": view_status,
            "focus_status_chip": focus_status,
        }

    def add_parameter_selector(self, available_params: List[str]):
        select = Select(
            options=available_params,
            value="LZeq",
            width=80,
            height=30,
            name="global_parameter_selector"
        )
        select.js_on_change("value", CustomJS(args={"select_widget": select}, code="""if (window.NoiseSurveyApp && window.NoiseSurveyApp.eventHandlers && window.NoiseSurveyApp.eventHandlers.handleParameterChange) {
                window.NoiseSurveyApp.eventHandlers.handleParameterChange(cb_obj.value, select_widget); // Pass the select widget itself
            } else {
                console.error('window.NoiseSurveyApp.eventHandlers.handleParameterChange function not found!');
            }""")) #active for overview, inactive for log
        return select

    def add_visibility_checkbox(self, chart_name: str, chart_label: str, initial_state: bool = True):
        """
        Adds a visibility checkbox for a specific chart.
        Called by DashBuilder after chart components are created.
        """
        # The chart_name is expected to be in the format 'figure_Position_chart-type', e.g., 'figure_East_timeseries'
        try:
            position_name = chart_name.split('_')[1]
        except IndexError:
            logger.warning(f"Could not determine position from chart name: '{chart_name}'. Grouping as 'unknown'.")
            position_name = "unknown"

        checkbox = CheckboxGroup(labels=[chart_label], active=[0] if initial_state else [], width=200, name=f"visibility_{chart_name}")
        
        if position_name not in self.visibility_checkboxes:
            self.visibility_checkboxes[position_name] = []
            # Track the order positions are added (preserves config file order)
            if position_name not in self.position_order:
                self.position_order.append(position_name)
        self.visibility_checkboxes[position_name].append((chart_name, checkbox))

        # --- Attach JS Callback ---
        checkbox_js_callback = CustomJS(args=dict(chart_name=chart_name),code=f"""
                if (window.NoiseSurveyApp && window.NoiseSurveyApp.eventHandlers && window.NoiseSurveyApp.eventHandlers.handleVisibilityChange) {{
                window.NoiseSurveyApp.eventHandlers.handleVisibilityChange(cb_obj, chart_name);
                }} else {{
                    console.error('NoiseSurveyApp.eventHandlers.handleVisibilityChange not defined!');
                }}
            """)
        checkbox.js_on_change("active", checkbox_js_callback)
        self._refresh_plot_visibility_menu()
        
    def _refresh_plot_visibility_menu(self):
        menu = []
        for position_name in self.position_order:
            position_checkboxes = self.visibility_checkboxes.get(position_name, [])
            for chart_name, widget in sorted(position_checkboxes, key=lambda item: item[0]):
                raw_label = widget.labels[0] if widget.labels else chart_name
                is_active = 0 in getattr(widget, 'active', [])
                menu.append((f"[{'x' if is_active else ' '}] {raw_label}", chart_name))
        self.plot_visibility_menu.menu = menu


    def layout(self):
        view_controls_group = Row(
            self.session_menu,
            self.plot_visibility_menu,
            self.param_select,
            self.view_toggle,
            self.log_threshold_spinner,
            self.hover_toggle,
            self.status_chips['layout'],
            name="view_controls_group",
            styles={
                "gap": "8px",
                "align-items": "center",
                "padding": "4px 8px",
                "border": "1px solid #cbd5e1",
                "border-radius": "8px",
                "background-color": "#ffffff",
                "flex-wrap": "wrap",
                "overflow": "visible"
            }
        )

        controls_children = [view_controls_group]
        if self.server_mode:
            controls_children.append(self.global_audio_controls['layout'])

        controls_group = Row(
            *controls_children,
            name="primary_controls_row",
            styles={
                "flex-wrap": "wrap",
                "gap": "8px",
                "align-items": "center"
            }
        )

        return column(
            controls_group,
            name="controls_component_layout",
            styles={
                "gap": "8px",
                "position": "sticky",
                "top": "0px",
                "background": "#f1f5f9",
                "padding": "10px 12px",
                "box-shadow": "0 2px 6px rgba(0, 0, 0, 0.08)",
                "z-index": "100"
            }
        )

    def get_all_visibility_checkboxes(self) -> list:
        """Returns a flat list of all checkbox widgets."""
        all_checkboxes = []
        for position_checkboxes in self.visibility_checkboxes.values():
            all_checkboxes.extend([widget for name, widget in position_checkboxes])
        return all_checkboxes

    def add_session_menu(self):
        dropdown = Dropdown(
            label="Menu",
            button_type="default",
            width=80,
            height=30,
            name="session_actions_dropdown",
            menu=[
                ("Save Setup to Config", "save_setup_to_config"),
                ("Save Workspace", "save"),
                ("Load Workspace", "load"),
                ("Export Annotations (CSV)", "export_annotations_csv"),
                ("Import Annotations (CSV)", "import_annotations_csv"),
                ("Export Classifications (CSV)", "export_classifications_csv"),
                ("Import Classifications (CSV/JSON)", "import_classifications"),
                ("Generate Static HTML (Offline)", "generate_static_html"),
            ],
        )

        if self.server_mode:
            menu = list(dropdown.menu)
            menu.insert(4, ("Export Annotations — Full Resolution", "export_annotations_full_resolution"))
            dropdown.menu = menu

        dropdown.js_on_event("menu_item_click", CustomJS(code="""
            const action = cb_obj?.item;
            if (window.NoiseSurveyApp?.session?.handleMenuAction) {
                window.NoiseSurveyApp.session.handleMenuAction(action);
            } else {
                console.error('[Session] Session manager is not available for action:', action);
            }
        """))

        return dropdown
