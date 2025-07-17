"""Application entry point for launching MesszelleApp."""

import gc
import sys
import traceback

from PySide6.QtCore import QSettings, QTimer
from PySide6.QtWidgets import QApplication

from src.main.cell import CellWindow
from src.utilities.logging_manager import get_logger, logging_manager

# Setup logger for this module
logger = get_logger(__name__)


def cleanup_logging():
    """Restore original stdout/stderr streams on app exit."""
    try:
        if (
            hasattr(logging_manager, "stdout_capture")
            and logging_manager.stdout_capture.original_stream
        ):
            sys.stdout = logging_manager.stdout_capture.original_stream
        if (
            hasattr(logging_manager, "stderr_capture")
            and logging_manager.stderr_capture.original_stream
        ):
            sys.stderr = logging_manager.stderr_capture.original_stream
        logger.info("Logging cleanup completed")
    except Exception as e:
        logger.error(f"Error during logging cleanup: {e}")


def setup_memory_management():
    """Set up periodic garbage collection to prevent memory leaks."""

    def force_gc():
        """Force garbage collection and log if significant cleanup occurred."""
        collected = gc.collect()
        if collected > 100:  # Only log if significant cleanup
            logger.debug(f"Garbage collector freed {collected} objects")

    # Set up timer for periodic garbage collection
    gc_timer = QTimer()
    gc_timer.timeout.connect(force_gc)
    gc_timer.start(30000)  # Every 30 seconds
    return gc_timer


def handle_exception(exc_type, exc_value, exc_traceback):
    """Global exception handler to catch uncaught exceptions."""
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return

    error_msg = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    logger.error(f"Uncaught exception: {error_msg}")

    # Try to continue running if possible
    logger.error("Application encountered an error but attempting to continue...")


if __name__ == "__main__":
    # Set up global exception handler
    sys.excepthook = handle_exception

    # Enable more aggressive garbage collection
    gc.set_threshold(700, 10, 10)  # More frequent collection

    try:
        logger.info("Starting MesszelleApp with enhanced error handling...")

        app = QApplication(sys.argv)
        # Set application metadata for QSettings
        app.setOrganizationName("MeasurementCellApp")
        app.setApplicationName("MesszelleApp")

        # Set up memory management
        gc_timer = setup_memory_management()
        logger.info("Memory management initialized")

        # Initialize logging manager settings after QApplication is properly set up
        logging_manager.initialize_settings()

        # Create and show the main window
        logger.info("Creating main window...")
        window = CellWindow()
        logger.info("Main window created successfully")

        # Restore previous window geometry if available
        settings = QSettings()
        if settings.contains("geometry"):
            try:
                window.restoreGeometry(settings.value("geometry"))
            except Exception as e:
                logger.warning(f"Could not restore geometry: {e}")
        if settings.contains("windowState"):
            try:
                window.restoreState(settings.value("windowState"))
            except Exception as e:
                logger.warning(f"Could not restore window state: {e}")

        # Connect close event to save geometry
        app.aboutToQuit.connect(
            lambda: settings.setValue("geometry", window.saveGeometry())
        )
        app.aboutToQuit.connect(
            lambda: settings.setValue("windowState", window.saveState())
        )

        # Connect close event to cleanup logging
        app.aboutToQuit.connect(cleanup_logging)

        # Cleanup timer on quit
        app.aboutToQuit.connect(gc_timer.stop)

        window.show()
        logger.info("MesszelleApp main window displayed")

        # Start the event loop
        logger.info("Starting Qt event loop...")
        exit_code = app.exec()

        logger.info("Application exiting normally")
        sys.exit(exit_code)

    except Exception as e:
        logger.error(f"Fatal error during application startup: {e}")
        traceback.print_exc()
        sys.exit(1)
