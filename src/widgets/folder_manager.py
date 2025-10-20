"""Folder Manager and folder list widget for the Droplet Wall Interaction Tool (DWIT).

Provides utilities for handling batch folder operations, drag-and-drop, and
context menus used by the application's folder list widget.
"""

import os
import subprocess
import sys
from collections.abc import Callable

from PySide6.QtCore import QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListView,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QTreeView,
)

from src.utilities.core_utils import get_logger

logger = get_logger(__name__)


class FolderDropZone(QFrame):
    """A drag-and-drop zone widget that mimics the appearance of a folder item."""

    # Signal emitted when folders are dropped
    folders_dropped = Signal(list)

    # Class-level attribute to make static analyzers (vulture) recognise
    # that instances will have this attribute (it's manipulated by Qt
    # event handlers). Having it at class level avoids false positives
    # about an "unused attribute" while not changing runtime behavior.
    _drag_active = False

    def __init__(self, parent=None):
        """Initialize the drop zone widget."""
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setMinimumHeight(32)  # Same height as folder items
        self.setMaximumHeight(32)

        # Use QFrame styling to match the overall GUI
        self.setFrameStyle(QFrame.StyledPanel | QFrame.Sunken)
        self.setLineWidth(1)
        self.setMidLineWidth(0)

        # Create a label for the text
        self.label = QLabel("Drag and drop folders")
        self.label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        # Create layout for the frame
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(self.label)

        self.setToolTip(
            "Drag and drop one or more folders here. The application will "
            "automatically find subfolders containing data (images or videos)."
        )

        # Track drag state for visual feedback
        self._drag_active = False  # ignore PyTypeChecker

    def dragEnterEvent(self, event: QDragEnterEvent):  # noqa: N802
        """Handle drag enter events."""
        # Read _drag_active to make static analysers aware this attribute
        # is intentionally used (Qt calls these handlers implicitly).
        _ = getattr(self, "_drag_active", False)
        if event.mimeData().hasUrls():
            # Check if any of the URLs are directories
            urls = event.mimeData().urls()
            has_folders = any(
                QUrl(url).toLocalFile()
                for url in urls
                if os.path.isdir(QUrl(url).toLocalFile())
            )

            if has_folders:
                event.acceptProposedAction()
                self._drag_active = True
                # Use raised frame to indicate active drop zone
                self.setFrameStyle(QFrame.StyledPanel | QFrame.Raised)
            else:
                event.ignore()
        else:
            event.ignore()

    def dragLeaveEvent(self, event):  # noqa: N802
        """Handle drag leave events."""
        # Read and then write to _drag_active so static analysers detect use.
        _ = getattr(self, "_drag_active", False)
        self._drag_active = False
        # Restore sunken frame style
        self.setFrameStyle(QFrame.StyledPanel | QFrame.Sunken)
        super().dragLeaveEvent(event)

    def dropEvent(self, event: QDropEvent):  # noqa: N802
        """Handle drop events."""
        # Read _drag_active to make static analysers aware this attribute
        # is intentionally used by the Qt event handlers.
        _ = getattr(self, "_drag_active", False)
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            folder_paths = []

            for url in urls:
                local_path = QUrl(url).toLocalFile()
                if local_path and os.path.isdir(local_path):
                    folder_paths.append(local_path)

            if folder_paths:
                event.acceptProposedAction()
                self.folders_dropped.emit(folder_paths)
            else:
                event.ignore()
        else:
            event.ignore()

        # Reset visual state
        self._drag_active = False
        # Restore sunken frame style
        self.setFrameStyle(QFrame.StyledPanel | QFrame.Sunken)

    # Reference event handler methods so static analysers like vulture
    # detect they are intentionally defined for use by the Qt event
    # system (these are not directly referenced in Python code).
    # This tuple is evaluated at import time and does not change runtime
    # behavior; it only provides an explicit reference.
    _vulture_references = (dragEnterEvent, dragLeaveEvent, dropEvent)


