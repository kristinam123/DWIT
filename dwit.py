"""Application entry point.

For launching Droplet Wall Interaction Tool (DWIT).
"""

import gc
import os
import sys
import traceback
from typing import Any, Optional

from PySide6.QtCore import QSettings, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from src.utilities.logging_manager import get_logger, logging_manager
from src.utilities.overlays import LogOverlay, NavigationOverlay


# Defer heavy imports until needed
def _lazy_import_analysis_core():
    """Lazy import of AnalysisCore to speed up startup."""
    from src.core import AnalysisCore

    return AnalysisCore


def _lazy_import_analysis_gui():
    """Lazy import of AnalysisGUI to speed up startup."""
    from src.widgets import AnalysisGUI

    return AnalysisGUI


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

            # Initialize controller and GUI with lazy imports
            analysis_core = _lazy_import_analysis_core()
            analysis_gui = _lazy_import_analysis_gui()

            self.controller = analysis_core(
                self.folder_path, analysis_mode=self.analysis_mode
            )

            self.gui = analysis_gui(self, self.controller)

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


class CellGUI(QWidget):
    """Modern Droplet Wall Interaction Tool (DWIT) control interface."""

    def __init__(self, parent):
        """Initialize the CellGUI with parent."""
        logger.debug("Initializing CellGUI")
        super().__init__(parent)

        # Initialize overlays
        self.log_overlay = LogOverlay(self)
        self.nav_overlay = NavigationOverlay(self)

        # Connect navigation overlay's page selection to page change
        if hasattr(self.nav_overlay, "page_selected"):
            self.nav_overlay.page_selected.connect(self._apply_selected_navigation)

        # Connect logging manager to log overlay
        logging_manager.set_log_overlay(self.log_overlay)
        self.log_overlay.set_logging_manager(logging_manager)

        logger.debug("CellGUI initialized successfully")

        self._create_widgets()

        # Connect log level updates to status indicator after widgets are created
        logging_manager.log_level_updated.connect(self._update_log_status_indicator)

    def _create_widgets(self):
        # Main layout (full width content + bottom controls)
        self._main_container = QWidget(self)
        self._main_container.setObjectName("main_container")
        main_layout = QVBoxLayout(self._main_container)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # === MAIN CONTENT AREA ===
        content_area = QWidget()
        content_layout = QVBoxLayout(content_area)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(3)

        # Top controls area
        top_controls = QWidget()
        top_controls_layout = QVBoxLayout(top_controls)
        top_controls_layout.setContentsMargins(0, 0, 0, 0)
        top_controls_layout.setSpacing(3)

        content_layout.addWidget(top_controls)

        # Content pages (stacked widget) - takes most space
        content_pages = self._create_content_pages()
        content_layout.addWidget(content_pages, 1)

        # Bottom controls with status indicator
        bottom_controls = self._create_bottom_controls()

        # Add to main layout
        main_layout.addWidget(content_area, 1)
        main_layout.addWidget(bottom_controls)

        # Place the main container in a layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._main_container)

        # Update navigation button to show the correct initial page
        if hasattr(self, "_initial_page_index"):
            self._update_nav_button_text(self._initial_page_index)

    def _create_content_pages(self):
        """Create the stacked content pages with lazy initialization and page memory."""
        self.content = QStackedWidget()
        self.content.setToolTip(
            "Displays the main content area for each experiment or control page."
        )
        self.page_names = [
            "Free Sedimentation",
            "Contact Angle",
            "Channel",
            "Structured Packing",
        ]
        # Store page widgets and their init functions
        self._page_widgets = [None] * len(self.page_names)
        self._page_inits = [
            self._init_free_sedimentation_page,
            self._init_contact_angle_page,
            self._init_channel_page,
            self._init_structured_packing_page,
        ]
        # Add empty widgets as placeholders
        for _ in self.page_names:
            self.content.addWidget(QWidget())

        # Restore the last active page from QSettings
        settings = QSettings()
        last_page_index = settings.value("lastPageIndex", 0, type=int)

        # Validate the restored index
        if not (0 <= last_page_index < len(self.page_names)):
            logger.warning(
                f"Invalid last page index {last_page_index}, defaulting to 0"
            )
            last_page_index = 0

        self._initial_page_index = last_page_index
        self._change_page(last_page_index)
        return self.content

    def _init_free_sedimentation_page(self):
        """Initialize the free sedimentation analysis page (deferred)."""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)

        # Defer the actual heavy initialization
        def _init_heavy():
            self.free_sedimentation_analysis_window = AnalysisWindow(
                page, analysis_mode="free_sedimentation"
            )
            layout.addWidget(self.free_sedimentation_analysis_window)

        # Defer heavy work to next event loop cycle
        QTimer.singleShot(50, _init_heavy)
        return page

    def _init_contact_angle_page(self):
        """Initialize the contact angle analysis page (deferred)."""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)

        # Defer the actual heavy initialization
        def _init_heavy():
            self.analysis_window = AnalysisWindow(page, analysis_mode="contact_angle")
            layout.addWidget(self.analysis_window)

        # Defer heavy work to next event loop cycle
        QTimer.singleShot(100, _init_heavy)
        return page

    def _init_channel_page(self):
        """Initialize the channel analysis page (deferred)."""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)

        # Defer the actual heavy initialization
        def _init_heavy():
            self.channel_analysis_window = AnalysisWindow(page, analysis_mode="channel")
            layout.addWidget(self.channel_analysis_window)

        # Defer heavy work to next event loop cycle
        QTimer.singleShot(150, _init_heavy)
        return page

    def _init_structured_packing_page(self):
        """Initialize the structured packing analysis page (deferred)."""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)

        # Defer the actual heavy initialization
        def _init_heavy():
            self.structured_packing_analysis_window = AnalysisWindow(
                page, analysis_mode="structured_packing"
            )
            layout.addWidget(self.structured_packing_analysis_window)

        # Defer heavy work to next event loop cycle
        QTimer.singleShot(200, _init_heavy)
        return page

    def _show_terminal_overlay(self):
        """Show the terminal overlay from the bottom button using LogOverlay class."""
        self.log_overlay.show_overlay()
        # Reset the status indicator when user opens the log
        logging_manager.reset_highest_level()

    def _update_log_status_indicator(self, highest_level: str):
        """Update the log status indicator based on the highest log level received."""
        # Check if the log status button exists before trying to update it
        if not hasattr(self, "log_status_btn"):
            return

        # Get current counts from logging manager
        counts = logging_manager.get_status_counts()
        warning_count = counts.get("warning_count", 0)
        error_count = counts.get("error_count", 0)

        # Determine what to show based on counts and highest level
        if error_count > 0:
            # Show error count with red background
            display_text = str(error_count)
            background_color = "#FF0000"  # Same red as overlay
            text_color = "white"
            tooltip = (
                f"Log Status - {error_count} error(s), "
                f"{warning_count} warning(s). Click to view logs"
            )
        elif warning_count > 0:
            # Show warning count with orange background
            display_text = str(warning_count)
            background_color = "#FFA500"  # Same orange as overlay
            text_color = "white"
            tooltip = f"Log Status - {warning_count} warning(s). Click to view logs"
        else:
            # Default green status
            display_text = "●"
            background_color = "transparent"
            text_color = "#00FF00"  # Green
            tooltip = "Log Status - No issues. Click to view logs"

        self.log_status_btn.setText(display_text)
        self.log_status_btn.setToolTip(tooltip)

        # Set hover styles based on background color
        hover_bg = (
            "rgba(255, 255, 255, 20)"
            if background_color == "transparent"
            else background_color
        )
        hover_border = (
            "1px solid rgba(255, 255, 255, 40)"
            if background_color != "transparent"
            else "none"
        )

        self.log_status_btn.setStyleSheet(
            f"""
            QToolButton {{
                background-color: {background_color};
                border: none;
                color: {text_color};
                font-size: 12px;
                font-weight: bold;
                border-radius: 12px;
                min-width: 24px;
                text-align: center;
            }}
            QToolButton:hover {{
                background-color: {hover_bg};
                border: {hover_border};
            }}
        """
        )

    def _open_navigation_selector(self):
        """Open the navigation selector overlay."""
        self.nav_overlay.toggle_overlay()

    def _apply_selected_navigation(self, page_index):
        """Apply the selected navigation page."""
        self._change_page(page_index)

    def _change_page(self, index):
        """Change the active page and update navigation button.

        Also save index to QSettings.
        """
        from PySide6.QtCore import QSettings

        if not (0 <= index < len(self.page_names)):
            logger.warning(f"Invalid page index {index}, defaulting to 0")
            index = 0

        logger.info(f"Changing to page: {self.page_names[index]}")
        # Lazy init: only create the page widget if not already done
        if self._page_widgets[index] is None:

            # Create the new widget
            self._page_widgets[index] = self._page_inits[index]()
            # Remove the placeholder widget at this index
            old_widget = self.content.widget(index)
            self.content.removeWidget(old_widget)
            old_widget.deleteLater()
            # Insert the new widget at the correct index
            self.content.insertWidget(index, self._page_widgets[index])
        self.content.setCurrentIndex(index)
        # Save current page index to QSettings
        settings = QSettings()
        settings.setValue("lastPageIndex", index)
        # Update navigation button text to show current page
        self._update_nav_button_text(index)

        # Update main window title to reflect current analysis mode
        main_window = self.window() if hasattr(self, "window") else None
        if main_window is not None:
            mode_name = self.page_names[index]
            main_window.setWindowTitle(f"{mode_name} DWIT")

    def _update_nav_button_text(self, index):
        """Update the navigation button text to show the current page."""
        if hasattr(self, "nav_button") and 0 <= index < len(self.page_names):
            page_name = self.page_names[index]
            self.nav_button.setText(f"{page_name} ▲")
            self.nav_button.setToolTip(
                f"Currently displaying: {page_name}. Click to select a different page."
            )

    def _create_bottom_controls(self):
        """Create bottom controls with navigation dropdown and ROI selection."""
        bottom_widget = QWidget()
        bottom_layout = QHBoxLayout(bottom_widget)
        bottom_layout.setContentsMargins(8, 5, 8, 5)
        bottom_layout.setSpacing(10)

        # Log button (left side)
        self.terminal_bottom_btn = QToolButton()
        self.terminal_bottom_btn.setText("▲ Log")
        self.terminal_bottom_btn.setToolTip("Show notification log")
        self.terminal_bottom_btn.clicked.connect(self._show_terminal_overlay)

        bottom_layout.addWidget(self.terminal_bottom_btn)

        # Log status indicator (next to log button)
        self.log_status_btn = QToolButton()
        self.log_status_btn.setText("●")  # Circle indicator
        self.log_status_btn.setToolTip("Log Status - Click to view logs")
        self.log_status_btn.clicked.connect(self._show_terminal_overlay)
        self.log_status_btn.setFixedSize(24, 24)
        self._update_log_status_indicator("info")  # Default status

        bottom_layout.addWidget(self.log_status_btn)
        bottom_layout.addStretch(1)

        # Navigation selection button (right side) - shows current page name
        self.nav_button = QPushButton("Free Sedimentation ▲")  # Default to first page
        self.nav_button.setToolTip(
            "Currently displaying: Free Sedimentation."
            " Click to select a different page."
        )
        self.nav_button.clicked.connect(self._open_navigation_selector)

        bottom_layout.addWidget(self.nav_button)

        return bottom_widget

    def mousePressEvent(self, event):  # noqa: N802
        """Handle mouse press events to close overlays when clicking on main content."""
        # Check if any overlay is visible and close it
        if self.log_overlay.isVisible():
            self.log_overlay.hide_overlay()
        elif self.nav_overlay.isVisible():
            self.nav_overlay.hide_overlay()

        # Call parent implementation to ensure normal behavior
        super().mousePressEvent(event)

    def cleanup_on_close(self):
        """Clean up any resources when the GUI is closing."""
        logger.debug("Starting CellGUI cleanup")
        try:
            # Clean up any analysis windows that might have running threads
            analysis_window_attrs = [
                "analysis_window",
                "free_sedimentation_analysis_window",
                "channel_analysis_window",
                "structured_packing_analysis_window",
            ]

            for attr_name in analysis_window_attrs:
                if hasattr(self, attr_name):
                    analysis_window = getattr(self, attr_name)
                    if hasattr(analysis_window, "gui"):
                        # Stop any background threads in the analysis GUI
                        analysis_window.gui.cleanup_all_threads()
            logger.debug("CellGUI cleanup completed")
        except Exception as e:
            logger.error(f"Error during CellGUI cleanup: {e}")


