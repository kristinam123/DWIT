"""Main application window.

For dosage control in Droplet Wall Interaction Tool (DWIT).
"""

import sys

from PySide6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget

from src.core.dosage_core import DosageCore
from src.utilities.logging_manager import get_logger
from src.widgets.dosage_widgets import DosageGUI

# Setup logger for this module
logger = get_logger(__name__)


class DosageWindow(QMainWindow):
    """Main window for the dosage control application."""

    def __init__(self, parent=None):
        """Initialize the DosageWindow."""
        super().__init__(parent)
        logger.debug("Initializing DosageWindow")

        self.setWindowTitle("Dosage Control")

        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # Main layout
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(0, 0, 0, 0)

        # Create controller and UI
        try:
            self.controller = DosageCore()

            self.gui = DosageGUI(central_widget, self.controller)

            layout.addWidget(self.gui)
            logger.debug("DosageWindow UI components initialized and added to layout")

        except Exception as e:
            logger.error(f"Error creating dosage controller or GUI: {e}")
            raise


if __name__ == "__main__":
    logger.debug("Starting DosageWindow standalone application")

    app = QApplication(sys.argv)

    try:
        window = DosageWindow()
        logger.debug("DosageWindow created successfully")

        window.show()
        logger.debug("DosageWindow displayed")

        logger.debug("Starting Qt event loop for dosage application")
        sys.exit(app.exec())

    except Exception as e:
        logger.error(f"Error running dosage application: {e}")
        sys.exit(1)
