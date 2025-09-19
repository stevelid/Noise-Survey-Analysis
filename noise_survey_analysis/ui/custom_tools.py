# in custom_tools.py
from bokeh.models import BoxSelectTool

class CustomPanBoxTool(BoxSelectTool):
    """ A custom tool that pans by default and box-selects when Shift is held. """
    __implementation__ = "custom_pan_box_tool.js" # Will point to your TS/JS file