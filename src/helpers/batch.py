"""Batch processing utilities.

For folder-based analysis in Droplet Wall Interaction Tool.
"""

import os
import threading
from contextlib import contextmanager

from PySide6.QtCore import (
    QMutex,
    QObject,
    QRect,
    QSize,
    Qt,
    QWaitCondition,
    Signal,
)
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QStyledItemDelegate, QStyleOptionViewItem

from src.utilities.core_utils import encode_path, get_logger

# Custom delegate for rendering folder items with progress bars
# Setup logger for this module
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


class FolderItemDelegate(QStyledItemDelegate):
    """Delegate for rendering folder items with progress bars."""

    def __init__(self, parent=None):
        """Initialize the FolderItemDelegate."""
        super().__init__(parent)
        self.progress_data = {}  # {folder_path: progress_value}
        # {folder_path: bool} whether results_raw.xlsx exists
        self.results_presence = {}
        self.folder_list_widget = None  # Reference to the folder list widget

    def set_results_presence(self, folder_path, has_results: bool):
        """Set whether a folder has results file present."""
        # Use encoded token as internal key so dictionaries only contain
        # ASCII-safe keys even when original paths contain non-ASCII chars.
        try:
            key = encode_path(folder_path) if folder_path else folder_path
        except Exception:
            # Fallback to raw path if encoding fails
            key = folder_path

        # Only update the presence flag here. Do NOT forcefully override
        # the per-folder progress value — progress should reflect live
        # processing and not be reset/overridden by background scans.
        self.results_presence[key] = bool(has_results)
        # Ensure an entry exists in progress_data to avoid KeyError on paint,
        # but do not change existing progress values when a scan reports
        # presence/absence. This preserves in-progress UI state.
        try:
            if key not in self.progress_data:
                # Default to 0 only if we don't already have progress info
                self.progress_data[key] = 0
        except Exception:
            # Defensive fallback
            self.progress_data = {key: 0}

    def clear_results_presence(self):
        """Clear all results presence data."""
        self.results_presence = {}
        # Also clear any per-row progress data to avoid stale progress bars
        try:
            self.progress_data = {}
        except Exception:
            self.progress_data = {}

    def set_progress(self, folder_path, progress_value):
        """Set progress value for a folder (0-100, or -1 for error)."""
        try:
            key = encode_path(folder_path) if folder_path else folder_path
        except Exception:
            key = folder_path
        self.progress_data[key] = progress_value

    def size_hint(self, option, index):
        """Return a larger size to accommodate path and progress bar."""
        base_size = super().size_hint(option, index)
        # Add more height for progress bar
        return QSize(base_size.width(), base_size.height() + 10)

    def paint(self, painter, option, index):
        """Draw an indicator left of the item text and progress bar below."""
        try:
            row = index.row()

            # Get the folder path from the item data to use as key
            folder_path = None
            if hasattr(index, "data") and index.data(Qt.UserRole):
                folder_path = index.data(Qt.UserRole)
            elif self.folder_list_widget and row < self.folder_list_widget.count():
                item = self.folder_list_widget.item(row)
                if item:
                    folder_path = item.data(Qt.UserRole)

            # Choose colors based on presence (use folder path as key)
            # Use encoded key lookup to support non-ASCII folder paths.
            try:
                lookup_key = encode_path(folder_path) if folder_path else folder_path
            except Exception:
                lookup_key = folder_path

            has_results = (
                self.results_presence.get(lookup_key, False) if folder_path else False
            )
            # green if results, gray otherwise
            circle_color = QColor(0, 170, 0) if has_results else QColor(150, 150, 150)

            icon_size = 14
            spacing = 8

            painter.save()

            # Draw the filled circle
            circle_rect = QRect(
                option.rect.left() + 4,
                option.rect.top() + (option.rect.height() - icon_size) // 2 - 2,
                icon_size,
                icon_size,
            )
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setBrush(circle_color)
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(circle_rect)

            # If has_results draw simple white checkmark
            if has_results:
                pen = QPen(Qt.white)
                pen.setWidth(2)
                painter.setPen(pen)
                # draw two-line checkmark
                x = circle_rect.left()
                y = circle_rect.top()
                w = circle_rect.width()
                h = circle_rect.height()
                painter.drawLine(
                    x + int(w * 0.22),
                    y + int(h * 0.53),
                    x + int(w * 0.45),
                    y + int(h * 0.75),
                )
                painter.drawLine(
                    x + int(w * 0.45),
                    y + int(h * 0.75),
                    x + int(w * 0.8),
                    y + int(h * 0.3),
                )

            # Draw progress bar (progress is independent from the done/checkmark)
            progress_value = self.progress_data.get(lookup_key, 0) if folder_path else 0

            # Only draw progress bar if we have some progress or completed folder
            if progress_value > 0 or has_results:
                # Progress bar dimensions - very thin line
                progress_height = 2
                progress_margin = 4

                # Full progress bar background (light gray)
                progress_bg_rect = QRect(
                    option.rect.left() + progress_margin,
                    option.rect.bottom() - progress_height - 2,
                    option.rect.width() - 2 * progress_margin,
                    progress_height,
                )

                painter.setBrush(QColor(200, 200, 200))
                painter.setPen(Qt.NoPen)
                painter.drawRect(progress_bg_rect)

                # Progress fill - same green as checkmark
                if progress_value > 0:
                    progress_width = int(
                        (progress_bg_rect.width() * min(progress_value, 100)) / 100
                    )
                    if progress_width > 0:
                        progress_fill_rect = QRect(
                            progress_bg_rect.left(),
                            progress_bg_rect.top(),
                            progress_width,
                            progress_height,
                        )

                        painter.setBrush(QColor(0, 170, 0))  # Same green as checkmark
                        painter.drawRect(progress_fill_rect)

            painter.restore()

            # Shift the option rect to the right so the base painting doesn't overlap
            # Also shift up slightly to make room for progress bar
            opt = QStyleOptionViewItem(option)
            opt.rect = QRect(
                option.rect.left() + icon_size + spacing,
                option.rect.top(),
                option.rect.width() - icon_size - spacing,
                option.rect.height() - 4,  # Leave space for progress bar at bottom
            )

            super().paint(painter, opt, index)
        except Exception:
            # Fallback to default painting on error
            super().paint(painter, option, index)