class DWIT(QMainWindow):
    """Main window for the Droplet Wall Interaction Tool (DWIT)."""

    def __init__(self):
        """Initialize the DWIT."""
        super().__init__()
        logger.debug("Initializing DWIT (Main Application Window)")

        # Set initial window title based on the first page
        if hasattr(self, "gui") and hasattr(self.gui, "page_names"):
            initial_mode = self.gui.page_names[
                getattr(self.gui, "_initial_page_index", 0)
            ]
            self.setWindowTitle(f"{initial_mode} DWIT")
        else:
            self.setWindowTitle("DWIT")

        # Set application icon
        icon_path = os.path.join(os.path.dirname(__file__), "resources", "avt.ico")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        else:
            logger.warning("No application icon set - icon file not found")

        # Create central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # Create controller and UI
        try:
            self.gui = CellGUI(central_widget)

        except Exception as e:
            logger.error(f"Error creating cell controller or GUI: {e}")
            raise

        # Set up layout
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.gui)
        logger.debug("DWIT UI components initialized and added to layout")

    def closeEvent(self, event):  # noqa: N802 - Qt requires closeEvent signature
        """Handle close event with proper cleanup."""
        logger.debug("DWIT main window close event triggered")
        try:
            # Clean up GUI components that might have threads
            if hasattr(self, "gui"):
                self.gui.cleanup_on_close()
        except Exception as e:
            logger.error(f"Error during GUI cleanup: {e}")

        # Accept the event and call parent
        event.accept()
        super().closeEvent(event)


