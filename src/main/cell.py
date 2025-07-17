"""Main application window for cell control in MesszelleApp."""

import os
import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget

from src.core.cell_core import CellCore
from src.utilities.logging_manager import get_logger
from src.widgets.cell_widgets import CellGUI

# Helper function to get the icon path
# Setup logger for this module
logger = get_logger(__name__)


def get_icon_path():
    """Return the path to the application icon if found, else None."""
    # Try resources/icons path first (typical location)
    base_dir = os.path.dirname(os.path.dirname(__file__))
    icon_paths = [
        os.path.join(base_dir, "resources", "icons", "avt.ico"),
        os.path.join(base_dir, "assets", "avt.ico"),
        os.path.join(base_dir, "resources", "avt.ico"),
        os.path.join(base_dir, "src", "resources", "icons", "avt.ico"),
        os.path.join(base_dir, "..", "resources", "icons", "avt.ico"),
    ]

    for path in icon_paths:
        if os.path.exists(path):
            return path

    # If all paths fail, log the search paths
    logger.warning(f"Application icon not found, searched paths: {icon_paths}")
    return None


class CellWindow(QMainWindow):
    """Main window for the Measurement Cell application."""

    def __init__(self):
        """Initialize the CellWindow."""
        super().__init__()
        logger.info("Initializing CellWindow (Main Application Window)")

        self.setWindowTitle("Measurement Cell Control Center")

        # Set application icon
        icon_path = get_icon_path()
        if icon_path:
            self.setWindowIcon(QIcon(icon_path))
        else:
            logger.warning("No application icon set - icon file not found")

        # Create central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # Create controller and UI
        try:
            self.controller = CellCore()

            self.gui = CellGUI(central_widget, self.controller)

        except Exception as e:
            logger.error(f"Error creating cell controller or GUI: {e}")
            raise

        # Set up layout
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.gui)
        logger.info("CellWindow UI components initialized and added to layout")


if __name__ == "__main__":
    logger.info("Starting CellWindow standalone application (Main Entry Point)")

    app = QApplication(sys.argv)

    # Set application icon for taskbar/dock
    icon_path = get_icon_path()
    if icon_path:
        app.setWindowIcon(QIcon(icon_path))
    else:
        logger.warning("No taskbar/dock icon set - icon file not found")

    try:
        window = CellWindow()
        logger.info("CellWindow (main application) created successfully")

        window.show()
        logger.info("CellWindow (main application) displayed")

        logger.info("Starting Qt event loop for main application")
        sys.exit(app.exec())

    except Exception as e:
        logger.error(f"Error running main application: {e}")
        sys.exit(1)
