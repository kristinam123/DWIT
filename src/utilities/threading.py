"""Threaded utilities for DWIT: analysis, automation, background creation.

And thread management.

This module provides utilities for running long-running operations off the GUI
thread and for safely managing QThread lifecycles:

- AnalysisThread: QThread that runs image analysis in the background and
    emits progress_signal, finished_signal, and error_signal for UI updates.
- AutomatisationThread: QThread for automation tasks that emits prompt and
    progress signals.
- create_background_threaded: starts background image creation in a separate
    ThreadPoolExecutor and returns a concurrent.futures.Future so background
    computation does not block startup (call .result() to wait for completion).
- _create_background_wrapper: internal wrapper for create_background_image with
    logging and error handling.
- ThreadManager: helper to stop worker QThreads with escalating termination
    (graceful -> extended wait -> forced terminate).
- qt_lock: context manager for QMutex to ensure proper lock/unlock.

Usage examples:
        future = create_background_threaded(
            files,
            rotate_angle=90,
            crop_params=(x, w, y, h),
        )
        background = future.result()

        thread = AnalysisThread(controller, save_files=True)
        thread.progress_signal.connect(on_progress)
        thread.finished_signal.connect(on_finished)
        thread.start()

Part of Droplet Wall Interaction Tool (DWIT).
"""

import copy
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import contextmanager

from PySide6.QtCore import (
    QMetaObject,
    QMutex,
    QObject,
    Qt,
    QThread,
    QWaitCondition,
    Signal,
)

from src.utilities.core_utils import get_logger
from src.utilities.image_utils import create_background_image

logger = get_logger(__name__)


@contextmanager
def qt_lock(mutex):
    """Context manager for QMutex to ensure proper lock/unlock.

    Args:
    ----
        mutex: QMutex instance to lock

    Yields:
    ------
        None

    Example:
    -------
        with qt_lock(self._pause_mutex):
            # Critical section
            self.is_paused = True

    """
    mutex.lock()
    try:
        yield
    finally:
        try:
            mutex.unlock()
        except RuntimeError:
            # Mutex already unlocked or destroyed
            pass


def create_background_threaded(
    image_paths: list[str],
    use_first_as_background: bool = False,
    num_images: int = 10,
    rotate_angle: float = 0,
    crop_params: tuple = (None, None, None, None),
    executor: ThreadPoolExecutor | None = None,
) -> Future:
    """Create background image in a separate thread.

    This function immediately returns a Future object and computes the
    background image in a background thread. This allows other operations
    (like baseline detection) to run concurrently.

    Args:
    ----
        image_paths: List of paths to all images
        use_first_as_background: Whether to use first image as background
        num_images: Number of images to use for background calculation
        rotate_angle: Rotation angle to apply to images
        crop_params: Tuple of (x, w, y, h) crop parameters
        executor: Optional ThreadPoolExecutor to use. If None, creates one.

    Returns:
    -------
        Future object that will contain the background image when complete.
        Call .result() to get the background (blocks until ready).

    Example:
    -------
        >>> # Start background creation
        >>> future = create_background_threaded(files, rotate_angle=90, ...)
        >>>
        >>> # Do other work
        >>> baseline_data = detect_baselines(files)
        >>>
        >>> # Get background (waits if not ready)
        >>> background = future.result()

    """
    logger.info("Starting background creation in separate thread")

    # Create executor if not provided
    owns_executor = executor is None
    if owns_executor:
        executor = ThreadPoolExecutor(max_workers=1)

    try:
        # Submit background creation task
        future = executor.submit(
            _create_background_wrapper,
            image_paths,
            use_first_as_background,
            num_images,
            rotate_angle,
            crop_params,
        )

        logger.debug("Background creation task submitted successfully")

        # If we created the executor, add callback to shut it down
        if owns_executor:

            def cleanup_callback(_):
                """Cleanup callback to shutdown executor after task completion."""
                executor.shutdown(wait=False)

            future.add_done_callback(cleanup_callback)

        return future

    except Exception as e:
        logger.error(f"Error submitting background creation task: {e}", exc_info=True)
        if owns_executor:
            executor.shutdown(wait=False)
        raise