# Modify the BatchProcessingWorker class to report image-by-image progress
class BatchProcessingWorker(QObject):
    """Worker for processing multiple folders in a batch."""

    progress_updated = Signal(
        int, str, int
    )  # folder_index, folder_path, progress_percent (0-100)
    folder_completed = Signal(int, str, bool)  # folder_index, folder_path, success
    all_completed = Signal()
    error_occurred = Signal(int, str, str)  # folder_index, folder_path, error_message
    overall_progress_updated = Signal(
        int, int, float
    )  # current_folder, total_folders, overall_progress (0-100)

    # Add new signal for preview images during batch processing
    preview_image_updated = Signal(
        float, list, list, list, dict, dict
    )  # q, adv_angles, rec_angles, center_points, result_images, result_lists

    # Signal to emit folder results after completion for frame data storage
    folder_results_ready = Signal(
        int, str, tuple
    )  # folder_index, folder_path, results (time, time_int, result_lists)

    def __init__(self, controller, folder_paths, progress_callback=None):
        """Initialize the BatchProcessor.

        Sets up controller, folder paths, and optional progress callback.
        """
        super().__init__()
        self.controller = controller
        self.folder_paths = folder_paths
        self.progress_callback = progress_callback

        # Thread-safe state management using RLock for reentrant locking
        self._state_lock = threading.RLock()
        self._is_paused = False
        self._should_stop = False
        self._should_skip_current = False

        # Thread-safe controller access
        self._controller_lock = threading.Lock()

        # Add Qt synchronization primitives for proper pause/resume
        self._pause_mutex = QMutex()
        self._pause_condition = QWaitCondition()

        thread_id = threading.get_ident()
        logger.debug(
            f"[Thread-{thread_id}] BatchProcessingWorker initialized "
            f"with {len(folder_paths)} folders"
        )

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

    @property
    def should_skip_current(self):
        """Thread-safe getter for should_skip_current flag."""
        with self._state_lock:
            return self._should_skip_current

    @should_skip_current.setter
    def should_skip_current(self, value):
        """Thread-safe setter for should_skip_current flag."""
        with self._state_lock:
            self._should_skip_current = value

    def _safe_set_folder_path(self, folder_path):
        """Thread-safe method to set controller folder path.

        This method ensures that controller access is protected by a lock
        to prevent race conditions when multiple threads access the controller.

        Args:
        ----
            folder_path: Path to the folder to set in the controller

        """
        with self._controller_lock:
            self.controller.set_folder_path(folder_path)
            thread_id = threading.get_ident()
            logger.debug(
                f"[Thread-{thread_id}] Controller folder path set to: {folder_path}"
            )

    def process_folders(self):
        """Process all folders in the queue."""
        thread_id = threading.get_ident()
        logger.info(f"[Thread-{thread_id}] Starting batch folder processing")
        self.is_paused = False
        self.should_stop = False
        total_folders = len(self.folder_paths)
        successful_folders = 0
        failed_folders = 0

        for i, folder_path in enumerate(self.folder_paths):
            if self.should_stop:
                logger.info(
                    f"Processing stopped by user at folder {i + 1}/{total_folders}"
                )
                break

            current_folder = i + 1
            logger.info(
                f"Processing folder {current_folder}/{total_folders}: {folder_path}"
            )

            # Emit overall progress signal - starting this folder
            # Calculate overall progress (combination of folders completed
            # and current folder progress)
            overall_progress = (
                i / total_folders
            ) * 100  # Progress from completed folders
            self.overall_progress_updated.emit(
                current_folder, total_folders, overall_progress
            )

            # Emit progress for starting the current folder
            self.progress_updated.emit(i, folder_path, 1)  # 1% to show starting

            try:
                # Handle pause state - wait until unpaused
                with qt_lock(self._pause_mutex):
                    while self.is_paused and not self.should_stop:
                        self._pause_condition.wait(self._pause_mutex)  # Proper Qt wait

                if self.should_stop:
                    break
                # Reset skip flag at start of folder
                self.should_skip_current = False

                # Set the current folder path in the controller (thread-safe)
                self._safe_set_folder_path(folder_path)

                # Process the folder
                results = self.controller.process_images(
                    lambda progress, *args: self._folder_progress_callback(
                        i,
                        current_folder,
                        total_folders,
                        folder_path,
                        progress,
                        *args,
                    ),
                    save_files=(True and not self.should_stop),
                    preview_middle=False,
                    use_first_as_background=False,
                )

                # If skip was requested mid-processing, mark folder as skipped
                if self.should_skip_current:
                    logger.info(f"Folder skipped by user: {folder_path}")
                    self.folder_completed.emit(i, folder_path, False)
                    continue

                # If we're stopping, don't emit completion signals
                if self.should_stop:
                    break

                success = results is not None
                if success:
                    successful_folders += 1
                    logger.info(f"Successfully processed folder: {folder_path}")
                    # Emit folder results for frame data storage
                    self.folder_results_ready.emit(i, folder_path, results)
                else:
                    failed_folders += 1
                    logger.warning(f"Failed to process folder: {folder_path}")

                self.folder_completed.emit(i, folder_path, success)

                # Update overall progress after folder completion
                overall_progress = (current_folder / total_folders) * 100
                self.overall_progress_updated.emit(
                    current_folder, total_folders, overall_progress
                )

            except Exception as e:
                failed_folders += 1
                logger.error(
                    f"Error processing folder {folder_path}: {e}", exc_info=True
                )
                self.error_occurred.emit(i, folder_path, str(e))
                self.folder_completed.emit(i, folder_path, False)

        logger.info(
            f"Batch processing completed: {successful_folders} successful, "
            f"{failed_folders} failed"
        )
        self.all_completed.emit()

    def stop(self):
        """Stop processing after the current image is complete."""
        # Acquire mutex and wake any waiting pause condition so the
        # worker can notice `should_stop` and exit promptly even if it
        # was paused when the stop was requested.
        with qt_lock(self._pause_mutex):
            self.should_stop = True
            self.is_paused = False  # Also clear pause state when stopping
            # Wake any threads waiting in the pause condition
            try:
                self._pause_condition.wakeAll()
            except Exception:
                # If wakeAll fails for whatever reason, continue and rely
                # on the next progress callback check to stop the loop.
                pass

        thread_id = threading.get_ident()
        logger.info(f"[Thread-{thread_id}] Batch processing stop requested")

    def _folder_progress_callback(
        self, folder_index, current_folder, total_folders, folder_path, progress, *args
    ):
        """Report progress within a single folder."""
        # Convert progress (0-1) to percent (0-100)
        progress_percent = int(progress * 100)

        # Ensure we emit at least 1% at the start and never more than 99% until complete
        if progress_percent < 1 and progress > 0:
            progress_percent = 1
        elif progress_percent > 99 and progress < 1:
            progress_percent = 99

        # Emit progress for current folder
        self.progress_updated.emit(folder_index, folder_path, progress_percent)

        # Calculate and emit overall progress
        # Previous completed folders + (progress through current folder / total folders)
        overall_progress = (((current_folder - 1) + progress) / total_folders) * 100
        self.overall_progress_updated.emit(
            current_folder, total_folders, overall_progress
        )

        # Forward preview images to the UI if args are provided
        if len(args) >= 4:
            # Unpack the arguments - now includes result_lists as 5th arg
            adv_angles = args[0]
            rec_angles = args[1]
            center_points = args[2]
            result_images = args[3]
            # Extract result_lists if available (5th argument)
            result_lists = args[4] if len(args) >= 5 else {}
            # Pass the folder index as additional info to know which folder
            # we're processing
            result_images["folder_index"] = folder_index
            result_images["folder_path"] = folder_path
            # Emit the preview image signal with result_lists
            self.preview_image_updated.emit(
                progress,
                adv_angles,
                rec_angles,
                center_points,
                result_images,
                result_lists,
            )

        # Return False if processing should stop or pause
        if self.should_stop:
            return False

        # If we should skip current folder, return False to break controller loop
        if self.should_skip_current:
            return False

        return not self.is_paused


