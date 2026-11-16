"""Compact per-position header strip.

One 24 px row above each position's charts: title, data status (log / overview / loading), the
effective clock-offset chip, a spectrogram read-out, and the buttons to show the offset spinners,
move the position up/down and collapse its spectrogram. The two offset spinners sit in a second row
that stays hidden until the "Offsets" button is pressed.

Model names are load-bearing: ``main.py::handle_save_setup_request`` and ``app_callbacks.py`` find
``chart_offset_spinner_{pos}`` / ``audio_offset_spinner_{pos}`` by name, and the JS renderers read the
returned dictionary through ``models.positionControls[pos]``.
"""

from typing import Optional

from bokeh.layouts import Row, column
from bokeh.models import Button, CustomJS, Div, Spinner, Toggle

from noise_survey_analysis.core.config import LAYOUT_SETTINGS

from .shared import logger

HEADER_HEIGHT = LAYOUT_SETTINGS['position_header_height']

_APP = "window.NoiseSurveyApp"


def _dispatch_js(expression: str) -> str:
    """CustomJS body that runs a thunk through the store when the app is ready."""
    return f"""
        const app = {_APP};
        if (app && app.store && app.thunks) {{
            app.store.dispatch({expression});
        }} else {{
            console.error('NoiseSurveyApp is not ready for a layout action.');
        }}
    """


def _small_button(label: str, name: str, css_class: str, width: int = 26) -> Button:
    return Button(
        label=label,
        width=width,
        height=HEADER_HEIGHT - 2,
        margin=0,
        button_type="default",
        name=name,
        css_classes=["nsa-pos-btn", css_class],
    )