def cleanup_logging():
    """Restore original stdout/stderr streams on dwit exit."""
    logger.debug("Attempting to clean up logging streams...")
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
        logger.debug("Logging cleanup completed")
    except Exception as e:
        logger.error(f"Error during logging cleanup: {e}")


def cleanup_all_threads():
    """Clean up all running threads before application exit."""
    logger.debug("Starting comprehensive thread cleanup...")
    try:
        # Import here to avoid circular imports
        from PySide6.QtCore import QThreadPool

        # Stop all active thread pools
        QThreadPool.globalInstance().waitForDone(2000)

        # Clean up any thread manager instances
        try:
            from src.utilities.thread_manager import thread_manager

            thread_manager.stop_all(wait_ms=1000)
        except ImportError:
            pass  # thread_manager may not exist yet

        logger.debug("Thread cleanup completed")
    except Exception as e:
        logger.error(f"Error during thread cleanup: {e}")


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
    logger.info("Application starting")
    # Set up global exception handler
    sys.excepthook = handle_exception

    # Enable more aggressive garbage collection
    gc.set_threshold(700, 10, 10)  # More frequent collection

    try:
        dwit = QApplication(sys.argv)
        # Set application metadata for QSettings
        dwit.setOrganizationName("Droplet Wall Interaction Tool (DWIT)")
        dwit.setApplicationName("Droplet Wall Interaction Tool (DWIT)")

        # Ensure application icon is set at the QApplication level so
        # it is used by the OS (taskbar / alt-tab on Windows)
        icon_path = os.path.join(os.path.dirname(__file__), "resources", "avt.ico")
        if os.path.exists(icon_path):
            try:
                dwit.setWindowIcon(QIcon(icon_path))
            except Exception:
                logger.debug("Failed to set QApplication icon")

        # Set up memory management
        gc_timer = setup_memory_management()

        # Initialize logging manager settings after QApplication is properly set up
        logging_manager.initialize_settings()

        # Create and show the main window
        logger.debug("Creating main window...")
        window = DWIT()
        logger.debug("Main window created successfully")

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
        dwit.aboutToQuit.connect(
            lambda: settings.setValue("geometry", window.saveGeometry())
        )
        dwit.aboutToQuit.connect(
            lambda: settings.setValue("windowState", window.saveState())
        )

        # Connect comprehensive cleanup on quit
        dwit.aboutToQuit.connect(cleanup_all_threads)
        dwit.aboutToQuit.connect(cleanup_logging)
        dwit.aboutToQuit.connect(gc_timer.stop)

        window.show()
        logger.debug("Droplet Wall Interaction Tool (DWIT) main window displayed")

        # Start the event loop
        logger.debug("Starting Qt event loop...")
        exit_code = dwit.exec()

        logger.info("Application shutting down")
        logger.debug("Application exiting normally")
        sys.exit(exit_code)

    except Exception as e:
        logger.error(f"Fatal error during application startup: {e}")
        logger.info("Application encountered an unrecoverable error and will exit")
        traceback.print_exc()
        sys.exit(1)
