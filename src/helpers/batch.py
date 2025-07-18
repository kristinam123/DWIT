"""Batch processing utilities for folder-based analysis in MesszelleApp."""

from PySide6.QtCore import QObject, QRect, QSize, QThread, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QStyledItemDelegate

from src.utilities.logging_manager import get_logger

# Custom delegate for rendering folder items with progress bars
# Setup logger for this module
logger = get_logger(__name__)


class FolderItemDelegate(QStyledItemDelegate):
    """Delegate for rendering folder items with progress bars."""

    def __init__(self, parent=None):
        """Initialize the FolderItemDelegate."""
        super().__init__(parent)
        self.progress_data = {}  # {row: progress_value}
        self.main_folder_index = -1  # Track which folder is the main folder

    def set_progress(self, row, progress_value):
        """Set progress value for a row (0-100, or -1 for error)."""
        self.progress_data[row] = progress_value

    def set_main_folder(self, index):
        """Set the index of the main folder to highlight."""
        self.main_folder_index = index

    def paint(self, painter, option, index):
        """Paint the folder item with progress bar and highlighting for main folder."""
        # Save original state
        painter.save()
        try:
            # 1. Draw main folder background first (if main folder)
            if index.row() == self.main_folder_index:
                rwth_blue = QColor(0, 84, 159)  # RWTH blue #00549F
                painter.fillRect(option.rect, rwth_blue)
                border_color = QColor(0, 60, 120)  # Darker RWTH blue for border
                painter.setPen(border_color)
                painter.drawRect(option.rect.adjusted(1, 1, -1, -1))
                text_color = QColor(255, 255, 255)  # White text
            else:
                text_color = option.palette.text().color()

            # 2. Draw progress bar for ALL folders (main and regular)
            progress = self.progress_data.get(index.row(), 0)
            text = index.data()
            if text:
                if index.row() == self.main_folder_index:
                    text_rect = option.rect.adjusted(0, 0, -4, 0)
                else:
                    text_rect = option.rect.adjusted(4, 0, -4, 0)
            else:
                text_rect = option.rect

            if progress > 0 or progress == -1:  # -1 indicates error state
                progress_rect = text_rect
                # Draw progress background
                painter.fillRect(progress_rect, QColor(200, 200, 200))
                # Draw progress
                if progress == -1:  # Error state
                    painter.fillRect(
                        progress_rect, QColor(255, 80, 80)
                    )  # Red for error
                else:
                    progress_width = int((progress_rect.width() * progress) / 100)
                    if progress_width > 0:
                        painter.fillRect(
                            QRect(
                                progress_rect.left(),
                                progress_rect.top(),
                                progress_width,
                                progress_rect.height(),
                            ),
                            QColor(0, 150, 0),  # Green for progress
                        )

            # 3. Draw text for all folders (on top of progress bar)
            text = index.data()
            if text:
                if index.row() == self.main_folder_index:
                    text_rect = option.rect.adjusted(0, 0, -4, 0)
                else:
                    text_rect = option.rect.adjusted(4, 0, -4, 0)
                painter.setPen(text_color)
                painter.drawText(text_rect, option.displayAlignment, str(text))

        except Exception as e:
            logger.error(f"Error painting folder item at row {index.row()}: {e}")
        finally:
            painter.restore()

    def size_hint(self, option, index):
        """Return a slightly larger size to accommodate the shortened path."""
        base_size = super().size_hint(option, index)
        return QSize(base_size.width(), base_size.height() + 6)  # Add a bit more height


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
        float, list, list, list, dict
    )  # q, adv_angles, rec_angles, center_points, result_images

    def __init__(self, controller, folder_paths, progress_callback=None):
        """Initialize the BatchProcessor.

        Sets up controller, folder paths, and optional progress callback.
        """
        super().__init__()
        self.controller = controller
        self.folder_paths = folder_paths
        self.progress_callback = progress_callback
        # Add new state variables for pause and stop functionality
        self.is_paused = False
        self.should_stop = False

        logger.debug(
            f"BatchProcessingWorker initialized with {len(folder_paths)} folders"
        )

    def process_folders(self):
        """Process all folders in the queue."""
        logger.info("Starting batch folder processing")
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
                while self.is_paused and not self.should_stop:
                    QThread.msleep(100)  # Sleep to avoid high CPU usage while paused

                if self.should_stop:
                    break
                    # Set the current folder path in the controller
                self.controller.set_folder_path(folder_path)

                # Process the folder
                results = self.controller.process_images(
                    lambda progress, *args: self._folder_progress_callback(
                        i, current_folder, total_folders, folder_path, progress, *args
                    ),
                    save_files=True and not self.should_stop,
                    preview_middle=False,
                    use_first_as_background=False,
                )

                # If we're stopping, don't emit completion signals
                if self.should_stop:
                    break

                success = results is not None
                if success:
                    successful_folders += 1
                    logger.info(f"Successfully processed folder: {folder_path}")
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
                logger.error(f"Error processing folder {folder_path}: {e}")
                self.error_occurred.emit(i, folder_path, str(e))
                self.folder_completed.emit(i, folder_path, False)

        logger.info(
            f"Batch processing completed: {successful_folders} successful, "
            f"{failed_folders} failed"
        )
        self.all_completed.emit()

    def pause(self):
        """Pause processing after the current image is complete."""
        self.is_paused = True
        logger.info("Batch processing paused")

    def resume(self):
        """Resume processing from where it was paused."""
        self.is_paused = False
        logger.info("Batch processing resumed")

    def stop(self):
        """Stop processing after the current image is complete."""
        self.should_stop = True
        self.is_paused = False  # Also clear pause state when stopping
        logger.info("Batch processing stop requested")

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
            adv_angles, rec_angles, center_points, result_images = args
            # Pass the folder index as additional info to know which folder
            # we're processing
            result_images["folder_index"] = folder_index
            result_images["folder_path"] = folder_path
            # Emit the preview image signal
            self.preview_image_updated.emit(
                progress, adv_angles, rec_angles, center_points, result_images
            )

        # Return False if processing should stop or pause
        if self.should_stop:
            return False

        return not self.is_paused
