# Placeholder for UI control creation functions
# (e.g., playback buttons, parameter selectors)
import logging
from bokeh.models import Button, Select, Div, CustomJS, RadioButtonGroup # Import CustomJS model

logger = logging.getLogger(__name__)

def create_global_audio_controls(audio_handler_available: bool) -> dict:
    """
    Creates the playback control widgets (Play, Pause buttons).
    Returns a dictionary containing the button models.
    """
    logger.debug("Creating playback control widgets...")

    # Play button: Enabled only if audio handler is available, disabled when playing.
    play_button = Button(
        label="► Play",
        visible=False # No longer used
    )

    # Pause button: Enabled only when playing. Initially disabled.
    pause_button = Button(
        label="❚❚ Pause",
        visible=False # No longer used
    )

    speed_control = RadioButtonGroup(
        labels=["1x", "1.25x", "1.5x", "2x", "4x"],
        active=0,
        width=200
    )

    amp_control = RadioButtonGroup(
        labels=["0dB", "+20dB", "+40dB"],
        active=0,
        width=200
    )

    controls = {
        'play_button': play_button,
        'pause_button': pause_button,
        'speed_control': speed_control,
        'amp_control': amp_control
    }

    if not audio_handler_available:
        logger.warning("Audio handler not available, playback controls will be disabled.")
        speed_control.disabled = True
        amp_control.disabled = True
    else:
        logger.info("Global audio control widgets created.")

    return controls

def create_parameter_selector(params: list[str], default_param: str | None) -> tuple[Select, Div] | tuple[None, None]:
    """
    Creates the parameter selection dropdown and a hidden Div to store the selection.

    Args:
        params (list[str]): List of spectral parameter names (e.g., ['LZeq', 'LAeq']).
        default_param (str | None): The parameter to select initially.

    Returns:
        tuple: (Select widget, Div widget) if params exist, otherwise (None, None).
    """
    if not params:
        logger.warning("Cannot create parameter selector: No spectral parameters provided.")
        return None, None

    # Validate default_param or choose the first available one
    if default_param not in params:
        selected_value = params[0]
        logger.warning(f"Default parameter '{default_param}' not in available list {params}. Using '{selected_value}' instead.")
    else:
        selected_value = default_param

    logger.debug(f"Creating parameter selector. Params: {params}, Selected: {selected_value}")

    param_select = Select(
        title="Spectral Parameter:", # Changed title slightly
        value=selected_value,
        options=params,
        width=150, # Adjusted width
        height=50, # Standard height might be better
        name="param_select"
    )

    # Hidden Div to store the currently selected parameter, accessible by JS/Python callbacks.
    # Its 'text' property holds the value.
    param_holder = Div(
        text=selected_value, # Initialize with the selected value
        visible=False, # Hide this Div from the user
        name="param_holder" # Name for easier selection/debugging
    )

    # JS callback is handled in the app_callbacks.py file.
    
    return param_select, param_holder

def create_position_play_button(position: str, audio_handler_available: bool) -> Button:
    """
    Creates a play button for a specific position.
    
    Args:
        position (str): The position identifier (e.g., 'SW', 'SE')
        audio_handler_available (bool): Whether audio playback is available
        
    Returns:
        Button: The Bokeh Button widget
    """
    logger.debug(f"Creating position play button for {position}")
    
    play_button = Button(
        label="► Play",
        width=60,  # Smaller than main play button
        height=25, # Smaller height for position headers
        button_type="success" if audio_handler_available else "default",
        disabled=not audio_handler_available,
        name=f"position_{position}_play_button",
        css_classes=["position-play-button"]
    )
    
    # Store the position identifier in the button's tags list
    play_button.tags = [position]
    
    return play_button

