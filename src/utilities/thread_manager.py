"""Thread management utilities for safe Qt threading patterns."""

from PySide6.QtCore import QObject

from src.utilities.logging_manager import get_logger

logger = get_logger(__name__)


class ThreadManager(QObject):
    """Manages multiple worker threads with timeouts and cleanup."""

    def __init__(self):
        """Initialize thread manager."""
        super().__init__()
        self._active_threads = {}  # thread_id -> (thread, worker, timer)

    def stop_worker(self, thread_id: str, wait_ms: int = 1000):
        """Stop a worker thread gracefully."""
        if thread_id not in self._active_threads:
            return

        thread, worker, timeout_timer = self._active_threads[thread_id]

        # Stop timeout timer
        timeout_timer.stop()

        # Request worker to stop
        worker.request_stop()

        # Quit thread and wait
        thread.quit()
        if not thread.wait(wait_ms):
            logger.warning(f"Thread {thread_id} did not stop gracefully")

        self._cleanup_thread(thread_id)

    def stop_all(self, wait_ms: int = 1000):
        """Stop all active worker threads."""
        thread_ids = list(self._active_threads.keys())
        for thread_id in thread_ids:
            self.stop_worker(thread_id, wait_ms)

    def _cleanup_thread(self, thread_id: str):
        """Clean up thread resources."""
        if thread_id in self._active_threads:
            thread, worker, timeout_timer = self._active_threads.pop(thread_id)
            timeout_timer.deleteLater()
            worker.deleteLater()
            thread.deleteLater()
            logger.debug(f"Cleaned up thread {thread_id}")


# Global thread manager instance
thread_manager = ThreadManager()
