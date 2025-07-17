"""Main application window for pump control in MesszelleApp."""

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
        logger.info("Initializing PumpWindow")

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
            logger.info("PumpWindow UI components initialized and added to layout")

        except Exception as e:
            logger.error(f"Error creating pump controller or GUI: {e}")
            raise


if __name__ == "__main__":
    logger.info("Starting PumpWindow standalone application")

    app = QApplication(sys.argv)

    try:
        window = PumpWindow()
        logger.info("PumpWindow created successfully")

        window.show()
        logger.info("PumpWindow displayed")

        logger.info("Starting Qt event loop for pump application")
        sys.exit(app.exec())

    except Exception as e:
        logger.error(f"Error running pump application: {e}")
        sys.exit(1)
