"""Regions panel components extracted without changing Bokeh wiring."""

from bokeh.models import (
    Button,
    ColorPicker,
    ColumnDataSource,
    CustomJS,
    DataTable,
    Div,
    HTMLTemplateFormatter,
    Select,
    TableColumn,
    TextAreaInput,
    Toggle,
)
from bokeh.layouts import Row, column

from .shared import SIDE_PANEL_WIDTH


class RegionPanelComponent:
    """Bokeh widget-based panel for managing regions."""

    def __init__(self) -> None:
        panel_width = SIDE_PANEL_WIDTH

        self.header = Div(
            text="<h2 style='margin:0;'>Regions</h2>",
            width=panel_width,
            name="region_panel_header",
        )

        self.visibility_toggle = Toggle(
            label="Regions",
            width=panel_width,
            name="region_visibility_toggle",
            active=True,
            button_type="primary",
        )

        self.auto_daynight_button = Button(
            label="Auto Day & Night",
            width=panel_width,
            name="region_auto_daynight_button",
            button_type="default",
        )

        self.auto_buttons = Row(
            children=[self.auto_daynight_button],
            name="region_auto_buttons",
            sizing_mode="stretch_width",
        )

        self.creation_indicator_div = Div(
            text=(
                "<div class='region-mode-indicator'>"
                "<strong>Create Region mode active.</strong> "
                "Press <kbd>R</kbd> again to finish at the current cursor position or <kbd>Esc</kbd> to cancel."
                "</div>"
            ),
            width=panel_width,
            name="region_panel_creation_indicator",
            visible=False,
            styles={
                "font-size": "12px",
                "line-height": "1.45",
                "margin-bottom": "8px",
            },
        )

        self.region_source = ColumnDataSource(
            data={
                "id": [],
                "title": [],
                "subtitle": [],
                "color": [],
                "data_source_label": [],
                "data_source_key": [],
            },
            name="region_panel_source",
        )

        region_card_template = """
            <div class=\"region-card\">
                <div class=\"region-card__accent\" style=\"background:<%= color %>;\"></div>
                <div class=\"region-card__body\">
                    <div class=\"region-card__title\"><%= title %></div>
                    <div class=\"region-card__subtitle\"><%= subtitle %></div>
                </div>
                <div class=\"region-card__source region-card__source--<%= data_source_key %>\"><%= data_source_label %></div>
            </div>
        """

        self.region_table = DataTable(
            source=self.region_source,
            columns=[
                TableColumn(
                    field="title",
                    title="",
                    formatter=HTMLTemplateFormatter(template=region_card_template),
                ),
                TableColumn(field="subtitle", title="Subtitle", visible=False),
                TableColumn(field="color", title="Color", visible=False),
                TableColumn(field="data_source_label", title="Source", visible=False),
                TableColumn(field="data_source_key", title="Source Key", visible=False),
            ],
            width=panel_width,
            height=240,
            index_position=None,
            header_row=False,
            row_height=64,
            name="region_panel_table",
            selectable=True,
            editable=False,
            reorderable=False,
            fit_columns=True,
            autosize_mode="fit_columns",
            sizing_mode="stretch_width",
            css_classes=["region-panel-table"],
        )
        self.region_table.stylesheets = [
            """
            .region-panel-table .bk-data-table {
                border: none;
                background: transparent;
                font-family: 'Segoe UI', sans-serif;
            }
            .region-panel-table .slick-viewport {
                background: transparent;
            }
            .region-panel-table .slick-row {
                border: 1px solid #e2e8f0 !important;
                margin: 3px 4px;
                border-radius: 6px;
                background: #ffffff !important;
                box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
                transition: all 0.12s ease;
                cursor: pointer;
            }
            .region-panel-table .slick-row.odd {
                background: #ffffff !important;
            }
            .region-panel-table .slick-row.even {
                background: #ffffff !important;
            }
            .region-panel-table .slick-row:hover {
                border-color: #cbd5e1;
                background: #f8fafc !important;
                box-shadow: 0 2px 4px rgba(0, 0, 0, 0.08);
                transform: translateY(-1px);
            }
            .region-panel-table .slick-row.active, .region-panel-table .slick-row.selected {
                background: #1e40af !important;
                border-color: #1e3a8a !important;
                box-shadow: 0 4px 12px rgba(30, 64, 175, 0.4), inset 0 1px 0 rgba(255, 255, 255, 0.15);
                transform: translateY(0);
            }
            .region-panel-table .slick-row .slick-cell {
                border: none !important;
                background: transparent !important;
                color: #1f2937;
                font-size: 13px;
                outline: none !important;
            }
            .region-panel-table .slick-row.selected .slick-cell {
                color: #ffffff;
                font-weight: 500;
            }
            .region-panel-table .slick-cell.active {
                border: none !important;
                outline: none !important;
                box-shadow: none !important;
            }
            .region-panel-table .slick-cell:focus {
                outline: none !important;
                border: none !important;
            }
            .region-panel-table .slick-row.active {
                outline: none !important;
                border: 1px solid rgba(15, 23, 42, 0.12) !important;
            }
            .region-panel-table .slick-row.active.selected {
                border-color: #1565c0 !important;
            }
            .region-panel-table .bk-cell-index {
                display: none;
            }
            .region-card {
                display: flex;
                align-items: center;
                gap: 12px;
                padding: 8px 12px;
            }
            .region-card__accent {
                width: 10px;
                height: 40px;
                border-radius: 6px;
                background: #1e88e5;
                flex-shrink: 0;
            }
            .region-card__body {
                display: flex;
                flex-direction: column;
                gap: 4px;
                min-width: 0;
                flex: 1;
            }
            .region-card__title {
                font-weight: 600;
                font-size: 13px;
                letter-spacing: 0.01em;
            }
            .region-panel-table .slick-row.selected .region-card__title {
                color: #ffffff;
            }
            .region-card__subtitle {
                font-size: 11px;
                color: rgba(31, 41, 55, 0.7);
            }
            .region-panel-table .slick-row.selected .region-card__subtitle {
                color: rgba(255, 255, 255, 0.85);
            }
            .region-card__source {
                flex-shrink: 0;
                border-radius: 999px;
                padding: 3px 7px;
                font-size: 10px;
                font-weight: 700;
                letter-spacing: 0.02em;
                color: #475569;
                background: #e2e8f0;
            }
            .region-card__source--log {
                color: #166534;
                background: #dcfce7;
            }
            .region-card__source--overview {
                color: #92400e;
                background: #fef3c7;
            }
            .region-panel-table .slick-row.selected .region-card__source {
                color: #ffffff;
                background: rgba(255, 255, 255, 0.2);
            }
        """
        ]

        self.color_picker = ColorPicker(
            title="Region Colour",
            color="#1e88e5",
            width=panel_width,
            name="region_color_picker",
            disabled=True,
        )

        # Placeholder only: the JS region panel renderer replaces this with the
        # full keyboard shortcut reference on first render.
        region_message_html = (
            "<div>"
            "<strong>No regions yet</strong><br>"
            "Drag on a chart to draw a region, or click a chart and press <kbd>R</kbd> "
            "to pin the start and again to set the end."
            "</div>"
        )
        self.message_div = Div(
            text=region_message_html,
            width=panel_width,
            name="region_panel_message_div",
            styles={"font-size": "12px", "line-height": "1.45", "margin-bottom": "8px"},
        )

        self.copy_button = Button(
            label="Copy Summary",
            width=int(panel_width / 2) - 6,
            name="region_copy_button",
            disabled=True,
        )

        self.delete_button = Button(
            label="Delete Region",
            width=int(panel_width / 2) - 6,
            button_type="danger",
            name="region_delete_button",
            disabled=True,
        )

        self.add_area_button = Button(
            label="Add Area",
            width=int(panel_width / 2) - 6,
            name="region_add_area_button",
            disabled=True,
        )

        self.merge_select = Select(
            title="Merge Selected With",
            value="",
            options=[],
            width=panel_width,
            name="region_merge_select",
            disabled=True,
            visible=False,
        )

        self.merge_button = Button(
            label="Merge Regions",
            width=int(panel_width / 2) - 6,
            name="region_merge_button",
            disabled=True,
        )

        self.split_button = Button(
            label="Split Areas",
            width=panel_width,
            name="region_split_button",
            disabled=True,
        )

        self.copy_target_select = Select(
            title="Copy Region To",
            value="",
            options=[],
            width=panel_width - 94,
            name="region_copy_target_select",
            disabled=True,
            visible=False,
        )

        self.copy_to_all_positions_button = Button(
            label="Copy",
            width=86,
            name="region_copy_to_all_positions_button",
            disabled=True,
            visible=False,
            align="end",
        )

        self.center_region_button = Button(
            label="Centre on Region",
            width=int(panel_width / 2) - 6,
            name="region_center_button",
            disabled=True,
        )

        self.back_to_previous_view_button = Button(
            label="Back (B)",
            width=int(panel_width / 2) - 6,
            name="region_back_to_previous_view_button",
            disabled=True,
        )

        self.recalculate_region_button = Button(
            label="Recalculate",
            width=panel_width,
            name="region_recalculate_button",
            disabled=True,
        )

        self.note_input = TextAreaInput(
            title="Notes",
            value="",
            rows=4,
            width=panel_width,
            name="region_note_input",
            placeholder="Add notes... (N to edit, Esc or Ctrl+Enter to save)",
            disabled=True,
            css_classes=["region-note-input"],
        )

        # Save indicator for the note ("Unsaved changes" / "Saved"). It is a
        # separate Div because changing the TextAreaInput's own title makes
        # Bokeh re-render the textarea, which would drop focus mid-typing.
        self.note_status_div = Div(
            text="",
            width=panel_width,
            name="region_note_status_div",
            visible=False,
            styles={"font-size": "11px", "color": "#64748b", "margin-top": "-4px"},
        )

        self.frequency_copy_button = Button(
            label="Copy Spectrum Values",
            width=panel_width,
            name="region_frequency_copy_button",
            disabled=True,
            visible=False,
        )

        self.frequency_table_div = Div(
            text="<p class='region-panel-empty'>No frequency data.</p>",
            width=panel_width,
            name="region_frequency_table_div",
            visible=False,
            styles={
                "font-size": "12px",
                "border-top": "1px solid #e2e8f0",
                "padding-top": "6px",
            },
        )

        self.metrics_div = Div(
            text="<p class='region-panel-empty'>Select a region to view metrics.</p>",
            width=panel_width,
            name="region_metrics_div",
            visible=False,
            styles={
                "font-size": "12px",
                "border-top": "1px solid #e2e8f0",
                "padding-top": "6px",
            },
        )

        self.spectrum_div = Div(
            text="",
            width=panel_width,
            name="region_spectrum_div",
            visible=False,
        )

        primary_actions = Row(
            children=[self.copy_button, self.delete_button],
            name="region_primary_actions",
            sizing_mode="stretch_width",
        )

        secondary_actions = Row(
            children=[self.add_area_button, self.merge_button],
            name="region_secondary_actions",
            sizing_mode="stretch_width",
        )

        copy_position_actions = Row(
            children=[self.copy_target_select, self.copy_to_all_positions_button],
            name="region_copy_position_actions",
            sizing_mode="stretch_width",
            spacing=8,
        )

        # Centre and Back are used together when reviewing regions, so they
        # sit side by side directly under the list.
        navigation_actions = Row(
            children=[self.center_region_button, self.back_to_previous_view_button],
            name="region_navigation_actions",
            sizing_mode="stretch_width",
        )

        # The note sits next to the list so the region and its note are visible
        # together; editing actions follow below.
        self.detail_layout = column(
            self.region_table,
            navigation_actions,
            self.note_input,
            self.note_status_div,
            self.color_picker,
            primary_actions,
            self.merge_select,
            secondary_actions,
            self.split_button,
            copy_position_actions,
            self.recalculate_region_button,
            self.metrics_div,
            self.frequency_copy_button,
            self.frequency_table_div,
            self.spectrum_div,
            name="region_panel_detail",
            sizing_mode="stretch_width",
            visible=False,
        )

        self.container = column(
            self.visibility_toggle,
            self.auto_buttons,
            self.creation_indicator_div,
            self.detail_layout,
            self.message_div,
            name="region_panel_container",
            styles={
                "border": "1px solid rgba(148, 163, 184, 0.25)",
                "padding": "12px",
                "background-color": "#ffffff",
                "border-radius": "16px",
                "box-shadow": "0 8px 20px rgba(15, 23, 42, 0.08)",
            },
            width=panel_width,
        )

        # Wire JS callbacks for user-driven events
        self._attach_callbacks()

    def _attach_callbacks(self) -> None:
        selection_callback = CustomJS(args={'source': self.region_source, 'table': self.region_table}, code="""
            if (!source || !table) {
                return;
            }
            const actions = window.NoiseSurveyApp?.actions;
            const store = window.NoiseSurveyApp?.store;
            if (!actions || typeof store?.dispatch !== 'function') {
                return;
            }
            if (table.__suppressSelectionDispatch) {
                return;
            }
            const indices = Array.isArray(source.selected?.indices) ? source.selected.indices : [];
            if (!indices.length) {
                if (typeof actions.regionClearSelection === 'function') {
                    store.dispatch(actions.regionClearSelection());
                }
                return;
            }
            const data = source.data || {};
            const ids = Array.isArray(data.id) ? data.id : [];
            const candidate = Number(ids[indices[0]]);
            if (Number.isFinite(candidate) && typeof actions.regionSelect === 'function') {
                store.dispatch(actions.regionSelect(candidate));
            }
        """)
        self.region_source.selected.js_on_change('indices', selection_callback)

        note_callback = CustomJS(args={'source': self.region_source}, code="""
            const indices = Array.isArray(source.selected?.indices) ? source.selected.indices : [];
            if (!indices.length) {
                return;
            }
            const data = source.data || {};
            const ids = Array.isArray(data.id) ? data.id : [];
            const regionId = Number(ids[indices[0]]);
            if (!Number.isFinite(regionId)) {
                return;
            }
            const store = window.NoiseSurveyApp?.store;
            const thunk = window.NoiseSurveyApp?.thunks?.saveRegionNoteIntent;
            if (typeof thunk === 'function' && typeof store?.dispatch === 'function') {
                store.dispatch(thunk(regionId, cb_obj.value ?? ''));
            }
        """)
        self.note_input.js_on_change('value', note_callback)

        # Fires on every keystroke so the label can show "unsaved" until the
        # note is committed (on blur, Esc or Ctrl+Enter).
        note_draft_callback = CustomJS(args={'source': self.region_source}, code="""
            const indices = Array.isArray(source.selected?.indices) ? source.selected.indices : [];
            if (!indices.length) {
                return;
            }
            const ids = Array.isArray(source.data?.id) ? source.data.id : [];
            const regionId = Number(ids[indices[0]]);
            const store = window.NoiseSurveyApp?.store;
            const thunk = window.NoiseSurveyApp?.thunks?.updateRegionNoteDraftIntent;
            if (Number.isFinite(regionId) && typeof thunk === 'function' && typeof store?.dispatch === 'function') {
                store.dispatch(thunk(regionId, cb_obj.value_input ?? ''));
            }
        """)
        self.note_input.js_on_change('value_input', note_draft_callback)

        color_callback = CustomJS(args={'source': self.region_source}, code="""
            const indices = Array.isArray(source.selected?.indices) ? source.selected.indices : [];
            if (!indices.length) {
                return;
            }
            const data = source.data || {};
            const ids = Array.isArray(data.id) ? data.id : [];
            const regionId = Number(ids[indices[0]]);
            if (!Number.isFinite(regionId)) {
                return;
            }
            const actions = window.NoiseSurveyApp?.actions;
            const store = window.NoiseSurveyApp?.store;
            const colorValue = typeof cb_obj.color === 'string' ? cb_obj.color : '';
            if (actions?.regionSetColor && typeof store?.dispatch === 'function') {
                store.dispatch(actions.regionSetColor(regionId, colorValue));
            }
        """)
        self.color_picker.js_on_change('color', color_callback)

        delete_callback = CustomJS(args={'source': self.region_source}, code="""
            const indices = Array.isArray(source.selected?.indices) ? source.selected.indices : [];
            if (!indices.length) {
                return;
            }
            const data = source.data || {};
            const ids = Array.isArray(data.id) ? data.id : [];
            const regionId = Number(ids[indices[0]]);
            if (!Number.isFinite(regionId)) {
                return;
            }
            const actions = window.NoiseSurveyApp?.actions;
            const store = window.NoiseSurveyApp?.store;
            if (actions?.regionRemove && typeof store?.dispatch === 'function') {
                store.dispatch(actions.regionRemove(regionId));
                const utils = window.NoiseSurveyApp?.features?.regions?.utils;
                if (utils?.invalidateRegionMetrics) {
                    utils.invalidateRegionMetrics(regionId);
                }
            }
        """)
        self.delete_button.js_on_event('button_click', delete_callback)

        copy_callback = CustomJS(args={'source': self.region_source}, code="""
            const indices = Array.isArray(source.selected?.indices) ? source.selected.indices : [];
            if (!indices.length) {
                return;
            }
            const data = source.data || {};
            const ids = Array.isArray(data.id) ? data.id : [];
            const regionId = Number(ids[indices[0]]);
            if (!Number.isFinite(regionId)) {
                return;
            }
            const store = window.NoiseSurveyApp?.store;
            const utils = window.NoiseSurveyApp?.features?.regions?.utils;
            if (!utils?.formatRegionSummary || typeof store?.getState !== 'function') {
                return;
            }
            const state = store.getState();
            const region = state?.regions?.byId?.[regionId];
            if (!region) {
                return;
            }
            const models = window.NoiseSurveyApp?.registry?.models;
            const metrics = utils?.getRegionMetrics
                ? utils.getRegionMetrics(region, state, window.NoiseSurveyApp?.dataCache, models)
                : null;
            const text = utils.formatRegionSummary(region, metrics, region.positionId);
            if (navigator?.clipboard?.writeText) {
                navigator.clipboard.writeText(text).catch(err => {
                    console.error('[Regions] Failed to copy summary:', err);
                });
            } else {
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
                    console.error('[Regions] execCommand copy failed:', err);
                }
                document.body.removeChild(temp);
            }
        """)
        self.copy_button.js_on_event('button_click', copy_callback)

        spectrum_copy_callback = CustomJS(args={'source': self.region_source}, code="""
            const indices = Array.isArray(source.selected?.indices) ? source.selected.indices : [];
            if (!indices.length) {
                return;
            }
            const data = source.data || {};
            const ids = Array.isArray(data.id) ? data.id : [];
            const regionId = Number(ids[indices[0]]);
            if (!Number.isFinite(regionId)) {
                return;
            }
            const store = window.NoiseSurveyApp?.store;
            const utils = window.NoiseSurveyApp?.features?.regions?.utils;
            if (!utils?.formatSpectrumClipboardText || typeof store?.getState !== 'function') {
                return;
            }
            const state = store.getState();
            const region = state?.regions?.byId?.[regionId];
            const models = window.NoiseSurveyApp?.registry?.models;
            const metrics = utils?.getRegionMetrics
                ? utils.getRegionMetrics(region, state, window.NoiseSurveyApp?.dataCache, models)
                : null;
            const spectrum = metrics?.spectrum;
            const text = utils.formatSpectrumClipboardText(spectrum);
            if (!text) {
                return;
            }
            if (navigator?.clipboard?.writeText) {
                navigator.clipboard.writeText(text).catch(err => {
                    console.error('[Regions] Failed to copy spectrum values:', err);
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
                console.error('[Regions] execCommand copy failed:', err);
            }
            document.body.removeChild(temp);
        """)
        self.frequency_copy_button.js_on_event('button_click', spectrum_copy_callback)

        add_area_callback = CustomJS(args={'source': self.region_source}, code="""
            const indices = Array.isArray(source.selected?.indices) ? source.selected.indices : [];
            if (!indices.length) {
                return;
            }
            const data = source.data || {};
            const ids = Array.isArray(data.id) ? data.id : [];
            const regionId = Number(ids[indices[0]]);
            if (!Number.isFinite(regionId)) {
                return;
            }
            const actions = window.NoiseSurveyApp?.actions;
            const store = window.NoiseSurveyApp?.store;
            if (!actions?.regionSetAddAreaMode || typeof store?.dispatch !== 'function' || typeof store?.getState !== 'function') {
                return;
            }
            const current = store.getState();
            const currentTarget = current?.regions?.addAreaTargetId ?? null;
            const nextTarget = currentTarget === regionId ? null : regionId;
            store.dispatch(actions.regionSetAddAreaMode(nextTarget));
        """)
        self.add_area_button.js_on_event('button_click', add_area_callback)

        merge_callback = CustomJS(args={'source': self.region_source, 'mergeSelect': self.merge_select, 'table': self.region_table}, code="""
            const actions = window.NoiseSurveyApp?.actions;
            const store = window.NoiseSurveyApp?.store;
            if (!actions || typeof store?.dispatch !== 'function' || typeof store?.getState !== 'function') {
                return;
            }
            const dispatch = store.dispatch.bind(store);
            const getState = store.getState.bind(store);

            const state = getState();
            const regionsState = state?.regions || {};
            const isMergeModeActive = !!regionsState.isMergeModeActive;

            const indices = Array.isArray(source.selected?.indices) ? source.selected.indices : [];
            if (!indices.length) {
                if (isMergeModeActive && typeof actions.regionSetMergeMode === 'function') {
                    dispatch(actions.regionSetMergeMode(false));
                }
                return;
            }
            const data = source.data || {};
            const ids = Array.isArray(data.id) ? data.id : [];
            const selectedId = Number(ids[indices[0]]);
            if (!Number.isFinite(selectedId)) {
                if (isMergeModeActive && typeof actions.regionSetMergeMode === 'function') {
                    dispatch(actions.regionSetMergeMode(false));
                }
                return;
            }

            const hasOtherRegions = Array.isArray(regionsState.allIds) && regionsState.allIds.length > 1;
            if (!hasOtherRegions) {
                if (isMergeModeActive && typeof actions.regionSetMergeMode === 'function') {
                    dispatch(actions.regionSetMergeMode(false));
                }
                return;
            }

            if (!isMergeModeActive) {
                if (typeof actions.regionSetMergeMode === 'function') {
                    dispatch(actions.regionSetMergeMode(true));
                }
                return;
            }

            const sourceId = Number(mergeSelect.value);
            if (!Number.isFinite(sourceId) || sourceId === selectedId) {
                return;
            }

            if (typeof actions.regionSelect === 'function') {
                const currentSelectedId = regionsState.selectedId ?? null;
                if (currentSelectedId !== selectedId) {
                    dispatch(actions.regionSelect(selectedId));
                }
            }

            const thunks = window.NoiseSurveyApp?.thunks;
            const mergeThunk = thunks?.mergeRegionIntoSelectedIntent;
            if (typeof mergeThunk === 'function') {
                dispatch(mergeThunk(sourceId));
            }

            if (typeof actions.regionSetMergeMode === 'function') {
                dispatch(actions.regionSetMergeMode(false));
            }
        """)
        self.merge_button.js_on_event('button_click', merge_callback)

        split_callback = CustomJS(args={'source': self.region_source}, code="""
            const store = window.NoiseSurveyApp?.store;
            const thunks = window.NoiseSurveyApp?.thunks;
            if (typeof store?.dispatch !== 'function' || typeof store?.getState !== 'function' || typeof thunks?.splitSelectedRegionIntent !== 'function') {
                return;
            }
            const indices = Array.isArray(source.selected?.indices) ? source.selected.indices : [];
            if (!indices.length) {
                return;
            }
            const state = store.getState();
            const regionsState = state?.regions || {};
            const selectedId = regionsState.selectedId;
            const selectedRegion = Number.isFinite(selectedId) ? regionsState.byId?.[selectedId] : null;
            const areas = Array.isArray(selectedRegion?.areas) ? selectedRegion.areas : [];
            if (areas.length <= 1) {
                return;
            }
            store.dispatch(thunks.splitSelectedRegionIntent());
        """)
        self.split_button.js_on_event('button_click', split_callback)

        copy_to_all_positions_callback = CustomJS(args={'targetSelect': self.copy_target_select}, code="""
            const store = window.NoiseSurveyApp?.store;
            const thunks = window.NoiseSurveyApp?.thunks;
            if (typeof store?.dispatch !== 'function') {
                return;
            }
            const target = String(targetSelect?.value || '');
            if (target === '__all__' && typeof thunks?.copyRegionToAllPositionsIntent === 'function') {
                store.dispatch(thunks.copyRegionToAllPositionsIntent());
                return;
            }
            if (target && typeof thunks?.copyRegionToPositionIntent === 'function') {
                store.dispatch(thunks.copyRegionToPositionIntent(target));
            }
        """)
        self.copy_to_all_positions_button.js_on_event('button_click', copy_to_all_positions_callback)

        center_region_callback = CustomJS(code="""
            const store = window.NoiseSurveyApp?.store;
            const thunk = window.NoiseSurveyApp?.thunks?.centerViewportOnSelectedRegionIntent;
            if (typeof store?.dispatch === 'function' && typeof thunk === 'function') {
                store.dispatch(thunk());
            }
        """)
        self.center_region_button.js_on_event('button_click', center_region_callback)

        back_to_previous_view_callback = CustomJS(code="""
            const store = window.NoiseSurveyApp?.store;
            const thunk = window.NoiseSurveyApp?.thunks?.returnToPreviousRegionViewIntent;
            if (typeof store?.dispatch === 'function' && typeof thunk === 'function') {
                store.dispatch(thunk());
            }
        """)
        self.back_to_previous_view_button.js_on_event('button_click', back_to_previous_view_callback)

        recalculate_region_callback = CustomJS(code="""
            const store = window.NoiseSurveyApp?.store;
            const thunk = window.NoiseSurveyApp?.thunks?.recalculateSelectedRegionIntent;
            if (typeof store?.dispatch === 'function' && typeof thunk === 'function') {
                store.dispatch(thunk());
            }
        """)
        self.recalculate_region_button.js_on_event('button_click', recalculate_region_callback)

        visibility_callback = CustomJS(code="""
            const actions = window.NoiseSurveyApp?.actions;
            const store = window.NoiseSurveyApp?.store;
            if (!actions?.regionVisibilitySet || typeof store?.dispatch !== 'function') {
                return;
            }
            const isVisible = !!cb_obj.active;
            store.dispatch(actions.regionVisibilitySet({ showPanel: isVisible, showOverlays: isVisible }));
        """)
        self.visibility_toggle.js_on_change('active', visibility_callback)

        auto_daynight_callback = CustomJS(code="""
            const handlers = window.NoiseSurveyApp?.eventHandlers;
            if (typeof handlers?.handleAutoRegions !== 'function') {
                console.error('NoiseSurveyApp.eventHandlers.handleAutoRegions not found.');
                return;
            }
            handlers.handleAutoRegions();
        """)
        self.auto_daynight_button.js_on_event('button_click', auto_daynight_callback)

    def layout(self):
        return self.container
