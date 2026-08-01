import logging
import os

import numpy as np
import pandas as pd
from bokeh.models import Div

logger = logging.getLogger(__name__)


def to_bokeh_ms(values) -> np.ndarray:
    """
    Convert datetimes to Bokeh datetime milliseconds, independent of numpy unit.

    Streaming calls this on every pan, so it takes a fast path when the input is
    already datetime64. `pd.to_datetime` would still be correct there, but it runs a
    `should_cache` heuristic that iterates the values element by element to decide
    whether a lookup table would pay off - which dominated the streaming profile.

    Args:
        values: Anything datetime-like: a Series, Index, ndarray or sequence.

    Returns:
        np.ndarray of int64 milliseconds since the epoch, UTC.
    """
    values = getattr(values, 'array', values) if isinstance(values, pd.Series) else values
    dtype = getattr(values, 'dtype', None)

    # Fast path: already datetime64, so reinterpret rather than re-parse. Both tz-aware
    # and naive values are stored as UTC-relative integers, so one cast covers each.
    if dtype is not None and (
        isinstance(dtype, pd.DatetimeTZDtype) or np.issubdtype(getattr(dtype, 'type', dtype), np.datetime64)
    ):
        as_index = pd.DatetimeIndex(values)
    else:
        # Slow path: strings, objects, mixed offsets - let pandas parse.
        as_index = pd.DatetimeIndex(pd.to_datetime(values, utc=True))

    if as_index.tz is not None:
        as_index = as_index.tz_convert('UTC').tz_localize(None)
    # Floor-divide rather than cast to datetime64[ms]: numpy's cast and Python's // round
    # differently below the epoch, and this keeps the original arithmetic exactly.
    return as_index.values.astype('datetime64[ns]').astype('int64') // 10**6

def add_error_to_doc(doc, message, error=None, height=50):
    """
    Adds a standardized error message to the document.
    
    This function provides a consistent way to display errors in the Bokeh application,
    with proper logging and error handling even if adding to the document fails.
    
    Args:
        doc: The Bokeh document to add the error to
        message (str): The main error message to display
        error (Exception, optional): The exception that caused the error. If provided, will be included in logs.
        height (int, optional): Height of the error div in pixels. Defaults to 50.
        
    Returns:
        bool: True if the error was successfully added to the document, False otherwise
    """
    # Log the error
    if error:
        logger.error(f"{message} Details: {error}", exc_info=True)
    else:
        logger.error(message)
    
    # Create the error div
    error_text = f"<h3 style='color:red;'>Error: {message}</h3>"
    if error:
        # Add error details for user if appropriate
        error_str = str(error).replace("<", "&lt;").replace(">", "&gt;")  # Escape HTML entities
        error_text += f"<p>Details: {error_str}</p>"
    
    error_div = Div(text=error_text, height=height, width=800)
    
    # Try to add the error to the document
    try:
        doc.add_root(error_div)
        return True
    except Exception as add_error:
        logger.error(f"Failed to add error message to document: {add_error}", exc_info=True)
        return False 

def find_lowest_common_folder(paths: list[str]) -> str | None:
    """Finds the lowest common directory from a list of file paths."""
    if not paths:
        return None
    try:
        # os.path.commonpath works well, but requires paths to be absolute strings
        common_path = os.path.commonpath([str(p) for p in paths])
        # If the common path is a file itself, get its parent directory
        if os.path.isfile(common_path):
            return os.path.dirname(common_path)
        return common_path
    except ValueError:
        # This can happen if paths are on different drives (e.g., C: and D:)
        logger.warning("Could not find a common path (paths might be on different drives).")
        return None