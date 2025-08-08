"""Analysis GUI widgets for experiment visualization and user interaction.

Part of Droplet Wall Interaction Tool (DWIT).
"""

import glob
import os
from typing import Any, Optional

import cv2
import numpy as np
from PySide6.QtCore import QCoreApplication, Qt, QThread, QTimer
from PySide6.QtGui import QIcon, QImage, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListView,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from src.helpers.baseline import find_single_baseline
from src.helpers.batch import BatchProcessingWorker, FolderItemDelegate
from src.helpers.preview import show_preview
from src.helpers.save_results import save_results
from src.helpers.velocity import calculate_velocities
from src.threads import AnalysisThread
from src.utilities.image import create_background_image, crop_image, rotate_image
from src.utilities.logging_manager import get_logger
from src.utilities.roi import ROISelector

# Setup logger for this module
logger = get_logger(__name__)


class AnalysisGUI(QWidget):
    """Modern GUI for analysis."""

    def __init__(self, parent: QWidget, controller: Any):
        """Initialize the AnalysisGUI with parent and controller."""
        logger.debug("Initializing AnalysisGUI")

        try:
            super().__init__(parent)
            self.controller = controller
            self.main_thread = None
            self.preview_thread = None

            # Add a processing state flag to track when analysis is running
            self.is_processing = False

            # Add initialization flag to prevent unwanted dialogs during setup
            self.is_initializing = True

            # Initialize image storage
            self.preview_images = {"original": [], "contour": [], "result": []}
            self.current_frame = 0
            self.total_frames = 0

            # Create debounce timer for parameter changes
            self.preview_timer = QTimer(self)
            self.preview_timer.setSingleShot(True)
            self.preview_timer.setInterval(100)
            self.preview_timer.timeout.connect(self._auto_preview)

            # Initialize context preview timer (will be created on demand)
            self.context_preview_timer = None

            # Add flag to track if we should show context-sensitive preview
            # This flag is set to True when a parameter is changed manually by the user
            # and reset to False after the preview completes or when starting
            # non-contextual operations
            self.should_show_context_preview = False

            if hasattr(self.controller, "image_processed"):
                self.controller.image_processed.connect(self._update_preview_image)

            else:
                logger.warning("Controller does not have image_processed signal")

            # Keep track of the last changed parameter type
            self.last_changed_param = None

            # Create UI
            self.create_widgets()

            # Load the folder list from controller after UI creation
            if hasattr(self.controller, "folder_paths"):
                self._update_folder_list(self.controller.folder_paths)

            else:
                logger.warning("Controller does not have folder_paths attribute")

            # Make sure main folder highlighting is applied
            self._update_main_folder_highlight()

            # Auto-trigger preview only if this widget is visible after initialization
            QTimer.singleShot(100, self._conditional_auto_preview)

            logger.info("AnalysisGUI initialization completed successfully")

        except Exception as e:
            logger.error(f"Failed to initialize AnalysisGUI: {e}")
            logger.error(f"Parent: {parent}")
            logger.error(f"Controller: {controller}")
            raise

        QTimer.singleShot(500, lambda: setattr(self, "is_initializing", False))
        logger.info("AnalysisGUI initialization completed")

    def _conditional_auto_preview(self):
        """Trigger auto-preview only if this analysis widget is currently visible.

        This prevents triggering previews for analysis modes that are not
        currently displayed when dwit starts.
        """
        # Check if this widget is visible by checking if it's the current page
        if self.isVisible() and self.parent():
            # Check if the parent's parent has a content stacked widget
            # and if this widget's page is currently active
            parent_widget = self.parent()
            while parent_widget:
                if hasattr(parent_widget, "content") and hasattr(
                    parent_widget.content, "currentWidget"
                ):
                    # Check if the current widget contains this analysis widget
                    current_widget = parent_widget.content.currentWidget()
                    if current_widget and self._is_widget_ancestor(
                        current_widget, self
                    ):
                        self.preview()
                        return
                parent_widget = parent_widget.parent()

    def _is_widget_ancestor(self, potential_ancestor, widget):
        """Check if potential_ancestor contains widget in its hierarchy."""
        if potential_ancestor == widget:
            return True
        if potential_ancestor == widget.parent():
            return True
        # Recursively check children
        for child in potential_ancestor.findChildren(type(widget)):
            if child == widget:
                return True
        return False

    def _update_preview_image(self, index: int, result_images: dict):
        """Update preview with the latest processed image."""
        if not result_images:
            return

        # Try to show image based on parameter type
        image_shown = self._show_parameter_specific_image(result_images)

        # Show fallback image if no specific image was shown
        if not image_shown:
            self._show_fallback_image(result_images)

        # Always update result canvas if available
        self._update_result_canvas(result_images)

        # Reset the context-sensitive preview flag after processing is complete
        # This ensures the preview dialog is only shown during parameter changes
        # Use a longer delay to keep preview open while user is actively changing
        if self.should_show_context_preview:
            # Cancel any existing timer to prevent premature reset
            if self.context_preview_timer:
                self.context_preview_timer.stop()

            # Set up a new timer with longer delay (2 seconds)
            if not self.context_preview_timer:
                self.context_preview_timer = QTimer()
                self.context_preview_timer.setSingleShot(True)
                self.context_preview_timer.timeout.connect(
                    lambda: setattr(self, "should_show_context_preview", False)
                )
            self.context_preview_timer.start(2000)  # 2 seconds delay

    def _show_parameter_specific_image(self, result_images: dict) -> bool:
        """Show image based on the last changed parameter type."""
        is_structured_packing = self.controller.analysis_mode == "structured_packing"

        if self.last_changed_param == "threshold":
            return self._show_threshold_image(result_images)
        elif self.last_changed_param == "roi":
            return self._show_roi_image(result_images, is_structured_packing)
        elif self.last_changed_param == "baseline":
            return self._show_baseline_image(result_images)
        elif self.last_changed_param == "rotation":
            return self._show_rotation_image(result_images, is_structured_packing)
        elif self.is_processing and "contour" in result_images:
            # Only show preview dialog if we're in context-sensitive mode
            if self.should_show_context_preview:
                show_preview(result_images["contour"], self)
            return True

        return False

    def _show_threshold_image(self, result_images: dict) -> bool:
        """Show threshold image if available."""
        logger.debug('Showing threshold image using "_show_threshold_image"')
        if "thresh" in result_images:
            # Only show preview dialog if we're in context-sensitive mode
            if self.should_show_context_preview:
                show_preview(result_images["thresh"], self)
            return True
        return False

    def _show_roi_image(self, result_images: dict, is_structured_packing: bool) -> bool:
        """Show ROI-related image based on analysis mode."""
        if is_structured_packing and "original_with_vertical" in result_images:
            # Only show preview dialog if we're in context-sensitive mode
            if self.should_show_context_preview:
                show_preview(result_images["original_with_vertical"], self)
            return True
        elif "original" in result_images:
            # Only show preview dialog if we're in context-sensitive mode
            if self.should_show_context_preview:
                show_preview(result_images["original"], self)
            return True
        return False

    def _show_baseline_image(self, result_images: dict) -> bool:
        """Show baseline image if available."""
        if "baseline" in result_images:
            # Only show preview dialog if we're in context-sensitive mode
            if self.should_show_context_preview:
                show_preview(result_images["baseline"], self)
            return True
        return False

    def _show_rotation_image(
        self, result_images: dict, is_structured_packing: bool
    ) -> bool:
        """Show rotation-related image based on analysis mode."""
        if is_structured_packing and "original_with_vertical" in result_images:
            # Only show preview dialog if we're in context-sensitive mode
            if self.should_show_context_preview:
                show_preview(result_images["original_with_vertical"], self)
            return True
        elif "original" in result_images:
            # Only show preview dialog if we're in context-sensitive mode
            if self.should_show_context_preview:
                show_preview(result_images["original"], self)
            return True
        return False

    def _show_fallback_image(self, result_images: dict) -> None:
        """Show fallback image if no parameter-specific image was shown."""
        fallback_keys = ["result", "contour", "baseline", "original", "fallback"]
        for key in fallback_keys:
            if key in result_images:
                # Only show preview dialog if we're in context-sensitive mode
                if self.should_show_context_preview:
                    show_preview(result_images[key], self)
                break

    def _update_result_canvas(self, result_images: dict) -> None:
        """Update the result canvas if result image is available."""
        if "result" in result_images:
            self.display_image_in_canvas(result_images["result"], self.canvas_result)

    def create_widgets(self) -> None:
        """Create all UI components."""
        try:
            # Main container

            self.frame = QWidget(self)
            self.main_layout = QVBoxLayout(self.frame)
            self.main_layout.setContentsMargins(0, 0, 0, 0)

            # Create action buttons and progress bar

            self._create_action_controls()

            # Create main content layout

            self._create_main_content_layout()

            # Apply to parent
            self._setup_parent_layout()

            # Add tooltips to all widgets after creation
            self._setup_all_tooltips()

            logger.info("Widget creation completed successfully")

        except Exception as e:
            logger.error(f"Failed to create widgets: {e}")
            raise

    def _create_main_content_layout(self) -> None:
        """Create the main content layout with parameters and preview areas."""
        # Fixed horizontal layout for parameters/settings and preview (no splitter)
        main_content = QWidget()
        main_content_layout = QHBoxLayout(main_content)
        main_content_layout.setContentsMargins(0, 0, 0, 0)

        # Parameters/settings area
        params_container = QWidget()
        self._create_parameter_section(params_container)
        params_container.setMinimumWidth(150)
        main_content_layout.addWidget(params_container)

        # Preview area
        preview_container = QWidget()
        self._create_preview_area(preview_container)
        preview_container.setMinimumWidth(400)
        main_content_layout.addWidget(preview_container, 1)

        # Add to main layout
        self.main_layout.addWidget(main_content, 1)

    def _setup_parent_layout(self) -> None:
        """Set up the parent layout configuration."""
        self.setLayout(QVBoxLayout())
        self.layout().setContentsMargins(0, 0, 0, 0)
        self.layout().addWidget(self.frame)

    def _setup_all_tooltips(self) -> None:
        """Set up tooltips for all widgets after creation."""
        self._setup_action_control_tooltips()
        self._setup_parameter_tooltips()
        self._setup_roi_control_tooltips()
        self._setup_preview_area_tooltips()
        self._setup_stats_section_tooltips()

    def _setup_action_control_tooltips(self) -> None:
        """Set up tooltips for action control widgets."""
        self.add_folders_btn.setToolTip(
            "Add one or more folders to the batch processing queue."
        )
        self.process_batch_btn.setToolTip(
            "Start processing all folders in the batch queue."
        )
        self.pause_resume_btn.setToolTip("Pause or resume the current processing.")
        self.stop_btn.setToolTip("Stop the current processing.")
        self.folder_list.setToolTip(
            "List of folders to process. Right-click for more options."
        )
        self.overall_progress.setToolTip(
            "Shows the overall progress of the current operation."
        )
        self.folder_counter.setToolTip(
            "Shows the number of processed folders out of total."
        )

    def _setup_parameter_tooltips(self) -> None:
        """Set up tooltips for parameter control widgets."""
        # Camera tooltips
        if hasattr(self, "PIXEL_entry"):
            self.PIXEL_entry.setToolTip("Set the pixel per mm (px/mm) for analysis.")
        if hasattr(self, "FPS_entry"):
            self.FPS_entry.setToolTip("Set the frames per second (FPS) for analysis.")

        # Threshold tooltips
        if hasattr(self, "threshold_entry"):
            self.threshold_entry.setToolTip(
                "Set the threshold value for image binarization."
            )

        # Adjustment tooltips
        if hasattr(self, "rotate_angle_entry"):
            self.rotate_angle_entry.setToolTip(
                "Set the rotation angle for image alignment."
            )
        if hasattr(self, "baseline_entry"):
            self.baseline_entry.setToolTip("Set the baseline offset for analysis.")

        # Manual baseline tooltips
        if hasattr(self, "Baseline_tf_checkbox"):
            self.Baseline_tf_checkbox.setToolTip(
                "Enable or disable manual baseline adjustment."
            )
        if hasattr(self, "manual_baseline_entry"):
            self.manual_baseline_entry.setToolTip("Set the manual baseline height.")

    def _setup_roi_control_tooltips(self) -> None:
        """Set up tooltips for ROI control widgets."""
        if hasattr(self, "left_roi_spinbox"):
            self.left_roi_spinbox.setToolTip(
                "Set the left boundary of the region of interest (ROI) in pixels."
            )
        if hasattr(self, "right_roi_spinbox"):
            self.right_roi_spinbox.setToolTip(
                "Set the right boundary of the region of interest (ROI) in pixels."
            )
        if hasattr(self, "top_roi_spinbox"):
            self.top_roi_spinbox.setToolTip(
                "Set the top boundary of the region of interest (ROI) in pixels."
            )
        if hasattr(self, "bottom_roi_spinbox"):
            self.bottom_roi_spinbox.setToolTip(
                "Set the bottom boundary of the region of interest (ROI) in pixels."
            )

    def _setup_preview_area_tooltips(self) -> None:
        """Set up tooltips for preview area widgets."""
        if hasattr(self, "canvas_result"):
            self.canvas_result.setToolTip(
                "Displays the result of the analysis or processing."
            )
        if hasattr(self, "frame_slider"):
            self.frame_slider.setToolTip(
                "Scroll through frames in the current preview or analysis."
            )

    def _setup_stats_section_tooltips(self) -> None:
        """Set up tooltips for statistics section widgets."""
        if hasattr(self, "adv_angle_label"):
            self.adv_angle_label.setToolTip("Shows the advancing contact angle.")
        if hasattr(self, "rec_angle_label"):
            self.rec_angle_label.setToolTip("Shows the receding contact angle.")
        if hasattr(self, "width_label"):
            self.width_label.setToolTip("Shows the measured width of the object in mm.")
        if hasattr(self, "height_label"):
            self.height_label.setToolTip(
                "Shows the measured height of the object in mm."
            )
        if hasattr(self, "center_label"):
            self.center_label.setToolTip("Shows the center position (X/Y) in pixels.")
        if hasattr(self, "velocity_value"):
            self.velocity_value.setToolTip("Shows the calculated velocity in mm/s.")

    def main(self) -> None:
        """Start main processing thread."""
        logger.info("Starting main analysis processing")
        # Check if already processing
        if self.is_processing:
            logger.warning("Analysis already in progress, ignoring request")
            return

        # Set processing flag
        self.is_processing = True

        # Set the preview_button and analyze_button as disabled
        #         self.analyze_button.setEnabled(False)
        #         self.preview_button.setEnabled(False)

        # Disable batch process button to prevent starting multiple processes
        #         self.process_batch_btn.setEnabled(False)
        #         self.add_folders_btn.setEnabled(False)

        # Disable folder context menu items during processing
        #         self.folder_list.setEnabled(False)

        # Enable pause/stop buttons
        #         self.pause_resume_btn.setEnabled(True)
        self.pause_resume_btn.setIcon(
            QIcon.fromTheme("media-playback-pause", QIcon(":/icons/pause.png"))
        )
        self.pause_resume_btn.setToolTip("Pause processing")
        #         self.stop_btn.setEnabled(True)

        self.overall_progress.setValue(0)  # Use overall_progress instead of progress

        # Update folder counter to show single file processing
        self.folder_counter.setText("Processing main folder...")

        # Reset last_changed_param when starting main analysis
        self.last_changed_param = None

        # Reset context-sensitive preview flag for main analysis
        self.should_show_context_preview = False

        # Clear previous preview images when starting a new run
        self.preview_images = {"original": [], "contour": [], "result": []}
        self.current_frame = 0
        self.total_frames = 0
        self.frame_slider.setMaximum(0)
        #         self.frame_slider.setEnabled(False)

        # Use the main folder for analysis if available,
        # otherwise use the current folder path
        folder_path = (
            self.controller.main_folder_path
            if self.controller.main_folder_path
            else self.controller.folder_path
        )

        # Set the current folder to the main folder if it's available
        if self.controller.main_folder_path:
            self.controller.set_folder_path(self.controller.main_folder_path)
            # Remove reference to non-existent folder_path_entry

        # Check if folder path exists
        if not folder_path or not os.path.isdir(folder_path):
            logger.error(f"Invalid or missing folder path: {folder_path}")
            #             self.analyze_button.setEnabled(True)
            #             self.preview_button.setEnabled(True)
            self.folder_counter.setText("0/0 folders")  # Reset folder counter
            #             self.pause_resume_btn.setEnabled(False)
            #             self.stop_btn.setEnabled(False)
            return

        logger.info(f"Creating analysis thread for folder: {folder_path}")
        # Create and configure the thread
        self.main_thread = AnalysisThread(
            self.controller,
            save_files=True,
            preview_middle=False,
            use_first_as_background=False,
        )

        self.main_thread.progress_signal.connect(self._update_stats)
        self.main_thread.finished_signal.connect(self._process_results)
        self.main_thread.error_signal.connect(self._handle_error)
        self.main_thread.finished.connect(self._enable_buttons)

        # Start the thread

        self.main_thread.start()

    def _auto_preview(self) -> None:
        """Triggered by timer to run preview after parameter changes."""
        # Only run if we have a valid folder and aren't already processing
        if (
            self.controller.folder_path
            and os.path.isdir(self.controller.folder_path)
            and self.analyze_button.isEnabled()
            and self.preview_button.isEnabled()
        ):
            self.preview()

    def _trigger_preview_update(self, param_type: Optional[str] = None) -> None:
        """Start the debounce timer to trigger preview update.

        Records parameter type.
        """
        # Skip all preview updates during initialization
        if getattr(self, "is_initializing", False):
            return

        # Store the parameter type that was changed
        self.last_changed_param = param_type
        logger.debug(f"Parameter changed: {param_type}")

        # Enable context-sensitive preview when a parameter is changed
        self.should_show_context_preview = True

        # Cancel any existing context preview timer to extend the preview duration
        if self.context_preview_timer:
            self.context_preview_timer.stop()

        # Show immediate preview dialog for different parameter types
        if param_type == "roi":
            self._show_roi_preview()
            # Reset the flag to prevent _show_roi_image from showing another preview
            self.should_show_context_preview = False
        elif param_type == "threshold":
            self._show_threshold_preview()
            self.should_show_context_preview = False
        elif param_type == "rotation":
            self._show_rotation_preview()
            self.should_show_context_preview = False
        elif param_type in ["baseline", "baseline_offset"]:
            self._show_baseline_preview()
            self.should_show_context_preview = False

        self.preview_timer.start()

    def _create_action_controls(self) -> None:
        """Create action buttons and controls."""
        # Add batch processing section - Removed GroupBox
        batch_widget = QWidget()
        batch_layout = QVBoxLayout(batch_widget)
        batch_layout.setContentsMargins(0, 0, 0, 0)

        # Create folder list widget with custom delegate for progress bars
        self.folder_list = QListWidget()
        self.folder_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.folder_list.setMinimumHeight(120)  # Increased from 80 to 120
        self.folder_list.setMaximumHeight(180)  # Increased from 120 to 180
        self.folder_delegate = FolderItemDelegate()
        self.folder_list.setItemDelegate(self.folder_delegate)
        self.folder_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.folder_list.customContextMenuRequested.connect(
            self._show_folder_context_menu
        )
        batch_layout.addWidget(self.folder_list)

        # Create buttons for batch processing in a single horizontal layout
        batch_buttons_layout = QHBoxLayout()

        self.add_folders_btn = QPushButton("Add Folders")
        self.add_folders_btn.clicked.connect(self.add_folders_to_batch)
        batch_buttons_layout.addWidget(self.add_folders_btn)

        # Add a single "Process All Folders" button
        self.process_batch_btn = QPushButton("Process All Folders")
        self.process_batch_btn.clicked.connect(self.process_all_folders)
        batch_buttons_layout.addWidget(self.process_batch_btn)

        # Create pause/resume button with icon
        self.pause_resume_btn = QPushButton()
        self.pause_resume_btn.setIcon(
            QIcon.fromTheme("media-playback-pause", QIcon(":/icons/pause.png"))
        )
        self.pause_resume_btn.setToolTip("Pause processing")
        #         self.pause_resume_btn.setEnabled(False)  # Disabled by default
        self.pause_resume_btn.clicked.connect(self._toggle_pause_resume)
        batch_buttons_layout.addWidget(self.pause_resume_btn)

        # Create stop button with icon
        self.stop_btn = QPushButton()
        self.stop_btn.setIcon(
            QIcon.fromTheme("media-playback-stop", QIcon(":/icons/stop.png"))
        )
        self.stop_btn.setToolTip("Stop processing")
        #         self.stop_btn.setEnabled(False)  # Disabled by default
        self.stop_btn.clicked.connect(self._stop_processing)
        batch_buttons_layout.addWidget(self.stop_btn)

        batch_layout.addLayout(batch_buttons_layout)

        overall_progress_layout = QHBoxLayout()
        overall_progress_layout.setContentsMargins(0, 0, 0, 0)

        # Add overall progress bar
        self.overall_progress = QProgressBar()
        self.overall_progress.setRange(0, 100)
        self.overall_progress.setValue(0)
        overall_progress_layout.addWidget(self.overall_progress)

        # Add folder counter label
        self.folder_counter = QLabel("0/0 folders")
        self.folder_counter.setMinimumWidth(80)
        overall_progress_layout.addWidget(self.folder_counter)

        batch_layout.addLayout(overall_progress_layout)

        self.main_layout.addWidget(batch_widget)

        # Create attributes for buttons that were removed
        # so other code can reference them
        self.preview_button = QPushButton()
        self.analyze_button = QPushButton()

    def _toggle_pause_resume(self):
        """Toggle between pause and resume states."""
        if self.pause_resume_btn.toolTip() == "Pause processing":
            self._pause_processing()
        else:
            self._resume_processing()

    def _pause_processing(self):
        """Pause the current processing."""
        # Check which thread is running and pause it
        if self.main_thread and self.main_thread.isRunning():
            self.main_thread.pause()
        elif (
            hasattr(self, "batch_thread")
            and self.batch_thread
            and self.batch_thread.isRunning()
        ):
            self.batch_worker.pause()

        # Update button icon and tooltip
        self.pause_resume_btn.setIcon(
            QIcon.fromTheme("media-playback-start", QIcon(":/icons/play.png"))
        )
        self.pause_resume_btn.setToolTip("Resume processing")

    def _resume_processing(self):
        """Resume the paused processing."""
        # Check which thread is running and resume it
        if self.main_thread and self.main_thread.isRunning():
            self.main_thread.resume()
        elif (
            hasattr(self, "batch_thread")
            and self.batch_thread
            and self.batch_thread.isRunning()
        ):
            self.batch_worker.resume()

        # Update button icon and tooltip
        self.pause_resume_btn.setIcon(
            QIcon.fromTheme("media-playback-pause", QIcon(":/icons/pause.png"))
        )
        self.pause_resume_btn.setToolTip("Pause processing")

    def _stop_processing(self):
        """Stop the current processing."""
        # Check which thread is running and stop it
        if self.main_thread and self.main_thread.isRunning():
            self.main_thread.stop()
        elif (
            hasattr(self, "batch_thread")
            and self.batch_thread
            and self.batch_thread.isRunning()
        ):
            self.batch_worker.stop()

    def _create_parameter_section(self, parent_widget=None) -> None:
        """Create parameter configuration area with vertical layout."""
        # Main parameters container
        params_widget = parent_widget or QWidget()
        params_layout = QVBoxLayout(params_widget)
        params_layout.setContentsMargins(0, 0, 0, 0)

        # Camera settings
        camera_items = [
            (
                "FPS",
                "spinbox",
                {
                    "min": 1,
                    "max": 1000,
                    "value": self.controller.fps,
                    "attr_name": "FPS_entry",
                    "setter": self.controller.set_fps,
                    "param_type": "camera",
                },
            ),
            (
                "Pixel",
                "doublespinbox",
                {
                    "min": 0,
                    "max": 100,
                    "step": 0.01,
                    "value": self.controller.pixel,
                    "attr_name": "PIXEL_entry",
                    "setter": self.controller.set_pixel,
                    "param_type": "camera",
                },
            ),
        ]
        camera_group = self._create_group_with_grid(
            "Camera", camera_items, spinbox_width=120
        )
        params_layout.addWidget(camera_group)

        # Add horizontal separator
        separator1 = QFrame()
        separator1.setFrameShape(QFrame.HLine)
        separator1.setFrameShadow(QFrame.Sunken)
        separator1.setLineWidth(1)
        params_layout.addWidget(separator1)

        # Threshold settings
        min_val = self.controller.threshold
        threshold_items = [
            (
                "Threshold",
                "spinbox",
                {
                    "min": 0,
                    "max": 255,
                    "value": min_val,
                    "attr_name": "threshold_entry",
                    "setter": self.controller.set_threshold,
                    "auto_preview": True,
                    "param_type": "threshold",
                },
            ),
        ]
        threshold_group = self._create_group_with_grid(
            "Threshold", threshold_items, spinbox_width=120
        )
        params_layout.addWidget(threshold_group)

        # Add horizontal separator
        self.separator2 = QFrame()
        self.separator2.setFrameShape(QFrame.HLine)
        self.separator2.setFrameShadow(QFrame.Sunken)
        self.separator2.setLineWidth(1)
        params_layout.addWidget(self.separator2)

        # Image adjustment settings
        adjustments_items = [
            (
                "Rotate",
                "doublespinbox",
                {
                    "min": -360,
                    "max": 360,
                    "step": 0.1,
                    "value": self.controller.rotate_angle,
                    "attr_name": "rotate_angle_entry",
                    "setter": self.controller.set_rotate_angle,
                    "auto_preview": True,
                    "param_type": "rotation",
                },
            ),
            (
                "Baseline",
                "spinbox",
                {
                    "min": -1000,
                    "max": 1000,
                    "value": self.controller.baseline,
                    "attr_name": "baseline_entry",
                    "setter": self.controller.set_baseline,
                    "auto_preview": True,
                    "param_type": "baseline_offset",
                },
            ),
        ]
        self.adjustments_group = self._create_group_with_grid(
            "Adjustments", adjustments_items, spinbox_width=120
        )
        params_layout.addWidget(self.adjustments_group)

        # Add horizontal separator
        self.separator3 = QFrame()
        self.separator3.setFrameShape(QFrame.HLine)
        self.separator3.setFrameShadow(QFrame.Sunken)
        self.separator3.setLineWidth(1)
        params_layout.addWidget(self.separator3)

        # Manual baseline settings
        baseline_items = [
            (
                "Enable",
                "checkbox",
                {
                    "value": self.controller.baseline_tf,
                    "attr_name": "Baseline_tf_checkbox",
                    "setter": self.controller.set_baseline_tf,
                    "callback": self._on_baseline_checkbox_change,
                    "auto_preview": True,
                    "param_type": "baseline",
                },
            ),
            (
                "Height",
                "spinbox",
                {
                    "min": 0,
                    "max": 1000,
                    "value": self.controller.manual_baseline,
                    "attr_name": "manual_baseline_entry",
                    "setter": self.controller.set_manual_baseline,
                    "auto_preview": True,
                    "param_type": "baseline",
                },
            ),
        ]
        self.manual_baseline_group = self._create_group_with_grid(
            "Manual Baseline", baseline_items, spinbox_width=120
        )
        params_layout.addWidget(self.manual_baseline_group)

        # Add horizontal separator
        self.separator4 = QFrame()
        self.separator4.setFrameShape(QFrame.HLine)
        self.separator4.setFrameShadow(QFrame.Sunken)
        self.separator4.setLineWidth(1)
        params_layout.addWidget(self.separator4)

        # Fitting items
        fitting_items = [
            (
                "Mode",
                "combobox",
                {
                    "items": ["Arc", "Tangent", "Polynom", "Ellipse"],
                    "value": self.controller.fitting_mode,
                    "attr_name": "polynom_entry",
                    "setter": self.controller.set_fitting_mode,
                    "param_type": "fitting",
                },
            ),
            (
                "Deg.",
                "spinbox",
                {
                    "min": 1,
                    "max": 10,
                    "value": self.controller.polynom,
                    "attr_name": "polynom_entry_spin",
                    "setter": self.controller.set_polynom,
                    "auto_preview": True,
                    "param_type": "fitting",
                },
            ),
        ]
        self.fitting_group = self._create_group_with_grid(
            "Fitting", fitting_items, spinbox_width=120
        )
        params_layout.addWidget(self.fitting_group)

        # Add thicker horizontal separator
        self.separator5 = QFrame()
        self.separator5.setFrameShape(QFrame.HLine)
        self.separator5.setFrameShadow(QFrame.Sunken)
        self.separator5.setLineWidth(2)  # Thicker line
        self.separator5.setMidLineWidth(1)
        params_layout.addWidget(self.separator5)

        # ROI settings - without the title
        roi_widget = QWidget()
        roi_layout = QVBoxLayout(roi_widget)
        roi_layout.setContentsMargins(0, 0, 0, 0)

        # Create select ROI button
        roi_button = QPushButton("Select ROI Visually")
        roi_button.setToolTip("Select region of interest visually")
        roi_button.clicked.connect(self.open_roi_selector)
        roi_layout.addWidget(roi_button)  # Moved ROI button down

        # Width group (Left/Right)
        width_group = QWidget()
        width_layout = QGridLayout(width_group)
        width_layout.setContentsMargins(0, 0, 0, 0)

        # Left spinbox
        left_label = QLabel("Left:")
        self.left_roi_spinbox = QSpinBox()
        self.left_roi_spinbox.setSingleStep(20)
        self.left_roi_spinbox.setSuffix(" px")  # Add px suffix
        self.left_roi_spinbox.setFixedWidth(120)  # Set fixed width
        self.left_roi_spinbox.valueChanged.connect(self.controller.set_x_img)
        self.left_roi_spinbox.valueChanged.connect(
            lambda value: self._trigger_preview_update("roi")
        )
        width_layout.addWidget(left_label, 0, 0)
        width_layout.addWidget(self.left_roi_spinbox, 0, 1)

        # Right spinbox
        right_label = QLabel("Right:")
        self.right_roi_spinbox = QSpinBox()
        self.right_roi_spinbox.setSingleStep(20)
        self.right_roi_spinbox.setSuffix(" px")  # Add px suffix
        self.right_roi_spinbox.setFixedWidth(120)  # Set fixed width
        self.right_roi_spinbox.valueChanged.connect(self.controller.set_w_img)
        self.right_roi_spinbox.valueChanged.connect(
            lambda value: self._trigger_preview_update("roi")
        )
        width_layout.addWidget(right_label, 1, 0)
        width_layout.addWidget(self.right_roi_spinbox, 1, 1)

        # Height group (Top/Bottom)
        height_group = QWidget()
        height_layout = QGridLayout(height_group)
        height_layout.setContentsMargins(0, 0, 0, 0)

        # Top spinbox
        top_label = QLabel("Top:")
        self.top_roi_spinbox = QSpinBox()
        self.top_roi_spinbox.setSingleStep(20)
        self.top_roi_spinbox.setSuffix(" px")  # Add px suffix
        self.top_roi_spinbox.setFixedWidth(120)  # Set fixed width
        self.top_roi_spinbox.valueChanged.connect(self.controller.set_y_img)
        self.top_roi_spinbox.valueChanged.connect(
            lambda value: self._trigger_preview_update("roi")
        )
        height_layout.addWidget(top_label, 0, 0)
        height_layout.addWidget(self.top_roi_spinbox, 0, 1)

        # Bottom spinbox
        bottom_label = QLabel("Bottom:")
        self.bottom_roi_spinbox = QSpinBox()
        self.bottom_roi_spinbox.setSingleStep(20)
        self.bottom_roi_spinbox.setSuffix(" px")  # Add px suffix
        self.bottom_roi_spinbox.setFixedWidth(120)  # Set fixed width
        self.bottom_roi_spinbox.valueChanged.connect(self.controller.set_h_img)
        self.bottom_roi_spinbox.valueChanged.connect(
            lambda value: self._trigger_preview_update("roi")
        )
        height_layout.addWidget(bottom_label, 1, 0)
        height_layout.addWidget(self.bottom_roi_spinbox, 1, 1)

        # Add groups to ROI layout
        roi_layout.addWidget(width_group)
        roi_layout.addWidget(height_group)

        params_layout.addWidget(roi_widget)

        # Add stretch to push all widgets to the top
        params_layout.addStretch(1)

        # Initialize ROI spinboxes with values from controller
        self._initialize_roi_spinboxes()

        # Initialize UI states
        self._on_baseline_checkbox_change()

        # Conditionally hide adjustments and manual baseline for certain modes
        if self.controller.analysis_mode in [
            "free_sedimentation",
            "structured_packing",
        ]:
            if hasattr(self, "adjustments_group"):
                self.adjustments_group.hide()
            if hasattr(self, "separator3"):
                # Make sure to add the created widget to the parent layout
                self.separator3.hide()
            if hasattr(self, "fitting_group"):
                self.fitting_group.hide()
            if hasattr(self, "separator4"):
                self.separator4.hide()
            if hasattr(self, "manual_baseline_group"):
                self.manual_baseline_group.hide()
            if hasattr(self, "separator5"):
                self.separator5.hide()

        if parent_widget is None:
            self.main_layout.addWidget(params_widget)

    def preview(self) -> None:
        """Start preview processing thread.

        Uses average background for the middle image analysis.
        """
        logger.info("Starting preview processing")
        # Check if already processing
        if self.is_processing:
            logger.warning("Processing already in progress, ignoring preview request")
            return

        # Set processing flag
        self.is_processing = True

        # Set the preview_button and analyze_button as disabled
        #         self.preview_button.setEnabled(False)
        #         self.analyze_button.setEnabled(False)

        # Disable batch process button to prevent starting multiple processes
        #         self.process_batch_btn.setEnabled(False)
        #         self.add_folders_btn.setEnabled(False)

        # Disable folder context menu items during processing
        #         self.folder_list.setEnabled(False)

        # Enable pause/stop buttons for preview too
        #         self.pause_resume_btn.setEnabled(True)
        self.pause_resume_btn.setIcon(
            QIcon.fromTheme("media-playback-pause", QIcon(":/icons/pause.png"))
        )
        self.pause_resume_btn.setToolTip("Pause processing")
        #         self.stop_btn.setEnabled(True)

        self.overall_progress.setValue(0)  # Use overall_progress instead of progress

        # Update folder counter to show preview processing
        self.folder_counter.setText("Processing preview...")

        # Save current parameter type before starting preview
        saved_param_type = self.last_changed_param
        # Force showing results for preview button
        self.last_changed_param = "preview"

        # If this preview is NOT called from _auto_preview (parameter change),
        # then disable context-sensitive preview
        if not self.should_show_context_preview:
            # This is a manual preview call, not from parameter change
            self.should_show_context_preview = False

        # Use the main folder for analysis if available,
        # otherwise use the current folder path
        folder_path = (
            self.controller.main_folder_path
            if self.controller.main_folder_path
            else self.controller.folder_path
        )

        # Set the current folder to the main folder if it's available
        if self.controller.main_folder_path:
            self.controller.set_folder_path(self.controller.main_folder_path)
            # No need to update folder_path_entry since it doesn't exist

        # Check if folder path exists
        if not folder_path or not os.path.isdir(folder_path):
            logger.error(f"Invalid or missing folder path for preview: {folder_path}")
            #             self.analyze_button.setEnabled(True)
            #             self.preview_button.setEnabled(True)
            self.folder_counter.setText("0/0 folders")  # Reset folder counter
            #             self.pause_resume_btn.setEnabled(False)
            #             self.stop_btn.setEnabled(False)
            return

        logger.info(f"Creating preview thread for folder: {folder_path}")
        # Create and configure the thread
        self.preview_thread = AnalysisThread(
            self.controller,
            save_files=False,
            preview_middle=True,
            use_first_as_background=False,
        )  # Changed to False to create average background

        self.preview_thread.progress_signal.connect(
            lambda q, a, r, c, result_images, result_lists=None: (
                self._update_stats_with_param(
                    q, a, r, c, result_images, result_lists, saved_param_type
                )
            )
        )
        self.preview_thread.error_signal.connect(self._handle_error)
        self.preview_thread.finished.connect(self._enable_buttons)

        # Start the thread

        self.preview_thread.start()

    def _initialize_roi_spinboxes(self):
        """Initialize ROI spinboxes with values from the controller."""
        # Block signals BEFORE setting ranges to prevent triggering valueChanged
        # when range changes force value adjustments
        self.left_roi_spinbox.blockSignals(True)
        self.right_roi_spinbox.blockSignals(True)
        self.top_roi_spinbox.blockSignals(True)
        self.bottom_roi_spinbox.blockSignals(True)

        # Set ranges based on image dimensions (or defaults if no image available)
        self._update_roi_ranges_from_image()

        # Set values from controller
        self.left_roi_spinbox.setValue(self.controller.x_img)
        self.right_roi_spinbox.setValue(self.controller.w_img)
        self.top_roi_spinbox.setValue(self.controller.y_img)
        self.bottom_roi_spinbox.setValue(self.controller.h_img)

        # Re-enable signals
        self.left_roi_spinbox.blockSignals(False)
        self.right_roi_spinbox.blockSignals(False)
        self.top_roi_spinbox.blockSignals(False)
        self.bottom_roi_spinbox.blockSignals(False)

    def open_roi_selector(self):
        """Open the ROI selector dialog with the middle image from the folder.

        Limits ROI spinboxes to rotated image size.
        """
        logger.info("Opening ROI selector dialog")
        # Check if we have a valid folder path
        if not self.controller.folder_path or not os.path.isdir(
            self.controller.folder_path
        ):
            logger.warning("No valid folder path for ROI selection")
            return

        # Find all images in the folder
        image_extensions = ["*.jpg", "*.jpeg", "*.png", "*.bmp", "*.tiff"]
        image_files = []
        for ext in image_extensions:
            image_files.extend(
                glob.glob(os.path.join(self.controller.folder_path, ext))
            )

        if not image_files:
            logger.warning("No images found in folder for ROI selection")
            return

        # Sort files and get the middle one
        image_files.sort()
        middle_idx = len(image_files) // 2
        middle_image = image_files[middle_idx]

        # Get rotation angle from controller
        rotation_angle = (
            self.controller.rotate_angle
            if hasattr(self.controller, "rotate_angle")
            else 0.0
        )

        # Load and rotate the image to get its size
        orig_img = cv2.imread(middle_image)

        temp_roi_image = rotate_image(orig_img, rotation_angle)

        # Limit spinboxes to rotated image size
        self.left_roi_spinbox.setRange(0, temp_roi_image.shape[1] - 1)
        self.right_roi_spinbox.setRange(1, temp_roi_image.shape[1])
        self.top_roi_spinbox.setRange(0, temp_roi_image.shape[0] - 1)
        self.bottom_roi_spinbox.setRange(1, temp_roi_image.shape[0])

        # Clamp current values to new bounds
        self.left_roi_spinbox.setValue(
            min(max(self.controller.x_img, 0), temp_roi_image.shape[1] - 1)
        )
        self.right_roi_spinbox.setValue(
            min(max(self.controller.w_img, 1), temp_roi_image.shape[1])
        )
        self.top_roi_spinbox.setValue(
            min(max(self.controller.y_img, 0), temp_roi_image.shape[0] - 1)
        )
        self.bottom_roi_spinbox.setValue(
            min(max(self.controller.h_img, 1), temp_roi_image.shape[0])
        )

        # Create and show the ROI selector
        roi_dialog = ROISelector(self, middle_image, rotation_angle)
        roi_dialog.set_roi(
            self.left_roi_spinbox.value(),
            self.top_roi_spinbox.value(),
            self.right_roi_spinbox.value(),
            self.bottom_roi_spinbox.value(),
        )

        # Connect the signal
        roi_dialog.roi_selected.connect(self.apply_selected_roi)

        # Show the dialog modally
        roi_dialog.exec()

    def apply_selected_roi(self, left, top, right, bottom):
        """Apply the selected ROI to the controller."""
        logger.info(
            "Applying selected ROI: left=%s, top=%s, right=%s, bottom=%s",
            left,
            top,
            right,
            bottom,
        )
        # Update the controller values
        self.controller.set_h_img(bottom)  # Bottom
        self.controller.set_w_img(right)  # Right
        self.controller.set_y_img(top)  # Top
        self.controller.set_x_img(left)  # Left

        # Update spinboxes
        self.left_roi_spinbox.blockSignals(True)
        self.top_roi_spinbox.blockSignals(True)
        self.right_roi_spinbox.blockSignals(True)
        self.bottom_roi_spinbox.blockSignals(True)

        self.left_roi_spinbox.setValue(left)
        self.top_roi_spinbox.setValue(top)
        self.right_roi_spinbox.setValue(right)
        self.bottom_roi_spinbox.setValue(bottom)

        self.left_roi_spinbox.blockSignals(False)
        self.top_roi_spinbox.blockSignals(False)
        self.right_roi_spinbox.blockSignals(False)
        self.bottom_roi_spinbox.blockSignals(False)

        # Trigger preview update with 'roi' as the parameter type
        self._trigger_preview_update("roi")

    def _show_roi_preview(self):
        """Show the ROI preview dialog with current ROI settings."""
        try:
            # Check if we have a valid folder path
            if not self.controller.folder_path or not os.path.isdir(
                self.controller.folder_path
            ):
                return

            # Find all images in the folder
            image_extensions = ["*.jpg", "*.jpeg", "*.png", "*.bmp", "*.tiff"]
            image_files = []
            for ext in image_extensions:
                image_files.extend(
                    glob.glob(os.path.join(self.controller.folder_path, ext))
                )

            if not image_files:
                return

            # Sort files and get the middle one (same as ROI selector)
            image_files.sort()
            middle_idx = len(image_files) // 2
            middle_image = image_files[middle_idx]

            # Load the image as numpy array
            image = cv2.imread(middle_image)
            if image is None:
                return

            # Apply rotation if specified in controller
            rotation_angle = getattr(self.controller, "rotate_angle", 0.0)
            image = rotate_image(image, rotation_angle)

            # Draw ROI rectangle on the rotated image
            roi_left = self.controller.x_img
            roi_top = self.controller.y_img
            roi_right = self.controller.w_img
            roi_bottom = self.controller.h_img

            # Make a copy of the image to draw on
            image_with_roi = image.copy()

            # Draw ROI rectangle in red
            cv2.rectangle(
                image_with_roi,
                (roi_left, roi_top),
                (roi_right, roi_bottom),
                (0, 0, 255),  # Red color in BGR format
                2,  # Line thickness
            )

            # Show the ROI preview with the rotated image and ROI overlay
            show_preview(image_with_roi, self)

        except Exception as e:
            logger.error(f"Error showing ROI preview: {e}")
            pass

    def _show_threshold_preview(self):
        """Show threshold preview with background subtraction like in normal process."""
        logger.debug('Showing threshold preview using "_show_threshold_preview"')
        try:
            # Get the processed image (rotated and cropped)
            image = self._get_processed_image()
            if image is None:
                return

            # Create background image like in normal process
            background = self._create_background_for_preview()
            if background is None:
                return

            # Ensure both images have the same shape and channels
            if image.shape != background.shape:
                # Resize background to match image
                background = cv2.resize(background, (image.shape[1], image.shape[0]))
                # Match channels if needed
                if image.shape[2] != background.shape[2]:
                    if background.shape[2] == 1 and image.shape[2] == 3:
                        background = cv2.cvtColor(background, cv2.COLOR_GRAY2BGR)
                    elif background.shape[2] == 3 and image.shape[2] == 1:
                        image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)

            # Apply background subtraction and threshold like in normal process
            diff = cv2.absdiff(image, background)
            gray = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)
            gray = cv2.GaussianBlur(gray, (5, 5), 0)
            _, thresh_image = cv2.threshold(
                gray, self.controller.threshold, 255, cv2.THRESH_BINARY
            )

            # Show the threshold preview
            show_preview(thresh_image, self)

        except Exception as e:
            logger.error(f"Error showing threshold preview: {e}")

    def _show_rotation_preview(self):
        """Show rotation preview with orientation lines."""
        try:
            # Get the original image and apply rotation
            image = self._get_original_image()
            if image is None:
                return

            rotation_angle = getattr(self.controller, "rotate_angle", 0.0)
            rotated_image = rotate_image(image, rotation_angle)

            # Draw orientation lines
            h, w = rotated_image.shape[:2]
            line_image = rotated_image.copy()

            # Draw subtle vertical lines (every 5% of width)
            for i in range(1, 20):  # 20 vertical lines
                x = int(w * i / 20)
                cv2.line(line_image, (x, 0), (x, h), (100, 100, 100), 1)

            # Draw subtle horizontal lines (every 5% of height)
            for i in range(1, 20):  # 20 horizontal lines
                y = int(h * i / 20)
                cv2.line(line_image, (0, y), (w, y), (100, 100, 100), 1)

            # Show the rotation preview
            show_preview(line_image, self)

        except Exception as e:
            logger.error(f"Error showing rotation preview: {e}")
            pass

    def _show_baseline_preview(self):
        """Show baseline preview with rotated, cropped image and proper baseline."""
        try:
            logger.info(
                f"Showing baseline preview, baseline_tf={self.controller.baseline_tf}, "
                f"baseline_offset={self.controller.baseline}, "
                f"manual_baseline={self.controller.manual_baseline}"
            )

            # Get the processed image (rotated and cropped)
            image = self._get_processed_image()
            if image is None:
                logger.warning("Could not get processed image for baseline preview")
                return

            # Get image dimensions
            img_h, img_w = image.shape[:2]

            # Calculate baseline like in normal process
            if self.controller.baseline_tf:
                # Manual baseline mode - use manual_baseline directly
                baseline_y = img_h - self.controller.manual_baseline
                logger.info(
                    f"Manual baseline at y={baseline_y}, "
                    f"manual_offset={self.controller.manual_baseline}"
                )
            else:
                # Automatic baseline detection with offset
                baseline_result = find_single_baseline(
                    image,
                    baseline_offset=self.controller.baseline,
                    baseline_tf=False,
                    manual_offset=0,
                )

                if isinstance(baseline_result, tuple):
                    # Returns (y1_left, y1_right)
                    baseline_y = baseline_result[0]
                else:
                    # Returns single value
                    baseline_y = baseline_result

                if baseline_y is not None:
                    # Apply the baseline offset
                    baseline_y = baseline_y + self.controller.baseline
                    logger.info(
                        f"Automatic baseline at y={baseline_y}, "
                        f"offset={self.controller.baseline}"
                    )

            # Draw baseline on image
            baseline_image = image.copy()
            if len(baseline_image.shape) == 2:  # Convert grayscale to color
                baseline_image = cv2.cvtColor(baseline_image, cv2.COLOR_GRAY2BGR)

            # Draw baseline in red if we have a valid baseline
            if baseline_y is not None:
                cv2.line(
                    baseline_image,
                    (0, int(baseline_y)),
                    (img_w, int(baseline_y)),
                    (0, 0, 255),
                    2,
                )

            # Show the baseline preview
            show_preview(baseline_image, self)

        except Exception as e:
            logger.error(f"Error showing baseline preview: {e}")
            pass

    def _get_original_image(self):
        """Get the original middle image from the folder."""
        try:
            if not self.controller.folder_path or not os.path.isdir(
                self.controller.folder_path
            ):
                return None

            # Find all images in the folder
            image_extensions = ["*.jpg", "*.jpeg", "*.png", "*.bmp", "*.tiff"]
            image_files = []
            for ext in image_extensions:
                image_files.extend(
                    glob.glob(os.path.join(self.controller.folder_path, ext))
                )

            if not image_files:
                return None

            # Sort files and get the middle one
            image_files.sort()
            middle_idx = len(image_files) // 2
            middle_image = image_files[middle_idx]

            # Load the image
            image = cv2.imread(middle_image)
            return image

        except Exception as e:
            logger.error(f"Error loading original image: {e}")
            return None

    def _get_processed_image(self):
        """Get the processed image (rotated and cropped)."""
        try:
            # Get original image
            image = self._get_original_image()
            if image is None:
                return None

            # Apply rotation
            rotation_angle = getattr(self.controller, "rotate_angle", 0.0)
            if rotation_angle != 0.0:
                image = rotate_image(image, rotation_angle)

            # Apply cropping
            crop_params = (
                self.controller.x_img,
                self.controller.w_img,
                self.controller.y_img,
                self.controller.h_img,
            )
            image = crop_image(image, crop_params)

            return image

        except Exception as e:
            logger.error(f"Error processing image: {e}")
            return None

    def _create_background_for_preview(self):
        """Create background image for preview using same method as normal process."""
        try:
            if not self.controller.folder_path or not os.path.isdir(
                self.controller.folder_path
            ):
                return None

            # Find all images in the folder
            image_extensions = ["*.jpg", "*.jpeg", "*.png", "*.bmp", "*.tiff"]
            image_files = []
            for ext in image_extensions:
                image_files.extend(
                    glob.glob(os.path.join(self.controller.folder_path, ext))
                )

            if not image_files:
                return None

            # Sort files
            image_files.sort()

            # Create background image using the same method as normal process
            background = create_background_image(
                image_files,
                use_first_as_background=False,  # Use average background
                rotate_angle=self.controller.rotate_angle,
                crop_params=(
                    self.controller.x_img,
                    self.controller.w_img,
                    self.controller.y_img,
                    self.controller.h_img,
                ),
            )

            return background

        except Exception as e:
            logger.error(f"Error creating background for preview: {e}")
            return None

    def _create_preview_area(self, parent_widget=None) -> None:
        """Create the image preview area with canvases stacked vertically."""
        # Use parent widget if provided, otherwise create new
        preview_widget = parent_widget or QWidget()

        # Create layout for the widget
        preview_layout = QVBoxLayout(preview_widget)
        preview_layout.setContentsMargins(0, 0, 0, 0)

        self.canvas_result = QLabel()
        self.canvas_result.setMinimumSize(400, 140)
        self.canvas_result.setAlignment(Qt.AlignCenter)
        self.canvas_result.setText("Result")
        self.canvas_result.setFrameShape(QFrame.Box)
        self.canvas_result.setFrameShadow(QFrame.Sunken)
        self.canvas_result.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # Add canvases to layout with equal stretch factors
        preview_layout.addWidget(self.canvas_result)

        # Create frame slider container
        slider_container = QWidget()
        slider_layout = QHBoxLayout(slider_container)
        slider_layout.setContentsMargins(0, 0, 0, 0)

        # Create frame slider with reversed direction
        self.frame_slider = QSlider(Qt.Horizontal)
        self.frame_slider.setMinimum(0)
        self.frame_slider.setMaximum(0)  # Will be updated when images are loaded
        #         self.frame_slider.setEnabled(False)  # Disabled by default
        self.frame_slider.valueChanged.connect(self._on_frame_changed)
        self.frame_slider.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        # Add slider and counter to container
        slider_layout.addWidget(self.frame_slider)

        # Add slider container to preview layout
        preview_layout.addWidget(slider_container)

        # Add statistics section directly underneath the preview images
        stats_frame = self._create_stats_section()
        preview_layout.addWidget(stats_frame)

        # If parent_widget was not provided, add to main layout
        if not parent_widget:
            self.main_layout.addWidget(preview_widget, 1)

    def _on_frame_changed(self, value: int) -> None:
        """Handle frame slider value change."""
        if 0 <= value < len(self.preview_images["original"]):
            self.current_frame = value
            self._update_frame_display()

    def _update_frame_display(self) -> None:
        """Update all preview canvases with current frame."""
        if self.current_frame < len(self.preview_images["original"]):
            self.display_image_in_canvas(
                self.preview_images["result"][self.current_frame], self.canvas_result
            )

    def _create_stats_section(self) -> QFrame:
        """Create statistics display area and return the frame."""
        # Create main container
        stats_frame = QFrame()
        stats_layout = QHBoxLayout(stats_frame)
        stats_layout.setContentsMargins(0, 0, 0, 0)

        # Create three evenly distributed stats panels - Removed GroupBoxes
        self.stats_panels = {}

        # Contact angle panel - evenly distributed (1/3 of width)
        contact_panel = QWidget()
        contact_layout = QVBoxLayout(contact_panel)
        contact_layout.setContentsMargins(0, 0, 0, 0)

        self.adv_angle_label = QLabel("<b>Advancing angle:</b> -- °")
        self.rec_angle_label = QLabel("<b>Receding angle:</b> -- °")

        contact_layout.addWidget(self.adv_angle_label)
        contact_layout.addWidget(self.rec_angle_label)
        self.stats_panels["contact"] = contact_panel

        # Width/Height panel - evenly distributed (1/3 of width)
        dimensions_panel = QWidget()
        dimensions_layout = QVBoxLayout(dimensions_panel)
        dimensions_layout.setContentsMargins(0, 0, 0, 0)

        self.width_label = QLabel("<b>Width:</b> -- mm")
        self.height_label = QLabel("<b>Height:</b> -- mm")

        dimensions_layout.addWidget(self.width_label)
        dimensions_layout.addWidget(self.height_label)
        self.stats_panels["dimensions"] = dimensions_panel

        # Position panel - evenly distributed (1/3 of width)
        position_panel = QWidget()
        position_layout = QVBoxLayout(position_panel)
        position_layout.setContentsMargins(0, 0, 0, 0)

        # Combine center X and Y into one line
        self.center_label = QLabel("<b>Center (X/Y):</b> (--/--)")
        self.velocity_value = QLabel("<b>Velocity:</b> -- mm/s")

        position_layout.addWidget(self.center_label)
        position_layout.addWidget(self.velocity_value)
        self.stats_panels["position"] = position_panel

        # Add all panels with stretch factors for even distribution
        stats_layout.addWidget(contact_panel, 1)
        stats_layout.addWidget(dimensions_panel, 1)
        stats_layout.addWidget(position_panel, 1)

        # Make labels wider to fit more content
        for panel in self.stats_panels.values():
            for i in range(panel.layout().count()):
                widget = panel.layout().itemAt(i).widget()
                if isinstance(widget, QLabel) and widget.text() not in [
                    "<b>Contact Angles</b>",
                    "<b>Width & Height</b>",
                    "<b>Position</b>",
                ]:
                    widget.setMinimumWidth(160)

        # Return the frame instead of adding it to main_layout
        return stats_frame

    def _create_group_with_grid(
        self,
        title: str,
        items: list[tuple[str, str, dict[str, Any]]],
        spinbox_width: int = 70,
        grid_layout: QGridLayout = None,
    ) -> QWidget:
        """Create a widget with a grid of labeled controls."""
        widget = QWidget()
        layout = grid_layout or QGridLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        label_tooltips = self._get_label_tooltips()

        for row, (label_text, control_type, config) in enumerate(items):
            # Create and configure label
            label = self._create_control_label(label_text, label_tooltips)
            layout.addWidget(label, row, 0)

            # Create appropriate control based on type
            control = self._create_control_by_type(
                control_type, config, label_text, title
            )

            # Configure control appearance and behavior
            self._configure_control(control, config, spinbox_width)
            layout.addWidget(control, row, 1)

        return widget

    def _get_label_tooltips(self) -> dict[str, str]:
        """Get tooltip mapping for control labels."""
        return {
            # Camera
            "FPS": "Frames per second for analysis.",
            "Pixel": "Pixel size for analysis (in px/mm).",
            # Threshold
            "Threshold": "Threshold value for image binarization.",
            # Adjustments
            "Rotate": "Rotation angle for image alignment.",
            "Baseline": "Baseline offset for analysis (in px).",
            # Manual Baseline
            "Enable": "Enable or disable manual baseline adjustment.",
            "Height": "Manual baseline height (in px).",
            # ROI
            "Left:": "Left boundary of the region of interest (ROI) in pixels.",
            "Right:": "Right boundary of the region of interest (ROI) in pixels.",
            "Top:": "Top boundary of the region of interest (ROI) in pixels.",
            "Bottom:": "Bottom boundary of the region of interest (ROI) in pixels.",
        }

    def _create_control_label(
        self, label_text: str, label_tooltips: dict[str, str]
    ) -> QLabel:
        """Create and configure a control label."""
        label = QLabel(label_text)
        label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        if label_text in label_tooltips:
            label.setToolTip(label_tooltips[label_text])
        return label

    def _create_control_by_type(
        self, control_type: str, config: dict[str, Any], label_text: str, title: str
    ) -> QWidget:
        """Create a control widget based on its type."""
        if control_type == "spinbox":
            return self._create_spinbox_control(config, label_text, title)
        elif control_type == "doublespinbox":
            return self._create_doublespinbox_control(config, label_text, title)
        elif control_type == "combobox":
            return self._create_combobox_control(config, title)
        elif control_type == "checkbox":
            return self._create_checkbox_control(config, title)
        else:
            raise ValueError(f"Unknown control type: {control_type}")

    def _create_spinbox_control(
        self, config: dict[str, Any], label_text: str, title: str
    ) -> QSpinBox:
        """Create and configure a spinbox control."""
        control = QSpinBox()
        control.setRange(config.get("min", 0), config.get("max", 100))
        control.setValue(config.get("value", 0))
        if config.get("step"):
            control.setSingleStep(config.get("step"))

        # Add suffix based on label text
        if label_text == "FPS":
            control.setSuffix(" 1/s")
        elif label_text == "Baseline" or label_text == "Height":
            control.setSuffix(" px")

        self._connect_control_signals(control, config, title, "valueChanged")
        return control

    def _create_doublespinbox_control(
        self, config: dict[str, Any], label_text: str, title: str
    ) -> QDoubleSpinBox:
        """Create and configure a double spinbox control."""
        control = QDoubleSpinBox()
        control.setRange(config.get("min", 0), config.get("max", 100))
        control.setValue(config.get("value", 0))
        if config.get("step"):
            control.setSingleStep(config.get("step"))

        # Add suffix based on label text
        if label_text == "Pixel":
            control.setSuffix(" px/mm")
        elif label_text == "Rotate":
            control.setSuffix(" °")

        self._connect_control_signals(control, config, title, "valueChanged")

        # Special case: if this is the rotation angle, also update ROI ranges
        if label_text == "Rotate":
            control.valueChanged.connect(
                lambda value: self._update_roi_ranges_from_image()
            )

        return control

    def _create_combobox_control(self, config: dict[str, Any], title: str) -> QComboBox:
        """Create and configure a combobox control."""
        control = QComboBox()
        control.addItems(config.get("items", []))
        control.setCurrentText(config.get("value", ""))

        self._connect_control_signals(control, config, title, "currentTextChanged")
        return control

    def _create_checkbox_control(self, config: dict[str, Any], title: str) -> QCheckBox:
        """Create and configure a checkbox control."""
        control = QCheckBox()
        control.setChecked(config.get("value", False))

        if config.get("setter"):
            control.stateChanged.connect(
                lambda state, setter=config.get("setter"): setter(state == Qt.Checked)
            )
        if config.get("callback"):
            control.stateChanged.connect(config.get("callback"))

        if config.get("auto_preview"):
            param_type = config.get("param_type", title.lower())
            control.stateChanged.connect(
                lambda state, p_type=param_type: self._trigger_preview_update(p_type)
            )

        return control

    def _connect_control_signals(
        self,
        control: QWidget,
        config: dict[str, Any],
        title: str,
        signal_name: str,
    ) -> None:
        """Connect control signals to appropriate handlers."""
        signal = getattr(control, signal_name, None)
        if not signal:
            return

        # Connect value changes to controller
        if config.get("setter"):
            signal.connect(config.get("setter"))

        # Connect callback if provided
        if config.get("callback"):
            signal.connect(config.get("callback"))

        # Connect to auto-preview if enabled
        if config.get("auto_preview"):
            param_type = config.get("param_type", title.lower())
            signal.connect(
                lambda value, p_type=param_type: self._trigger_preview_update(p_type)
            )

    def _configure_control(
        self, control: QWidget, config: dict[str, Any], spinbox_width: int
    ) -> None:
        """Configure control appearance and store reference if needed."""
        # Set fixed width if applicable and make it stretch horizontally
        if spinbox_width and hasattr(control, "setFixedWidth"):
            control.setFixedWidth(spinbox_width)

        control.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)

        # Store reference if attribute name provided
        if config.get("attr_name"):
            setattr(self, config.get("attr_name"), control)

    def _on_baseline_checkbox_change(self) -> None:
        """Handle baseline checkbox state change."""
        is_checked = self.Baseline_tf_checkbox.isChecked()
        self.controller.set_baseline_tf(is_checked)

    #         self.manual_baseline_entry.setEnabled(is_checked)

    def display_image_in_canvas(self, img: Any, canvas: QLabel) -> None:
        """Display an OpenCV image in a Qt label properly scaled to fit."""
        if img is None:
            return

        try:
            # Enhanced type checking
            if not isinstance(img, np.ndarray):
                return

            h, w = img.shape[:2]

            # Convert to RGB format if needed (ensure we handle color format correctly)
            if len(img.shape) == 3:
                # Make a copy to avoid modifying the source image
                display_img = img.copy()
                if img.shape[2] == 3:  # BGR to RGB
                    display_img = cv2.cvtColor(display_img, cv2.COLOR_BGR2RGB)
            else:
                # Convert grayscale to RGB
                display_img = cv2.cvtColor(img.copy(), cv2.COLOR_GRAY2RGB)

            # Convert to QImage
            h, w, ch = display_img.shape
            bytes_per_line = ch * w
            q_img = QImage(display_img.data, w, h, bytes_per_line, QImage.Format_RGB888)
            pixmap = QPixmap.fromImage(q_img)

            # Get canvas size
            canvas_width = canvas.width()
            canvas_height = canvas.height()

            # Check if the canvas has a valid size
            if canvas_width <= 1 or canvas_height <= 1:
                # Use the minimum size as fallback
                canvas_width = canvas.minimumWidth()
                canvas_height = canvas.minimumHeight()

            # Scale the image to fit within the canvas while maintaining aspect ratio
            if w > 0 and h > 0 and canvas_width > 0 and canvas_height > 0:
                scaled_pixmap = pixmap.scaled(
                    canvas_width,
                    canvas_height,
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation,
                )
                canvas.setPixmap(scaled_pixmap)
            else:
                # Fallback if dimensions are invalid
                canvas.setPixmap(pixmap)

            # Center the image in the canvas
            canvas.setAlignment(Qt.AlignCenter)

        except Exception as e:
            logger.error(f"Failed to display image in canvas: {e}")
            pass

    def _enable_buttons(self) -> None:
        """Re-enable buttons after thread completion."""
        # Reset processing flag
        self.is_processing = False

        #         self.analyze_button.setEnabled(True)
        #         self.preview_button.setEnabled(True)

        # Re-enable batch buttons
        #         self.process_batch_btn.setEnabled(True)
        #         self.add_folders_btn.setEnabled(True)

        # Re-enable the folder list
        #         self.folder_list.setEnabled(True)

        # Disable pause/stop buttons
        #         self.pause_resume_btn.setEnabled(False)
        #         self.stop_btn.setEnabled(False)

        # Also reset the pause button state for next time
        self.pause_resume_btn.setIcon(
            QIcon.fromTheme("media-playback-pause", QIcon(":/icons/pause.png"))
        )
        self.pause_resume_btn.setToolTip("Pause processing")

        # Reset folder counter to default state if not in batch processing
        if not (
            hasattr(self, "batch_thread")
            and self.batch_thread
            and self.batch_thread.isRunning()
        ):
            self.folder_counter.setText("0/0 folders")

    def _handle_error(self) -> None:
        """Handle errors from processing thread."""
        logger.error("Error occurred during processing, cleaning up")
        self._enable_buttons()

        # Also reset the pause button state
        self.pause_resume_btn.setIcon(
            QIcon.fromTheme("media-playback-pause", QIcon(":/icons/pause.png"))
        )
        self.pause_resume_btn.setToolTip("Pause processing")

    def _process_results(self, results: tuple) -> None:
        """Process and save the results from analysis."""
        logger.info("Processing analysis results")
        try:
            # Check if we received the new format (3 values)
            # or the old format (13 values)
            if len(results) == 3:
                # New format: time, time_int, result_lists
                time, time_int, result_lists = results

                # Make sure all required fields exist in the dictionary
                required_fields = [
                    "advancing_contact_angles",
                    "receding_contact_angles",
                    "rect_width_px",
                    "rect_height_px",
                    "rect_width_mm",
                    "rect_height_mm",
                    "velocity",
                    "center_points_px",
                    "center_points_mm",
                    "contact_line_px",
                    "contact_line_mm",
                ]

                # Initialize missing fields with NaN values
                for field in required_fields:
                    if field not in result_lists or result_lists[field] is None:
                        result_lists[field] = [float("nan")] * len(time)

                # Extract values for processing
                advancing_contact_angles = result_lists["advancing_contact_angles"]
                receding_contact_angles = result_lists["receding_contact_angles"]
                rect_width_px = result_lists["rect_width_px"]
                rect_height_px = result_lists["rect_height_px"]
                rect_width_mm = result_lists["rect_width_mm"]
                rect_height_mm = result_lists["rect_height_mm"]
                velocity = result_lists["velocity"]
                center_points_px = result_lists["center_points_px"]
                center_points_mm = result_lists["center_points_mm"]
            else:
                # Original format with 13 values (legacy support)
                (
                    time,
                    time_int,
                    advancing_contact_angles,
                    receding_contact_angles,
                    rect_width_px,
                    rect_height_px,
                    rect_width_mm,
                    rect_height_mm,
                    velocity,
                    center_points_px,
                    center_points_mm,
                ) = results

                # Create a result_lists dictionary for the save_results function
                result_lists = {
                    "advancing_contact_angles": advancing_contact_angles,
                    "receding_contact_angles": receding_contact_angles,
                    "rect_width_px": rect_width_px,
                    "rect_height_px": rect_height_px,
                    "rect_width_mm": rect_width_mm,
                    "rect_height_mm": rect_height_mm,
                    "velocity": velocity,
                    "center_points_px": center_points_px,
                    "center_points_mm": center_points_mm,
                    "contact_line_px": [float("nan")]
                    * len(time),  # Initialize if not available
                    "contact_line_mm": [float("nan")]
                    * len(time),  # Initialize if not available
                }

            # Calculate velocity if it's missing
            if not result_lists["velocity"] or all(
                np.isnan(v) for v in result_lists["velocity"]
            ):
                try:
                    result_lists["velocity"] = calculate_velocities(
                        center_points_px,
                        self.controller.pixel,
                        self.controller._fps,
                        time_int,
                    )
                except Exception as e:
                    logger.error(f"Failed to calculate velocity: {e}")
                    pass

            # If we have a folder path, save the results
            if self.controller.folder_path:
                output_dir = os.path.join(self.controller.folder_path, "Output")
                logger.info(f"Saving results to: {output_dir}")
                save_results(output_dir, time, result_lists)
            else:
                logger.warning("No folder path available, results not saved")

        except ValueError as e:
            # Handle case where there's a mismatch in the number of return values
            logger.error(f"Failed to process results due to value error: {e}")
            pass
        except Exception as e:
            logger.error(f"Failed to process results: {e}")
            pass

        self.overall_progress.setValue(100)

        # Reset folder counter after processing is done
        self.folder_counter.setText("0/0 folders")
        logger.info("Analysis results processing completed")

    def _update_stats(
        self,
        q: float,
        advancing_contact_angles: list[float],
        receding_contact_angles: list[float],
        center_points_px: list[tuple[float, float]],
        result_images: dict[str, Any],
        result_lists: Optional[dict[str, Any]] = None,
    ) -> None:
        """Update UI with current processing results."""
        # Update progress bar
        self.overall_progress.setValue(int(q * 100))

        # Update images and UI elements
        self._update_result_images(result_images)

        # Update statistics labels
        self._update_statistics_labels(
            advancing_contact_angles,
            receding_contact_angles,
            center_points_px,
            result_images,
            result_lists or {},
        )

    def _update_result_images(self, result_images: dict[str, Any]) -> None:
        """Update result images and frame slider."""
        try:
            # Only store images if this is from the main analysis (not preview)
            is_main_analysis = (
                self.main_thread is not None and self.main_thread.isRunning()
            )

            # Result image with baseline, intersection points, and contact angles
            if "result" in result_images:
                # Display the result image
                self.display_image_in_canvas(
                    result_images["result"], self.canvas_result
                )
                # Only store if this is main analysis
                if is_main_analysis:
                    self.preview_images["result"].append(result_images["result"])

            # Update frame slider only for main analysis
            if is_main_analysis:
                self.total_frames = len(self.preview_images["original"])
                if self.total_frames > 0:
                    self.frame_slider.setMaximum(self.total_frames - 1)

            # Force UI update
            QCoreApplication.processEvents()

        except Exception as e:
            logger.error(f"Failed to update UI: {e}")

    def _update_statistics_labels(
        self,
        advancing_contact_angles: list[float],
        receding_contact_angles: list[float],
        center_points_px: list[tuple[float, float]],
        result_images: dict[str, Any],
        result_lists: dict[str, Any],
    ) -> None:
        """Update all statistics labels with current values."""
        try:
            self._update_contact_angle_labels(
                advancing_contact_angles, receding_contact_angles
            )
            self._update_dimension_labels(result_images, result_lists)
            self._update_position_labels(center_points_px, result_images)

        except Exception as e:
            logger.error(f"Failed to update statistics: {e}")

    def _update_contact_angle_labels(
        self,
        advancing_contact_angles: list[float],
        receding_contact_angles: list[float],
    ) -> None:
        """Update contact angle labels."""
        # Get the latest values
        latest_adv = (
            advancing_contact_angles[-1] if advancing_contact_angles else float("NaN")
        )
        latest_rec = (
            receding_contact_angles[-1] if receding_contact_angles else float("NaN")
        )

        # Update contact angle labels
        self.adv_angle_label.setText(
            f"<b>Advancing angle:</b> {latest_adv:.1f} °"
            if not np.isnan(latest_adv)
            else "<b>Advancing angle:</b> -- °"
        )
        self.rec_angle_label.setText(
            f"<b>Receding angle:</b> {latest_rec:.1f} °"
            if not np.isnan(latest_rec)
            else "<b>Receding angle:</b> -- °"
        )

    def _update_dimension_labels(
        self,
        result_images: dict[str, Any],
        result_lists: dict[str, Any],
    ) -> None:
        """Update width and height labels."""
        # Update width and height labels if available in result_images
        if "rect_width_mm" in result_images and "rect_height_mm" in result_images:
            width_mm = result_images["rect_width_mm"]
            height_mm = result_images["rect_height_mm"]
            self.width_label.setText(
                f"<b>Width:</b> {width_mm:.2f} mm"
                if not np.isnan(width_mm)
                else "<b>Width:</b> -- mm"
            )
            self.height_label.setText(
                f"<b>Height:</b> {height_mm:.2f} mm"
                if not np.isnan(height_mm)
                else "<b>Height:</b> -- mm"
            )
        elif (
            result_lists
            and "rect_width_mm" in result_lists
            and "rect_height_mm" in result_lists
        ):
            # Fallback to result_lists if available
            width_list = result_lists["rect_width_mm"]
            height_list = result_lists["rect_height_mm"]

            # Get the latest values from the lists
            width_mm = (
                width_list[-1] if width_list and len(width_list) > 0 else float("nan")
            )
            height_mm = (
                height_list[-1]
                if height_list and len(height_list) > 0
                else float("nan")
            )

            self.width_label.setText(
                f"<b>Width:</b> {width_mm:.2f} mm"
                if not np.isnan(width_mm)
                else "<b>Width:</b> -- mm"
            )
            self.height_label.setText(
                f"<b>Height:</b> {height_mm:.2f} mm"
                if not np.isnan(height_mm)
                else "<b>Height:</b> -- mm"
            )
        else:
            # No data available, show default values
            self.width_label.setText("<b>Width:</b> -- mm")
            self.height_label.setText("<b>Height:</b> -- mm")

    def _update_position_labels(
        self,
        center_points_px: list[tuple[float, float]],
        result_images: dict[str, Any],
    ) -> None:
        """Update center position and velocity labels."""
        # Update center point and velocity if available
        if center_points_px and len(center_points_px) > 0:
            latest_center = center_points_px[-1]
            if isinstance(latest_center, (list, tuple)) and len(latest_center) >= 2:
                center_x_mm = (
                    latest_center[0] / self.controller.pixel
                    if latest_center[0] is not None and self.controller.pixel > 0
                    else 0
                )
                center_y_mm = (
                    latest_center[1] / self.controller.pixel
                    if latest_center[1] is not None and self.controller.pixel > 0
                    else 0
                )
                self.center_label.setText(
                    f"<b>Center (X/Y):</b> ({center_x_mm:.2f}/{center_y_mm:.2f})"
                )
            else:
                self.center_label.setText("<b>Center (X/Y):</b> (--/--)")

        if "velocity" in result_images:
            velocity = result_images["velocity"]
            self.velocity_value.setText(
                f"<b>Velocity:</b> {velocity:.2f} mm/s"
                if not np.isnan(velocity)
                else "<b>Velocity:</b> -- mm/s"
            )

    def add_folders_to_batch(self) -> None:
        """Add multiple folders to the batch processing queue."""
        logger.info("Opening folder selection dialog for batch processing")
        folder_dialog = QFileDialog()
        folder_dialog.setFileMode(QFileDialog.Directory)
        folder_dialog.setOption(QFileDialog.DontUseNativeDialog, True)

        # Hack to allow selecting multiple directories
        list_view = folder_dialog.findChild(QListView, "listView")
        if list_view:
            list_view.setSelectionMode(QAbstractItemView.ExtendedSelection)

        tree_view = folder_dialog.findChild(QTreeView)
        if tree_view:
            tree_view.setSelectionMode(QAbstractItemView.ExtendedSelection)

        if folder_dialog.exec():
            folders = folder_dialog.selectedFiles()
            logger.info(f"User selected {len(folders)} folders for batch processing")
            for folder in folders:
                if folder and folder not in self.controller.folder_paths:
                    self.controller.add_folder_path(folder)
                    # Display the full path for consistency
                    item = QListWidgetItem(folder)
                    item.setData(Qt.UserRole, folder)
                    self.folder_list.addItem(item)
        else:
            pass

    def remove_selected_folders(self) -> None:
        """Remove selected folders from the batch list."""
        selected_items = self.folder_list.selectedItems()
        if not selected_items:
            return

        logger.info(f"Removing {len(selected_items)} folders from batch list")
        for item in selected_items:
            # Get the full path from item data instead of display text
            folder_path = item.data(Qt.UserRole)

            self.controller.remove_folder_path(folder_path)
            row = self.folder_list.row(item)
            self.folder_list.takeItem(row)

    def clear_folder_list(self) -> None:
        """Clear all folders from the batch list."""
        logger.info("Clearing all folders from batch list")
        self.controller.clear_folder_paths()
        self.folder_list.clear()
        self.folder_list.clear()

    def process_all_folders(self) -> None:
        """Process all folders in the batch list sequentially."""
        logger.info("Starting batch processing of all folders")
        # Check if already processing
        if self.is_processing:
            logger.warning("Processing already in progress, ignoring batch request")
            return

        folder_count = self.folder_list.count()
        if folder_count == 0:
            logger.warning("No folders in batch queue to process")
            return

        logger.info(f"Starting batch processing of {folder_count} folders")
        # Set processing flag
        self.is_processing = True

        # Reset progress for all folders
        for i in range(folder_count):
            self.folder_delegate.set_progress(i, 0)
            # Update each item individually instead of the whole list
            self.folder_list.update(self.folder_list.model().index(i, 0))

        # Reset overall progress
        self.overall_progress.setValue(0)
        self.folder_counter.setText("0/" + str(folder_count) + " folders")

        # Disable UI buttons during processing
        #         self.process_batch_btn.setEnabled(False)
        #         self.add_folders_btn.setEnabled(False)
        #         self.analyze_button.setEnabled(False)

        # Enable pause/stop buttons and RESET the state of the pause button
        #         self.pause_resume_btn.setEnabled(True)
        self.pause_resume_btn.setIcon(
            QIcon.fromTheme("media-playback-pause", QIcon(":/icons/pause.png"))
        )
        self.pause_resume_btn.setToolTip("Pause processing")
        #         self.stop_btn.setEnabled(True)

        # Clear previous preview images
        self.preview_images = {"original": [], "contour": [], "result": []}
        self.current_frame = 0
        self.total_frames = 0
        self.frame_slider.setMaximum(0)
        #         self.frame_slider.setEnabled(False)

        # Create and start the batch processing thread
        self.batch_thread = QThread()
        self.batch_worker = BatchProcessingWorker(
            self.controller,
            self.controller.folder_paths,
            self._update_batch_progress,
        )
        self.batch_worker.moveToThread(self.batch_thread)
        self.batch_thread.started.connect(self.batch_worker.process_folders)
        self.batch_worker.progress_updated.connect(self._update_batch_progress)
        self.batch_worker.folder_completed.connect(self._on_folder_completed)
        self.batch_worker.overall_progress_updated.connect(
            self._update_overall_progress
        )
        self.batch_worker.all_completed.connect(self._on_batch_completed)
        self.batch_worker.error_occurred.connect(self._handle_batch_error)

        # Connect the new preview image signal to update our preview display
        self.batch_worker.preview_image_updated.connect(self._update_stats)

        self.batch_thread.start()

    def _update_batch_progress(self, folder_index, folder_path, progress_percent):
        """Update UI with batch processing progress."""
        # Update progress bar for this folder
        self.folder_delegate.set_progress(folder_index, progress_percent)
        # Update the specific item rather than the whole list
        self.folder_list.update(self.folder_list.model().index(folder_index, 0))

    def _on_folder_completed(self, folder_index, folder_path, success):
        """Handle completion of a single folder in the batch."""
        if success:
            # Set progress to 100% for success
            self.folder_delegate.set_progress(folder_index, 100)
        else:
            # For failure, set a specific value that can be styled differently
            self.folder_delegate.set_progress(
                folder_index, -1
            )  # Using -1 to indicate error

        # Update the specific item
        self.folder_list.update(self.folder_list.model().index(folder_index, 0))

    def _on_batch_completed(self):
        """Handle completion of the entire batch process."""
        # Reset processing flag
        self.is_processing = False

        # Re-enable UI buttons
        #         self.process_batch_btn.setEnabled(True)
        #         self.add_folders_btn.setEnabled(True)
        #         self.analyze_button.setEnabled(True)

        # Disable pause/stop buttons
        #         self.pause_resume_btn.setEnabled(False)
        #         self.stop_btn.setEnabled(False)

        # Reset the pause button state for next time
        self.pause_resume_btn.setIcon(
            QIcon.fromTheme("media-playback-pause", QIcon(":/icons/pause.png"))
        )
        self.pause_resume_btn.setToolTip("Pause processing")

        # Clean up thread
        self.batch_thread.quit()
        self.batch_thread.wait()

    def _handle_batch_error(self, folder_index, folder_path, error_msg):
        """Handle errors during batch processing."""
        logger.error(f"Batch processing error for folder {folder_path}: {error_msg}")
        # Mark as errored in the progress bar
        self.folder_delegate.set_progress(
            folder_index, -1
        )  # Using -1 to indicate error
        self.folder_list.repaint()

        # Reset the pause button state
        self.pause_resume_btn.setIcon(
            QIcon.fromTheme("media-playback-pause", QIcon(":/icons/pause.png"))
        )
        self.pause_resume_btn.setToolTip("Pause processing")

    def _update_folder_list(self, folder_paths):
        """Update the folder list widget when paths in controller change."""
        self.folder_list.clear()
        for path in folder_paths:
            # Create an item with the shortened path for display
            item = QListWidgetItem(path)
            # Store the full path as data
            item.setData(Qt.UserRole, path)
            self.folder_list.addItem(item)

        # Reset progress data when updating the list
        self.folder_delegate.progress_data = {}

        # Ensure main folder is highlighted
        self._update_main_folder_highlight()

        # If no main folder is selected but we have folders, set the first one
        if not self.controller.main_folder_path and folder_paths:
            self.controller.set_main_folder_path(folder_paths[0])
            self._update_main_folder_highlight()

        # Delay setting the horizontal scrollbar value to the right side
        QTimer.singleShot(
            0,
            lambda: self.folder_list.horizontalScrollBar().setValue(
                self.folder_list.horizontalScrollBar().maximum()
            ),
        )

    def _update_stats_with_param(
        self,
        q,
        advancing_angles,
        receding_angles,
        center_points,
        result_images,
        result_lists,
        param_type,
    ):
        """Update stats while preserving the original parameter type."""
        # Temporarily save current param type
        current_param = self.last_changed_param

        # Don't override context_menu_preview parameter type
        if current_param != "context_menu_preview":
            # Set to the saved one from when preview was started
            self.last_changed_param = param_type

        # Call the regular update stats method
        self._update_stats(
            q,
            advancing_angles,
            receding_angles,
            center_points,
            result_images,
            result_lists,
        )

        # Restore the original in case it changed (unless it's context_menu_preview)
        if current_param != "context_menu_preview":
            self.last_changed_param = current_param

    def _update_overall_progress(self, current_folder, total_folders, progress_percent):
        """Update the overall progress bar and counter."""
        # Update the overall progress bar
        self.overall_progress.setValue(int(progress_percent))

        # Update the folder counter
        self.folder_counter.setText(f"{current_folder}/{total_folders} folders")

    def _show_folder_context_menu(self, position):
        """Show context menu for folder list."""
        menu = QMenu(self.folder_list)

        # Add the Preview and Start Analysis actions at the top of the menu
        selected_items = self.folder_list.selectedItems()
        if selected_items and len(selected_items) == 1:
            # Get the full path from the item's data
            full_path = selected_items[0].data(Qt.UserRole)

            # Create preview action with tooltip showing full path
            preview_action = menu.addAction("Preview")
            preview_action.setToolTip(full_path)
            preview_action.triggered.connect(
                lambda: self.preview_selected_folder(full_path)
            )

            # Create analyze action
            analyze_action = menu.addAction("Start Analysis")
            analyze_action.setToolTip(full_path)
            analyze_action.triggered.connect(
                lambda: self.analyze_selected_folder(full_path)
            )

            menu.addSeparator()

        menu.addAction("Remove Selected", self.remove_selected_folders)
        menu.addAction("Clear All", self.clear_folder_list)

        # Show the menu at the cursor position
        menu.exec(self.folder_list.mapToGlobal(position))

    def _update_main_folder_highlight(self):
        """Update the highlighting of the main folder in the list."""
        main_path = self.controller.main_folder_path

        # Find the index of the main folder in the list
        for i in range(self.folder_list.count()):
            # Compare with the full path stored in data, not the display text
            if self.folder_list.item(i).data(Qt.UserRole) == main_path:
                break

        # Update the list display
        self.folder_list.viewport().update()

    def show_event(self, event):
        """Handle show event."""
        super().show_event(event)
        QTimer.singleShot(
            50,
            lambda: self.folder_list.horizontalScrollBar().setValue(
                self.folder_list.horizontalScrollBar().maximum()
            ),
        )

    def preview_selected_folder(self, folder_path: str) -> None:
        """Run preview on a specific folder and set it as the main folder."""
        # Check if already processing
        if self.is_processing:
            logger.warning("Processing already in progress, ignoring preview request")
            return

        # Set the selected folder as the main folder path
        self.controller.set_main_folder_path(folder_path)

        # Update the main folder highlight
        self._update_main_folder_highlight()

        # Set a special parameter for context menu preview
        # This will ensure we always display the contour image
        self.last_changed_param = "context_menu_preview"

        # Run preview
        self.preview()

    def analyze_selected_folder(self, folder_path: str) -> None:
        """Run analysis on a specific folder and set it as the main folder."""
        # Check if already processing
        if self.is_processing:
            return

        # Set the selected folder as the main folder path
        self.controller.set_main_folder_path(folder_path)

        # Update the main folder highlight
        self._update_main_folder_highlight()

        # Run analysis
        self.main()

    def _update_roi_ranges_from_image(self):
        """Update ROI spinbox ranges based on the rotated image dimensions."""
        # Check if we have a valid folder path
        if not self.controller.folder_path or not os.path.isdir(
            self.controller.folder_path
        ):
            # If no folder, use default large ranges
            self._set_default_roi_ranges()
            return

        # Find all images in the folder
        image_extensions = ["*.jpg", "*.jpeg", "*.png", "*.bmp", "*.tiff"]
        image_files = []
        for ext in image_extensions:
            image_files.extend(
                glob.glob(os.path.join(self.controller.folder_path, ext))
            )

        if not image_files:
            # If no images, use default large ranges
            self._set_default_roi_ranges()
            return

        # Sort files and get the middle one
        image_files.sort()
        middle_idx = len(image_files) // 2
        middle_image = image_files[middle_idx]

        # Get rotation angle from controller
        rotation_angle = (
            self.controller.rotate_angle
            if hasattr(self.controller, "rotate_angle")
            else 0.0
        )

        # Load and rotate the image to get its size
        orig_img = cv2.imread(middle_image)

        temp_roi_image = rotate_image(orig_img, rotation_angle)

        # Block signals to prevent triggering valueChanged when range changes
        self.left_roi_spinbox.blockSignals(True)
        self.right_roi_spinbox.blockSignals(True)
        self.top_roi_spinbox.blockSignals(True)
        self.bottom_roi_spinbox.blockSignals(True)

        # Set ranges based on rotated image dimensions
        self.left_roi_spinbox.setRange(0, temp_roi_image.shape[1] - 1)
        self.right_roi_spinbox.setRange(1, temp_roi_image.shape[1])
        self.top_roi_spinbox.setRange(0, temp_roi_image.shape[0] - 1)
        self.bottom_roi_spinbox.setRange(1, temp_roi_image.shape[0])

        # Clamp current values to new bounds if necessary
        current_left = self.left_roi_spinbox.value()
        current_right = self.right_roi_spinbox.value()
        current_top = self.top_roi_spinbox.value()
        current_bottom = self.bottom_roi_spinbox.value()

        clamped_left = min(max(current_left, 0), temp_roi_image.shape[1] - 1)
        clamped_right = min(max(current_right, 1), temp_roi_image.shape[1])
        clamped_top = min(max(current_top, 0), temp_roi_image.shape[0] - 1)
        clamped_bottom = min(max(current_bottom, 1), temp_roi_image.shape[0])

        # Update values if they were clamped
        if clamped_left != current_left:
            self.left_roi_spinbox.setValue(clamped_left)
            self.controller.set_x_img(clamped_left)
        if clamped_right != current_right:
            self.right_roi_spinbox.setValue(clamped_right)
            self.controller.set_w_img(clamped_right)
        if clamped_top != current_top:
            self.top_roi_spinbox.setValue(clamped_top)
            self.controller.set_y_img(clamped_top)
        if clamped_bottom != current_bottom:
            self.bottom_roi_spinbox.setValue(clamped_bottom)
            self.controller.set_h_img(clamped_bottom)

        # Re-enable signals
        self.left_roi_spinbox.blockSignals(False)
        self.right_roi_spinbox.blockSignals(False)
        self.top_roi_spinbox.blockSignals(False)
        self.bottom_roi_spinbox.blockSignals(False)

    def _set_default_roi_ranges(self):
        """Set default large ranges for ROI spinboxes."""
        # Block signals to prevent triggering valueChanged when range changes
        self.left_roi_spinbox.blockSignals(True)
        self.right_roi_spinbox.blockSignals(True)
        self.top_roi_spinbox.blockSignals(True)
        self.bottom_roi_spinbox.blockSignals(True)

        # Set default large ranges
        self.left_roi_spinbox.setRange(0, 9999)
        self.right_roi_spinbox.setRange(1, 10000)
        self.top_roi_spinbox.setRange(0, 9999)
        self.bottom_roi_spinbox.setRange(1, 10000)

        # Re-enable signals
        self.left_roi_spinbox.blockSignals(False)
        self.right_roi_spinbox.blockSignals(False)
        self.top_roi_spinbox.blockSignals(False)
        self.bottom_roi_spinbox.blockSignals(False)
