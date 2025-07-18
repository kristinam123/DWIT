"""Cell GUI widgets for experiment setup and control in MesszelleApp."""

from PySide6.QtCore import QSettings, Qt, Slot
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from src.main.analysis import AnalysisWindow
from src.main.camera import CameraWindow
from src.main.dosage import DosageWindow
from src.main.pump import PumpWindow
from src.main.table import TableWindow
from src.utilities.logging_manager import get_logger, logging_manager
from src.utilities.overlays import LogOverlay, NavigationOverlay

# Setup logger for this module
logger = get_logger(__name__)


class CellGUI(QWidget):
    """Modern Measurement Cell control interface."""

    def __init__(self, parent, controller):
        """Initialize the CellGUI with parent and controller."""
        logger.debug("Initializing CellGUI")
        super().__init__(parent)
        self.controller = controller
        self.folder_path = controller.folder_path

        # Initialize overlays
        self.log_overlay = LogOverlay(self)
        self.nav_overlay = NavigationOverlay(self)

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

        # Setup controller references
        self._setup_controller_references()
        # Connect controller signals
        self.controller.prompt_changed.connect(self._update_prompt)
        self.controller.progress_changed.connect(self._update_progress)

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
            "Controllers",
            "Free Sedimentation",
            "Contact Angle",
            "Channel",
            "Structured Packing",
            "Table",
        ]
        # Store page widgets and their init functions
        self._page_widgets = [None] * len(self.page_names)
        self._page_inits = [
            self._init_controller_page,
            self._init_free_sedimentation_page,
            self._init_contact_angle_page,
            self._init_channel_page,
            self._init_structured_packing_page,
            self._init_table_page,
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

    def _init_controller_page(self):
        """Initialize the controller page with camera, pump, and dosage widgets."""
        controller_page = QWidget()
        controller_layout = QVBoxLayout(controller_page)
        controller_layout.setContentsMargins(0, 0, 0, 0)
        controller_layout.setSpacing(8)

        # Add workspace group to the controller page
        workspace_group = QWidget()
        workspace_layout = QVBoxLayout(workspace_group)
        workspace_layout.setContentsMargins(0, 0, 0, 0)
        workspace_layout.setSpacing(5)

        # Status/prompt area
        self.prompt = QLabel("Ready to start")
        self.prompt.setAlignment(Qt.AlignCenter)
        self.prompt.setMinimumHeight(24)
        self.prompt.setWordWrap(True)
        self.prompt.setToolTip("Displays the current status or prompt message.")
        prompt_font = QFont()
        prompt_font.setPointSize(10)
        self.prompt.setFont(prompt_font)
        workspace_layout.addWidget(self.prompt)

        # Add folder selection to a horizontal layout
        folder_layout = QHBoxLayout()
        folder_label = QLabel("Working Directory:")
        folder_label.setMaximumWidth(100)
        folder_label.setToolTip(
            "Shows the current working directory for experiment data."
        )
        self.folder_entry = QLineEdit()
        self.folder_entry.setText(self.controller.folder_path)
        self.folder_entry.setReadOnly(True)
        self.folder_entry.setToolTip(
            "Displays the current working directory. "
            "Use the Browse button to change it."
        )
        self.browse_button = QPushButton("Browse...")
        self.browse_button.setMaximumWidth(70)
        self.browse_button.setToolTip("Browse for a working directory.")
        self.browse_button.clicked.connect(self.select_folder)

        folder_layout.addWidget(folder_label)
        folder_layout.addWidget(self.folder_entry, 1)
        folder_layout.addWidget(self.browse_button)
        workspace_layout.addLayout(folder_layout)

        # Controls section in the same group
        controls_layout = QHBoxLayout()
        # Start/Stop button
        self.start_button = QPushButton("Start")
        self.start_button.setMinimumHeight(30)
        self.start_button.setToolTip("Start or stop the automation process.")
        self.start_button.clicked.connect(self._toggle_running)

        # Progress bar
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setToolTip("Shows the progress of the current operation.")

        controls_layout.addWidget(self.start_button)
        controls_layout.addWidget(self.progress, 1)
        workspace_layout.addLayout(controls_layout)

        # Add workspace group to controller layout
        controller_layout.addWidget(workspace_group)

        # Create horizontal splitter for better arrangement
        controller_splitter = QSplitter(Qt.Vertical)

        # Camera section
        camera_group = QWidget()
        camera_layout = QVBoxLayout(camera_group)
        camera_layout.setContentsMargins(0, 0, 0, 0)
        self.camera_window = CameraWindow(self)
        camera_layout.addWidget(self.camera_window.gui)
        controller_splitter.addWidget(camera_group)

        # Remove lower_splitter (QSplitter) and use a fixed QHBoxLayout
        # for pump and dosage
        lower_section = QWidget()
        lower_layout = QHBoxLayout(lower_section)
        lower_layout.setContentsMargins(0, 0, 0, 0)
        lower_layout.setSpacing(0)

        # Pump section
        pump_group = QWidget()
        pump_layout = QVBoxLayout(pump_group)
        pump_layout.setContentsMargins(0, 0, 0, 0)
        self.pump_window = PumpWindow(self)
        pump_layout.addWidget(self.pump_window.gui)
        pump_group.setMinimumWidth(350)
        lower_layout.addWidget(pump_group)

        # Dosage section
        dosage_group = QWidget()
        dosage_layout = QVBoxLayout(dosage_group)
        dosage_layout.setContentsMargins(0, 0, 0, 0)
        self.dosage_window = DosageWindow(self)
        dosage_layout.addWidget(self.dosage_window.gui)
        dosage_group.setMinimumWidth(350)
        lower_layout.addWidget(dosage_group)

        # Add lower_section to controller_splitter (vertical)
        controller_splitter.addWidget(lower_section)

        controller_layout.addWidget(controller_splitter)

        # Set up controller references for automation (now that components exist)
        self.controller.camera_gui = self.camera_window.gui
        self.controller.pump_gui = self.pump_window.gui
        self.controller.dosage_gui = self.dosage_window.gui

        # Set up port refresh callbacks
        self.pump_window.gui.parent_refresh_callback = self.refresh_all_ports
        self.dosage_window.gui.parent_refresh_callback = self.refresh_all_ports

        return controller_page

    def _init_free_sedimentation_page(self):
        """Initialize the free sedimentation analysis page."""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)
        self.free_sedimentation_analysis_window = AnalysisWindow(
            page, analysis_mode="free_sedimentation"
        )
        layout.addWidget(self.free_sedimentation_analysis_window)
        return page

    def _init_contact_angle_page(self):
        """Initialize the contact angle analysis page."""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)
        self.analysis_window = AnalysisWindow(page, analysis_mode="contact_angle")
        layout.addWidget(self.analysis_window)
        return page

    def _init_channel_page(self):
        """Initialize the channel analysis page."""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)
        self.channel_analysis_window = AnalysisWindow(page, analysis_mode="channel")
        layout.addWidget(self.channel_analysis_window)
        return page

    def _init_structured_packing_page(self):
        """Initialize the structured packing analysis page."""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)
        self.structured_packing_analysis_window = AnalysisWindow(
            page, analysis_mode="structured_packing"
        )
        layout.addWidget(self.structured_packing_analysis_window)
        return page

    def _init_table_page(self):
        """Initialize the table page."""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        self.table_window = TableWindow(self)
        layout.addWidget(self.table_window.gui)
        self.controller.table_gui = self.table_window
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

    def _setup_controller_references(self):
        """Set up references to all components in the controller."""
        # Store GUI references for automation controller (used in cell_core.py)
        pass

    def refresh_all_ports(self):
        """Refresh ports in both dosage and pump widgets."""
        # Get ports from shared port manager to ensure both widgets see the same list
        try:
            # Only refresh if the windows exist (controller page has been initialized)
            if hasattr(self, "pump_window") and hasattr(self, "dosage_window"):
                # Get ports from pump controller
                pump_ports = self.pump_window.gui.controller.get_available_ports()
                self.pump_window.gui.refresh_ports_internal(pump_ports)

                # Get ports from dosage controller
                dosage_ports, _ = self.dosage_window.gui.controller.populate_ports()
                self.dosage_window.gui.refresh_ports_internal(dosage_ports)

        except Exception as e:
            logger.error(f"Error refreshing ports: {e}")
            pass

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

    def _update_nav_button_text(self, index):
        """Update the navigation button text to show the current page."""
        if hasattr(self, "nav_button") and 0 <= index < len(self.page_names):
            page_name = self.page_names[index]
            self.nav_button.setText(f"{page_name} ▲")
            self.nav_button.setToolTip(
                f"Currently displaying: {page_name}. Click to select a different page."
            )

    @Slot()
    def select_folder(self):
        """Open folder selection dialog."""
        logger.info("Opening folder selection dialog")
        folder_selected = QFileDialog.getExistingDirectory(
            self, "Select Working Directory", self.controller.folder_path or ""
        )
        if folder_selected:
            logger.info(f"Folder selected: {folder_selected}")
            # Update folder path in controller
            self.controller.select_folder(folder_selected)
            self.folder_entry.setText(folder_selected)
        else:
            pass

    @Slot()
    def automatisation(self):
        """Start the automation process."""
        logger.info("Starting automation process")
        # Check if table has data
        if not hasattr(self.table_window, "result") or not self.table_window.results:
            logger.warning("No table data available for automation")
            return

        # Disable the start button while automation is running
        #         self.start_button.setEnabled(False)
        # Start the automation thread
        logger.info("Starting automation thread")
        self.controller.start_automation()

    @Slot(str)
    def _update_prompt(self, message):
        """Update the prompt message."""
        # Only update if the controller page (and prompt widget) has been initialized
        if hasattr(self, "prompt"):
            self.prompt.setText(message)

    @Slot(int)
    def _update_progress(self, value):
        """Update the progress bar."""
        # Only update if the controller page (and progress widget) has been initialized
        if hasattr(self, "progress"):
            self.progress.setValue(value)

    @Slot()
    def _toggle_running(self):
        """Handle start/stop button clicks."""
        if hasattr(self.controller, "start_automation"):
            if self.start_button.text() == "Start":
                self.automatisation()
                self.start_button.setText("Stop")
            else:
                if hasattr(self.controller, "stop_automation"):
                    self.controller.stop_automation()
                self.start_button.setText("Start")
        else:
            pass

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
        self.nav_button = QPushButton("Controllers ▲")  # Default to first page
        self.nav_button.setToolTip(
            "Currently displaying: Controllers. Click to select a different page."
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
