"""Markers panel components extracted without changing Bokeh wiring."""

from bokeh.models import (
    Button,
    ColorPicker,
    ColumnDataSource,
    CustomJS,
    DataTable,
    Div,
    TableColumn,
    TextAreaInput,
    Toggle,
)
from bokeh.layouts import Row, column

from .shared import SIDE_PANEL_WIDTH


class MarkerPanelComponent:
    """Bokeh widget-based panel for managing point-in-time markers."""

    #Todo: tool tips for shortcuts under markers
    def __init__(self) -> None:
        panel_width = SIDE_PANEL_WIDTH

        self.visibility_toggle = Toggle(
            label="Markers",
            width=panel_width,
            name="marker_visibility_toggle",
            active=True,
            button_type="primary",
        )

        self.marker_source = ColumnDataSource(
            data={
                "id": [],
                "timestamp": [],
                "timestamp_display": [],
                "note_preview": [],
                "color": [],
            },
            name="marker_panel_source",
        )

        timestamp_column_width = int(panel_width * 0.48)
        note_column_width = max(int(panel_width * 0.42), panel_width - timestamp_column_width - 24)

        self.marker_table = DataTable(
            source=self.marker_source,
            columns=[
                TableColumn(field="timestamp_display", title="Timestamp", width=timestamp_column_width),
                TableColumn(field="note_preview", title="Note", width=note_column_width),
                TableColumn(field="id", title="ID", visible=False),
                TableColumn(field="timestamp", title="Timestamp (raw)", visible=False),
                TableColumn(field="color", title="Color", visible=False),
            ],
            width=panel_width,
            height=220,
            index_position=None,
            header_row=True,
            row_height=42,
            name="marker_panel_table",
            selectable=True,
            editable=False,
            reorderable=False,
            autosize_mode="none",
            sizing_mode="stretch_width",
            css_classes=["marker-panel-table"],
        )
        self.marker_table.stylesheets = [
            """
            .marker-panel-table .bk-data-table {
                border: none;
                background: transparent;
                font-family: 'Segoe UI', sans-serif;
            }
            .marker-panel-table .slick-header-columns {
                background: rgba(148, 163, 184, 0.1);
                border-bottom: 1px solid rgba(148, 163, 184, 0.4);
            }
            .marker-panel-table .slick-header-column {
                font-weight: 600;
                color: #1f2937;
            }
            .marker-panel-table .slick-viewport {
                background: transparent;
            }
            .marker-panel-table .slick-row {
                border: none !important;
                margin: 4px 4px;
                border-radius: 10px;
                background: rgba(255, 255, 255, 0.85);
                box-shadow: 0 1px 3px rgba(15, 23, 42, 0.08);
                transition: transform 0.18s ease, box-shadow 0.18s ease, background 0.18s ease;
            }
            .marker-panel-table .slick-row:hover {
                transform: translateY(-1px);
                box-shadow: 0 6px 12px rgba(15, 23, 42, 0.12);
                background: rgba(124, 179, 66, 0.16);
            }
            .marker-panel-table .slick-row.active,
            .marker-panel-table .slick-row.selected {
                background: #43a047 !important;
                box-shadow: 0 8px 16px rgba(67, 160, 71, 0.25);
            }
            .marker-panel-table .slick-row .slick-cell {
                border: none !important;
                background: transparent !important;
                color: #1f2937;
                font-size: 12px;
            }
            .marker-panel-table .slick-row.selected .slick-cell {
                color: #ffffff;
            }
            .marker-panel-table .bk-cell-index {
                display: none;
            }
            """
        ]

        self.message_div = Div(
            text="<p class='marker-panel-empty'>No markers recorded.</p>",
            width=panel_width,
            name="marker_panel_message_div",
        )

        self.color_picker = ColorPicker(
            title="Marker Colour",
            color="#43a047",
            width=panel_width,
            name="marker_color_picker",
            disabled=True,
        )

        button_width = int(panel_width / 3) - 8

        self.copy_button = Button(
            label="Copy Details",
            width=button_width,
            name="marker_copy_button",
            disabled=True,
        )

        self.delete_button = Button(
            label="Delete Marker",
            width=button_width,
            name="marker_delete_button",
            button_type="danger",
            disabled=True,
        )

        self.add_at_tap_button = Button(
            label="Add Marker at Tap",
            width=button_width,
            name="marker_add_at_tap_button",
            button_type="success",
            disabled=True,
        )

        self.note_input = TextAreaInput(
            title="Notes",
            value="",
            rows=4,
            width=panel_width,
            name="marker_note_input",
            placeholder="Describe this marker...",
            disabled=True,
        )

        self.metrics_div = Div(
            text="<p class='marker-panel-empty'>Select a marker to view metrics.</p>",
            width=panel_width,
            name="marker_metrics_div",
            styles={
                "font-size": "12px",
                "border-top": "1px solid #e2e8f0",
                "padding-top": "6px",
            },
        )

        action_row = Row(
            children=[self.copy_button, self.delete_button, self.add_at_tap_button],
            name="marker_action_buttons",
            sizing_mode="stretch_width",
        )

        self.detail_layout = column(
            self.marker_table,
            self.color_picker,
            action_row,
            self.note_input,
            self.metrics_div,
            name="marker_panel_detail",
            sizing_mode="stretch_width",
            visible=False,
        )

        self.container = column(
            self.visibility_toggle,
            self.detail_layout,
            self.message_div,
            name="marker_panel_container",
            styles={
                "border": "1px solid rgba(148, 163, 184, 0.25)",
                "padding": "12px",
                "background-color": "#ffffff",
                "border-radius": "16px",
                "box-shadow": "0 8px 20px rgba(15, 23, 42, 0.08)",
            },
            width=panel_width,
        )

        self._attach_callbacks()

    def _attach_callbacks(self) -> None:
        selection_callback = CustomJS(args={'source': self.marker_source, 'table': self.marker_table}, code="""
            if (!source || !table) {
                return;
            }
            const actions = window.NoiseSurveyApp?.actions;
            const thunks = window.NoiseSurveyApp?.thunks;
            const store = window.NoiseSurveyApp?.store;
            if (!actions || typeof store?.dispatch !== 'function') {
                return;
            }
            const indices = Array.isArray(source.selected?.indices) ? source.selected.indices : [];
            const data = source.data || {};
            const ids = Array.isArray(data.id) ? data.id : [];
            const candidate = Number(ids[indices[0]]);

            if (table.__suppressSelectionDispatch) {
                if (Number.isFinite(candidate) && typeof thunks?.computeMarkerMetricsIntent === 'function') {
                    store.dispatch(thunks.computeMarkerMetricsIntent(candidate));
                }
                return;
            }

            if (!indices.length) {
                if (typeof actions.markerSelect === 'function') {
                    store.dispatch(actions.markerSelect(null));
                }
                return;
            }
            if (!Number.isFinite(candidate)) {
                return;
            }
            if (typeof actions.markerSelect === 'function') {
                store.dispatch(actions.markerSelect(candidate));
            }
            if (typeof thunks?.computeMarkerMetricsIntent === 'function') {
                store.dispatch(thunks.computeMarkerMetricsIntent(candidate));
            }
        """)
        self.marker_source.selected.js_on_change('indices', selection_callback)

        note_callback = CustomJS(args={'source': self.marker_source}, code="""
            const indices = Array.isArray(source.selected?.indices) ? source.selected.indices : [];
            if (!indices.length) {
                return;
            }
            const data = source.data || {};
            const ids = Array.isArray(data.id) ? data.id : [];
            const markerId = Number(ids[indices[0]]);
            if (!Number.isFinite(markerId)) {
                return;
            }
            const actions = window.NoiseSurveyApp?.actions;
            const store = window.NoiseSurveyApp?.store;
            if (actions?.markerSetNote && typeof store?.dispatch === 'function') {
                store.dispatch(actions.markerSetNote(markerId, cb_obj.value ?? ''));
            }
        """)
        self.note_input.js_on_change('value', note_callback)

        color_callback = CustomJS(args={'source': self.marker_source}, code="""
            const indices = Array.isArray(source.selected?.indices) ? source.selected.indices : [];
            if (!indices.length) {
                return;
            }
            const data = source.data || {};
            const ids = Array.isArray(data.id) ? data.id : [];
            const markerId = Number(ids[indices[0]]);
            if (!Number.isFinite(markerId)) {
                return;
            }
            const actions = window.NoiseSurveyApp?.actions;
            const store = window.NoiseSurveyApp?.store;
            const colorValue = typeof cb_obj.color === 'string' ? cb_obj.color : '';
            if (actions?.markerSetColor && typeof store?.dispatch === 'function') {
                store.dispatch(actions.markerSetColor(markerId, colorValue));
            }
        """)
        self.color_picker.js_on_change('color', color_callback)

        delete_callback = CustomJS(args={'source': self.marker_source}, code="""
            const indices = Array.isArray(source.selected?.indices) ? source.selected.indices : [];
            if (!indices.length) {
                return;
            }
            const data = source.data || {};
            const ids = Array.isArray(data.id) ? data.id : [];
            const markerId = Number(ids[indices[0]]);
            if (!Number.isFinite(markerId)) {
                return;
            }
            const actions = window.NoiseSurveyApp?.actions;
            const store = window.NoiseSurveyApp?.store;
            if (actions?.markerRemove && typeof store?.dispatch === 'function') {
                store.dispatch(actions.markerRemove(markerId));
            }
        """)
        self.delete_button.js_on_event('button_click', delete_callback)

        copy_callback = CustomJS(args={'source': self.marker_source}, code="""
            const indices = Array.isArray(source.selected?.indices) ? source.selected.indices : [];
            if (!indices.length) {
                return;
            }
            const data = source.data || {};
            const ids = Array.isArray(data.id) ? data.id : [];
            const markerId = Number(ids[indices[0]]);
            if (!Number.isFinite(markerId)) {
                return;
            }
            const store = window.NoiseSurveyApp?.store;
            const renderer = window.NoiseSurveyApp?.services?.markerPanelRenderer;
            if (!renderer || typeof renderer.buildClipboardText !== 'function' || typeof store?.getState !== 'function') {
                return;
            }
            const state = store.getState();
            const markersState = state?.markers || {};
            const marker = markersState?.byId?.[markerId];
            if (!marker) {
                return;
            }
            const text = renderer.buildClipboardText(marker, state);
            if (!text) {
                return;
            }
            if (navigator?.clipboard?.writeText) {
                navigator.clipboard.writeText(text).catch(err => {
                    console.error('[Markers] Failed to copy details:', err);
                });
                return;
            }
            const temp = document.createElement('textarea');
            temp.value = text;
            temp.style.position = 'fixed';
            temp.style.opacity = '0';
            document.body.appendChild(temp);
            temp.focus();
            temp.select();
            try {
                document.execCommand('copy');
            } catch (err) {
                console.error('[Markers] execCommand copy failed:', err);
            }
            document.body.removeChild(temp);
        """)
        self.copy_button.js_on_event('button_click', copy_callback)

        add_at_tap_callback = CustomJS(code="""
            const thunks = window.NoiseSurveyApp?.thunks;
            const store = window.NoiseSurveyApp?.store;
            
            if (typeof thunks?.createMarkerIntent !== 'function' || typeof store?.dispatch !== 'function') {
                console.error('[MarkerPanel] Cannot create marker: createMarkerIntent thunk or store is missing.');
                return;
            }
            store.dispatch(thunks.createMarkerIntent());
        """)
        self.add_at_tap_button.js_on_event('button_click', add_at_tap_callback)

        visibility_callback = CustomJS(code="""
            const actions = window.NoiseSurveyApp?.actions;
            const store = window.NoiseSurveyApp?.store;
            if (!actions?.markersVisibilitySet || typeof store?.dispatch !== 'function') {
                return;
            }
            const isEnabled = !!cb_obj.active;
            store.dispatch(actions.markersVisibilitySet(isEnabled));
        """)
        self.visibility_toggle.js_on_change('active', visibility_callback)

    def layout(self):
        return self.container
