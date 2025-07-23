"""Main application window.

For experiment table management in Droplet Wall Interaction Tool (DWIT).
"""

import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget

from src.core.table_core import TableCore
from src.utilities.logging_manager import get_logger
from src.widgets.table_widgets import TableGUI

# Setup logger for this module
logger = get_logger(__name__)


class TableWindow(QMainWindow):
    """Main window for the table functionality."""

    def __init__(self, parent=None):
        """Initialize the TableWindow with optional parent."""
        super().__init__(parent)
        logger.debug("Initializing TableWindow")

        self.setWindowTitle("Table Control")

        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # Main layout
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(0, 0, 0, 0)

        # Create controller and UI
        try:
            self.controller = TableCore()

            self.gui = TableGUI(central_widget, self.controller)

            layout.addWidget(self.gui)
            logger.info("TableWindow UI components initialized and added to layout")

        except Exception as e:
            logger.error(f"Error creating table controller or GUI: {e}")
            raise

        # Load data after initialization
        QTimer.singleShot(100, self.load_data)

    def load_data(self):
        """Load saved data and update the UI."""
        logger.info("Loading saved data and updating TableWindow UI")

        try:
            # Load substance data
            substance = self.controller.substance or "Butyl Acetate"
            self.gui.substance_combo.setCurrentText(substance)

            # Load numeric data fields
            droplet_data = self.controller.droplet_diameters or ""
            self.gui.droplet_entry.setText(droplet_data)

            flow_data = self.controller.counter_flows or ""
            self.gui.flow_entry.setText(flow_data)

            tilt_data = self.controller.tilts or ""
            self.gui.tilt_entry.setText(tilt_data)

            trial_data = self.controller.trials or "3"
            self.gui.trial_entry.setText(trial_data)

            # Check if all required data is available for processing
            if all(
                [
                    self.controller.substance,
                    self.controller.droplet_diameters,
                    self.controller.counter_flows,
                    self.controller.tilts,
                ]
            ):
                logger.debug(
                    "All required data available, processing and updating table"
                )

                self.controller.process_data(
                    self.controller.substance,
                    self.controller.droplet_diameters,
                    self.controller.counter_flows,
                    self.controller.tilts,
                )

                self.gui.update_table()
                logger.debug("Data loaded and table updated successfully")
                return True
            else:
                logger.warning("Some required data missing, table not updated")
                return False

        except Exception as e:
            logger.error(f"Error loading data: {e}")
            return False


if __name__ == "__main__":
    logger.debug("Starting TableWindow standalone application")

    app = QApplication(sys.argv)

    try:
        window = TableWindow()
        logger.debug("TableWindow created successfully")

        window.show()
        logger.debug("TableWindow displayed")

        logger.debug("Starting Qt event loop for table application")
        sys.exit(app.exec())

    except Exception as e:
        logger.error(f"Error running table application: {e}")
        sys.exit(1)