def _create_background_wrapper(
    image_paths: list[str],
    use_first_as_background: bool,
    num_images: int,
    rotate_angle: float,
    crop_params: tuple,
):
    """Wrap create_background_image with error handling.

    This internal function wraps the actual background creation with
    comprehensive error handling and logging for the background thread.

    Args:
    ----
        image_paths: List of paths to all images
        use_first_as_background: Whether to use first image as background
        num_images: Number of images to use for background calculation
        rotate_angle: Rotation angle to apply to images
        crop_params: Tuple of (x, w, y, h) crop parameters

    Returns:
    -------
        Background image or None if creation fails

    """
    try:
        logger.info("Background thread started")

        background = create_background_image(
            image_paths,
            use_first_as_background=use_first_as_background,
            num_images=num_images,
            rotate_angle=rotate_angle,
            crop_params=crop_params,
        )

        if background is None:
            logger.error("Background creation returned None")
        else:
            logger.info(f"Background created successfully: {background.shape}")

        return background

    except Exception as e:
        logger.error(f"Error in background thread: {e}", exc_info=True)
        return None


class ThreadManager(QObject):
    """Manages multiple worker threads with timeouts and cleanup.

    This manager provides escalating termination strategies:
    1. Graceful stop: Request worker to stop and wait
    2. Extended wait: Give worker more time to complete
    3. Forced termination: Call terminate() as last resort

    Thread Safety:
        - All methods are safe to call from any thread
        - Internal dict protected by proper synchronization

    Lifecycle:
        1. Register threads via internal tracking
        2. Stop with stop_worker() or stop_all()
        3. Automatic cleanup of resources
    """

    def __init__(self):
        """Initialize thread manager."""
        super().__init__()
        self._active_threads = {}  # thread_id -> (thread, worker, timer)

    def stop_worker(
        self,
        thread_id: str,
        graceful_wait_ms: int = 1000,
        extended_wait_ms: int = 3000,
        force_terminate: bool = True,
    ):
        """Stop a worker thread with escalating termination strategy.

        This method implements a three-phase shutdown:
        1. Graceful: Request stop and wait graceful_wait_ms
        2. Extended: Wait additional extended_wait_ms for completion
        3. Forced: Call terminate() if force_terminate is True

        Args:
        ----
            thread_id: Identifier for the thread to stop
            graceful_wait_ms: Initial wait time for graceful stop (ms)
            extended_wait_ms: Additional wait time before forced termination (ms)
            force_terminate: Whether to force terminate if thread doesn't stop

        Example:
        -------
            >>> manager.stop_worker("worker_1", graceful_wait_ms=1000,
            ...                     extended_wait_ms=2000, force_terminate=True)

        """
        thread_info_id = threading.get_ident()

        if thread_id not in self._active_threads:
            logger.debug(
                f"[Thread-{thread_info_id}] Thread {thread_id} not found "
                f"in active threads"
            )
            return

        thread, worker, timeout_timer = self._active_threads[thread_id]

        # Stop timeout timer if exists
        if timeout_timer:
            try:
                # Ensure stopping the QTimer happens in the timer's own thread
                # to avoid "QObject::killTimer:
                #   Timers cannot be stopped from another thread".
                QMetaObject.invokeMethod(
                    timeout_timer,
                    "stop",
                    Qt.QueuedConnection,
                )
            except Exception:
                # Fallback to direct call
                # if invokeMethod is not available for some reason
                try:
                    timeout_timer.stop()
                except Exception:
                    pass

        # Phase 1: Graceful stop
        logger.info(
            f"[Thread-{thread_info_id}] Phase 1: Graceful stop requested "
            f"for thread {thread_id}"
        )

        if hasattr(worker, "request_stop"):
            worker.request_stop()
        elif hasattr(worker, "stop"):
            worker.stop()

        thread.quit()

        if thread.wait(graceful_wait_ms):
            logger.info(
                f"[Thread-{thread_info_id}] Thread {thread_id} stopped gracefully "
                f"within {graceful_wait_ms}ms"
            )
            self._cleanup_thread(thread_id)
            return

        # Phase 2: Extended wait
        logger.warning(
            f"[Thread-{thread_info_id}] Phase 2: Thread {thread_id} did not stop "
            f"gracefully, waiting additional {extended_wait_ms}ms"
        )

        if thread.wait(extended_wait_ms):
            logger.info(
                f"[Thread-{thread_info_id}] Thread {thread_id} stopped after "
                f"extended wait"
            )
            self._cleanup_thread(thread_id)
            return

        # Phase 3: Forced termination
        if force_terminate:
            logger.error(
                f"[Thread-{thread_info_id}] Phase 3: Forcing termination of "
                f"thread {thread_id} after {graceful_wait_ms + extended_wait_ms}ms",
                exc_info=False,
            )
            thread.terminate()

            # Wait briefly for termination to complete
            if thread.wait(500):
                logger.warning(
                    f"[Thread-{thread_info_id}] Thread {thread_id} forcibly terminated"
                )
            else:
                logger.error(
                    f"[Thread-{thread_info_id}] Thread {thread_id} failed to "
                    f"terminate even after terminate() call",
                    exc_info=False,
                )
        else:
            logger.error(
                f"[Thread-{thread_info_id}] Thread {thread_id} did not stop and "
                f"force_terminate=False, leaving thread running",
                exc_info=False,
            )

        self._cleanup_thread(thread_id)

    def stop_all(
        self,
        graceful_wait_ms: int = 1000,
        extended_wait_ms: int = 3000,
        force_terminate: bool = True,
    ):
        """Stop all active worker threads with escalating termination.

        Args:
        ----
            graceful_wait_ms: Initial wait time for graceful stop (ms)
            extended_wait_ms: Additional wait time before forced termination (ms)
            force_terminate: Whether to force terminate threads that don't stop

        Example:
        -------
            >>> manager.stop_all(graceful_wait_ms=1000, extended_wait_ms=2000)

        """
        thread_info_id = threading.get_ident()
        thread_ids = list(self._active_threads.keys())
        logger.info(
            f"[Thread-{thread_info_id}] Stopping {len(thread_ids)} active threads"
        )

        for thread_id in thread_ids:
            self.stop_worker(
                thread_id,
                graceful_wait_ms=graceful_wait_ms,
                extended_wait_ms=extended_wait_ms,
                force_terminate=force_terminate,
            )

    def _cleanup_thread(self, thread_id: str):
        """Clean up thread resources.

        Args:
        ----
            thread_id: Identifier for the thread to clean up

        """
        thread_info_id = threading.get_ident()

        if thread_id in self._active_threads:
            thread, worker, timeout_timer = self._active_threads.pop(thread_id)

            # Clean up Qt objects
            if timeout_timer:
                timeout_timer.deleteLater()
            if worker:
                worker.deleteLater()
            if thread:
                thread.deleteLater()

            logger.debug(f"[Thread-{thread_info_id}] Cleaned up thread {thread_id}")


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
        thread_id = threading.get_ident()
        logger.debug(f"[Thread-{thread_id}] Initializing AutomatisationThread")

        self.controller = controller

        # Explicitly reference unused signals for static analysis
        _ = (self.prompt_message, self.progress_update)

    def run(self):
        """Execute the automation process in the thread."""
        thread_id = threading.get_ident()
        logger.info(f"[Thread-{thread_id}] AutomatisationThread started")
        logger.debug(f"[Thread-{thread_id}] Starting automation process in thread")

        # Explicitly mark thread run() method as used for static analysis
        # This method is automatically called by Qt's threading system
        # when start() is invoked
        _ = AutomatisationThread.run

        try:
            result = self.controller._automatisation()
            thread_id = threading.get_ident()
            logger.debug(
                f"[Thread-{thread_id}] Automation completed successfully "
                f"with result: {result}"
            )
            self.prompt_signal.emit(result)
        except Exception as e:
            thread_id = threading.get_ident()
            logger.error(
                f"[Thread-{thread_id}] Automation error occurred: {e!s}",
                exc_info=True,
            )
            error_message = f"Automation error: {e!s}"
            self.prompt_signal.emit(error_message)
        finally:
            thread_id = threading.get_ident()
            logger.info(f"[Thread-{thread_id}] AutomatisationThread finished")


