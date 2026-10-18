"""Classifications panel components extracted without changing Bokeh wiring."""

from bokeh.models import (
    Button,
    CheckboxGroup,
    ColumnDataSource,
    CustomJS,
    DataTable,
    Div,
    HTMLTemplateFormatter,
    NumberFormatter,
    Slider,
    TableColumn,
    Toggle,
)
from bokeh.layouts import Row, column

from .shared import SIDE_PANEL_WIDTH


class ClassificationPanelComponent:
    """Bokeh widget panel for imported audio classifier intervals."""

    def __init__(self) -> None:
        panel_width = SIDE_PANEL_WIDTH

        self.visibility_toggle = Toggle(
            label="Classifications",
            width=panel_width,
            name="classification_visibility_toggle",
            active=True,
            button_type="primary",
        )

        self.classification_source = ColumnDataSource(
            data={
                "id": [],
                "source": [],
                "position": [],
                "time_span": [],
                "confidence": [],
                "score_value": [],
                "start_ms": [],
                "start_display": [],
                "state": [],
                "color": [],
                "role": [],
            },
            name="classification_panel_source",
        )

        # Sortable columns bind to the RAW numeric fields (start_ms, score_value)
        # with display formatters, not to the pre-formatted text fields — binding
        # to text would sort lexicographically ("9%" > "80%", "09:5" > "10:0").
        # `time_span`/`confidence` are retained as hidden fields because the
        # detail panel and existing consumers still read them.
        self.classification_table = DataTable(
            source=self.classification_source,
            scroll_to_selection=True,
            sortable=True,
            columns=[
                TableColumn(field="source", title="Source", width=int(panel_width * 0.40), sortable=True),
                # Bound to the numeric `start_ms` so sorting is chronological,
                # but rendered from the sibling `start_display` string. Bokeh's
                # DateFormatter renders UTC, which would disagree with the
                # browser-local times shown in the detail panel below (an hour
                # out during BST); HTMLTemplateFormatter lets the column sort on
                # the number while displaying the already-localised text.
                TableColumn(
                    field="start_ms",
                    title="Start",
                    width=int(panel_width * 0.30),
                    sortable=True,
                    formatter=HTMLTemplateFormatter(template="<%= start_display %>"),
                ),
                TableColumn(
                    field="score_value",
                    title="Score",
                    width=int(panel_width * 0.18),
                    sortable=True,
                    formatter=NumberFormatter(format="0.00"),
                ),
                TableColumn(field="start_display", title="StartText", visible=False),
                TableColumn(field="position", title="Pos", visible=False),
                TableColumn(field="time_span", title="TimeSpan", visible=False),
                TableColumn(field="confidence", title="ScoreText", visible=False),
                TableColumn(field="state", title="State", visible=False),
                TableColumn(field="color", title="Color", visible=False),
                TableColumn(field="role", title="Role", visible=False),
                TableColumn(field="id", title="ID", visible=False),
            ],
            width=panel_width,
            height=240,
            index_position=None,
            header_row=True,
            row_height=42,
            name="classification_panel_table",
            selectable=True,
            editable=False,
            reorderable=False,
            autosize_mode="none",
            sizing_mode="stretch_width",
            css_classes=["classification-panel-table"],
        )
        self.classification_table.stylesheets = [
            """
            .classification-panel-table .bk-data-table {
                border: none;
                background: transparent;
                font-family: 'Segoe UI', sans-serif;
            }
            .classification-panel-table .slick-header-columns {
                background: rgba(148, 163, 184, 0.1);
                border-bottom: 1px solid rgba(148, 163, 184, 0.4);
            }
            .classification-panel-table .slick-header-column {
                font-weight: 600;
                color: #1f2937;
            }
            .classification-panel-table .slick-row {
                border: none !important;
                margin: 4px 4px;
                border-radius: 8px;
                background: rgba(255, 255, 255, 0.9);
                box-shadow: 0 1px 3px rgba(15, 23, 42, 0.08);
            }
            .classification-panel-table .slick-row:hover {
                background: rgba(46, 134, 171, 0.12) !important;
            }
            .classification-panel-table .slick-row.active,
            .classification-panel-table .slick-row.selected {
                background: #2e86ab !important;
            }
            .classification-panel-table .slick-row .slick-cell {
                border: none !important;
                background: transparent !important;
                color: #1f2937;
                font-size: 12px;
            }
            .classification-panel-table .slick-row.selected .slick-cell {
                color: #ffffff;
            }
            .classification-panel-table .bk-cell-index {
                display: none;
            }
            """
        ]

        self.message_div = Div(
            text="<p class='classification-panel-empty'>No classifications imported.</p>",
            width=panel_width,
            name="classification_panel_message_div",
            styles={"font-size": "12px", "line-height": "1.45"},
        )

        self.detail_div = Div(
            text="<p class='classification-panel-empty'>Select a classification to view details.</p>",
            width=panel_width,
            name="classification_panel_detail_div",
            styles={
                "font-size": "12px",
                "border-top": "1px solid #e2e8f0",
                "padding-top": "6px",
            },
        )

        button_width = int(panel_width / 2) - 6
        self.import_button = Button(
            label="Import",
            width=button_width,
            name="classification_import_button",
            button_type="default",
        )
        self.export_button = Button(
            label="Export",
            width=button_width,
            name="classification_export_button",
            button_type="default",
        )
        self.elevate_button = Button(
            label="Elevate to Region",
            width=button_width,
            name="classification_elevate_button",
            button_type="success",
            disabled=True,
        )
        self.delete_button = Button(
            label="Delete",
            width=button_width,
            name="classification_delete_button",
            button_type="danger",
            disabled=True,
        )

        self.preview_button = Button(
            label="Preview (P)",
            width=button_width,
            name="classification_preview_button",
            button_type="primary",
            disabled=True,
        )

        # --- Filter controls (Phase 4) ---
        # Score is the raw model output, not a calibrated probability, so the
        # control is deliberately labelled "Minimum score" rather than
        # "confidence".
        self.minimum_score_slider = Slider(
            start=0.0,
            end=1.0,
            value=0.0,
            step=0.01,
            title="Minimum score",
            width=panel_width,
            name="classification_minimum_score_slider",
        )

        self.showing_count_div = Div(
            text="",
            width=panel_width,
            name="classification_showing_count_div",
            styles={"font-size": "11px", "color": "#475569", "padding": "2px 0"},
        )

        # Compact collapsible source list — kept collapsed by default so the
        # narrow side panel does not fill with checkboxes.
        self.source_filter_toggle = Toggle(
            label="Sources",
            width=panel_width,
            active=False,
            name="classification_source_filter_toggle",
            button_type="default",
        )
        self.source_checkbox_group = CheckboxGroup(
            labels=[],
            active=[],
            width=panel_width,
            name="classification_source_checkbox_group",
        )
        self.source_all_button = Button(
            label="All",
            width=int(panel_width / 2) - 6,
            name="classification_source_all_button",
            button_type="default",
        )
        self.source_none_button = Button(
            label="None",
            width=int(panel_width / 2) - 6,
            name="classification_source_none_button",
            button_type="default",
        )
        source_action_row = Row(
            children=[self.source_all_button, self.source_none_button],
            name="classification_source_action_buttons",
            sizing_mode="stretch_width",
        )
        self.source_filter_layout = column(
            self.source_checkbox_group,
            source_action_row,
            name="classification_source_filter_layout",
            sizing_mode="stretch_width",
            visible=False,
        )

        # Direct/supporting role filter. Hidden entirely unless the imported
        # set actually contains supporting events (renderer controls this).
        self.role_checkbox_group = CheckboxGroup(
            labels=["Direct", "Supporting"],
            active=[0],
            width=panel_width,
            name="classification_role_checkbox_group",
        )
        self.role_filter_layout = column(
            self.role_checkbox_group,
            name="classification_role_filter_layout",
            sizing_mode="stretch_width",
            visible=False,
        )

        self.filter_layout = column(
            self.minimum_score_slider,
            self.source_filter_toggle,
            self.source_filter_layout,
            self.role_filter_layout,
            self.showing_count_div,
            name="classification_filter_layout",
            sizing_mode="stretch_width",
            visible=False,
        )

        import_export_row = Row(
            children=[self.import_button, self.export_button],
            name="classification_import_export_buttons",
            sizing_mode="stretch_width",
        )
        action_row = Row(
            children=[self.elevate_button, self.delete_button],
            name="classification_action_buttons",
            sizing_mode="stretch_width",
        )
        preview_row = Row(
            children=[self.preview_button],
            name="classification_preview_row",
            sizing_mode="stretch_width",
        )

        self.detail_layout = column(
            self.classification_table,
            preview_row,
            action_row,
            self.detail_div,
            name="classification_panel_detail",
            sizing_mode="stretch_width",
            visible=False,
        )

        self.container = column(
            self.visibility_toggle,
            import_export_row,
            self.filter_layout,
            self.detail_layout,
            self.message_div,
            name="classification_panel_container",
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
        selection_callback = CustomJS(args={'source': self.classification_source, 'table': self.classification_table}, code="""
            if (!source || !table) {
                return;
            }
            const app = window.NoiseSurveyApp;
            const actions = app?.actions;
            const thunks = app?.thunks;
            const store = app?.store;
            if (!actions || typeof store?.dispatch !== 'function') {
                return;
            }
            const indices = Array.isArray(source.selected?.indices) ? source.selected.indices : [];
            const ids = Array.isArray(source.data?.id) ? source.data.id : [];
            const candidate = Number(ids[indices[0]]);

            if (table.__suppressSelectionDispatch) {
                return;
            }
            if (!indices.length || !Number.isFinite(candidate)) {
                if (typeof actions.classificationClearSelection === 'function') {
                    store.dispatch(actions.classificationClearSelection());
                }
                return;
            }
            if (typeof thunks?.selectClassificationIntent === 'function') {
                store.dispatch(thunks.selectClassificationIntent(candidate));
            } else if (typeof actions.classificationSelect === 'function') {
                store.dispatch(actions.classificationSelect(candidate));
            }
        """)
        self.classification_source.selected.js_on_change('indices', selection_callback)

        visibility_callback = CustomJS(code="""
            const actions = window.NoiseSurveyApp?.actions;
            const store = window.NoiseSurveyApp?.store;
            if (!actions?.classificationVisibilitySet || typeof store?.dispatch !== 'function') {
                return;
            }
            const isVisible = !!cb_obj.active;
            store.dispatch(actions.classificationVisibilitySet({ showPanel: isVisible, showOverlays: isVisible }));
        """)
        self.visibility_toggle.js_on_change('active', visibility_callback)

        import_callback = CustomJS(code="""
            const session = window.NoiseSurveyApp?.session;
            if (typeof session?.handleImportClassifications !== 'function') {
                console.error('[Classifications] Import handler is unavailable.');
                return;
            }
            session.handleImportClassifications();
        """)
        self.import_button.js_on_event('button_click', import_callback)

        export_callback = CustomJS(code="""
            const session = window.NoiseSurveyApp?.session;
            if (typeof session?.handleExportClassifications !== 'function') {
                console.error('[Classifications] Export handler is unavailable.');
                return;
            }
            session.handleExportClassifications();
        """)
        self.export_button.js_on_event('button_click', export_callback)

        elevate_callback = CustomJS(args={'source': self.classification_source}, code="""
            const indices = Array.isArray(source.selected?.indices) ? source.selected.indices : [];
            if (!indices.length) {
                return;
            }
            const ids = Array.isArray(source.data?.id) ? source.data.id : [];
            const classificationId = Number(ids[indices[0]]);
            const thunks = window.NoiseSurveyApp?.thunks;
            const store = window.NoiseSurveyApp?.store;
            if (Number.isFinite(classificationId) && typeof thunks?.elevateClassificationToRegionIntent === 'function'
                && typeof store?.dispatch === 'function') {
                store.dispatch(thunks.elevateClassificationToRegionIntent(classificationId));
            }
        """)
        self.elevate_button.js_on_event('button_click', elevate_callback)

        delete_callback = CustomJS(args={'source': self.classification_source}, code="""
            const indices = Array.isArray(source.selected?.indices) ? source.selected.indices : [];
            if (!indices.length) {
                return;
            }
            const ids = Array.isArray(source.data?.id) ? source.data.id : [];
            const classificationId = Number(ids[indices[0]]);
            const actions = window.NoiseSurveyApp?.actions;
            const store = window.NoiseSurveyApp?.store;
            if (Number.isFinite(classificationId) && typeof actions?.classificationRemove === 'function'
                && typeof store?.dispatch === 'function') {
                store.dispatch(actions.classificationRemove(classificationId));
            }
        """)
        self.delete_button.js_on_event('button_click', delete_callback)

        preview_callback = CustomJS(code="""
            const thunks = window.NoiseSurveyApp?.features?.classifications?.thunks;
            const store = window.NoiseSurveyApp?.store;
            if (typeof thunks?.previewSelectedClassificationIntent === 'function'
                && typeof store?.dispatch === 'function') {
                store.dispatch(thunks.previewSelectedClassificationIntent());
            }
        """)
        self.preview_button.js_on_event('button_click', preview_callback)

        # --- Filter control callbacks (Phase 4) ---
        minimum_score_callback = CustomJS(code="""
            const actions = window.NoiseSurveyApp?.actions;
            const store = window.NoiseSurveyApp?.store;
            if (typeof actions?.classificationMinimumScoreSet !== 'function'
                || typeof store?.dispatch !== 'function') {
                return;
            }
            store.dispatch(actions.classificationMinimumScoreSet(Number(cb_obj.value)));
        """)
        self.minimum_score_slider.js_on_change('value', minimum_score_callback)

        source_filter_toggle_callback = CustomJS(args={'toggle': self.source_filter_toggle}, code="""
            const actions = window.NoiseSurveyApp?.actions;
            const store = window.NoiseSurveyApp?.store;
            if (toggle.__suppressDispatch) {
                return;
            }
            if (typeof actions?.classificationSourceFilterExpandedSet === 'function'
                && typeof store?.dispatch === 'function') {
                store.dispatch(actions.classificationSourceFilterExpandedSet(!!cb_obj.active));
            }
        """)
        self.source_filter_toggle.js_on_change('active', source_filter_toggle_callback)

        # The checkbox group's `active` list is index-based; map indices back to
        # source IDs via the label order the renderer last wrote.
        source_checkbox_callback = CustomJS(args={'group': self.source_checkbox_group}, code="""
            const actions = window.NoiseSurveyApp?.actions;
            const store = window.NoiseSurveyApp?.store;
            if (typeof store?.dispatch !== 'function' || !actions) {
                return;
            }
            if (group.__suppressDispatch) {
                return;
            }
            const sourceIds = Array.isArray(group.__sourceIds) ? group.__sourceIds : [];
            const active = Array.isArray(cb_obj.active) ? cb_obj.active : [];
            sourceIds.forEach((sourceId, index) => {
                const visible = active.includes(index);
                if (typeof actions.classificationSourceVisibilitySet === 'function') {
                    store.dispatch(actions.classificationSourceVisibilitySet(sourceId, visible));
                }
            });
        """)
        self.source_checkbox_group.js_on_change('active', source_checkbox_callback)

        source_all_callback = CustomJS(code="""
            const actions = window.NoiseSurveyApp?.actions;
            const store = window.NoiseSurveyApp?.store;
            if (typeof actions?.classificationAllSourcesVisibilitySet === 'function'
                && typeof store?.dispatch === 'function') {
                store.dispatch(actions.classificationAllSourcesVisibilitySet(true));
            }
        """)
        self.source_all_button.js_on_event('button_click', source_all_callback)

        source_none_callback = CustomJS(code="""
            const actions = window.NoiseSurveyApp?.actions;
            const store = window.NoiseSurveyApp?.store;
            if (typeof actions?.classificationAllSourcesVisibilitySet === 'function'
                && typeof store?.dispatch === 'function') {
                store.dispatch(actions.classificationAllSourcesVisibilitySet(false));
            }
        """)
        self.source_none_button.js_on_event('button_click', source_none_callback)

        role_checkbox_callback = CustomJS(args={'group': self.role_checkbox_group}, code="""
            const actions = window.NoiseSurveyApp?.actions;
            const store = window.NoiseSurveyApp?.store;
            if (typeof actions?.classificationRoleVisibilitySet !== 'function'
                || typeof store?.dispatch !== 'function') {
                return;
            }
            if (group.__suppressDispatch) {
                return;
            }
            const active = Array.isArray(cb_obj.active) ? cb_obj.active : [];
            store.dispatch(actions.classificationRoleVisibilitySet({
                showDirect: active.includes(0),
                showSupporting: active.includes(1)
            }));
        """)
        self.role_checkbox_group.js_on_change('active', role_checkbox_callback)

    def layout(self):
        return self.container
