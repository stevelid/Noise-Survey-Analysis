"""Side panel components extracted without changing Bokeh wiring."""

from bokeh.models import CustomJS, TabPanel, Tabs
from typing import Optional

from .shared import SIDE_PANEL_WIDTH

from .regions_panel import RegionPanelComponent
from .markers_panel import MarkerPanelComponent
from .classifications_panel import ClassificationPanelComponent


class SidePanelComponent:
    """Container that organises region, marker, and classifier panels into tabs."""

    def __init__(
        self,
        region_panel: RegionPanelComponent,
        marker_panel: MarkerPanelComponent,
        classification_panel: Optional[ClassificationPanelComponent] = None,
    ) -> None:
        self.region_panel = region_panel
        self.marker_panel = marker_panel
        self.classification_panel = classification_panel

        self.region_tab = TabPanel(
            child=self.region_panel.layout(),
            title="Regions",
            name="regions_tab_panel",
        )
        self.marker_tab = TabPanel(
            child=self.marker_panel.layout(),
            title="Markers",
            name="markers_tab_panel",
        )
        self.classification_tab = None
        tabs = [self.region_tab, self.marker_tab]
        if self.classification_panel is not None:
            self.classification_tab = TabPanel(
                child=self.classification_panel.layout(),
                title="Classifications",
                name="classifications_tab_panel",
            )
            tabs.append(self.classification_tab)

        self.tabs = Tabs(
            tabs=tabs,
            name="side_panel_tabs",
            width=SIDE_PANEL_WIDTH + 32,
        )

        # Keep the store in sync with user tab clicks; without this the next
        # render pass forces the tabs back to state.view.activeSidePanelTab.
        self.tabs.js_on_change("active", CustomJS(code="""
            const app = window.NoiseSurveyApp;
            if (app?.store?.dispatch && app?.actions?.setActiveSidePanelTab) {
                const current = app.store.getState()?.view?.activeSidePanelTab;
                if (current !== cb_obj.active) {
                    app.store.dispatch(app.actions.setActiveSidePanelTab(cb_obj.active));
                }
            } else {
                console.error('NoiseSurveyApp.actions.setActiveSidePanelTab not available!');
            }
        """))

    def layout(self):
        return self.tabs