class AnalysisThread(QThread):
    """Thread for running analysis operations."""

    progress_signal = Signal(float, list, list, list, dict, dict)
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

        # Thread-safe state management using RLock for reentrant locking
        self._state_lock = threading.RLock()
        self._is_paused = False
        self._should_stop = False

        # Add Qt synchronization primitives for proper pause/resume
        self._pause_mutex = QMutex()
        self._pause_condition = QWaitCondition()

    # Thread-safe property accessors
    @property
    def is_paused(self):
        """Thread-safe getter for is_paused flag."""
        with self._state_lock:
            return self._is_paused

    @is_paused.setter
    def is_paused(self, value):
        """Thread-safe setter for is_paused flag."""
        with self._state_lock:
            self._is_paused = value

    @property
    def should_stop(self):
        """Thread-safe getter for should_stop flag."""
        with self._state_lock:
            return self._should_stop

    @should_stop.setter
    def should_stop(self, value):
        """Thread-safe setter for should_stop flag."""
        with self._state_lock:
            self._should_stop = value

    # In the run method of AnalysisThread
    def run(self):
        """Run analysis process in a separate thread."""
        thread_id = threading.get_ident()
        logger.info(f"[Thread-{thread_id}] AnalysisThread started")
        try:
            # Reset state variables at start
            self.is_paused = False
            self.should_stop = False
            logger.debug(
                f"[Thread-{thread_id}] State reset: is_paused=False, should_stop=False"
            )

            # Get all parameters from controller
            thread_id = threading.get_ident()
            logger.debug(
                f"[Thread-{thread_id}] Updating analysis parameters from controller"
            )
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
            thread_id = threading.get_ident()
            logger.info(f"[Thread-{thread_id}] Starting image analysis process")
            results = self.controller.process_images(
                progress_callback=self._progress_callback,
                save_files=self.save_files,
                preview_middle=self.preview_middle,
                use_first_as_background=self.use_first_as_background,
            )

            if results:
                thread_id = threading.get_ident()
                logger.info(
                    f"[Thread-{thread_id}] Image analysis completed successfully"
                )
                self.finished_signal.emit(results)
            else:
                thread_id = threading.get_ident()
                logger.warning(
                    f"[Thread-{thread_id}] Image analysis did not return results"
                )

        except Exception as e:
            thread_id = threading.get_ident()
            logger.error(
                f"[Thread-{thread_id}] Error in processing thread: {e}",
                exc_info=True,
            )
            self.error_signal.emit(str(e))
        finally:
            thread_id = threading.get_ident()
            logger.info(f"[Thread-{thread_id}] AnalysisThread finished")

    def stop(self):
        """Stop processing after the current image is complete."""
        thread_id = threading.get_ident()
        logger.info(f"[Thread-{thread_id}] AnalysisThread stop requested")
        # Wake any waiting pause condition so the thread can break out
        # of a paused wait and observe should_stop
        with qt_lock(self._pause_mutex):
            self.should_stop = True
            self.is_paused = False  # Clear pause state when stopping
            try:
                self._pause_condition.wakeAll()
            except Exception:
                # If wakeAll fails, the thread will still observe should_stop
                pass

    def _progress_callback(
        self,
        progress,
        advancing_contact_angles,
        receding_contact_angles,
        center_points_px,
        result_images,
        result_lists=None,
    ):
        """Handle progress updates during analysis and emit signals.

        Args:
        ----
            progress: Current progress value (0-100)
            advancing_contact_angles: List of advancing contact angles
            receding_contact_angles: List of receding contact angles
            center_points_px: List of center points in pixels
            result_images: Dictionary of result images
            result_lists: Dictionary of complete result lists (optional)

        Returns:
        -------
            bool: False if processing should stop, True otherwise

        """
        # Emit the signal with a deep copy of result_images to prevent reference
        # issues when the signal is queued across threads. Deep copy is necessary
        # because the dict contains numpy arrays that would be shared with shallow copy.
        self.progress_signal.emit(
            progress,
            advancing_contact_angles,
            receding_contact_angles,
            center_points_px,
            copy.deepcopy(result_images),
            result_lists or {},
        )

        # Handle pause - wait for resume signal
        with qt_lock(self._pause_mutex):
            while self.is_paused and not self.should_stop:
                self._pause_condition.wait(self._pause_mutex)  # Proper Qt wait

        # Return False if should stop, which will abort the processing
        return not self.should_stop
