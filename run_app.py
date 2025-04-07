import os
import sys
import subprocess
import argparse
import logging

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

    logger.info("Starting Noise Survey Analysis application...")
    logger.info(f"Application directory: {app_dir}")
    logger.info(f"Using port: {port}")
    logger.info(f"Debug mode: {debug}")

    # Run the Bokeh server targeting the directory with custom port
    cmd = ["bokeh", "serve", "--show", app_dir, "--port", str(port),
           "--unused-session-lifetime", "30000",  # 30 seconds in milliseconds
           "--check-unused-sessions", "10000"]     # Check every 10 seconds
    
    # Add debug flag if enabled - be more explicit with all options
    if debug:
        cmd.extend(["--log-level=debug", "--log-format=%(asctime)s %(levelname)s %(name)s: %(message)s"])
    
    # Make sure the current working directory is the project root
    # so that imports within the app work correctly relative to the package.
    logger.debug(f"Running command: {' '.join(cmd)}")
    
    env = os.environ.copy()
    if debug:
        # Set environment variables to force debug mode
        env["PYTHONIOENCODING"] = "utf-8"  # Ensure proper encoding for logs
        env["BOKEH_LOG_LEVEL"] = "debug"   # Set Bokeh log level via env var too
        env["BOKEH_PY_LOG_LEVEL"] = "debug"
    
    try:
        subprocess.run(cmd, check=True, cwd=script_dir, env=env) # Ensure running from script's dir with debug env vars
    except subprocess.CalledProcessError as e:
        logger.error(f"Error running Bokeh server: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        logger.info("\nBokeh server stopped by user.")
        sys.exit(0)


if __name__ == "__main__":
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Run Noise Survey Analysis Bokeh application")
    parser.add_argument("--port", type=int, default=5006, 
                        help="Port to run the Bokeh server on (default: 5006)")
    parser.add_argument("--debug", action="store_true",
                        help="Enable debug mode for more detailed logging")
    args = parser.parse_args()
    
    run_bokeh_server(port=args.port, debug=args.debug)