class FolderManager:
    """Manager class for folder list operations, context menus, and batch processing."""

    def __init__(
        self,
        folder_list: QListWidget,
        folder_delegate,
        controller,
        on_preview_folder: Callable[[str], None] | None = None,
        on_analyze_folder: Callable[[str], None] | None = None,
        on_scan_single_folder: Callable[[str], None] | None = None,
    ):
        """Initialize the FolderManager.

        Parameters
        ----------
        folder_list : QListWidget
            The folder list widget to manage
        folder_delegate : FolderItemDelegate
            The delegate for rendering folder items
        controller : Any
            The application controller
        on_preview_folder : Callable[[str], None] | None
            Callback for previewing a folder
        on_analyze_folder : Callable[[str], None] | None
            Callback for analyzing a folder
        on_scan_single_folder : Callable[[str], None] | None
            Callback for scanning a single folder for results

        """
        self.folder_list = folder_list
        self.folder_delegate = folder_delegate
        self.controller = controller
        self.on_preview_folder = on_preview_folder
        self.on_analyze_folder = on_analyze_folder
        self.on_scan_single_folder = on_scan_single_folder

    def add_folders_to_batch(self) -> None:
        """Add multiple folders to the batch processing queue."""
        logger.info("Opening folder selection dialog for batch processing")
        folder_dialog = QFileDialog()
        folder_dialog.setFileMode(QFileDialog.Directory)
        folder_dialog.setOption(
            QFileDialog.DontUseNativeDialog, False
        )  # Use native file dialog

        # Hack to allow selecting multiple directories
        list_view = folder_dialog.findChild(QListView, "listView")
        if list_view:
            list_view.setSelectionMode(QAbstractItemView.ExtendedSelection)

        tree_view = folder_dialog.findChild(QTreeView)
        if tree_view:
            tree_view.setSelectionMode(QAbstractItemView.ExtendedSelection)

        if folder_dialog.exec():
            folders = folder_dialog.selectedFiles()
            logger.info(f"User selected {len(folders)} folders for batch processing")
            self.process_selected_folders(folders)

    def show_folder_detection_help(self) -> None:
        """Show help dialog explaining the folder detection."""
        msg = QMessageBox()
        msg.setWindowTitle("Folder Detection")
        msg.setIcon(QMessageBox.Information)

        help_text = (
            "<b>How Folder Detection Works:</b><br><br>"
            "When you add a folder (via drag-and-drop or 'Add Folders' button), "
            "the application automatically:<br><br>"
            "• <b>Scans</b> the folder and all its subfolders<br>"
            "• <b>Finds</b> folders containing sufficient data:<br>"
            "&nbsp;&nbsp;- At least 3 image files (.jpg, .png, .bmp, etc.) OR<br>"
            "&nbsp;&nbsp;- At least 1 video file (.mp4, .avi, .mov, etc.)<br>"
            "• <b>Adds</b> only the data-containing folders to the processing "
            "queue<br><br>"
            "<b>Example:</b><br>"
            "If you add a parent folder containing 10 subfolders, but only 4 contain "
            "enough images/videos, only those 4 folders will be added to the queue."
        )

        msg.setText(help_text)
        msg.setStandardButtons(QMessageBox.Ok)
        msg.exec()

    def handle_dropped_folders(self, folder_paths: list[str]) -> None:
        """Handle folders dropped onto the drop zone."""
        logger.info(f"User dropped {len(folder_paths)} folders")
        self.process_selected_folders(folder_paths)

    def find_data_folders(self, parent_folder: str) -> list[str]:
        """Find all subfolders containing data (images or videos).

        Criteria:
        - At least 3 image files (jpg, jpeg, png, bmp, tiff) OR
        - At least 1 video file (mp4, avi, mov, mkv, wmv)

        Parameters
        ----------
        parent_folder : str
            Path to the parent folder to search

        Returns
        -------
        list[str]
            List of folder paths containing data

        """
        data_folders = []

        # Image extensions
        image_extensions = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif"}
        # Video extensions
        video_extensions = {".mp4", ".avi", ".mov", ".mkv", ".wmv", ".m4v", ".flv"}

        try:
            # Check if the parent folder itself contains data
            if self.folder_contains_data(
                parent_folder, image_extensions, video_extensions
            ):
                data_folders.append(parent_folder)

            # Walk through all subdirectories
            for root, _, _ in os.walk(parent_folder):
                # Skip the parent folder itself (already checked above)
                if root == parent_folder:
                    continue

                if self.folder_contains_data(root, image_extensions, video_extensions):
                    data_folders.append(root)

        except Exception as e:
            logger.error(f"Error scanning folder {parent_folder}: {e}")
            # If scanning fails, return the parent folder as fallback
            return [parent_folder]

        # If no subfolders with data found, return the parent folder
        if not data_folders:
            logger.info(
                f"No data folders found in {parent_folder}, using parent folder"
            )
            return [parent_folder]

        logger.info(f"Found {len(data_folders)} data folders in {parent_folder}")
        return data_folders

    def folder_contains_data(
        self, folder_path: str, image_exts: set, video_exts: set
    ) -> bool:
        """Check if a folder contains sufficient data files.

        Parameters
        ----------
        folder_path : str
            Path to check
        image_exts : set
            Set of image file extensions
        video_exts : set
            Set of video file extensions

        Returns
        -------
        bool
            True if folder contains at least 3 images or 1 video

        """
        try:
            files = os.listdir(folder_path)
            image_count = 0
            video_count = 0

            for file in files:
                file_lower = file.lower()
                file_ext = os.path.splitext(file_lower)[1]

                if file_ext in image_exts:
                    image_count += 1
                elif file_ext in video_exts:
                    video_count += 1

                # Early exit if criteria met
                if image_count >= 3 or video_count >= 1:
                    return True

            return False

        except Exception as e:
            logger.error(f"Error checking folder contents {folder_path}: {e}")
            return False

    def process_selected_folders(self, folders: list[str]) -> None:
        """Process selected folders, validating paths and adding to the list.

        Parameters
        ----------
        folders : list[str]
            List of folder paths selected by user

        """
        # Expand to data-containing subfolders (deduplicated)
        unique_data_folders = self.expand_to_data_folders(folders)
        logger.info(f"Found {len(unique_data_folders)} unique data folders")

        # Add validated data folders to the UI and controller
        self.add_folders_to_list(unique_data_folders)

    def expand_to_data_folders(self, folders: list[str]) -> list[str]:
        """Return deduplicated list of data-containing folders from given roots.

        Parameters
        ----------
        folders : list[str]
            List of root folder paths

        Returns
        -------
        list[str]
            Deduplicated list of data-containing folders

        """
        all_data_folders = []
        for folder in folders:
            if os.path.isdir(folder):
                data_folders = self.find_data_folders(folder)
                all_data_folders.extend(data_folders)
            else:
                logger.warning(f"Skipping invalid folder: {folder}")

        # Remove duplicates while preserving order
        seen = set()
        unique = []
        for f in all_data_folders:
            if f not in seen:
                seen.add(f)
                unique.append(f)
        return unique

    def add_folders_to_list(self, folders: list[str]) -> None:
        """Add NEW folders to controller and folder_list widget, updating scanner.

        Parameters
        ----------
        folders : list[str]
            List of folder paths to add

        """
        for folder in folders:
            if not folder or folder in self.controller._folder_paths:
                continue
            self.controller.add_folder_path(folder)
            display_path = os.path.abspath(folder)
            item = QListWidgetItem(display_path)
            # Store absolute path in the item data
            item.setData(Qt.UserRole, display_path)
            item.setToolTip(display_path)
            item.setSizeHint(QSize(300, 32))
            self.folder_list.addItem(item)

            # Defer checking this folder for results
            if self.on_scan_single_folder:
                QTimer.singleShot(
                    0, lambda p=display_path: self.on_scan_single_folder(p)
                )

    def sync_folders_from_controller(self, folders: list[str]) -> None:
        """Sync folder list widget with folders from controller.

        This populates the visual list without adding to controller and is
        used when loading existing folders from settings.

        Parameters
        ----------
        folders : list[str]
            List of folder paths to display

        """
        for folder in folders:
            if not folder:
                continue
            display_path = os.path.abspath(folder)
            item = QListWidgetItem(display_path)
            # Store absolute path in the item data
            item.setData(Qt.UserRole, display_path)
            item.setToolTip(display_path)
            item.setSizeHint(QSize(300, 32))
            self.folder_list.addItem(item)

            # Defer checking this folder for results
            if self.on_scan_single_folder:
                QTimer.singleShot(
                    0, lambda p=display_path: self.on_scan_single_folder(p)
                )

    def remove_selected_folders(self) -> None:
        """Remove selected folders from the batch list."""
        selected_items = self.folder_list.selectedItems()
        if not selected_items:
            return

        logger.info(f"Removing {len(selected_items)} folders from batch list")
        for item in selected_items:
            folder_path = item.data(Qt.UserRole)

            # Clear state for this folder before removing
            if folder_path:
                try:
                    from src.utilities.core_utils import encode_path

                    key = encode_path(folder_path)
                except Exception:
                    key = folder_path
                self.folder_delegate.progress_data.pop(key, None)
                self.folder_delegate.results_presence.pop(key, None)

            self.controller.remove_folder_path(folder_path)
            row = self.folder_list.row(item)
            self.folder_list.takeItem(row)

        # If list is empty, add default test folder
        self._add_default_test_folder_if_empty()

    def clear_folder_list(self) -> None:
        """Clear all folders from the batch list."""
        logger.info("Clearing all folders from batch list")
        self.controller.clear_folder_paths()
        self.folder_list.clear()

        # Clear stored presence info
        try:
            self.folder_delegate.clear_results_presence()
        except Exception:
            pass

        # Clear main folder and current folder path in controller
        try:
            if hasattr(self.controller, "set_main_folder_path"):
                self.controller.set_main_folder_path("")
            if hasattr(self.controller, "set_folder_path"):
                self.controller.set_folder_path("")
        except Exception:
            pass

        # Add default test folder if list is empty
        self._add_default_test_folder_if_empty()

    def _add_default_test_folder_if_empty(self) -> None:
        """Add mode-specific test folder if list is empty."""
        try:
            if self.folder_list.count() == 0:
                mode = getattr(self.controller, "analysis_mode", "")
                test_map = {
                    "free_sedimentation": ("tests/free_sedimentation (BuAc_d_large)"),
                    "channel": ("tests/channel (BuAc_d_large)"),
                    "structured_packing": ("tests/structured_packing (BuAc_d_large)"),
                    "contact_angle": ("tests/contact_wall (BuAc_d_large)"),
                }
                rel = test_map.get(mode, "tests/contact_wall (BuAc_d_large)")
                default_test = os.path.abspath(rel)
                if os.path.isdir(default_test):
                    self.add_folders_to_list([default_test])
        except Exception:
            logger.exception("Failed to add default test folder")

    def show_folder_context_menu(self, position) -> None:
        """Show context menu for folder list.

        Parameters
        ----------
        position : QPoint
            Position where context menu was requested

        """
        menu = QMenu(self.folder_list)

        # Add Preview and Start Analysis actions for single selection
        selected_items = self.folder_list.selectedItems()
        if selected_items and len(selected_items) == 1:
            full_path = selected_items[0].data(Qt.UserRole)

            # Preview action
            preview_action = menu.addAction("Preview")
            preview_action.setToolTip(full_path)
            if self.on_preview_folder:
                preview_action.triggered.connect(
                    lambda: self.on_preview_folder(full_path)
                )

            # Analyze action
            analyze_action = menu.addAction("Start Analysis")
            analyze_action.setToolTip(full_path)
            if self.on_analyze_folder:
                analyze_action.triggered.connect(
                    lambda: self.on_analyze_folder(full_path)
                )

            menu.addSeparator()

            # Open Folder action
            open_action = menu.addAction("Open Folder")
            open_action.setToolTip(full_path)
            open_action.triggered.connect(
                lambda: self.open_folder_in_explorer(full_path)
            )

            # Open Results action if results exist
            try:
                results_file = os.path.join(full_path, "results_raw.xlsx")
                has_results = os.path.exists(results_file)
            except Exception:
                has_results = False

            if has_results:
                open_results_action = menu.addAction("Open Results")
                open_results_action.setToolTip(results_file)
                open_results_action.triggered.connect(
                    lambda: self.open_results_file(full_path)
                )

        menu.addAction("Remove Selected", self.remove_selected_folders)
        menu.addAction("Clear All", self.clear_folder_list)

        # Show the menu at the cursor position
        menu.exec(self.folder_list.mapToGlobal(position))

    def open_folder_in_explorer(self, folder_path: str) -> None:
        """Open the given folder in the system file explorer.

        Parameters
        ----------
        folder_path : str
            Path to folder to open

        """
        try:
            if not folder_path or not os.path.isdir(folder_path):
                logger.error(
                    "Cannot open folder in explorer, invalid path: %s", folder_path
                )
                return

            # Windows
            if os.name == "nt":
                subprocess.Popen(["explorer", folder_path], shell=False)
                return

            # macOS
            if sys.platform == "darwin":
                subprocess.Popen(["open", folder_path])
                return

            # Linux and others
            subprocess.Popen(["xdg-open", folder_path])

        except Exception as e:
            logger.error(f"Failed to open folder in explorer: {e}")

    def open_results_file(self, folder_path: str) -> None:
        """Open the results file (results_raw.xlsx) in the system default app.

        Parameters
        ----------
        folder_path : str
            Path to folder containing results file

        """
        try:
            if not folder_path or not os.path.isdir(folder_path):
                logger.error("Cannot open results, invalid folder: %s", folder_path)
                return

            results_file = os.path.join(folder_path, "results_raw.xlsx")
            if not os.path.exists(results_file):
                logger.warning("Results file does not exist: %s", results_file)
                return

            # Windows
            if os.name == "nt":
                subprocess.Popen(["cmd", "/c", "start", "", results_file], shell=False)
                return

            # macOS
            if sys.platform == "darwin":
                subprocess.Popen(["open", results_file])
                return

            # Linux and others
            subprocess.Popen(["xdg-open", results_file])

        except Exception as e:
            logger.error(f"Failed to open results file: {e}")
