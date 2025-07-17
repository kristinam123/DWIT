"""Thread for running analysis operations in a separate QThread.

This module defines AnalysisThread, which handles image analysis in a background thread,
emitting progress, finished, and error signals for UI updates.
"""

from PySide6.QtCore import QThread, Signal

from src.utilities.logging_manager import get_logger

# Setup logger for this module
logger = get_logger(__name__)


class AnalysisThread(QThread):
    """Thread for running analysis operations."""

    progress_signal = Signal(float, list, list, list, dict)
    finished_signal = Signal(tuple)
    error_signal = Signal(str)

    def __init__(
        self,
        controller,
        save_files=False,
        preview_middle=False,
        use_first_as_background=False,
    ):
        """Initialize the analysis thread.

        Args:
            controller: The controller object managing analysis logic and parameters.
            save_files (bool): Whether to save result files during analysis.
            preview_middle (bool): Whether to preview the middle image.
            use_first_as_background (bool): Use the first image as background for
                analysis.

        """
        super().__init__()
        self.controller = controller
        self.save_files = save_files
        self.preview_middle = preview_middle
        self.use_first_as_background = use_first_as_background
        # Add state variables for pause and stop functionality
        self.is_paused = False
        self.should_stop = False

    # In the run method of AnalysisThread
    def run(self):
        """Run analysis process in a separate thread."""
        try:
            # Reset state variables at start
            self.is_paused = False
            self.should_stop = False

            # Get all parameters from controller
            self.controller.update_parameters(
                self.controller.fitting_mode,
                self.controller.polynom,
                self.controller.baseline_tf,
                self.controller.fps,
                self.controller.pixel,
                self.controller.h_img,
                self.controller.y_img,
                self.controller.w_img,
                self.controller.x_img,
                self.controller.manual_baseline,
                self.controller.rotate_angle,
                self.controller.baseline,
                self.controller.threshold,
            )

            # Process images with the proper callback
            results = self.controller.process_images(
                progress_callback=self._progress_callback,
                save_files=self.save_files,
                preview_middle=self.preview_middle,
                use_first_as_background=self.use_first_as_background,
            )

            if results:
                self.finished_signal.emit(results)

        except Exception as e:
            logger.error("Error in processing thread")
            logger.exception(e)
            self.error_signal.emit(str(e))

    def pause(self):
        """Pause processing after the current image is complete."""
        self.is_paused = True

    def resume(self):
        """Resume processing from where it was paused."""
        self.is_paused = False

    def stop(self):
        """Stop processing after the current image is complete."""
        self.should_stop = True
        self.is_paused = False  # Clear pause state when stopping

    def _progress_callback(
        self,
        progress,
        advancing_contact_angles,
        receding_contact_angles,
        center_points_px,
        result_images,
    ):
        """Handle progress updates during analysis and emit signals.

        Args:
            progress: Current progress value (0-100)
            advancing_contact_angles: List of advancing contact angles
            receding_contact_angles: List of receding contact angles
            center_points_px: List of center points in pixels
            result_images: Dictionary of result images

        Returns:
            bool: False if processing should stop, True otherwise

        """
        # Emit the signal with the data
        self.progress_signal.emit(
            progress,
            advancing_contact_angles,
            receding_contact_angles,
            center_points_px,
            result_images,
        )

        # Handle pause - sleep while paused
        while self.is_paused and not self.should_stop:
            self.msleep(100)  # Sleep to avoid high CPU usage

        # Return False if should stop, which will abort the processing
        return not self.should_stop

    def update_progress(
        self,
        progress,
        advancing_contact_angles,
        receding_contact_angles,
        center_points_px,
        result_images,
    ):
        """Update progress and emit signal."""
        self.progress_signal.emit(
            progress,
            advancing_contact_angles,
            receding_contact_angles,
            center_points_px,
            result_images,
        )
