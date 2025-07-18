"""Main application window for camera control in MesszelleApp."""

import sys
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QVBoxLayout, QWidget

from src.core.camera_core import CameraCore
from src.utilities.logging_manager import get_logger
from src.widgets.camera_widgets import CameraGUI

# Setup logger for this module
logger = get_logger(__name__)


class CameraWindow(QWidget):
    """Main camera interface combining camera core and GUI components.

    This widget serves as the container for the camera functionality,
    handling the connection between core camera operations and the user interface.
    """

    def __init__(self, parent: Optional[QWidget] = None):
        """Initialize the CameraWindow with optional parent."""
        super().__init__(parent)
        logger.debug("Initializing CameraWindow")

        self.setWindowTitle("Camera Control")

        # Initialize core components
        try:
            self.controller = CameraCore()
        except Exception as e:
            logger.error(f"Error creating camera controller: {e}")
            raise

        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Initialize and add GUI
        try:
            self.gui = CameraGUI(self, self.controller)

            main_layout.addWidget(self.gui)
            logger.debug("CameraWindow UI components initialized and added to layout")

        except Exception as e:
            logger.error(f"Error creating camera GUI: {e}")
            raise

    def close_event(self, event) -> None:
        """Handle window close event, ensuring proper cleanup.

        Args:
        ----
            event: Close event to handle.

        """
        logger.debug("CameraWindow close event triggered")

        # Safely shut down camera before closing
        try:
            self.controller.close()
            logger.debug("Camera controller closed successfully")

        except Exception as e:
            logger.error(f"Error closing camera: {e}")
        super().close_event(event)


if __name__ == "__main__":
    logger.debug("Starting CameraWindow standalone application")

    app = QApplication(sys.argv)

    try:
        window = CameraWindow()
        logger.debug("CameraWindow created successfully")

        window.setWindowState(Qt.WindowMaximized)

        window.show()
        logger.debug("CameraWindow displayed")

        logger.debug("Starting Qt event loop for camera application")
        sys.exit(app.exec())

    except Exception as e:
        logger.error(f"Error running camera application: {e}")
        sys.exit(1)
