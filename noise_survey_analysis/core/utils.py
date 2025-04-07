import logging
from bokeh.models import Div

logger = logging.getLogger(__name__)

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