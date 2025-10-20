"""Analysis GUI for experiment visualization and user interaction.

Part of Droplet Wall Interaction Tool (DWIT).
"""

import glob
import os
from typing import Any

import cv2
from PySide6.QtCore import (
    Qt,
    QThread,
    QTimer,
)
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.helpers.preview import show_preview
from src.utilities.core_utils import get_logger
from src.utilities.image_utils import ROISelector, rotate_image, safe_imread
from src.utilities.preview_optimisation import get_optimized_preview_generator
from src.utilities.processors import BatchProcessor, ResultsProcessor, StatsUpdater
from src.utilities.threading import AnalysisThread
from src.widgets.batch_control_panel import BatchControlPanel
from src.widgets.display_panel import ImageSlider, PreviewCanvas, StatsOverlay
from src.widgets.folder_manager import FolderManager
from src.widgets.parameter_panel import FlexibleDoubleSpinBox, ParameterPanel

# Setup logger for this module
logger = get_logger(__name__)


# Reference FlexibleDoubleSpinBox methods so static analysers (vulture)
_vulture_references_flexible_spinbox = (
    FlexibleDoubleSpinBox.validate,
    FlexibleDoubleSpinBox.valueFromText,
)


class AnalysisGUI(QWidget):
    """Modern GUI for analysis."""

    def __init__(self, parent: QWidget, controller: Any):
        """Initialize the AnalysisGUI with parent and controller."""
        logger.debug("Initializing AnalysisGUI")

        try:
            super().__init__(parent)
            self.controller = controller
            self.main_thread = None

            # Path validation preferences
            self.preview_thread = None

            # Add a processing state flag to track when analysis is running
            self.is_processing = False

            # Add initialization flag to prevent unwanted dialogs during setup
            self.is_initializing = True

            # Initialize image slider widget (will be created in create_widgets)
            self.image_slider_widget = None

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

            # Add flag to track when we're in preview mode (no progress updates)
            self.is_in_preview_mode = False

            # Add flag to track when we're in preview mode (no progress updates)
            self.is_in_preview_mode = False

            if hasattr(self.controller, "image_processed"):
                self.controller.image_processed.connect(self._update_preview_image)

            else:
                logger.warning("Controller does not have image_processed signal")

            # Keep track of the last changed parameter type
            self.last_changed_param = None

            # Initialize optimized preview generator
            self.optimized_preview = get_optimized_preview_generator()
            self.optimized_preview.preview_ready.connect(self._handle_optimized_preview)

            # Create UI
            self.create_widgets()

            # Initialize processors after widgets are created
            self._initialize_processors()

            # Load the folder list from controller after UI creation
            if hasattr(self.controller, "_folder_paths"):
                folder_paths = self.controller._folder_paths
                logger.info(f"Loading {len(folder_paths)} folders from controller")
                if folder_paths:
                    logger.debug(f"First folder: {folder_paths[0]}")
                    self._update_folder_list(folder_paths)
                else:
                    logger.debug("No folders to load from controller")
                # Start background scanner for results files
                try:
                    self._start_results_scanner()
                except Exception:
                    logger.exception("Failed to start results scanner")

            else:
                logger.warning("Controller does not have _folder_paths attribute")

            # Make sure main folder highlighting is applied
            self._update_main_folder_highlight()

            # Flag used to indicate the user requested a hard stop/skip
            # which should prevent any final saving of `results_raw.xlsx`.
            self._user_requested_stop_no_save = False

            # Initialize index mapping for batch processing
            self.processing_to_ui_index_map = {}

            # Initialize processing mode
            self.processing_mode = "undone"

            # Auto-trigger preview only if this widget is visible after initialization
            # Ensure we're in the main thread before starting timer
            try:
                from PySide6.QtCore import QCoreApplication

                QCoreApplication.processEvents()
                QTimer.singleShot(100, self._conditional_auto_preview)
            except Exception:
                # If timer fails, just skip auto-preview
                logger.debug("Could not start auto-preview timer, skipping")

            logger.info("AnalysisGUI initialization completed successfully")

        except Exception as e:
            logger.error(f"Failed to initialize AnalysisGUI: {e}")
            logger.error(f"Parent: {parent}")
            logger.error(f"Controller: {controller}")
            raise

        # Set initialization flag with defensive timer
        try:
            from PySide6.QtCore import QCoreApplication

            QCoreApplication.processEvents()
            QTimer.singleShot(500, lambda: setattr(self, "is_initializing", False))
        except Exception:
            # If timer fails, set flag directly
            self.is_initializing = False
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

        if hasattr(self, "stats_updater"):
            self.stats_updater.update_frame_specific_stats(index)

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

    def _handle_optimized_preview(self, image, preview_type: str):
        """Handle optimized preview results."""
        try:
            if image is not None:
                show_preview(image, self)
                logger.debug(f"Displayed optimized {preview_type} preview")
        except Exception as e:
            logger.error(f"Error displaying optimized {preview_type} preview: {e}")

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
            self.display_image_in_canvas(result_images["result"])

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

        # Parameters/settings area with tighter width
        params_container = QWidget()
        self._create_parameter_section(params_container)
        params_container.setFixedWidth(180)  # Tighter width
        params_container.setMinimumWidth(180)
        main_content_layout.addWidget(params_container)

        # Preview area
        preview_container = QWidget()
        self._create_preview_area(preview_container)
        preview_container.setMinimumWidth(400)
        main_content_layout.addWidget(preview_container, 1)

        # Add main content (preview/canvas area) with higher stretch (2)
        self.main_layout.addWidget(main_content, 2)

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
        # based on the current processing mode
        self.pause_resume_btn.setToolTip("Pause or resume the current processing.")
        self.stop_btn.setToolTip("Stop the current processing.")
        self.folder_list.setToolTip(
            "List of folders to process. Right-click for more options. "
            "Green circles indicate completed folders with results."
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
        if hasattr(self, "ellipse_diameter_label"):
            self.ellipse_diameter_label.setToolTip(
                "Shows the ellipse diameter calculated from width and height "
                "(d = sqrt(w*h))."
            )
        if hasattr(self, "center_label"):
            self.center_label.setToolTip("Shows the center position (X/Y) in pixels.")
        if hasattr(self, "velocity_value"):
            self.velocity_value.setToolTip("Shows the calculated velocity in mm/s.")
        if hasattr(self, "area_diameter_label"):
            self.area_diameter_label.setToolTip(
                "Shows the diameter calculated from detected area (d = sqrt(4*A/π))."
            )

    def main(self) -> None:
        """Start main processing thread."""
        logger.info("Starting main analysis processing")
        # Check if already processing
        if self.is_processing:
            logger.warning("Analysis already in progress, ignoring request")
            return

        # Clear preview mode flag for main analysis
        self.is_in_preview_mode = False

        # Set processing flag
        self.is_processing = True

        # Clear previous frame data for new analysis
        self.stats_updater.clear_frame_data()

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
        self.batch_control_panel.set_pause_resume_state(is_paused=False)
        #         self.stop_btn.setEnabled(True)

        self.overall_progress.setValue(0)  # Use overall_progress instead of progress

        # Reset last_changed_param when starting main analysis
        self.last_changed_param = None

        # Reset context-sensitive preview flag for main analysis
        self.should_show_context_preview = False

        # Clear previous preview images when starting a new run via stats updater
        self.stats_updater.preview_images = {
            "original": [],
            "contour": [],
            "result": [],
        }
        self.stats_updater.total_frames = 0
        # Reset image slider state
        self._update_slider_state()

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
            self.folder_counter.setText("0/0")  # Reset folder counter
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

    def _trigger_preview_update(self, param_type: str | None = None) -> None:
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
        """Create action buttons and controls using BatchControlPanel widget."""
        # Create batch control panel widget
        self.batch_control_panel = BatchControlPanel(
            parent=self,
            on_add_folders=self._on_add_folders_clicked,
            on_folders_dropped=self._on_folders_dropped,
            on_show_help=self._on_show_help_clicked,
            on_process_batch=self.process_selected_folders,
            on_set_process_mode=self._on_process_mode_changed,
            on_stop=self._stop_processing,
            on_context_menu=self._on_folder_context_menu,
        )

        # Store references to child widgets for compatibility
        self.folder_list = self.batch_control_panel.folder_list
        self.folder_delegate = self.batch_control_panel.folder_delegate
        self.batch_progress = self.batch_control_panel.batch_progress
        self.add_folders_btn = self.batch_control_panel.add_folders_btn
        self.drop_zone = self.batch_control_panel.drop_zone
        self.help_btn = self.batch_control_panel.help_btn
        self.process_batch_btn = self.batch_control_panel.process_batch_btn
        self.mode_dropdown_btn = self.batch_control_panel.mode_dropdown_btn
        self.pause_resume_btn = self.batch_control_panel.pause_resume_btn
        self.stop_btn = self.batch_control_panel.stop_btn
        self.folder_counter = self.batch_control_panel.folder_counter
        self.overall_progress = self.batch_control_panel.overall_progress

        # Scanner thread attributes (initialized later)
        self._results_scanner_thread = None
        self._results_scanner_worker = None

        # Store processing mode
        self.processing_mode = self.batch_control_panel.processing_mode

        # Create FolderManager for handling folder operations
        self.folder_manager = FolderManager(
            folder_list=self.folder_list,
            folder_delegate=self.folder_delegate,
            controller=self.controller,
            on_preview_folder=self.preview_selected_folder,
            on_analyze_folder=self.analyze_selected_folder,
            on_scan_single_folder=self._scan_single_folder_results,
        )

        # Add batch control panel to main layout with stretch factor 1
        self.main_layout.addWidget(self.batch_control_panel, 1)

        # Create attributes for removed legacy buttons (placeholders)
        self.preview_button = QPushButton()
        self.analyze_button = QPushButton()

    def _on_add_folders_clicked(self) -> None:
        """Handle Add Folders button click (delegated to FolderManager)."""
        self.folder_manager.add_folders_to_batch()

    def _on_folders_dropped(self, folder_paths: list[str]) -> None:
        """Handle folders dropped (delegated to FolderManager)."""
        self.folder_manager.handle_dropped_folders(folder_paths)

    def _on_show_help_clicked(self) -> None:
        """Handle help button click (delegated to FolderManager)."""
        self.folder_manager.show_folder_detection_help()

    def _on_folder_context_menu(self, position) -> None:
        """Handle folder context menu (delegated to FolderManager)."""
        self.folder_manager.show_folder_context_menu(position)

    def _initialize_processors(self) -> None:
        """Initialize processor objects after widgets are created."""
        # Stats updater processor
        self.stats_updater = StatsUpdater(
            controller=self.controller,
            stats_overlay_widget=self.stats_overlay_widget,
            image_slider_widget=self.image_slider_widget,
            canvas_result=self.canvas_result,
            overall_progress=self.overall_progress,
            folder_list=self.folder_list,
            folder_delegate=self.folder_delegate,
            display_image_callback=self.display_image_in_canvas,
        )

        # Results processor
        self.results_processor = ResultsProcessor(
            controller=self.controller,
            folder_counter=self.folder_counter,
            overall_progress=self.overall_progress,
            batch_progress=self.batch_progress,
        )

        # Batch processor
        self.batch_processor = BatchProcessor(
            controller=self.controller,
            folder_list=self.folder_list,
            folder_delegate=self.folder_delegate,
            overall_progress=self.overall_progress,
            folder_counter=self.folder_counter,
            batch_control_panel=self.batch_control_panel,
            on_preview_update=self._update_stats,
            on_slider_update=lambda: (
                setattr(
                    self.stats_updater,
                    "preview_images",
                    {"original": [], "contour": [], "result": []},
                ),
                setattr(self.stats_updater, "total_frames", 0),
                self._update_slider_state(),
            ),
            on_folder_results=self._handle_folder_results,
            on_batch_completed=self._on_batch_processing_completed,
        )

    def _stop_processing(self):
        """Stop the current processing - delegated to processor."""
        # Record that the user requested a stop that should prevent saving
        self._user_requested_stop_no_save = True
        if self.main_thread and self.main_thread.isRunning():
            self.main_thread.stop()
        else:
            self.batch_processor.stop_processing()
            # Reset the GUI's is_processing flag when stopping batch processing
            self.is_processing = False

    def _create_parameter_section(self, parent_widget=None) -> None:
        """Create parameter configuration area using ParameterPanel widget."""
        # Create ParameterPanel widget with callbacks
        self.parameter_panel_widget = ParameterPanel(
            parent=parent_widget or self,
            controller=self.controller,
            on_preview_trigger=self._trigger_preview_update,
            on_roi_select=self.open_roi_selector,
            on_reset_defaults=self._on_reset_defaults_clicked,
        )

        # Store references to widget controls for compatibility
        self._setup_parameter_widget_references()

        # Initialize ROI spinboxes
        self._initialize_roi_spinboxes()

        # If parent_widget provided, set up its layout and add the widget
        if parent_widget is not None:
            layout = QVBoxLayout(parent_widget)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.addWidget(self.parameter_panel_widget)
        else:
            # Add to main layout if no parent widget provided
            self.main_layout.addWidget(self.parameter_panel_widget)

    def _setup_parameter_widget_references(self) -> None:
        """Set up references to ParameterPanel controls for compatibility."""
        # Video Calibration controls
        self.FPS_entry = self.parameter_panel_widget.FPS_entry
        self.PIXEL_entry = self.parameter_panel_widget.PIXEL_entry
        self.threshold_entry = self.parameter_panel_widget.threshold_entry
        self.rotate_angle_entry = self.parameter_panel_widget.rotate_angle_entry

        # ROI controls
        self.left_roi_spinbox = self.parameter_panel_widget.left_roi_spinbox
        self.right_roi_spinbox = self.parameter_panel_widget.right_roi_spinbox
        self.top_roi_spinbox = self.parameter_panel_widget.top_roi_spinbox
        self.bottom_roi_spinbox = self.parameter_panel_widget.bottom_roi_spinbox

        # Baseline controls
        self.baseline_entry = self.parameter_panel_widget.baseline_entry
        self.Baseline_tf_checkbox = self.parameter_panel_widget.Baseline_tf_checkbox
        self.manual_baseline_entry = self.parameter_panel_widget.manual_baseline_entry

        # Angle Method controls
        self.polynom_entry = self.parameter_panel_widget.polynom_entry
        self.polynom_entry_spin = self.parameter_panel_widget.polynom_entry_spin

        # Groups
        self.video_calibration_group = (
            self.parameter_panel_widget.video_calibration_group
        )
        self.roi_group = self.parameter_panel_widget.roi_group
        self.baseline_group = self.parameter_panel_widget.baseline_group
        self.angle_method_group = self.parameter_panel_widget.angle_method_group

        # Reset button
        self.reset_defaults_btn = self.parameter_panel_widget.reset_defaults_btn

    def preview(self) -> None:
        """Start preview processing thread.

        Uses average background for the middle image analysis.
        """
        logger.info("Starting preview processing")
        # Check if already processing
        if self.is_processing:
            return

        # Set preview mode flag to prevent progress bar updates
        self.is_in_preview_mode = True

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
        self.batch_control_panel.set_pause_resume_state(is_paused=False)
        #         self.stop_btn.setEnabled(True)

        self.overall_progress.setValue(0)  # Use overall_progress instead of progress

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
            self.folder_counter.setText("0/0")  # Reset folder counter
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
        # Set ranges based on image dimensions (or defaults if no image available)
        self._update_roi_ranges_from_image()

        # Use ParameterPanel's initialization method to set values
        # This handles signal blocking internally
        self.parameter_panel_widget.initialize_roi_spinboxes(
            x=self.controller.x_img,
            y=self.controller.y_img,
            w=self.controller.w_img,
            h=self.controller.h_img,
        )

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
        orig_img = safe_imread(middle_image)

        temp_roi_image = rotate_image(orig_img, rotation_angle)
        if temp_roi_image is None:
            logger.error(f"Failed to load/rotate image for ROI ranges: {middle_image}")
            self._set_default_roi_ranges()
            return

        if temp_roi_image is None:
            logger.error(f"Failed to load/rotate image for ROI ranges: {middle_image}")
            self._set_default_roi_ranges()
            return
        if temp_roi_image is None:
            logger.error(
                f"Failed to load/rotate image for ROI selector: {middle_image}"
            )
            return

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
        """Show the ROI preview dialog with current ROI settings (optimized)."""
        if not self.controller.folder_path or not os.path.isdir(
            self.controller.folder_path
        ):
            return

        # Use optimized preview generation with debouncing
        def generate_roi_preview():
            """Generate preview with current ROI settings."""
            roi_params = (
                self.controller.x_img,
                self.controller.y_img,
                self.controller.w_img,
                self.controller.h_img,
            )
            return self.optimized_preview.generate_roi_preview(
                self.controller.folder_path,
                roi_params,
                self.controller.rotate_angle,
                self.controller.analysis_mode,
            )

        self.optimized_preview.debounced_preview_update(
            "roi", generate_roi_preview, delay_ms=25
        )

    def _show_threshold_preview(self):
        """Show threshold preview with background subtraction (optimized)."""
        if not self.controller.folder_path or not os.path.isdir(
            self.controller.folder_path
        ):
            return

        # Use optimized preview generation with debouncing
        def generate_threshold_preview():
            """Generate preview with current threshold settings."""
            crop_params = (
                self.controller.x_img,
                self.controller.w_img,
                self.controller.y_img,
                self.controller.h_img,
            )
            return self.optimized_preview.generate_threshold_preview(
                self.controller.folder_path,
                self.controller.threshold,
                self.controller.rotate_angle,
                crop_params,
                self.controller.analysis_mode,
            )

        self.optimized_preview.debounced_preview_update(
            "threshold", generate_threshold_preview, delay_ms=25
        )

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
        """Show baseline preview with rotated, cropped image and baseline.

        Uses optimized preview generation.
        """
        if not self.controller.folder_path or not os.path.isdir(
            self.controller.folder_path
        ):
            return

        # Use optimized preview generation with debouncing
        def generate_baseline_preview():
            """Generate preview with current baseline settings."""
            crop_params = (
                self.controller.x_img,
                self.controller.w_img,
                self.controller.y_img,
                self.controller.h_img,
            )
            manual_baseline = (
                self.controller.manual_baseline if self.controller.baseline_tf else None
            )
            return self.optimized_preview.generate_baseline_preview(
                self.controller.folder_path,
                self.controller.baseline,
                manual_baseline,
                self.controller.rotate_angle,
                crop_params,
                self.controller.analysis_mode,
            )

        self.optimized_preview.debounced_preview_update(
            "baseline", generate_baseline_preview, delay_ms=25
        )

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
            image = safe_imread(middle_image)
            return image

        except Exception as e:
            logger.error(f"Error loading original image: {e}")
            return None

    def _create_preview_area(self, parent_widget=None) -> None:
        """Create the image preview area with controls above and canvases."""
        # Use parent widget if provided, otherwise create new
        preview_widget = parent_widget or QWidget()

        # Create layout for the widget
        preview_layout = QVBoxLayout(preview_widget)
        preview_layout.setContentsMargins(0, 0, 0, 0)

        # Create canvas container with stats overlay and image slider on top
        canvas_container = self._create_canvas_with_stats_overlay()
        preview_layout.addWidget(canvas_container)

        # If parent_widget was not provided, add to main layout
        if not parent_widget:
            self.main_layout.addWidget(preview_widget, 1)

    def _create_canvas_with_stats_overlay(self) -> QWidget:
        """Create the canvas container with stats overlay on top of image."""
        # Create PreviewCanvas widget with stats toggle callback
        self.preview_canvas_widget = PreviewCanvas(
            parent=self, on_stats_toggle=self._toggle_stats_overlay_impl
        )

        # Create stats overlay using the new StatsOverlay widget
        analysis_mode = getattr(self.controller, "analysis_mode", "")
        self.stats_overlay_widget = StatsOverlay(
            parent=self.preview_canvas_widget, analysis_mode=analysis_mode
        )

        # Store references for compatibility
        self.stats_overlay = self.stats_overlay_widget
        self.canvas_result = self.preview_canvas_widget.get_canvas_label()

        # Position overlay at top-left corner
        self.stats_overlay_widget.move(0, 0)
        self.stats_overlay_widget.raise_()
        self.stats_overlay_widget.show()  # Explicitly show the overlay

        # Create and add the image slider on top of canvas
        self.image_slider_widget = ImageSlider(
            parent=self.preview_canvas_widget,
            on_frame_changed=self._on_frame_changed,
            get_fps=lambda: getattr(self.controller, "fps", 30),
        )
        self.image_slider_widget.setFixedHeight(50)  # Fixed height for slider panel

        # Set the image slider in the canvas for positioning
        self.preview_canvas_widget.set_image_slider(self.image_slider_widget)
        self.image_slider_widget.show()

        return self.preview_canvas_widget

    def _toggle_stats_overlay_impl(self) -> bool:
        """Toggle the visibility of the stats overlay (implementation).

        Returns
        -------
        bool
            New visibility state

        """
        if not hasattr(self, "stats_overlay_widget"):
            return True

        is_visible = self.stats_overlay_widget.toggle_visibility()

        # Update canvas widget's internal state
        if hasattr(self, "preview_canvas_widget"):
            self.preview_canvas_widget.set_stats_overlay_visible(is_visible)

        return is_visible

    def _on_frame_changed(self, index: int) -> None:
        """Handle frame changes from the image slider widget.

        Parameters
        ----------
        index : int
            The new frame index.

        """
        self._display_frame_at_index(index)
        # Update stats overlay when frame changes via stats updater
        self.stats_updater.update_stats_overlay()

    def _display_frame_at_index(self, index: int) -> None:
        """Display the image at the specified index and update stats.

        Parameters
        ----------
        index : int
            The frame index to display.

        """
        try:
            result_images = self.stats_updater.preview_images.get("result", [])
            if 0 <= index < len(result_images):
                image = result_images[index]
                if image is not None:
                    self.display_image_in_canvas(image, self.canvas_result)
                    # Update stats for current frame via stats updater
                    self.stats_updater.update_frame_specific_stats(index)
                    # Ensure overlay stays on top after image update
                    if hasattr(self, "stats_overlay") and self.stats_overlay:
                        self.stats_overlay.raise_()
                        if hasattr(self, "stats_icon_btn"):
                            self.stats_icon_btn.raise_()
                else:
                    logger.warning(f"Image at index {index} is None")
        except Exception as e:
            logger.error(f"Error displaying frame at index {index}: {e}")

    def _update_slider_state(self) -> None:
        """Update the slider state when new images are loaded."""
        # Safety check: ensure slider widget exists
        if not hasattr(self, "image_slider_widget") or self.image_slider_widget is None:
            return

        total_frames = len(self.stats_updater.preview_images.get("result", []))
        self.image_slider_widget.set_total_frames(total_frames)

    def _on_baseline_checkbox_change(self) -> None:
        """Handle baseline checkbox state change (delegated to widget)."""
        if hasattr(self, "parameter_panel_widget"):
            self.parameter_panel_widget._on_baseline_checkbox_change()

    def _on_fitting_mode_changed(self, *args) -> None:
        """Enable degree spinbox only when fitting mode is 'Polynom' (delegated)."""
        if hasattr(self, "parameter_panel_widget"):
            self.parameter_panel_widget._on_fitting_mode_changed(*args)

    def _on_reset_defaults_clicked(self) -> None:
        """Handle Reset to Default button click: reset controller and update UI."""
        # Show confirmation dialog
        msg_box = QMessageBox(self)
        msg_box.setIcon(QMessageBox.Warning)
        msg_box.setWindowTitle("Reset to Defaults")
        msg_box.setText(
            "Are you sure you want to reset all parameters to default values?"
        )
        msg_box.setInformativeText(
            "This will:\n"
            "• Reset all analysis parameters (FPS, Pixel, Threshold, etc.)\n"
            "• Clear the current folder list\n"
            "• Load the default test folder for the current analysis mode\n"
            "• Reset ROI settings to default values\n\n"
            "All current parameter configurations will be lost."
        )
        msg_box.setStandardButtons(QMessageBox.Yes | QMessageBox.Cancel)
        msg_box.setDefaultButton(QMessageBox.Cancel)

        # Execute the dialog and check the result
        result = msg_box.exec()
        if result != QMessageBox.Yes:
            return  # User cancelled, do nothing

        try:
            if hasattr(self.controller, "reset_to_defaults"):
                self.controller.reset_to_defaults()
            else:
                logger.warning("Controller has no reset_to_defaults method")

            # Clear current folder list and add the mode-specific test folder
            try:
                # This helper clears controller paths and will add the test
                # folder for the current analysis mode when the list is empty.
                self.clear_folder_list()
            except Exception:
                logger.exception("Failed to clear and reset folder list")

            # Update UI controls to reflect controller values
            self._apply_controller_values_to_ui()

        except Exception as e:
            logger.error(f"Error resetting defaults: {e}")

    def _apply_controller_values_to_ui(self) -> None:
        """Update all parameter controls from controller values.

        Without triggering auto-preview callbacks.
        """
        try:
            controls = self._gather_ui_controls()
            # Block signals while updating to avoid triggering previews
            self._block_ui_controls(controls, True)
            try:
                self._set_ui_values_from_controller()
            except Exception as e:
                logger.error(f"Failed to apply controller values to UI: {e}")
            finally:
                # Unblock signals after update
                self._block_ui_controls(controls, False)
        except Exception as e:
            logger.error(f"Error updating UI from controller: {e}")

    def _gather_ui_controls(self) -> list:
        """Return a list of UI controls to be updated from the controller."""
        controls: list = []
        # Basic controls
        for name in (
            "FPS_entry",
            "PIXEL_entry",
            "threshold_entry",
            "rotate_angle_entry",
            "baseline_entry",
            "Baseline_tf_checkbox",
            "manual_baseline_entry",
            "polynom_entry",
            "polynom_entry_spin",
        ):
            if hasattr(self, name):
                controls.append(getattr(self, name))

        # ROI controls (may or may not exist)
        controls.extend(
            [
                getattr(self, "left_roi_spinbox", None),
                getattr(self, "right_roi_spinbox", None),
                getattr(self, "top_roi_spinbox", None),
                getattr(self, "bottom_roi_spinbox", None),
            ]
        )
        # Filter out None values
        return [c for c in controls if c is not None]

    def _block_ui_controls(self, controls: list, block: bool) -> None:
        """Block or unblock signals for a list of controls."""
        for c in controls:
            try:
                c.blockSignals(block)
            except Exception:
                # Best-effort: ignore controls that do not support blocking
                pass

    def _set_ui_values_from_controller(self) -> None:
        """Set values on UI controls from controller properties."""
        # Delegate to smaller helpers to reduce McCabe complexity
        self._apply_basic_mappings()
        self._apply_checkbox_and_combobox()
        self._apply_roi_mappings()

    def _apply_basic_mappings(self) -> None:
        """Apply simple numeric mappings from controller to UI controls."""
        mappings = [
            ("FPS_entry", "fps", int, "setValue"),
            ("PIXEL_entry", "pixel", float, "setValue"),
            ("threshold_entry", "threshold", int, "setValue"),
            ("rotate_angle_entry", "rotate_angle", float, "setValue"),
            ("baseline_entry", "baseline", int, "setValue"),
            ("manual_baseline_entry", "manual_baseline", int, "setValue"),
            ("polynom_entry_spin", "polynom", int, "setValue"),
        ]

        for ui_name, ctrl_name, caster, method in mappings:
            ui_ctrl = getattr(self, ui_name, None)
            if ui_ctrl is None or not hasattr(self.controller, ctrl_name):
                continue
            try:
                value = getattr(self.controller, ctrl_name)
                getattr(ui_ctrl, method)(caster(value))
            except Exception:
                continue

    def _apply_checkbox_and_combobox(self) -> None:
        """Apply checkbox and combobox values from controller."""
        if hasattr(self, "Baseline_tf_checkbox") and hasattr(
            self.controller, "baseline_tf"
        ):
            try:
                self.Baseline_tf_checkbox.setChecked(bool(self.controller.baseline_tf))
            except Exception:
                pass

        if hasattr(self, "polynom_entry"):
            try:
                self.polynom_entry.setCurrentText(
                    str(getattr(self.controller, "fitting_mode", ""))
                )
            except Exception:
                pass

        # Ensure dependent controls reflect current settings
        try:
            # Toggle baseline/manual baseline controls
            if hasattr(self, "_on_baseline_checkbox_change"):
                self._on_baseline_checkbox_change()
        except Exception:
            pass

        try:
            # Toggle polynom degree control according to current fitting mode
            if hasattr(self, "_on_fitting_mode_changed"):
                self._on_fitting_mode_changed()
        except Exception:
            pass

    def _apply_roi_mappings(self) -> None:
        """Apply ROI spinbox values from controller."""
        roi_mappings = [
            ("left_roi_spinbox", "x_img"),
            ("right_roi_spinbox", "w_img"),
            ("top_roi_spinbox", "y_img"),
            ("bottom_roi_spinbox", "h_img"),
        ]
        for ui_name, ctrl_name in roi_mappings:
            ui_ctrl = getattr(self, ui_name, None)
            if ui_ctrl is None or not hasattr(self.controller, ctrl_name):
                continue
            try:
                ui_ctrl.setValue(int(getattr(self.controller, ctrl_name)))
            except Exception:
                pass

    def display_image_in_canvas(self, img: Any, canvas: QLabel | None = None) -> None:
        """Display an OpenCV image in the canvas properly scaled to fit.

        This method delegates to the PreviewCanvas widget for actual display.
        The canvas parameter is kept for backward compatibility but is ignored.

        Parameters
        ----------
        img : Any
            OpenCV image to display
        canvas : QLabel | None, optional
            Ignored parameter kept for compatibility

        """
        if hasattr(self, "preview_canvas_widget"):
            self.preview_canvas_widget.display_image(img)

    def _enable_buttons(self) -> None:
        """Re-enable buttons after thread completion."""
        # Reset processing flag
        self.is_processing = False

        # Clear preview mode flag
        self.is_in_preview_mode = False

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
        self.batch_control_panel.set_pause_resume_state(is_paused=False)

        # Reset folder counter to default state if not in batch processing
        if not (
            hasattr(self, "batch_thread")
            and self.batch_thread
            and self.batch_thread.isRunning()
        ):
            self.folder_counter.setText("0/0")

    def _handle_error(self) -> None:
        """Handle errors from processing thread."""
        logger.error("Error occurred during processing, cleaning up")
        self._enable_buttons()

        # Also reset the pause button state
        self.batch_control_panel.set_pause_resume_state(is_paused=False)

    def _process_results(self, results: tuple) -> None:
        """Process and save the results from analysis (delegated to processor)."""
        # Set stop flag if user requested it
        if getattr(self, "_user_requested_stop_no_save", False):
            self.results_processor.set_stop_no_save_flag(True)
            self._user_requested_stop_no_save = False

        # Process results using processor
        result_lists = self.results_processor.process_results(results)

        # Store frame data for slider navigation via stats updater
        if result_lists:
            self.stats_updater.store_frame_data(result_lists)

    def _handle_folder_results(
        self, folder_index: int, folder_path: str, results: tuple
    ) -> None:
        """Handle folder results from batch processing to store frame data.

        Parameters
        ----------
        folder_index : int
            Index of the completed folder
        folder_path : str
            Path to the folder
        results : tuple
            Results tuple (time, time_int, result_lists)

        """
        try:
            # Extract result_lists from the results tuple
            if results and len(results) == 3:
                _time, _time_int, result_lists = results
                # Store frame data for the completed folder
                if result_lists:
                    self.stats_updater.store_frame_data(result_lists)
                    logger.info(
                        f"Stored frame data for batch folder {folder_index}: "
                        f"{folder_path}"
                    )
        except Exception as e:
            logger.error(
                f"Error handling folder results for {folder_path}: {e}",
                exc_info=True,
            )

    def _update_stats(
        self,
        q: float,
        advancing_contact_angles: list[float],
        receding_contact_angles: list[float],
        center_points_px: list[tuple[float, float]],
        result_images: dict[str, Any],
        result_lists: dict[str, Any] | None = None,
    ) -> None:
        """Update UI with current processing results - delegated to processor."""
        # Set threading state in stats updater
        self.stats_updater.set_threads(
            self.main_thread, getattr(self.batch_processor, "batch_thread", None)
        )
        self.stats_updater.set_preview_mode(self.is_in_preview_mode)

        # Delegate to stats updater
        self.stats_updater.update_stats(
            q,
            advancing_contact_angles,
            receding_contact_angles,
            center_points_px,
            result_images,
            result_lists,
        )

        # Update slider state after image updates
        self._update_slider_state()

    def remove_selected_folders(self) -> None:
        """Remove selected folders from the batch list (delegated)."""
        self.folder_manager.remove_selected_folders()
        # Reset folder counter and preview images via stats updater
        self.folder_counter.setText("0/0")
        self.stats_updater.preview_images = {
            "original": [],
            "contour": [],
            "result": [],
        }
        self.stats_updater.total_frames = 0
        self._update_slider_state()
        self._update_main_folder_highlight()

    def clear_folder_list(self) -> None:
        """Clear all folders from the batch list (delegated)."""
        self.folder_manager.clear_folder_list()

        # Reset scanner worker
        if self._results_scanner_worker is not None:
            self._results_scanner_worker.set_folder_paths([])

        # Reset folder counter and preview images via stats updater
        self.folder_counter.setText("0/0")
        self.stats_updater.preview_images = {
            "original": [],
            "contour": [],
            "result": [],
        }
        self.stats_updater.total_frames = 0
        self._update_slider_state()
        self._update_main_folder_highlight()

    def process_selected_folders(self) -> None:
        """Process folders based on selected mode - delegated to processor."""
        self.is_processing = True
        self.batch_processor.process_selected_folders(self.processing_mode)

    def _on_batch_processing_completed(self) -> None:
        """Handle completion of batch processing - reset GUI state."""
        self.is_processing = False
        logger.debug("Batch processing completed - GUI is_processing flag reset")

    def _on_process_mode_changed(self, mode: str) -> None:
        """Update processing mode when changed in batch control panel.

        Args:
            mode: Processing mode ('undone' or 'all')

        """
        self.processing_mode = mode
        logger.debug(f"Processing mode changed to: {mode}")

    def _update_folder_list(self, folder_paths):
        """Update the folder list widget when paths in controller change."""
        self.folder_list.clear()

        # Clear all old state data first
        if hasattr(self, "folder_delegate"):
            self.folder_delegate.progress_data = {}
            self.folder_delegate.results_presence = {}
            self.folder_delegate.folder_list_widget = self.folder_list

        # Sync folders from controller to visual list
        if hasattr(self, "folder_manager") and folder_paths:
            logger.debug(f"Syncing {len(folder_paths)} folders to visual list")
            self.folder_manager.sync_folders_from_controller(folder_paths)
            # Force visual update of the folder list
            self.folder_list.viewport().update()
            self.folder_list.repaint()
        else:
            logger.warning(
                "Cannot add folders: folder_manager exists=%s, "
                "folder_paths provided=%s",
                hasattr(self, "folder_manager"),
                bool(folder_paths),
            )

        # Reset results presence and defer scan
        try:
            self.folder_delegate.clear_results_presence()
            QTimer.singleShot(100, self._immediate_scan_folder_results)
        except Exception:
            logger.exception("Error setting up folder results scanning during update")

        # Ensure main folder is highlighted
        self._update_main_folder_highlight()

        # If no main folder is selected but we have folders, set the first one
        if not self.controller.main_folder_path and folder_paths:
            self.controller.set_main_folder_path(folder_paths[0])
            self._update_main_folder_highlight()

        # Set horizontal scrollbar to right
        try:
            from PySide6.QtCore import QCoreApplication

            QCoreApplication.processEvents()
            if hasattr(self, "folder_list") and self.folder_list:
                QTimer.singleShot(
                    0,
                    lambda: (
                        self.folder_list.horizontalScrollBar().setValue(
                            self.folder_list.horizontalScrollBar().maximum()
                        )
                        if hasattr(self, "folder_list") and self.folder_list
                        else None
                    ),
                )
        except Exception:
            try:
                if hasattr(self, "folder_list") and self.folder_list:
                    self.folder_list.horizontalScrollBar().setValue(
                        self.folder_list.horizontalScrollBar().maximum()
                    )
            except Exception:
                pass

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
        # Set horizontal scrollbar to maximum safely
        try:
            from PySide6.QtCore import QCoreApplication

            QCoreApplication.processEvents()
            if hasattr(self, "folder_list") and self.folder_list:
                QTimer.singleShot(
                    50,
                    lambda: (
                        self.folder_list.horizontalScrollBar().setValue(
                            self.folder_list.horizontalScrollBar().maximum()
                        )
                        if hasattr(self, "folder_list") and self.folder_list
                        else None
                    ),
                )
        except Exception:
            # If timer fails, set scroll position directly
            try:
                if hasattr(self, "folder_list") and self.folder_list:
                    self.folder_list.horizontalScrollBar().setValue(
                        self.folder_list.horizontalScrollBar().maximum()
                    )
            except Exception:
                pass

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
        # Load image and attempt rotation; handle failures gracefully
        orig_img = safe_imread(middle_image)
        temp_roi_image = rotate_image(orig_img, rotation_angle)
        if temp_roi_image is None:
            logger.error(f"Failed to load/rotate image for ROI ranges: {middle_image}")
            # Use default ranges instead of crashing
            self._set_default_roi_ranges()
            return

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

    def _update_existing_scanner(self):
        """Update the existing scanner with current folder paths."""
        try:
            paths = [
                self.folder_list.item(i).data(Qt.UserRole)
                for i in range(self.folder_list.count())
            ]
            self._results_scanner_worker.set_folder_paths(paths)
        except Exception:
            pass

    def _get_folder_paths_for_scanner(self):
        """Get folder paths for scanner initialization."""
        try:
            return [
                self.folder_list.item(i).data(Qt.UserRole)
                for i in range(self.folder_list.count())
            ]
        except Exception:
            return []

    def _immediate_scan_folder_results(self):
        """Immediately scan all folders for results files (synchronous)."""
        try:
            for i in range(self.folder_list.count()):
                item = self.folder_list.item(i)
                if item:
                    folder_path = item.data(Qt.UserRole)
                    if folder_path and isinstance(folder_path, str):
                        try:
                            results_file = os.path.join(folder_path, "results_raw.xlsx")
                            has_results = (
                                os.path.exists(folder_path)
                                and os.path.isdir(folder_path)
                                and os.path.exists(results_file)
                            )
                            self.folder_delegate.set_results_presence(
                                folder_path, has_results
                            )
                            # Update each item individually
                            if hasattr(self, "folder_list") and self.folder_list:
                                self.folder_list.update(
                                    self.folder_list.model().index(i, 0)
                                )
                        except (OSError, PermissionError, FileNotFoundError):
                            self.folder_delegate.set_results_presence(
                                folder_path, False
                            )
                        except Exception:
                            self.folder_delegate.set_results_presence(
                                folder_path, False
                            )

        except Exception as e:
            logger.error(f"Failed to scan folder results immediately: {e}")

    def _scan_single_folder_results(self, folder_path: str):
        """Scan a single folder for results (for deferred scanning)."""
        try:
            results_file = os.path.join(folder_path, "results_raw.xlsx")
            has_results = (
                os.path.exists(folder_path)
                and os.path.isdir(folder_path)
                and os.path.exists(results_file)
            )
            self.folder_delegate.set_results_presence(folder_path, has_results)

            # Find the index to update the UI item
            for i in range(self.folder_list.count()):
                item = self.folder_list.item(i)
                if item and item.data(Qt.UserRole) == folder_path:
                    if hasattr(self, "folder_list") and self.folder_list:
                        self.folder_list.update(self.folder_list.model().index(i, 0))
                    break

            # Update scanner worker if it exists
            if self._results_scanner_worker is not None:
                paths = [
                    self.folder_list.item(i).data(Qt.UserRole)
                    for i in range(self.folder_list.count())
                ]
                self._results_scanner_worker.set_folder_paths(paths)
        except Exception:
            pass

    def _create_scan_result_callback(self):
        """Create callback function for scan results.

        The returned callback safely locates the current list item matching
        a scanned `folder_path` and updates the delegate. This avoids using
        stale indices when the user adds/removes folders while the scanner
        is running.
        """

        # Keep callback minimal by delegating to class helper methods below.
        def _on_scan_result(idx, folder_path, has):
            """Handle scan result callback to update folder status indicators."""
            # If delegate is missing there's nothing to do
            if not getattr(self, "folder_delegate", None):
                return

            list_widget = getattr(self, "folder_list", None)

            # If list widget is missing, try to update delegate directly and return
            if list_widget is None:
                try:
                    delegate = getattr(self, "folder_delegate", None)
                    if delegate is not None and hasattr(
                        delegate, "set_results_presence"
                    ):
                        delegate.set_results_presence(folder_path, has)
                    else:
                        logger.debug(
                            "No folder_list and no usable folder_delegate to update for"
                        )
                except Exception:
                    logger.exception(
                        "Failed to update folder_delegate directly for index %s",
                        idx,
                    )
                return

            target_index = self._find_list_index_by_path(list_widget, folder_path)
            if target_index is None:
                return

            self._update_delegate_and_refresh(
                list_widget, target_index, has, folder_path
            )

        return _on_scan_result

    def _find_list_index_by_path(self, list_widget, folder_path):
        """Return the list index whose `Qt.UserRole` equals `folder_path`.

        Returns `None` if not found. Skips items that raise when accessed.
        """
        # Defensive search: iterate and compare stored Qt.UserRole data
        if list_widget is None:
            return None

        try:
            count = list_widget.count()
        except Exception:
            logger.exception("Failed to get count from folder_list")
            return None

        for i in range(count):
            try:
                item = list_widget.item(i)
                if item is None:
                    continue
                data = item.data(Qt.UserRole)
                if data == folder_path:
                    return i
            except Exception:
                logger.debug(
                    "Skipping list item while scanning for path: %s",
                    folder_path,
                )
                continue

        return None

    def _update_delegate_and_refresh(self, list_widget, target_index, has, folder_path):
        """Set results presence on delegate and refresh the list item if possible."""
        try:
            if getattr(self, "folder_delegate", None) is not None:
                self.folder_delegate.set_results_presence(folder_path, has)
        except Exception:
            logger.exception(
                "Failed to set results presence for index %s",
                target_index,
            )

        try:
            if list_widget is None:
                logger.debug("No folder_list available to refresh for path")
                return
            model = list_widget.model()
            if model is None:
                logger.debug("Folder list model is None, cannot update item")
                return
            idx = model.index(target_index, 0)
            if idx.isValid():
                list_widget.update(idx)
            else:
                logger.debug("Model index invalid for target index")
        except Exception:
            logger.exception("Unexpected error while updating list widget for path")

    def _start_results_scanner(self):
        """Start a background `ResultsScannerWorker` in its own QThread."""
        # If worker is already running, just update its folder paths
        if self._results_scanner_worker is not None:
            self._update_existing_scanner()
            return

        try:
            from src.helpers.batch import ResultsScannerWorker

            self._results_scanner_thread = QThread(self)
            # Use longer interval (5 seconds) to reduce system load
            self._results_scanner_worker = ResultsScannerWorker(interval_ms=5000)

            paths = self._get_folder_paths_for_scanner()
            self._results_scanner_worker.set_folder_paths(paths)

            self._results_scanner_worker.moveToThread(self._results_scanner_thread)
            self._results_scanner_thread.started.connect(
                self._results_scanner_worker.start_scanning
            )
            self._results_scanner_worker.finished.connect(
                self._results_scanner_thread.quit
            )
            # Ensure thread is cleaned up after finishing
            self._results_scanner_thread.finished.connect(
                self._results_scanner_thread.deleteLater
            )

            scan_callback = self._create_scan_result_callback()
            self._results_scanner_worker.scan_result.connect(scan_callback)

            self._results_scanner_thread.start()
            logger.debug("Background results scanner started successfully")

        except Exception as e:
            logger.error(f"Failed to start background results scanner: {e}")
            # Clean up if initialization failed
            self._results_scanner_thread = None
            self._results_scanner_worker = None

    def _stop_results_scanner(self):
        """Stop the background results scanner if it exists."""
        try:
            if self._results_scanner_worker is not None:
                logger.debug("Stopping background results scanner...")
                self._results_scanner_worker.stop()

            if self._results_scanner_thread is not None:
                self._results_scanner_thread.quit()
                # Use shorter timeout to avoid blocking UI
                if not self._results_scanner_thread.wait(500):  # 500ms max
                    logger.warning("Results scanner thread did not stop gracefully")
                    # Don't call terminate() - just continue cleanup

                # Clean up references
                self._results_scanner_thread = None
                self._results_scanner_worker = None
                logger.debug("Background results scanner stopped successfully")

        except Exception as e:
            logger.error(f"Failed to stop results scanner: {e}")
            # Force cleanup even if there was an error
            self._results_scanner_thread = None
            self._results_scanner_worker = None

    def cleanup_all_threads(self):
        """Clean up all threads associated with this AnalysisGUI."""
        logger.debug("Starting AnalysisGUI thread cleanup")
        try:
            # Stop results scanner
            self._stop_results_scanner()

            # Stop main analysis thread
            if hasattr(self, "main_thread") and self.main_thread:
                self.main_thread.stop()
                if not self.main_thread.wait(1000):
                    logger.warning("Main thread did not stop gracefully")

            # Stop preview thread
            if hasattr(self, "preview_thread") and self.preview_thread:
                self.preview_thread.stop()
                if not self.preview_thread.wait(1000):
                    logger.warning("Preview thread did not stop gracefully")

            # Stop batch processing thread
            if hasattr(self, "batch_thread") and self.batch_thread:
                if hasattr(self, "batch_worker"):
                    self.batch_worker.stop()
                self.batch_thread.quit()
                if not self.batch_thread.wait(1000):
                    logger.warning("Batch thread did not stop gracefully")

            logger.debug("AnalysisGUI thread cleanup completed")
        except Exception as e:
            logger.error(f"Error during AnalysisGUI thread cleanup: {e}")

    def closeEvent(self, event):  # noqa: N802 - Qt requires closeEvent signature
        """Ensure scanner thread is stopped when widget is closed."""
        try:
            # Attempt comprehensive thread cleanup
            self.cleanup_all_threads()
        except Exception as e:
            logger.exception("Error stopping threads during closeEvent: %s", e)

        # Accept the event and call parent implementation
        if event:
            event.accept()
        return super().closeEvent(event)

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
