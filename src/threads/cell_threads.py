"""Cell threading utilities for automation and experiment control in MesszelleApp."""

from PySide6.QtCore import QMutex, QObject, QThread, QWaitCondition, Signal

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


class StopEvent(QObject):
    """Thread-safe event for stopping threads."""

    def __init__(self):
        """Initialize the StopEvent."""
        super().__init__()

        self._mutex = QMutex()
        self._condition = QWaitCondition()
        self._flag = False

    def set(self):
        """Set the internal flag to true and wake all waiting threads."""
        self._mutex.lock()
        self._flag = True
        self._condition.wakeAll()
        self._mutex.unlock()
        logger.debug("StopEvent flag set, all waiting threads notified")

    def clear(self):
        """Clear the stop event flag."""
        self._mutex.lock()
        self._flag = False
        self._mutex.unlock()

    def is_set(self):
        """Check whether the internal flag is set."""
        self._mutex.lock()
        result = self._flag
        self._mutex.unlock()
        return result

    def wait(self, timeout=None):
        """Block until the stop event is set or the timeout expires."""
        self._mutex.lock()
        if not self._flag:
            if timeout is not None:
                self._condition.wait(self._mutex, timeout * 1000)  # Convert to ms
            else:
                self._condition.wait(self._mutex)
        result = self._flag
        self._mutex.unlock()
        return result
