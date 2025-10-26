"""Processors module for DWIT.

Contains processors used by the Droplet Wall Interaction Tool (DWIT):

- BatchProcessor: manages batch processing of folders, thread/worker lifecycle,
    progress reporting, and integration with UI folder list and delegates.
- StatsUpdater: updates UI overlays, preview/result images, frame data storage,
    and real-time statistics during analysis.
- ResultsProcessor: validates and normalises analysis results, computes missing
    velocities, and saves results to the output folder (results_raw.xlsx).

This module centralises batch, stats, and result-saving responsibilities and
integrates with the controller, UI widgets, and the BatchProcessingWorker.
"""

import logging
import os
from collections.abc import Callable
from typing import Any

import numpy as np
from PySide6.QtCore import QCoreApplication, Qt, QThread

from src.helpers.batch import BatchProcessingWorker
from src.helpers.save_results import save_results
from src.utilities.measurement_utils import calculate_velocities

logger = logging.getLogger(__name__)


class ResultsProcessor:
    """Handles processing and saving of analysis results."""

    def __init__(self, controller, folder_counter, overall_progress, batch_progress):
        """Initialize the ResultsProcessor.

        Parameters
        ----------
        controller : Any
            The analysis controller
        folder_counter : QLabel
            Label for displaying folder counter
        overall_progress : QProgressBar
            Overall progress bar
        batch_progress : QProgressBar
            Batch progress bar

        """
        self.controller = controller
        self.folder_counter = folder_counter
        self.overall_progress = overall_progress
        self.batch_progress = batch_progress
        self._user_requested_stop_no_save = False

    def set_stop_no_save_flag(self, value: bool) -> None:
        """Set the flag to prevent saving when user stops processing.

        Parameters
        ----------
        value : bool
            True to prevent saving, False to allow saving

        """
        self._user_requested_stop_no_save = value

    def process_results(self, results: tuple) -> dict[str, Any]:
        """Process and save the results from analysis.

        Parameters
        ----------
        results : tuple
            Results tuple from analysis thread

        Returns
        -------
        dict[str, Any]
            Processed result_lists dictionary

        """
        logger.info("Processing analysis results")
        try:
            # Check format (new 3-value or legacy 13-value)
            if len(results) == 3:
                result_lists = self._process_new_format(results)
            else:
                result_lists = self._process_legacy_format(results)

            time, time_int = results[0], results[1]

            # Ensure velocity exists
            self._ensure_velocity(result_lists, time, time_int)

            # Save results if folder path available
            if self.controller.folder_path:
                self._save_results_to_folder(time, result_lists)
            else:
                logger.warning("No folder path available, results not saved")

        except ValueError as e:
            logger.error(f"Failed to process results due to value error: {e}")
            result_lists = {}
        except Exception as e:
            logger.error(f"Failed to process results: {e}")
            # Log all result_lists keys and values for debugging
            result_lists = {}

        self.overall_progress.setValue(100)
        self.batch_progress.setValue(100)
        self.folder_counter.setText("0/0")
        logger.info("Analysis results processing completed")

        return result_lists

    def _process_new_format(self, results: tuple) -> dict[str, Any]:
        """Process new 3-value result format.

        Parameters
        ----------
        results : tuple
            (time, time_int, result_lists)

        Returns
        -------
        dict[str, Any]
            Processed result_lists

        """
        time, _time_int, result_lists = results

        required_fields = [
            "advancing_contact_angles",
            "receding_contact_angles",
            "rect_width_px",
            "rect_height_px",
            "rect_width_mm",
            "rect_height_mm",
            "ellipse_diameter_px",
            "ellipse_diameter_mm",
            "velocity",
            "center_points_px",
            "center_points_mm",
            "contact_line_px",
            "contact_line_mm",
        ]

        # Initialize missing fields with NaN
        for field in required_fields:
            if field not in result_lists or result_lists[field] is None:
                result_lists[field] = [float("nan")] * len(time)

        return result_lists

    def _process_legacy_format(self, results: tuple) -> dict[str, Any]:
        """Process legacy 13-value result format.

        Parameters
        ----------
        results : tuple
            Legacy format with 13 values

        Returns
        -------
        dict[str, Any]
            Processed result_lists dictionary

        """
        (
            time,
            _time_int,
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

        return {
            "advancing_contact_angles": advancing_contact_angles,
            "receding_contact_angles": receding_contact_angles,
            "rect_width_px": rect_width_px,
            "rect_height_px": rect_height_px,
            "rect_width_mm": rect_width_mm,
            "rect_height_mm": rect_height_mm,
            "ellipse_diameter_px": [float("nan")] * len(time),
            "ellipse_diameter_mm": [float("nan")] * len(time),
            "velocity": velocity,
            "area_diameter_px": [float("nan")] * len(time),
            "area_diameter_mm": [float("nan")] * len(time),
            "center_points_px": center_points_px,
            "center_points_mm": center_points_mm,
            "contact_line_px": [float("nan")] * len(time),
            "contact_line_mm": [float("nan")] * len(time),
        }

    def _ensure_velocity(self, result_lists: dict, time: list, time_int: list) -> None:
        """Calculate velocities if missing or all NaN.

        Parameters
        ----------
        result_lists : dict
            Results dictionary to update
        time : list
            Time values
        time_int : list
            Time interval values

        """
        vel = result_lists.get("velocity")
        if not vel or all(np.isnan(v) for v in vel):
            center_mm = result_lists.get("center_points_mm", [])
            logger.debug("Calculating velocities from center points")
            result_lists["velocity"] = calculate_velocities(
                center_mm,
                pixel=self.controller.pixel,
                fps=self.controller.fps,
                time_values=time,
            )

    def _save_results_to_folder(self, time: list, result_lists: dict) -> None:
        """Save results to the output folder.

        Parameters
        ----------
        time : list
            Time values
        result_lists : dict
            Results dictionary to save

        """
        output_dir = self.controller.folder_path
        logger.info(f"Saving results into folder: {output_dir}")

        parameters = self.build_save_parameters()
        folder_name = os.path.basename(output_dir or "")
        _file_names = self._find_representative_file_names(output_dir)

        # Check if user requested stop without saving
        if self._user_requested_stop_no_save:
            logger.info("User requested stop — skipping saving results_raw.xlsx")
            self._user_requested_stop_no_save = False
        else:
            save_results(
                output_dir,
                time,
                result_lists,
                parameters=parameters,
                folder_name=folder_name,
                file_names=result_lists.get("filenames"),
            )

    def build_save_parameters(self) -> dict:
        """Build parameters dict for saving results from controller attributes.

        Returns
        -------
        dict
            Parameters dictionary

        """
        return {
            "fps": getattr(self.controller, "fps", None),
            "pixel": getattr(self.controller, "pixel", None),
            "threshold": getattr(self.controller, "threshold", None),
            "rotate_angle": getattr(self.controller, "rotate_angle", None),
            "x_img": getattr(self.controller, "x_img", None),
            "y_img": getattr(self.controller, "y_img", None),
            "w_img": getattr(self.controller, "w_img", None),
            "h_img": getattr(self.controller, "h_img", None),
            "baseline": getattr(self.controller, "baseline", None),
            "baseline_tf": getattr(self.controller, "baseline_tf", None),
            "manual_baseline": getattr(self.controller, "manual_baseline", None),
            "polynom": getattr(self.controller, "polynom", None),
            "polynom_enabled": getattr(self.controller, "polynom_enabled", None),
            "analysis_mode": getattr(self.controller, "analysis_mode", "contact_angle"),
            "vertical_line_left": getattr(self.controller, "vertical_line_left", None),
            "vertical_line_right": getattr(
                self.controller, "vertical_line_right", None
            ),
        }

    def _find_representative_file_names(self, output_dir: str) -> list[str]:
        """Find representative image file names from the output directory.

        Parameters
        ----------
        output_dir : str
            Directory to search for files

        Returns
        -------
        list[str]
            List of representative file names

        """
        try:
            import glob

            image_files = []
            for ext in ["*.jpg", "*.jpeg", "*.png", "*.bmp", "*.tiff"]:
                image_files.extend(glob.glob(os.path.join(output_dir, ext)))

            if image_files:
                image_files.sort()
                return [os.path.basename(f) for f in image_files[:3]]
        except Exception as e:
            logger.error(f"Failed to find representative file names: {e}")

        return []


class StatsUpdater:
    """Processor for updating statistics and overlays during analysis."""

    def __init__(
        self,
        controller,
        stats_overlay_widget,
        image_slider_widget,
        canvas_result,
        overall_progress,
        folder_list,
        folder_delegate,
        display_image_callback,
    ):
        """Initialize the StatsUpdater.

        Parameters
        ----------
        controller : Controller
            The main controller instance.
        stats_overlay_widget : StatsOverlay
            The stats overlay widget.
        image_slider_widget : ImageSlider
            The image slider widget.
        canvas_result : PreviewCanvas
            The result canvas widget.
        overall_progress : QProgressBar
            The overall progress bar.
        folder_list : QListWidget
            The folder list widget.
        folder_delegate : FolderDelegate
            The folder list delegate.
        display_image_callback : callable
            Callback to display images in canvas.

        """
        self.controller = controller
        self.stats_overlay_widget = stats_overlay_widget
        self.image_slider_widget = image_slider_widget
        self.canvas_result = canvas_result
        self.overall_progress = overall_progress
        self.folder_list = folder_list
        self.folder_delegate = folder_delegate
        self.display_image_callback = display_image_callback

        # Frame data storage
        self.frame_data = {}
        self.preview_images = {"original": [], "contour": [], "result": []}
        self.total_frames = 0

        # Threading state
        self.main_thread = None
        self.batch_thread = None
        self.is_in_preview_mode = False

    def set_threads(self, main_thread, batch_thread):
        """Set thread references for state checking."""
        self.main_thread = main_thread
        self.batch_thread = batch_thread

    def set_preview_mode(self, is_preview: bool):
        """Set preview mode flag."""
        self.is_in_preview_mode = is_preview

    def update_stats(
        self,
        q: float,
        advancing_contact_angles: list[float],
        receding_contact_angles: list[float],
        center_points_px: list[tuple[float, float]],
        result_images: dict[str, Any],
        result_lists: dict[str, Any] | None = None,
    ) -> None:
        """Update UI with current processing results."""
        # Only update progress bars when NOT in preview mode
        if not self.is_in_preview_mode:
            # Update progress bar
            progress_value = int(q * 100)
            self.overall_progress.setValue(progress_value)

            # Update folder progress if we're analyzing a main folder
            self._update_folder_progress(q)

        # Update images and UI elements
        self._update_result_images(result_images)

        # Update stats overlay directly with real-time data during analysis
        self.update_overlay_from_realtime_data(
            advancing_contact_angles,
            receding_contact_angles,
            center_points_px,
            result_images,
            result_lists or {},
        )

    def _update_result_images(self, result_images: dict[str, Any]) -> None:
        """Update result images and internal preview image storage."""
        try:
            # Only store images if this is from the main analysis or batch processing
            is_main_analysis = (
                self.main_thread is not None and self.main_thread.isRunning()
            )
            is_batch_processing = (
                self.batch_thread is not None and self.batch_thread.isRunning()
            )
            should_store_images = is_main_analysis or is_batch_processing

            # Result image with baseline, intersection points, and contact angles
            if "result" in result_images:
                # Display the result image
                self.display_image_callback(result_images["result"], self.canvas_result)
                # Only store if this is main analysis or batch processing
                if should_store_images:
                    self.preview_images["result"].append(result_images["result"])

            # Update internal frame count only for main analysis or batch processing
            if should_store_images:
                self.total_frames = len(self.preview_images["original"])

            # Force UI update
            QCoreApplication.processEvents()

        except Exception as e:
            logger.error(f"Failed to update UI: {e}")

    def _update_folder_progress(self, progress: float) -> None:
        """Update progress for the currently analyzing folder."""
        main_folder_path = self.controller.main_folder_path
        if not main_folder_path:
            return

        # Find the folder in the list
        for i in range(self.folder_list.count()):
            item = self.folder_list.item(i)
            if item and item.data(Qt.UserRole) == main_folder_path:
                # Update progress for this folder (0-100)
                progress_percent = int(progress * 100)
                self.folder_delegate.set_progress(i, progress_percent)
                # Update the specific item
                self.folder_list.update(self.folder_list.model().index(i, 0))
                break

    def update_overlay_from_realtime_data(
        self,
        advancing_contact_angles,
        receding_contact_angles,
        center_points_px,
        result_images,
        result_lists,
    ):
        """Update overlay directly from real-time analysis data."""
        try:
            if not self.stats_overlay_widget:
                return

            # Debug: Print what we're receiving
            img_keys = list(result_images.keys())
            list_keys = list(result_lists.keys()) if result_lists else None
            logger.debug(
                f"Stats updater - result_images keys: {img_keys}, "
                f"result_lists keys: {list_keys}"
            )

            self.stats_overlay_widget.update_from_realtime_data(
                advancing_contact_angles,
                receding_contact_angles,
                result_images,
                result_lists,
            )

        except Exception as e:
            logger.error(f"Error updating overlay from real-time data: {e}")

    def update_stats_overlay(self):
        """Update the stats overlay with current analysis data."""
        try:
            if not self.stats_overlay_widget:
                return

            # Get current frame index from slider widget
            current_index = 0
            if self.image_slider_widget:
                current_index = self.image_slider_widget.get_current_frame()

            # Only update if we have frame data (after processing complete)
            # During real-time processing, updates come via
            # update_overlay_from_realtime_data
            if self.frame_data:
                self.stats_overlay_widget.update_from_frame_data(
                    self.frame_data, current_index
                )
            # Don't reset during processing - let real-time updates handle it

        except Exception as e:
            logger.error(f"Error updating stats overlay: {e}")

    def store_frame_data(self, result_lists: dict[str, Any]) -> None:
        """Store frame data for slider navigation stats display."""
        try:
            # Store the complete result lists for frame navigation
            self.frame_data = {
                "advancing_contact_angles": result_lists.get(
                    "advancing_contact_angles", []
                ),
                "receding_contact_angles": result_lists.get(
                    "receding_contact_angles", []
                ),
                "center_points_px": result_lists.get("center_points_px", []),
                "center_points_mm": result_lists.get("center_points_mm", []),
                "velocity": result_lists.get("velocity", []),
                "rect_width_mm": result_lists.get("rect_width_mm", []),
                "rect_height_mm": result_lists.get("rect_height_mm", []),
                "ellipse_diameter_mm": result_lists.get("ellipse_diameter_mm", []),
                "area_diameter_mm": result_lists.get("area_diameter_mm", []),
                "area_mm2": result_lists.get("area_mm2", []),
                "filenames": result_lists.get("filenames", []),
            }
            frame_count = len(self.frame_data.get("advancing_contact_angles", []))
            logger.info("Stored frame data for %d frames", frame_count)
        except Exception as e:
            logger.error(f"Error storing frame data: {e}")
            self.frame_data = {}

    def clear_frame_data(self) -> None:
        """Clear frame data when starting new analysis."""
        self.frame_data = {}

    def update_frame_specific_stats(self, index: int) -> None:
        """Update stats display for a specific frame."""
        if not self.frame_data:
            return

        total_frames = len(self.frame_data.get("advancing_contact_angles", []))
        if index < 0 or index >= total_frames:
            return

        try:
            # Update stats overlay using the proper method
            if self.stats_overlay_widget:
                self.stats_overlay_widget.update_from_frame_data(self.frame_data, index)

        except Exception as e:
            logger.error(f"Error updating frame-specific stats: {e}")


class BatchProcessor:
    """Handles batch processing of multiple folders."""

    def __init__(
        self,
        controller,
        folder_list,
        folder_delegate,
        overall_progress,
        folder_counter,
        batch_control_panel,
        on_preview_update: Callable | None = None,
        on_slider_update: Callable | None = None,
        on_folder_results: Callable | None = None,
        on_batch_completed: Callable | None = None,
    ):
        """Initialize the BatchProcessor.

        Parameters
        ----------
        controller : Any
            The analysis controller
        folder_list : QListWidget
            Folder list widget
        folder_delegate : FolderItemDelegate
            Folder item delegate for progress display
        overall_progress : QProgressBar
            Overall progress bar widget
        folder_counter : QLabel
            Folder counter label widget
        batch_control_panel : BatchControlPanel
            Batch control panel widget
        on_preview_update : Callable | None
            Callback for preview image updates
        on_slider_update : Callable | None
            Callback for slider updates
        on_folder_results : Callable | None
            Callback for folder results
        on_batch_completed : Callable | None
            Callback when batch processing completes or stops

        """
        self.controller = controller
        self.folder_list = folder_list
        self.folder_delegate = folder_delegate
        self.overall_progress = overall_progress
        self.folder_counter = folder_counter
        self.batch_control_panel = batch_control_panel
        self.on_preview_update = on_preview_update
        self.on_slider_update = on_slider_update
        self.on_folder_results = on_folder_results
        self.on_batch_completed = on_batch_completed

        # Thread management
        self.batch_thread = None
        self.batch_worker = None
        self.processing_to_ui_index_map = {}

        # State
        self.is_processing = False

    def process_selected_folders(self, processing_mode: str) -> None:
        """Process folders based on the selected mode.

        Parameters
        ----------
        processing_mode : str
            "undone" or "all"

        """
        if processing_mode == "undone":
            self.process_undone_folders()
        else:
            self.process_all_folders()

    def process_undone_folders(self) -> None:
        """Process only folders that don't have results_raw.xlsx file."""
        logger.info("Starting batch processing of undone folders only")

        if self.is_processing:
            logger.warning("Processing already in progress, ignoring batch request")
            return

        # Get folders without results
        undone_folders = []
        undone_indices = []

        for i in range(self.folder_list.count()):
            item = self.folder_list.item(i)
            folder_path = item.data(0x0100)  # Qt.UserRole

            results_file = os.path.join(folder_path, "results_raw.xlsx")
            if not os.path.exists(results_file):
                undone_folders.append(folder_path)
                undone_indices.append(i)

        if not undone_folders:
            logger.info("No undone folders found to process")
            return

        logger.info(
            f"Starting batch processing of {len(undone_folders)} undone folders "
            f"(out of {self.folder_list.count()} total folders)"
        )

        self.start_batch_processing(undone_folders, undone_indices)

    def process_all_folders(self) -> None:
        """Process all folders in the batch list sequentially."""
        logger.info("Starting batch processing of all folders")

        if self.is_processing:
            logger.warning("Processing already in progress, ignoring batch request")
            return

        folder_count = self.folder_list.count()
        if folder_count == 0:
            logger.warning("No folders in batch queue to process")
            return

        # Get all folder paths and indices
        all_folders = []
        all_indices = []

        for i in range(folder_count):
            item = self.folder_list.item(i)
            folder_path = item.data(0x0100)  # Qt.UserRole
            all_folders.append(folder_path)
            all_indices.append(i)

        logger.info(f"Starting batch processing of {len(all_folders)} folders")
        self.start_batch_processing(all_folders, all_indices)

    def start_batch_processing(self, folder_paths: list, folder_indices: list) -> None:
        """Start batch processing with the given folders.

        Parameters
        ----------
        folder_paths : list
            List of folder paths to process
        folder_indices : list
            List of corresponding indices in the UI

        """
        self.is_processing = True

        # Reset progress for all folders
        for i in range(self.folder_list.count()):
            item = self.folder_list.item(i)
            if item:
                folder_path = item.data(0x0100)  # Qt.UserRole
                if folder_path:
                    self.folder_delegate.set_progress(folder_path, 0)
                    self.folder_list.update(self.folder_list.model().index(i, 0))

        # Reset overall progress
        self.overall_progress.setValue(0)
        self.folder_counter.setText(f"0/{len(folder_paths)}")

        # Reset pause button state
        self.batch_control_panel.set_pause_resume_state(is_paused=False)

        # Clear preview images and update slider
        if self.on_slider_update:
            self.on_slider_update()

        # Create and start batch thread
        self.batch_thread = QThread()
        self.batch_worker = BatchProcessingWorker(
            self.controller,
            folder_paths,
            self.update_batch_progress,
        )

        # Store index mapping
        self.processing_to_ui_index_map = {
            processing_idx: ui_idx
            for processing_idx, ui_idx in enumerate(folder_indices)
        }

        self.batch_worker.moveToThread(self.batch_thread)
        self.batch_thread.started.connect(self.batch_worker.process_folders)
        self.batch_worker.progress_updated.connect(self.update_batch_progress)
        self.batch_worker.folder_completed.connect(self.on_folder_completed)
        self.batch_worker.overall_progress_updated.connect(self.update_overall_progress)
        self.batch_worker.all_completed.connect(self.on_batch_completed)
        self.batch_worker.error_occurred.connect(self.handle_batch_error)

        # Connect preview image signal if callback provided
        if self.on_preview_update:
            self.batch_worker.preview_image_updated.connect(self.on_preview_update)

        # Connect folder results signal for storing frame data
        if self.on_folder_results:
            self.batch_worker.folder_results_ready.connect(self.on_folder_results)

        self.batch_thread.start()

    def update_batch_progress(
        self, folder_index: int, folder_path: str, progress_percent: float
    ) -> None:
        """Update UI with batch processing progress.

        Parameters
        ----------
        folder_index : int
            Index of the folder being processed
        folder_path : str
            Path to the folder
        progress_percent : float
            Progress percentage (0-100)

        """
        self.folder_delegate.set_progress(folder_path, progress_percent)

        # Find UI index and update
        ui_index = None
        for i in range(self.folder_list.count()):
            item = self.folder_list.item(i)
            if item and item.data(0x0100) == folder_path:  # Qt.UserRole
                ui_index = i
                break

        if ui_index is not None:
            self.folder_list.update(self.folder_list.model().index(ui_index, 0))

    def on_folder_completed(
        self, folder_index: int, folder_path: str, success: bool
    ) -> None:
        """Handle completion of a single folder.

        Parameters
        ----------
        folder_index : int
            Index of the completed folder
        folder_path : str
            Path to the folder
        success : bool
            Whether processing was successful

        """
        ui_index = self.processing_to_ui_index_map.get(folder_index, folder_index)

        if success:
            self.folder_delegate.set_progress(ui_index, 100)
        else:
            self.folder_delegate.set_progress(ui_index, -1)  # Error indicator

        self.folder_list.update(self.folder_list.model().index(ui_index, 0))

    def on_batch_completed(self) -> None:
        """Handle completion of the entire batch process."""
        self.is_processing = False

        # Reset pause button state
        self.batch_control_panel.set_pause_resume_state(is_paused=False)

        # Clean up thread
        try:
            if self.batch_thread:
                self.batch_thread.quit()
                self.batch_thread.wait()
        except Exception as e:
            logger.error(
                f"Error while quitting batch_thread during completion: {e}",
                exc_info=True,
            )
        finally:
            self.batch_thread = None
            self.batch_worker = None

        # Notify parent (GUI) that batch processing has completed
        if self.on_batch_completed:
            self.on_batch_completed()

    def handle_batch_error(
        self, folder_index: int, folder_path: str, error_msg: str
    ) -> None:
        """Handle errors during batch processing.

        Parameters
        ----------
        folder_index : int
            Index of the folder with error
        folder_path : str
            Path to the folder
        error_msg : str
            Error message

        """
        logger.error(f"Batch processing error for folder {folder_path}: {error_msg}")
        self.folder_delegate.set_progress(folder_index, -1)
        self.folder_list.repaint()

        # Reset pause button
        self.batch_control_panel.set_pause_resume_state(is_paused=False)

        # Reset processing flag
        self.is_processing = False

        # Cleanup
        try:
            if self.batch_thread:
                self.batch_thread.quit()
                self.batch_thread.wait(1000)
            self.batch_thread = None
            self.batch_worker = None
        except Exception:
            pass

        # Notify parent (GUI) that batch processing has stopped due to error
        if self.on_batch_completed:
            self.on_batch_completed()

    def update_overall_progress(
        self, current_folder: int, total_folders: int, progress_percent: float
    ) -> None:
        """Update the batch progress bar based on folder progress.

        Parameters
        ----------
        current_folder : int
            Current folder number
        total_folders : int
            Total number of folders
        progress_percent : float
            Progress percentage

        """
        if total_folders > 0:
            folder_progress = int((current_folder / total_folders) * 100)
            self.batch_control_panel.batch_progress.setValue(folder_progress)
        else:
            self.batch_control_panel.batch_progress.setValue(0)

        self.folder_counter.setText(f"{current_folder}/{total_folders}")

    def stop_processing(self) -> None:
        """Stop the current batch processing."""
        if self.batch_worker:
            self.batch_worker.stop()

        # Wait for thread to finish properly before cleanup
        if self.batch_thread and self.batch_thread.isRunning():
            logger.info("Waiting for batch thread to stop...")
            self.batch_thread.quit()
            self.batch_thread.wait(5000)  # Wait up to 5 seconds

        # Clean up thread and worker
        self.batch_thread = None
        self.batch_worker = None

        # Reset processing flag after thread cleanup
        self.is_processing = False

        # Reset pause button state
        self.batch_control_panel.set_pause_resume_state(is_paused=False)

        # Notify parent (GUI) that batch processing has been stopped
        if self.on_batch_completed:
            self.on_batch_completed()
