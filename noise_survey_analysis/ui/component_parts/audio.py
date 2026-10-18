"""Audio components extracted without changing Bokeh wiring."""

from bokeh.models import (
    Button,
    CustomJS,
    Div,
    Spinner,
    Toggle,
)
from bokeh.layouts import Row

from .shared import logger


def create_audio_controls_for_position(position_id: str) -> dict:
    """
    Creates a dictionary of Bokeh widgets for controlling audio playback for a single position.

    Args:
        position_id (str): The identifier for the measurement position (e.g., 'SW', 'N').

    Returns:
        dict: A dictionary containing the Bokeh widgets ('play_toggle', 'playback_rate_button', 
              'volume_boost_button') and their containing 'layout'.
    """
    # Play/Pause Toggle Button
    play_toggle = Toggle(
        label="Play", 
        button_type="success", 
        width=80,
        height=25,
        name=f"play_toggle_{position_id}"
    )

    play_toggle_callback = CustomJS(
        args=dict(position_id=position_id, button=play_toggle),
        code="""
            if (window.NoiseSurveyApp && window.NoiseSurveyApp.eventHandlers && window.NoiseSurveyApp.eventHandlers.togglePlayPause) {
                // Call the togglePlayPause handler with the new toggle state so the thunk can validate the intent
                window.NoiseSurveyApp.eventHandlers.togglePlayPause({ positionId: position_id, isActive: button.active });
            } else {
                console.error('NoiseSurveyApp.eventHandlers.togglePlayPause function not found!');
            }
        """
    )
    play_toggle.js_on_change('active', play_toggle_callback)

    # Playback Rate Button
    playback_rate_button = Button(
        label="1.0x",
        width=60,
        height=25,
        name=f"playback_rate_{position_id}"
    )
    playback_rate_button.js_on_click(CustomJS(
        args=dict(position_id=position_id),
        code="""
            if (window.NoiseSurveyApp && window.NoiseSurveyApp.eventHandlers && window.NoiseSurveyApp.eventHandlers.handlePlaybackRateChange) {
                window.NoiseSurveyApp.eventHandlers.handlePlaybackRateChange({ positionId: position_id });
            } else {
                console.error('NoiseSurveyApp.eventHandlers.handlePlaybackRateChange function not found!');
            }
        """
    ))

    # Volume Boost Toggle Button
    volume_boost_button = Toggle(
        label="Boost",
        width=70,
        height=25,
        name=f"volume_boost_{position_id}",
        active=False # Default to off
    )
    volume_boost_button.js_on_change('active', CustomJS(
        args=dict(position_id=position_id, button=volume_boost_button),
        code="""
            if (window.NoiseSurveyApp && window.NoiseSurveyApp.eventHandlers && window.NoiseSurveyApp.eventHandlers.handleVolumeBoostToggle) {
                window.NoiseSurveyApp.eventHandlers.handleVolumeBoostToggle({ positionId: position_id, isBoostActive: button.active });
            } else {
                console.error('NoiseSurveyApp.eventHandlers.handleVolumeBoostToggle function not found!');
            }
        """
    ))

    # Layout for the controls
    chart_offset_label = Div(
        text="Chart Offset (s)",
        width=80,
        height=25,
        styles={"font-size": "9px", "display": "flex", "align-items": "center"},
        name=f"chart_offset_label_{position_id}"
    )
    chart_offset_spinner = Spinner(
        width=60,
        height=25,
        low=-6000,
        high=6000,
        step=0.1,
        value=0.0,
        format="0.0",
        name=f"chart_offset_spinner_{position_id}"
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
        text="Audio Offset (s)",
        width=80,
        height=25,
        styles={"font-size": "9px", "display": "flex", "align-items": "center"},
        name=f"audio_offset_label_{position_id}"
    )
    audio_offset_spinner = Spinner(
        width=60,
        height=25,
        low=-6000,
        high=6000,
        step=0.1,
        value=0.0,
        format="0.0",
        name=f"audio_offset_spinner_{position_id}"
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

    effective_offset_display = Div(
        text="Effective: +0.00 s",
        width=120,
        height=25,
        name=f"effective_offset_display_{position_id}",
        styles={"font-size": "9px", "display": "flex", "align-items": "center"}
    )

    controls_layout = Row(
        play_toggle,
        playback_rate_button,
        volume_boost_button,
        chart_offset_label,
        chart_offset_spinner,
        audio_offset_label,
        audio_offset_spinner,
        effective_offset_display,
        name=f"audio_controls_{position_id}"
    )

    logger.debug(f"Audio controls created for position '{position_id}'.")
    return {
        "play_toggle": play_toggle,
        "playback_rate_button": playback_rate_button,
        "volume_boost_button": volume_boost_button,
        "chart_offset_spinner": chart_offset_spinner,
        "audio_offset_spinner": audio_offset_spinner,
        "effective_offset_display": effective_offset_display,
        "layout": controls_layout
    }


def create_position_title_and_offsets(
    position_id: str,
    display_title: str = None,
    chart_offset_seconds: float = 0.0,
    audio_offset_seconds: float = 0.0,
) -> dict:
    """
    Creates position title display and offset controls (without playback buttons).
    This is used for all positions to show title and allow offset adjustments.
    
    Args:
        position_id (str): The identifier for the measurement position (e.g., 'SW', 'N').
        display_title (str): Optional custom display title. If None, uses position_id.
        chart_offset_seconds (float): Initial chart offset, normally restored from
            the job config. Set at construction rather than assigned afterwards so
            the value is part of the document the browser first receives; a later
            assignment races the JS store initialisation and gets reset to zero.
        audio_offset_seconds (float): Initial audio offset, same reasoning.
    
    Returns:
        dict: A dictionary containing the Bokeh widgets and their containing 'layout'.
    """
    if display_title is None:
        display_title = position_id
    
    # Position title display
    title_div = Div(
        text=f"<strong style='font-size: 13px; color: #0f172a; white-space: nowrap;'>{display_title}</strong>",
        width=220,
        height=35,
        name=f"position_title_{position_id}",
        styles={"display": "flex", "align-items": "center", "justify-content": "flex-start", "flex-shrink": "0"}
    )

    # Chart Offset controls
    chart_offset_label = Div(
        text="<span style='font-size: 10px; color: #64748b;'>Chart Offset (s):</span>",
        width=85,
        height=35,
        styles={"display": "flex", "align-items": "center", "padding-left": "8px"},
        name=f"chart_offset_label_{position_id}"
    )
    chart_offset_spinner = Spinner(
        width=55,
        height=28,
        low=-6000,
        high=6000,
        step=0.1,
        value=float(chart_offset_seconds or 0.0),
        format="0.0",
        name=f"chart_offset_spinner_{position_id}"
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

    # Audio Offset controls
    audio_offset_label = Div(
        text="<span style='font-size: 10px; color: #64748b;'>Audio Offset (s):</span>",
        width=85,
        height=35,
        styles={"display": "flex", "align-items": "center", "padding-left": "8px"},
        name=f"audio_offset_label_{position_id}"
    )
    audio_offset_spinner = Spinner(
        width=55,
        height=28,
        low=-6000,
        high=6000,
        step=0.1,
        value=float(audio_offset_seconds or 0.0),
        format="0.0",
        name=f"audio_offset_spinner_{position_id}"
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

    # Effective offset display (text is overwritten by JS; styles here control its appearance)
    effective_offset_display = Div(
        text="Effective offset: +0.00 s",
        width=135,
        height=35,
        name=f"effective_offset_display_{position_id}",
        styles={
            "display": "flex",
            "align-items": "center",
            "padding-left": "8px",
            "white-space": "nowrap",
            "font-size": "10px",
            "color": "#64748b"
        }
    )

    controls_layout = Row(
        title_div,
        chart_offset_label,
        chart_offset_spinner,
        audio_offset_label,
        audio_offset_spinner,
        effective_offset_display,
        name=f"position_controls_{position_id}",
        styles={
            "gap": "6px",
            "background-color": "#f1f5f9",
            "border-top": "1px solid #e2e8f0",
            "border-bottom": "1px solid #e2e8f0",
            "padding": "4px 12px",
            "align-items": "center",
            "justify-content": "space-between",
            "flex-wrap": "wrap",
            "row-gap": "4px",
            "min-height": "38px"
        }
    )

    logger.debug(f"Position title and offset controls created for '{position_id}'.")
    return {
        "title_div": title_div,
        "display_title_div": title_div,
        "chart_offset_label": chart_offset_label,
        "chart_offset_spinner": chart_offset_spinner,
        "audio_offset_label": audio_offset_label,
        "audio_offset_spinner": audio_offset_spinner,
        "effective_offset_display": effective_offset_display,
        "layout": controls_layout
    }
