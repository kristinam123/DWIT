"""Main application window for experiment analysis in MesszelleApp."""

import os
import sys
from typing import Any, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QVBoxLayout, QWidget

from src.core.analysis_core import AnalysisCore
from src.utilities.logging_manager import get_logger
from src.widgets.analysis_widgets import AnalysisGUI

# Setup logger for this module
logger = get_logger(__name__)


class AnalysisWindow(QWidget):
    """Analysis application.

    This widget integrates the analysis core with the GUI components,
    providing a complete interface for analyzing droplet contact angles.
    """

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        folder_path: Optional[str] = None,
        analysis_mode: str = "contact_angle",
    ):
        """Initialize Analysis widget.

        Args:
        ----
            parent: Parent widget
            folder_path: Path to folder containing images for analysis
            analysis_mode: The mode of analysis (e.g., "contact_angle",
                "free:_sedimentation", etc.).

        """
        super().__init__(parent)
        logger.debug(f"Initializing AnalysisWindow with mode: {analysis_mode}")

        try:
            self.setWindowTitle(f"Analysis - {analysis_mode.replace('_', ' ').title()}")
            self.analysis_mode = analysis_mode

            # Main layout with no margins for modern look
            layout = QVBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(0)

            # Extract and validate path
            self.folder_path = self._extract_path(folder_path)

            # Initialize controller and GUI
            self.controller = AnalysisCore(
                self.folder_path, analysis_mode=self.analysis_mode
            )

            self.gui = AnalysisGUI(self, self.controller)

            # Add GUI to layout
            layout.addWidget(self.gui)
            logger.debug("AnalysisWindow UI components initialized and added to layout")

        except Exception as e:
            # Handle initialization errors
            logger.error(f"Error initializing AnalysisWindow: {e}")
            logger.error(f"Analysis mode: {analysis_mode}")
            logger.error(f"Folder path: {folder_path}")
            raise

    def _extract_path(self, path_obj: Any) -> Optional[str]:
        """Extract path from various path object types.

        Handles path objects that might be wrapper objects with get/value methods,
        or direct string paths.

        Args:
        ----
            path_obj: Path object to extract from.

        Returns:
        -------
            Extracted path as string, or None if invalid.

        """
        if path_obj is None:
            return None

        # Check for object type and protect against non-path objects
        if hasattr(path_obj, "__class__"):
            logger.warning(
                "Path object has __class__ attribute, might not be a path object"
            )
            return None

        if hasattr(path_obj, "get"):
            extracted_path = path_obj.get()
            return extracted_path
        elif hasattr(path_obj, "value"):
            extracted_path = path_obj.value
            return extracted_path

        # Ensure path is a string
        try:
            path_str = str(path_obj)

            # Verify this looks like a valid path
            if os.path.exists(path_str) or os.path.exists(os.path.dirname(path_str)):
                logger.info(f"Valid path extracted: {path_str}")
                return path_str
            else:
                logger.warning(f"Path does not exist: {path_str}")
                return None

        except Exception as e:
            logger.error(f"Error converting path object to string: {e}")
            return None


if __name__ == "__main__":
    logger.debug("Starting AnalysisWindow standalone application")

    app = QApplication(sys.argv)

    try:
        window = AnalysisWindow()
        logger.info("AnalysisWindow created successfully")

        window.setWindowState(Qt.WindowMaximized)

        window.show()
        logger.info("AnalysisWindow displayed")

        logger.info("Starting Qt event loop for analysis application")
        sys.exit(app.exec())

    except Exception as e:
        logger.error(f"Error running analysis application: {e}")
        sys.exit(1)
