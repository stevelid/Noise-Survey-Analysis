import os
import sys
import subprocess
import argparse
import logging
import socket

# Force debug mode for all loggers
def configure_logging(debug=False):
    """Configure logging for the application with proper propagation."""
    level = logging.DEBUG if debug else logging.INFO
    
    # Configure root logger
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        force=True  # Override any existing configuration
    )
    
    # Make sure all relevant loggers are set to DEBUG
    if debug:
        # Root logger
        logging.getLogger().setLevel(logging.DEBUG)
        
        # Bokeh loggers
        for name in ['bokeh', 'bokeh.server', 'tornado', 'tornado.application']:
            logger = logging.getLogger(name)
            logger.setLevel(logging.DEBUG)
            logger.propagate = True
            
        # Application loggers
        app_logger = logging.getLogger('noise_survey_analysis')
        app_logger.setLevel(logging.DEBUG)
        app_logger.propagate = True
        
        # Current module logger
        logger = logging.getLogger(__name__)
        logger.setLevel(logging.DEBUG)
        logger.debug("Debug logging enabled")

# Initialize logger but we'll configure it properly later
logger = logging.getLogger(__name__)

def is_port_in_use(port):
    """Check if a port is already in use."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) == 0

def find_available_port(start_port=5006, max_attempts=10):
    """Find an available port starting from start_port."""
    port = start_port
    for _ in range(max_attempts):
        if not is_port_in_use(port):
            return port
        port += 1
    raise RuntimeError(f"Could not find an available port after {max_attempts} attempts starting from {start_port}")

def create_directory_browser_app(doc):
    """
    Create a Bokeh application that lets users browse for a directory
    and select which data files to use.
    """
    from bokeh.layouts import column
    from bokeh.models import Div
    from noise_survey_analysis.ui.data_source_selector import create_data_source_selector
    from noise_survey_analysis.main import create_app
    
    def on_data_sources_selected(data_sources):
        """
        Callback function when data sources are selected.
        This will clear the document and load the main application with the selected sources.
        """
        if not data_sources:
            # User cancelled - show a message
            doc.clear()
            message = Div(
                text="<h2>Selection cancelled.</h2><p>Reload the page to start again.</p>",
                width=800
            )
            doc.add_root(message)
            return
        
        logger.info(f"Selected {len(data_sources)} data sources. Creating visualization...")
        
        # Clear the document
        doc.clear()
        
        # Create the main application with the selected data sources
        create_app(doc, data_sources)
    
    # Create the data source selector
    create_data_source_selector(doc, on_data_sources_selected)
    
    logger.info("Directory browser application created")

def run_bokeh_server(port=5006, debug=False):
    """
    Run the Bokeh server with the Noise Survey Analysis application.
    
    Args:
        port (int): The port to run the Bokeh server on
        debug (bool): Enable debug mode for Bokeh server
    """
    # Configure logging based on debug flag
    configure_logging(debug)
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    # Target the directory containing the Bokeh app
    app_dir = os.path.join(script_dir, "noise_survey_analysis")

    # Check if the directory exists
    if not os.path.isdir(app_dir):
        logger.error(f"Application directory not found at {app_dir}")
        sys.exit(1)

    # Check if the requested port is available, if not find another
    if is_port_in_use(port):
        logger.warning(f"Port {port} is already in use. Attempting to find an available port...")
        try:
            port = find_available_port(port)
            logger.info(f"Found available port: {port}")
        except RuntimeError as e:
            logger.error(str(e))
            sys.exit(1)

    logger.info("Starting Noise Survey Analysis application...")
    logger.info(f"Application directory: {app_dir}")
    logger.info(f"Using port: {port}")
    logger.info(f"Debug mode: {debug}")

    from bokeh.server.server import Server
    from bokeh.application import Application
    from bokeh.application.handlers.function import FunctionHandler
    from tornado.ioloop import IOLoop

    # Create a Bokeh application using the directory browser function
    bokeh_app = Application(FunctionHandler(create_directory_browser_app))
    
    # Start the server
    server = Server({'/': bokeh_app}, port=port, io_loop=IOLoop.current(),
                   allow_websocket_origin=[f"localhost:{port}"])
    
    server.start()
    logger.info(f"Server started at http://localhost:{port}")
    
    # Open the application in a browser
    try:
        server.io_loop.add_callback(lambda: os.system(f"start http://localhost:{port}"))
        server.io_loop.start()
    except KeyboardInterrupt:
        logger.info("Server stopped")
        sys.exit(0)

def generate_standalone_html(output_path, debug=False):
    """
    Generate a standalone HTML file with Bokeh plots (no audio functionality).
    
    Args:
        output_path (str): Path where the HTML file will be saved
        debug (bool): Enable debug logging
    """
    # Configure logging based on debug flag
    configure_logging(debug)
    
    logger.info(f"Generating standalone HTML file at {output_path}")
    
    # Import the generate_standalone_html function from the main module
    from noise_survey_analysis.main import generate_standalone_html
    
    # Generate the standalone HTML file
    output_file = generate_standalone_html(output_path=output_path)
    
    logger.info(f"Standalone HTML file generated at: {output_file}")
    return output_file


if __name__ == "__main__":
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Run Noise Survey Analysis Bokeh application")
    parser.add_argument("--port", type=int, default=5006, 
                        help="Port to run the Bokeh server on (default: 5006)")
    parser.add_argument("--debug", action="store_true",
                        help="Enable debug mode for more detailed logging")
    parser.add_argument("--generate-html", type=str, metavar="OUTPUT_PATH", nargs="?", const="auto",
                        help="Generate a standalone HTML file (without audio) and exit. If no path is provided, will create in the surveys folder.")
    args = parser.parse_args()
    
    if args.generate_html:
        # Generate standalone HTML and exit
        if args.generate_html == "auto":
            # Let the function determine the default output path
            output_path = None
        else:
            output_path = args.generate_html
        generate_standalone_html(output_path, debug=args.debug)
    else:
        # Run the Bokeh server as normal
        run_bokeh_server(port=args.port, debug=args.debug)