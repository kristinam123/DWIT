"""Camera threading utilities for image acquisition in MesszelleApp."""

from PySide6.QtCore import QMutex, QObject, QThread

from src.utilities.logging_manager import get_logger

# Setup logger for this module
logger = get_logger(__name__)


class StoppableThread(QObject):
    """Helper class to manage thread stopping mechanism with Qt objects."""

    def __init__(self):
        """Initialize the StoppableThread."""
        super().__init__()

        self._stop_requested = False
        self._mutex = QMutex()

    def stop(self):
        """Request the thread to stop by setting the stop flag."""
        self._mutex.lock()
        self._stop_requested = True
        self._mutex.unlock()
        logger.info("Thread stop requested")

    def clear_stop(self):
        """Clear the stop request flag for the thread."""
        self._mutex.lock()
        self._stop_requested = False
        self._mutex.unlock()

    def is_stop_requested(self):
        """Check if a stop has been requested for the thread."""
        self._mutex.lock()
        result = self._stop_requested
        self._mutex.unlock()
        return result


class LiveFeedThread(QThread):
    """Thread for running the live camera feed loop."""

    def __init__(self, camera_core):
        """Initialize the LiveFeedThread with camera_core."""
        super().__init__()
        logger.info("Initializing LiveFeedThread")

        self.camera_core = camera_core
        self.stopper = StoppableThread()

    def run(self):
        """Execute the live feed loop in the thread."""
        logger.info("Starting live feed thread execution")

        try:
            frame_count = 0
            for _ in self.camera_core.live_feed_loop(self.stopper):
                frame_count += 1

                if self.stopper.is_stop_requested():
                    logger.info("Stop requested for live feed thread")
                    break

            logger.info(
                f"Live feed thread completed after processing {frame_count} frames"
            )

        except Exception as e:
            logger.error(f"Error in live feed thread: {e}")


class RecordingThread(QThread):
    """Thread for running the camera recording loop."""

    def __init__(self, camera_core):
        """Initialize the RecordingThread with camera_core."""
        super().__init__()
        logger.info("Initializing RecordingThread")

        self.camera_core = camera_core
        self.stopper = StoppableThread()

    def run(self):
        """Execute the recording loop in the thread."""
        logger.info("Starting camera recording thread execution")

        try:
            self.camera_core.record_feed_loop(self.stopper)
            logger.info("Camera recording thread completed successfully")

        except Exception as e:
            logger.error(f"Error in camera recording thread: {e}")


# Explicitly mark thread run() methods as used for static analysis
# These methods are automatically called by Qt's threading system
# when start() is invoked
_ = (LiveFeedThread.run, RecordingThread.run)
