"""Main application window.

For pump control in Droplet Wall Interaction Tool (DWIT).
"""

import sys

from PySide6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget

from src.core.pump_core import PumpCore
from src.utilities.logging_manager import get_logger
from src.widgets.pump_widgets import PumpGUI

# Setup logger for this module
logger = get_logger(__name__)


class PumpWindow(QMainWindow):
    """Main window for the pump control application."""

    def __init__(self, parent=None):
        """Initialize the PumpWindow."""
        super().__init__(parent)
        logger.debug("Initializing PumpWindow")

        self.setWindowTitle("Pump Control")

        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # Main layout
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(0, 0, 0, 0)

        # Create controller and UI
        try:
            self.controller = PumpCore()

            self.gui = PumpGUI(self, self.controller)

            layout.addWidget(self.gui)
            logger.debug("PumpWindow UI components initialized and added to layout")

        except Exception as e:
            logger.error(f"Error creating pump controller or GUI: {e}")
            raise


if __name__ == "__main__":
    logger.debug("Starting PumpWindow standalone application")

    app = QApplication(sys.argv)

    try:
        window = PumpWindow()
        logger.debug("PumpWindow created successfully")

        window.show()
        logger.debug("PumpWindow displayed")

        logger.debug("Starting Qt event loop for pump application")
        sys.exit(app.exec())

    except Exception as e:
        logger.error(f"Error running pump application: {e}")
        sys.exit(1)
