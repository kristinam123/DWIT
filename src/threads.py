"""Thread for running analysis operations in a separate QThread.

This module defines AnalysisThread, which handles image analysis in a background thread,
emitting progress, finished, and error signals for UI updates.
"""

from PySide6.QtCore import QMutex, QThread, QWaitCondition, Signal

from src.utilities.logging_manager import get_logger

# Setup logger for this module
logger = get_logger(__name__)


class AutomatisationThread(QThread):
    """Custom QThread for handling automation tasks."""

    # Signals used by the automation system
    prompt_signal = Signal(str)
    progress_signal = Signal(int)

    # Legacy signal names for backward compatibility
    # explicitly mark as used for static analysis
    prompt_message = Signal(str)
    progress_update = Signal(int)

    def __init__(self, controller):
        """Initialize the AutomatisationThread with controller."""
        super().__init__()
        logger.debug("Initializing AutomatisationThread")

        self.controller = controller

        # Explicitly reference unused signals for static analysis
        _ = (self.prompt_message, self.progress_update)

    def run(self):
        """Execute the automation process in the thread."""
        logger.info("AutomatisationThread started")
        logger.debug("Starting automation process in thread")

        # Explicitly mark thread run() method as used for static analysis
        # This method is automatically called by Qt's threading system
        # when start() is invoked
        _ = AutomatisationThread.run

        try:
            result = self.controller._automatisation()
            logger.debug(f"Automation completed successfully with result: {result}")
            self.prompt_signal.emit(result)
        except Exception as e:
            logger.error(f"Automation error occurred: {e!s}")
            error_message = f"Automation error: {e!s}"
            self.prompt_signal.emit(error_message)
        finally:
            logger.info("AutomatisationThread finished")


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
        ----
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
        # Add Qt synchronization primitives for proper pause/resume
        self._pause_mutex = QMutex()
        self._pause_condition = QWaitCondition()

    # In the run method of AnalysisThread
    def run(self):
        """Run analysis process in a separate thread."""
        logger.info("AnalysisThread started")
        try:
            # Reset state variables at start
            self.is_paused = False
            self.should_stop = False
            logger.debug("State reset: is_paused=False, should_stop=False")

            # Get all parameters from controller
            logger.debug("Updating analysis parameters from controller")
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
            logger.info("Starting image analysis process")
            results = self.controller.process_images(
                progress_callback=self._progress_callback,
                save_files=self.save_files,
                preview_middle=self.preview_middle,
                use_first_as_background=self.use_first_as_background,
            )

            if results:
                logger.info("Image analysis completed successfully")
                self.finished_signal.emit(results)
            else:
                logger.warning("Image analysis did not return results")

        except Exception as e:
            logger.error("Error in processing thread")
            logger.exception(e)
            self.error_signal.emit(str(e))
        finally:
            logger.info("AnalysisThread finished")

    def pause(self):
        """Pause processing after the current image is complete."""
        logger.info("AnalysisThread pause requested")
        self._pause_mutex.lock()
        self.is_paused = True
        self._pause_mutex.unlock()

    def resume(self):
        """Resume processing from where it was paused."""
        logger.info("AnalysisThread resume requested")
        self._pause_mutex.lock()
        self.is_paused = False
        self._pause_condition.wakeAll()  # Wake up any waiting threads
        self._pause_mutex.unlock()

    def stop(self):
        """Stop processing after the current image is complete."""
        logger.info("AnalysisThread stop requested")
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
        ----
            progress: Current progress value (0-100)
            advancing_contact_angles: List of advancing contact angles
            receding_contact_angles: List of receding contact angles
            center_points_px: List of center points in pixels
            result_images: Dictionary of result images

        Returns:
        -------
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

        # Handle pause - wait for resume signal
        self._pause_mutex.lock()
        while self.is_paused and not self.should_stop:
            self._pause_condition.wait(self._pause_mutex)  # Proper Qt wait
        self._pause_mutex.unlock()

        # Return False if should stop, which will abort the processing
        return not self.should_stop