class ResultsScannerWorker(QObject):
    """Worker that periodically scans a list of folders for presence of results file.

    Emits `scan_result` with (folder_index:int, folder_path:str, has_results:bool)
    and `finished` when stopped.
    """

    scan_result = Signal(int, str, bool)
    finished = Signal()

    def __init__(self, parent=None, interval_ms: int = 5000):
        """Initialize the ResultsScannerWorker."""
        super().__init__(parent)
        self.interval_ms = max(int(interval_ms), 2000)  # Minimum 2 seconds
        self._running = False
        self._folder_paths = []
        self._stop_requested = False
        # Initialize timer as None - will be created in start_scanning
        self._scan_timer = None

    def __del__(self):
        """Ensure timer is cleaned up when worker is destroyed."""
        try:
            if hasattr(self, "_scan_timer") and self._scan_timer:
                self._scan_timer.stop()
                self._scan_timer.deleteLater()
        except Exception:
            pass  # Ignore cleanup errors during destruction

    def set_folder_paths(self, folder_paths: list[str]):
        """Set the list of folder paths to scan."""
        try:
            self._folder_paths = list(folder_paths) if folder_paths else []
        except Exception:
            self._folder_paths = []

    def _check_single_folder(self, folder_path: str) -> bool:
        """Check if a single folder has results file."""
        if not folder_path or not isinstance(folder_path, str):
            return False

        try:
            if not (os.path.exists(folder_path) and os.path.isdir(folder_path)):
                return False
            results_path = os.path.join(folder_path, "results_raw.xlsx")
            return os.path.exists(results_path)
        except (
            OSError,
            PermissionError,
            FileNotFoundError,
            TypeError,
            ValueError,
        ):
            return False
        except Exception:
            return False

    def _emit_scan_result(self, i: int, folder_path: str, has: bool):
        """Safely emit scan result."""
        if self._stop_requested or not self._running:
            return
        # Emit scan result with proper error handling and logging
        if self._stop_requested or not self._running:
            return

        try:
            idx = int(i)
            path = "" if folder_path is None else str(folder_path)
            has_flag = bool(has)
            self.scan_result.emit(idx, path, has_flag)
        except Exception as exc:
            # Log the failure but don't raise to avoid stopping the scanner loop
            logger.exception(
                "Failed to emit scan_result for folder %r (index=%r): %s",
                folder_path,
                i,
                exc,
            )

    def start_scanning(self):
        """Start the scanning loop using QTimer."""
        from PySide6.QtCore import QTimer

        self._running = True
        self._stop_requested = False

        # Create timer for periodic scanning in the worker's thread
        self._scan_timer = QTimer(self)  # Parent to this QObject
        self._scan_timer.timeout.connect(self._do_scan_iteration)
        self._scan_timer.setSingleShot(False)
        self._scan_timer.start(self.interval_ms)

    def _do_scan_iteration(self):
        """Perform one scan iteration."""
        if self._stop_requested or not self._running:
            if hasattr(self, "_scan_timer") and self._scan_timer:
                self._scan_timer.stop()
                self._scan_timer.deleteLater()
                self._scan_timer = None
            self.finished.emit()
            return

        try:
            current_paths = self._folder_paths.copy()

            for i, folder_path in enumerate(current_paths):
                if self._stop_requested or not self._running:
                    break

                has = self._check_single_folder(folder_path)
                self._emit_scan_result(i, folder_path, has)

        except Exception:
            # If something goes wrong, continue on next iteration
            pass

    def stop(self):
        """Stop scanning after the current loop iteration."""
        self._stop_requested = True
        self._running = False

        # Emit finished signal immediately to ensure cleanup
        if hasattr(self, "_scan_timer") and self._scan_timer:
            # Use QTimer.singleShot to safely stop timer from any thread
            from PySide6.QtCore import QTimer

            QTimer.singleShot(0, self._safe_timer_stop)
        else:
            self.finished.emit()

    def _safe_timer_stop(self):
        """Safely stop the timer from the correct thread."""
        if hasattr(self, "_scan_timer") and self._scan_timer:
            self._scan_timer.stop()
            self._scan_timer.deleteLater()
            self._scan_timer = None
        self.finished.emit()