def create_position_header(
    position_id: str,
    display_title: Optional[str] = None,
    chart_offset_seconds: float = 0.0,
    audio_offset_seconds: float = 0.0,
    hover_div: Optional[Div] = None,
) -> dict:
    """Builds the header widgets for one position.

    Args:
        position_id: Position identifier (``P1`` ...); used in model names and thunk calls.
        display_title: Title shown at the left; defaults to the position id.
        chart_offset_seconds: Initial chart offset. Set at construction rather than assigned later:
            a later assignment races the JS store initialisation and gets reset to zero.
        audio_offset_seconds: Initial audio offset, same reasoning.
        hover_div: The spectrogram's hover read-out, placed in the row so it costs no chart height.

    Returns:
        dict with every widget plus ``layout`` (the column holding both rows) and ``header_row``.
    """
    if display_title is None:
        display_title = position_id

    title_div = Div(
        text=f"<b>{display_title}</b>",
        height=HEADER_HEIGHT - 2,
        margin=0,
        name=f"position_title_{position_id}",
        styles={
            "font-size": "12px",
            "color": "#0f172a",
            "white-space": "nowrap",
            "line-height": f"{HEADER_HEIGHT - 2}px",
            "flex-shrink": "0",
        },
    )

    status_div = Div(
        text="",
        height=HEADER_HEIGHT - 2,
        margin=0,
        name=f"position_status_{position_id}",
        styles={
            "font-size": "10px",
            "color": "#475569",
            "white-space": "nowrap",
            "line-height": f"{HEADER_HEIGHT - 2}px",
            "flex-shrink": "0",
        },
    )

    # Text and visibility are driven by controlWidgetsRenderer.js (hidden while the offset is zero).
    effective_offset_display = Div(
        text="",
        height=HEADER_HEIGHT - 2,
        margin=0,
        visible=False,
        name=f"effective_offset_display_{position_id}",
        styles={
            "font-size": "10px",
            "color": "#92400e",
            "background-color": "#fef3c7",
            "border-radius": "999px",
            "padding": "0 7px",
            "white-space": "nowrap",
            "line-height": f"{HEADER_HEIGHT - 2}px",
            "flex-shrink": "0",
        },
    )

    chart_offset_label = Div(
        text="<span style='font-size: 10px; color: #64748b;'>Chart offset (s):</span>",
        height=26,
        margin=0,
        styles={"display": "flex", "align-items": "center", "padding-left": "8px", "white-space": "nowrap"},
        name=f"chart_offset_label_{position_id}",
    )
    chart_offset_spinner = Spinner(
        width=70,
        height=26,
        margin=0,
        low=-6000,
        high=6000,
        step=0.1,
        value=float(chart_offset_seconds or 0.0),
        format="0.0",
        name=f"chart_offset_spinner_{position_id}",
    )
    chart_offset_spinner.js_on_change('value', CustomJS(
        args=dict(position_id=position_id, spinner=chart_offset_spinner),
        code="""
            if (window.NoiseSurveyApp && window.NoiseSurveyApp.eventHandlers && window.NoiseSurveyApp.eventHandlers.handlePositionChartOffsetChange) {
                const offset = typeof spinner.value === 'number' ? spinner.value : Number(spinner.value || 0);
                window.NoiseSurveyApp.eventHandlers.handlePositionChartOffsetChange({ positionId: position_id, offsetSeconds: offset });
            } else {
                console.error('NoiseSurveyApp.eventHandlers.handlePositionChartOffsetChange function not found!');
            }
        """
    ))

    audio_offset_label = Div(
        text="<span style='font-size: 10px; color: #64748b;'>Audio offset (s):</span>",
        height=26,
        margin=0,
        styles={"display": "flex", "align-items": "center", "padding-left": "8px", "white-space": "nowrap"},
        name=f"audio_offset_label_{position_id}",
    )
    audio_offset_spinner = Spinner(
        width=70,
        height=26,
        margin=0,
        low=-6000,
        high=6000,
        step=0.1,
        value=float(audio_offset_seconds or 0.0),
        format="0.0",
        name=f"audio_offset_spinner_{position_id}",
    )
    audio_offset_spinner.js_on_change('value', CustomJS(
        args=dict(position_id=position_id, spinner=audio_offset_spinner),
        code="""
            if (window.NoiseSurveyApp && window.NoiseSurveyApp.eventHandlers && window.NoiseSurveyApp.eventHandlers.handlePositionAudioOffsetChange) {
                const offset = typeof spinner.value === 'number' ? spinner.value : Number(spinner.value || 0);
                window.NoiseSurveyApp.eventHandlers.handlePositionAudioOffsetChange({ positionId: position_id, offsetSeconds: offset });
            } else {
                console.error('NoiseSurveyApp.eventHandlers.handlePositionAudioOffsetChange function not found!');
            }
        """
    ))

    offsets_row = Row(
        chart_offset_label,
        chart_offset_spinner,
        audio_offset_label,
        audio_offset_spinner,
        name=f"position_offsets_row_{position_id}",
        visible=False,
        sizing_mode="stretch_width",
        height=32,
        margin=0,
        styles={
            "gap": "6px",
            "background-color": "#f8fafc",
            "border-bottom": "1px solid #e2e8f0",
            "padding": "3px 8px",
            "align-items": "center",
        },
    )

    offsets_toggle = Toggle(
        label="Offsets",
        width=58,
        height=HEADER_HEIGHT - 2,
        margin=0,
        active=False,
        button_type="default",
        name=f"position_offsets_toggle_{position_id}",
        css_classes=["nsa-pos-btn", "nsa-pos-offsets"],
    )
    offsets_toggle.js_on_change('active', CustomJS(
        args=dict(row=offsets_row),
        code="row.visible = cb_obj.active;",
    ))

    up_button = _small_button("▲", f"position_up_{position_id}", "nsa-pos-up")
    up_button.js_on_click(CustomJS(
        args=dict(position_id=position_id),
        code=_dispatch_js("app.thunks.movePositionIntent({ positionId: position_id, delta: -1 })"),
    ))
    down_button = _small_button("▼", f"position_down_{position_id}", "nsa-pos-down")
    down_button.js_on_click(CustomJS(
        args=dict(position_id=position_id),
        code=_dispatch_js("app.thunks.movePositionIntent({ positionId: position_id, delta: 1 })"),
    ))
    # The label (chevron) follows the spectrogram state; layoutRenderer.js keeps it in sync.
    spec_button = _small_button("Spec ▾", f"position_spec_toggle_{position_id}", "nsa-pos-spec", width=54)
    spec_button.js_on_click(CustomJS(
        args=dict(position_id=position_id),
        code=_dispatch_js("app.thunks.cycleSpectrogramModeIntent({ positionId: position_id })"),
    ))

    banner_div = Div(
        text="",
        visible=False,
        name=f"position_banner_{position_id}",
        margin=0,
        css_classes=["nsa-pos-banner"],
        styles={
            "position": "absolute",
            "top": "34px",
            "left": "50%",
            "transform": "translateX(-50%)",
            "z-index": "20",
            "pointer-events": "none",
            "background-color": "rgba(255, 247, 237, 0.96)",
            "border": "1px solid #fdba74",
            "border-radius": "6px",
            "color": "#9a3412",
            "font-size": "12px",
            "padding": "4px 12px",
            "white-space": "nowrap",
            "box-shadow": "0 2px 8px rgba(15, 23, 42, 0.15)",
        },
    )

    header_children = [title_div, status_div, effective_offset_display]
    if hover_div is not None:
        header_children.append(hover_div)
    else:
        header_children.append(Div(text="", sizing_mode="stretch_width", height=HEADER_HEIGHT - 2, margin=0))
    header_children.extend([offsets_toggle, up_button, down_button, spec_button])

    header_row = Row(
        *header_children,
        name=f"position_header_row_{position_id}",
        sizing_mode="stretch_width",
        height=HEADER_HEIGHT,
        margin=0,
        css_classes=["nsa-pos-header"],
        styles={
            "gap": "8px",
            "background-color": "#f1f5f9",
            "border-top": "1px solid #e2e8f0",
            "border-bottom": "1px solid #e2e8f0",
            "padding": "0 8px",
            "align-items": "center",
            "min-width": "0",
            "overflow": "hidden",
        },
    )

    layout = column(
        header_row,
        offsets_row,
        name=f"position_controls_{position_id}",
        sizing_mode="stretch_width",
        margin=0,
        styles={"min-width": "0"},
    )

    logger.debug(f"Position header created for '{position_id}'.")
    return {
        "title_div": title_div,
        "display_title_div": title_div,
        "status_div": status_div,
        "chart_offset_label": chart_offset_label,
        "chart_offset_spinner": chart_offset_spinner,
        "audio_offset_label": audio_offset_label,
        "audio_offset_spinner": audio_offset_spinner,
        "effective_offset_display": effective_offset_display,
        "offsets_row": offsets_row,
        "offsets_toggle": offsets_toggle,
        "up_button": up_button,
        "down_button": down_button,
        "spec_button": spec_button,
        "hover_div": hover_div,
        "banner_div": banner_div,
        "header_row": header_row,
        "layout": layout,
    }
