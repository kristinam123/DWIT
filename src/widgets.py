"""Analysis GUI widgets for experiment visualization and user interaction.

Part of Droplet Wall Interaction Tool (DWIT).
"""

import glob
import os
import sys
from typing import Any, Optional

import cv2
import numpy as np
from PySide6.QtCore import (
    QCoreApplication,
    QPoint,
    QSize,
    Qt,
    QThread,
    QTimer,
    QUrl,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QDragEnterEvent,
    QDropEvent,
    QIcon,
    QImage,
    QKeySequence,
    QPainter,
    QPixmap,
    QPolygon,
    QShortcut,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListView,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QTextEdit,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from src.helpers.batch import BatchProcessingWorker, FolderItemDelegate
from src.helpers.preview import show_preview
from src.helpers.save_results import save_results
from src.helpers.velocity import calculate_velocities
from src.threads import AnalysisThread
from src.utilities.image import rotate_image
from src.utilities.logging_manager import get_logger
from src.utilities.preview_optimization import get_optimized_preview_generator
from src.utilities.roi import ROISelector

# Setup logger for this module
logger = get_logger(__name__)


def normalize_path_for_ascii(path: str) -> str:
    """Convert a path with special characters to ASCII-compatible version.

    Args:
    ----
        path: Original path that may contain special characters

    Returns:
    -------
        str: ASCII-compatible version of the path

    """
    import unicodedata

    # Normalize unicode characters to their ASCII equivalents where possible
    normalized = unicodedata.normalize("NFKD", path)
    # Remove accents and diacritics
    ascii_path = "".join(c for c in normalized if ord(c) < 128)

    # Handle Windows drive letters specially (preserve C:, D:, etc.)
    drive_letter = ""
    remaining_path = ascii_path
    if len(ascii_path) >= 2 and ascii_path[1] == ":":
        drive_letter = ascii_path[:2]  # Keep "C:", "D:", etc.
        remaining_path = ascii_path[2:]  # Process the rest

    # Replace any remaining problematic characters with underscores
    # Keep valid path characters: letters, numbers, and common path symbols
    valid_chars = set(
        "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789\\/_-. ()"
    )
    cleaned_remaining = "".join(c if c in valid_chars else "_" for c in remaining_path)

    # Combine drive letter with cleaned path
    ascii_path = drive_letter + cleaned_remaining

    # Clean up multiple consecutive underscores
    while "__" in ascii_path:
        ascii_path = ascii_path.replace("__", "_")
    # Remove leading/trailing underscores from each path component
    path_parts = ascii_path.split("\\")
    cleaned_parts = []
    for i, part in enumerate(path_parts):
        if i == 0 and ":" in part:
            # Keep drive letter as-is
            cleaned_parts.append(part)
        elif part.strip("_"):
            cleaned_parts.append(part.strip("_"))
    return "\\".join(cleaned_parts)


class PathValidationDialog(QDialog):
    """Dialog for validating and converting folder paths with special characters."""

    def __init__(self, parent=None):
        """Initialize the path validation dialog."""
        super().__init__(parent)
        self.setWindowTitle("Folder Path Validation")
        self.setModal(True)
        self.setMinimumWidth(600)
        self.setMinimumHeight(400)

        # Results storage
        self.user_choice = None  # 'yes', 'no', or None
        self.path_mappings = {}  # {original_path: converted_path}
        self._setup_ui()

    def _setup_ui(self):
        """Set up the dialog UI."""
        layout = QVBoxLayout(self)

        # Title and description
        title_label = QLabel("Folder Path Contains Special Characters")
        title_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(title_label)

        description = QLabel(
            "The selected folder path(s) contain special characters (e.g., ü, ä, ö, ß) "
            "that may cause issues with the analysis. The application can "
            "automatically rename these folders and files to ASCII-compatible versions."
        )
        description.setWordWrap(True)
        layout.addWidget(description)

        # Warning label
        warning_label = QLabel(
            "⚠️ Warning: This will permanently rename the folders and files. "
            "Make sure you have backups if needed."
        )
        warning_label.setStyleSheet("color: #FF6B00; font-weight: bold;")
        warning_label.setWordWrap(True)
        layout.addWidget(warning_label)

        # Path conversion display - two column layout
        display_layout = QHBoxLayout()

        # Left column: paths with highlighted problematic characters
        left_layout = QVBoxLayout()
        path_label = QLabel("Paths with problematic characters:")
        path_label.setStyleSheet("font-weight: bold;")
        left_layout.addWidget(path_label)

        self.path_display = QTextEdit()
        self.path_display.setReadOnly(True)
        self.path_display.setMaximumHeight(200)
        left_layout.addWidget(self.path_display)

        # Right column: character replacement mappings
        right_layout = QVBoxLayout()
        mapping_label = QLabel("Character replacements:")
        mapping_label.setStyleSheet("font-weight: bold;")
        right_layout.addWidget(mapping_label)

        self.mapping_display = QTextEdit()
        self.mapping_display.setReadOnly(True)
        self.mapping_display.setMaximumHeight(200)
        self.mapping_display.setMaximumWidth(200)
        right_layout.addWidget(self.mapping_display)

        display_layout.addLayout(left_layout)
        display_layout.addLayout(right_layout)
        layout.addLayout(display_layout)

        # Checkbox removed as all paths are renamed anyway

        # Buttons
        button_layout = QHBoxLayout()

        self.yes_button = QPushButton("Yes - Rename Folder(s)")
        self.yes_button.clicked.connect(self._on_yes_clicked)
        button_layout.addWidget(self.yes_button)

        self.no_button = QPushButton("No - Cancel")
        self.no_button.clicked.connect(self._on_no_clicked)
        button_layout.addWidget(self.no_button)

        layout.addLayout(button_layout)

    def set_paths(self, paths: list[str]):
        """Set the paths to be validated and show before/after conversion.

        Args:
        ----
            paths: List of folder paths to validate

        """
        self.path_mappings = {}
        display_html = ""
        char_mappings = set()  # Track unique character replacements

        for path in paths:
            try:
                path.encode("ascii")
                continue
            except UnicodeEncodeError:
                converted_path = normalize_path_for_ascii(path)
                self.path_mappings[path] = converted_path

                # Create highlighted version with only problematic chars marked
                highlighted_path = self._highlight_problematic_chars(
                    path, char_mappings
                )
                display_html += f"{highlighted_path}<br>"

        if display_html:
            self.path_display.setHtml(display_html)
            # Show character mappings
            mapping_text = "\n".join(sorted(char_mappings))
            self.mapping_display.setPlainText(mapping_text)
        else:
            self.path_display.setPlainText("No paths require conversion.")
            self.mapping_display.setPlainText("No character replacements needed.")

    def _on_yes_clicked(self):
        """Handle Yes button click."""
        self.user_choice = "yes"
        self.accept()

    def _highlight_problematic_chars(self, path: str, char_mappings: set) -> str:
        """Highlight problematic characters in the path and track replacements.

        Args:
        ----
            path: The original path
            char_mappings: Set to collect character replacement mappings

        Returns:
        -------
            str: HTML string with problematic characters highlighted

        """
        import unicodedata

        result = ""

        for char in path:
            try:
                char.encode("ascii")
                # Character is ASCII-compatible
                result += char
            except UnicodeEncodeError:
                # Character needs replacement
                normalized = unicodedata.normalize("NFKD", char)
                ascii_char = "".join(c for c in normalized if ord(c) < 128)
                if not ascii_char:
                    ascii_char = "_"

                # Add to mappings (avoid duplicates)
                char_mappings.add(f"{char} → {ascii_char}")

                # Highlight the problematic character
                highlighted = (
                    '<span style="color: red; font-weight: bold; '
                    'text-decoration: underline;">'
                    f"{char}"
                    "</span>"
                )
                result += highlighted

        return result

    def _on_no_clicked(self):
        """Handle No button click."""
        self.user_choice = "no"
        self.reject()


class FolderDropZone(QFrame):
    """A drag-and-drop zone widget that mimics the appearance of a folder item."""

    # Signal emitted when folders are dropped
    folders_dropped = Signal(list)

    # Class-level attribute to make static analyzers (vulture) recognise
    # that instances will have this attribute (it's manipulated by Qt
    # event handlers). Having it at class level avoids false positives
    # about an "unused attribute" while not changing runtime behaviour.
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
    # behaviour; it only provides an explicit reference.
    _vulture_references = (dragEnterEvent, dragLeaveEvent, dropEvent)


class CollapsibleGroupBox(QWidget):
    """A collapsible group box widget with a clickable header."""

    def __init__(self, title: str, collapsed: bool = True, parent=None):
        """Initialize collapsible group box.

        Parameters
        ----------
        title : str
            The title text for the group
        collapsed : bool
            Whether to start in collapsed state
        parent : QWidget
            Parent widget

        """
        super().__init__(parent)
        self.collapsed = collapsed

        # Main layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header button
        self.header_btn = QPushButton()
        self.header_btn.setCheckable(True)
        self.header_btn.setChecked(not collapsed)
        self.header_btn.clicked.connect(self.toggle_collapsed)
        self.update_header_text(title)

        # Style the header button to ensure left alignment
        self.header_btn.setStyleSheet(
            """
            QPushButton {
                text-align: left;
            }
        """
        )

        layout.addWidget(self.header_btn)

        # Content widget
        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(8, 4, 8, 4)

        layout.addWidget(self.content_widget)

        # Set initial state
        self.content_widget.setVisible(not collapsed)

        self.title = title

    def update_header_text(self, title: str):
        """Update header text with left-aligned collapse indicator."""
        arrow = "▼" if not self.collapsed else "▶"
        # Put arrow on the left with space, left-aligned text
        self.header_btn.setText(f"{arrow} {title}")

    def toggle_collapsed(self):
        """Toggle the collapsed state."""
        self.collapsed = not self.collapsed
        self.content_widget.setVisible(not self.collapsed)
        self.update_header_text(self.title)

    def add_widget(self, widget):
        """Add a widget to the content area."""
        self.content_layout.addWidget(widget)


class AnalysisGUI(QWidget):
    """Modern GUI for analysis."""

    def __init__(self, parent: QWidget, controller: Any):
        """Initialize the AnalysisGUI with parent and controller."""
        logger.debug("Initializing AnalysisGUI")

        try:
            super().__init__(parent)
            self.controller = controller
            self.main_thread = None

            # Path validation preferences
            self._path_validation_choice = None  # 'yes', 'no', or None
            self._apply_to_all_paths = False
            self.preview_thread = None

            # Add a processing state flag to track when analysis is running
            self.is_processing = False

            # Add initialization flag to prevent unwanted dialogs during setup
            self.is_initializing = True

            # Initialize image storage
            self.preview_images = {"original": [], "contour": [], "result": []}
            self.total_frames = 0

            # Initialize image slider attributes
            self.current_frame_index = 0
            self.is_auto_playing = False
            self.auto_play_timer = None
            self.image_slider = None
            self.btn_prev_frame = None
            self.btn_next_frame = None
            self.btn_play_pause = None
            self.speed_slider = None
            self.speed_label = None

            # Create debounce timer for parameter changes
            self.preview_timer = QTimer(self)
            self.preview_timer.setSingleShot(True)
            self.preview_timer.setInterval(100)
            self.preview_timer.timeout.connect(self._auto_preview)

            # Initialize context preview timer (will be created on demand)
            self.context_preview_timer = None

            # Add flag to track if we should show context-sensitive preview
            # This flag is set to True when a parameter is changed manually by the user
            # and reset to False after the preview completes or when starting
            # non-contextual operations
            self.should_show_context_preview = False

            # Add flag to track when we're in preview mode (no progress updates)
            self.is_in_preview_mode = False

            # Add flag to track when we're in preview mode (no progress updates)
            self.is_in_preview_mode = False

            if hasattr(self.controller, "image_processed"):
                self.controller.image_processed.connect(self._update_preview_image)

            else:
                logger.warning("Controller does not have image_processed signal")

            # Keep track of the last changed parameter type
            self.last_changed_param = None

            # Initialize optimized preview generator
            self.optimized_preview = get_optimized_preview_generator()
            self.optimized_preview.preview_ready.connect(self._handle_optimized_preview)

            # Create UI
            self.create_widgets()

            # Load the folder list from controller after UI creation
            if hasattr(self.controller, "folder_paths"):
                self._update_folder_list(self.controller.folder_paths)
                # Start background scanner for results files
                try:
                    self._start_results_scanner()
                except Exception:
                    logger.exception("Failed to start results scanner")

            else:
                logger.warning("Controller does not have folder_paths attribute")

            # Make sure main folder highlighting is applied
            self._update_main_folder_highlight()

            # Flag used to indicate the user requested a hard stop/skip
            # which should prevent any final saving of `results_raw.xlsx`.
            self._user_requested_stop_no_save = False

            # Initialize index mapping for batch processing
            self.processing_to_ui_index_map = {}

            # Initialize processing mode
            self.processing_mode = "undone"

            # Auto-trigger preview only if this widget is visible after initialization
            # Ensure we're in the main thread before starting timer
            try:
                from PySide6.QtCore import QCoreApplication

                QCoreApplication.processEvents()
                QTimer.singleShot(100, self._conditional_auto_preview)
            except Exception:
                # If timer fails, just skip auto-preview
                logger.debug("Could not start auto-preview timer, skipping")

            logger.info("AnalysisGUI initialization completed successfully")

        except Exception as e:
            logger.error(f"Failed to initialize AnalysisGUI: {e}")
            logger.error(f"Parent: {parent}")
            logger.error(f"Controller: {controller}")
            raise

        # Set initialization flag with defensive timer
        try:
            from PySide6.QtCore import QCoreApplication

            QCoreApplication.processEvents()
            QTimer.singleShot(500, lambda: setattr(self, "is_initializing", False))
        except Exception:
            # If timer fails, set flag directly
            self.is_initializing = False
        logger.info("AnalysisGUI initialization completed")

    def _conditional_auto_preview(self):
        """Trigger auto-preview only if this analysis widget is currently visible.

        This prevents triggering previews for analysis modes that are not
        currently displayed when dwit starts.
        """
        # Check if this widget is visible by checking if it's the current page
        if self.isVisible() and self.parent():
            # Check if the parent's parent has a content stacked widget
            # and if this widget's page is currently active
            parent_widget = self.parent()
            while parent_widget:
                if hasattr(parent_widget, "content") and hasattr(
                    parent_widget.content, "currentWidget"
                ):
                    # Check if the current widget contains this analysis widget
                    current_widget = parent_widget.content.currentWidget()
                    if current_widget and self._is_widget_ancestor(
                        current_widget, self
                    ):
                        self.preview()
                        return
                parent_widget = parent_widget.parent()

    def _is_widget_ancestor(self, potential_ancestor, widget):
        """Check if potential_ancestor contains widget in its hierarchy."""
        if potential_ancestor == widget:
            return True
        if potential_ancestor == widget.parent():
            return True
        # Recursively check children
        for child in potential_ancestor.findChildren(type(widget)):
            if child == widget:
                return True
        return False

    def _update_preview_image(self, index: int, result_images: dict):
        """Update preview with the latest processed image."""
        if not result_images:
            return

        # Try to show image based on parameter type
        image_shown = self._show_parameter_specific_image(result_images)

        # Show fallback image if no specific image was shown
        if not image_shown:
            self._show_fallback_image(result_images)

        # Always update result canvas if available
        self._update_result_canvas(result_images)

        # Reset the context-sensitive preview flag after processing is complete
        # This ensures the preview dialog is only shown during parameter changes
        # Use a longer delay to keep preview open while user is actively changing
        if self.should_show_context_preview:
            # Cancel any existing timer to prevent premature reset
            if self.context_preview_timer:
                self.context_preview_timer.stop()

            # Set up a new timer with longer delay (2 seconds)
            if not self.context_preview_timer:
                self.context_preview_timer = QTimer()
                self.context_preview_timer.setSingleShot(True)
                self.context_preview_timer.timeout.connect(
                    lambda: setattr(self, "should_show_context_preview", False)
                )
            self.context_preview_timer.start(2000)  # 2 seconds delay

    def _handle_optimized_preview(self, image, preview_type: str):
        """Handle optimized preview results."""
        try:
            if image is not None:
                show_preview(image, self)
                logger.debug(f"Displayed optimized {preview_type} preview")
        except Exception as e:
            logger.error(f"Error displaying optimized {preview_type} preview: {e}")

    def _show_parameter_specific_image(self, result_images: dict) -> bool:
        """Show image based on the last changed parameter type."""
        is_structured_packing = self.controller.analysis_mode == "structured_packing"

        if self.last_changed_param == "threshold":
            return self._show_threshold_image(result_images)
        elif self.last_changed_param == "roi":
            return self._show_roi_image(result_images, is_structured_packing)
        elif self.last_changed_param == "baseline":
            return self._show_baseline_image(result_images)
        elif self.last_changed_param == "rotation":
            return self._show_rotation_image(result_images, is_structured_packing)
        elif self.is_processing and "contour" in result_images:
            # Only show preview dialog if we're in context-sensitive mode
            if self.should_show_context_preview:
                show_preview(result_images["contour"], self)
            return True

        return False

    def _show_threshold_image(self, result_images: dict) -> bool:
        """Show threshold image if available."""
        logger.debug('Showing threshold image using "_show_threshold_image"')
        if "thresh" in result_images:
            # Only show preview dialog if we're in context-sensitive mode
            if self.should_show_context_preview:
                show_preview(result_images["thresh"], self)
            return True
        return False

    def _show_roi_image(self, result_images: dict, is_structured_packing: bool) -> bool:
        """Show ROI-related image based on analysis mode."""
        if is_structured_packing and "original_with_vertical" in result_images:
            # Only show preview dialog if we're in context-sensitive mode
            if self.should_show_context_preview:
                show_preview(result_images["original_with_vertical"], self)
            return True
        elif "original" in result_images:
            # Only show preview dialog if we're in context-sensitive mode
            if self.should_show_context_preview:
                show_preview(result_images["original"], self)
            return True
        return False

    def _show_baseline_image(self, result_images: dict) -> bool:
        """Show baseline image if available."""
        if "baseline" in result_images:
            # Only show preview dialog if we're in context-sensitive mode
            if self.should_show_context_preview:
                show_preview(result_images["baseline"], self)
            return True
        return False

    def _show_rotation_image(
        self, result_images: dict, is_structured_packing: bool
    ) -> bool:
        """Show rotation-related image based on analysis mode."""
        if is_structured_packing and "original_with_vertical" in result_images:
            # Only show preview dialog if we're in context-sensitive mode
            if self.should_show_context_preview:
                show_preview(result_images["original_with_vertical"], self)
            return True
        elif "original" in result_images:
            # Only show preview dialog if we're in context-sensitive mode
            if self.should_show_context_preview:
                show_preview(result_images["original"], self)
            return True
        return False

    def _show_fallback_image(self, result_images: dict) -> None:
        """Show fallback image if no parameter-specific image was shown."""
        fallback_keys = ["result", "contour", "baseline", "original", "fallback"]
        for key in fallback_keys:
            if key in result_images:
                # Only show preview dialog if we're in context-sensitive mode
                if self.should_show_context_preview:
                    show_preview(result_images[key], self)
                break

    def _update_result_canvas(self, result_images: dict) -> None:
        """Update the result canvas if result image is available."""
        if "result" in result_images:
            self.display_image_in_canvas(result_images["result"], self.canvas_result)

    def create_widgets(self) -> None:
        """Create all UI components."""
        try:
            # Main container

            self.frame = QWidget(self)
            self.main_layout = QVBoxLayout(self.frame)
            self.main_layout.setContentsMargins(0, 0, 0, 0)

            # Create action buttons and progress bar

            self._create_action_controls()

            # Create main content layout

            self._create_main_content_layout()

            # Apply to parent
            self._setup_parent_layout()

            # Add tooltips to all widgets after creation
            self._setup_all_tooltips()

            # Set up keyboard shortcuts for image slider
            self._setup_slider_keyboard_shortcuts()

            logger.info("Widget creation completed successfully")

        except Exception as e:
            logger.error(f"Failed to create widgets: {e}")
            raise

    def _create_main_content_layout(self) -> None:
        """Create the main content layout with parameters and preview areas."""
        # Fixed horizontal layout for parameters/settings and preview (no splitter)
        main_content = QWidget()
        main_content_layout = QHBoxLayout(main_content)
        main_content_layout.setContentsMargins(0, 0, 0, 0)

        # Parameters/settings area with tighter width
        params_container = QWidget()
        self._create_parameter_section(params_container)
        params_container.setFixedWidth(180)  # Tighter width
        params_container.setMinimumWidth(180)
        main_content_layout.addWidget(params_container)

        # Preview area
        preview_container = QWidget()
        self._create_preview_area(preview_container)
        preview_container.setMinimumWidth(400)
        main_content_layout.addWidget(preview_container, 1)

        # Add main content (preview/canvas area) with higher stretch (2)
        self.main_layout.addWidget(main_content, 2)

    def _setup_parent_layout(self) -> None:
        """Set up the parent layout configuration."""
        self.setLayout(QVBoxLayout())
        self.layout().setContentsMargins(0, 0, 0, 0)
        self.layout().addWidget(self.frame)

    def _setup_all_tooltips(self) -> None:
        """Set up tooltips for all widgets after creation."""
        self._setup_action_control_tooltips()
        self._setup_parameter_tooltips()
        self._setup_roi_control_tooltips()
        self._setup_preview_area_tooltips()
        self._setup_stats_section_tooltips()

    def _setup_action_control_tooltips(self) -> None:
        """Set up tooltips for action control widgets."""
        # The tooltip for process_batch_btn is set dynamically in _set_process_mode
        # based on the current processing mode
        self.pause_resume_btn.setToolTip("Pause or resume the current processing.")
        self.stop_btn.setToolTip("Stop the current processing.")
        self.folder_list.setToolTip(
            "List of folders to process. Right-click for more options. "
            "Green circles indicate completed folders with results."
        )
        self.overall_progress.setToolTip(
            "Shows the overall progress of the current operation."
        )
        self.folder_counter.setToolTip(
            "Shows the number of processed folders out of total."
        )

    def _setup_parameter_tooltips(self) -> None:
        """Set up tooltips for parameter control widgets."""
        # Camera tooltips
        if hasattr(self, "PIXEL_entry"):
            self.PIXEL_entry.setToolTip("Set the pixel per mm (px/mm) for analysis.")
        if hasattr(self, "FPS_entry"):
            self.FPS_entry.setToolTip("Set the frames per second (FPS) for analysis.")

        # Threshold tooltips
        if hasattr(self, "threshold_entry"):
            self.threshold_entry.setToolTip(
                "Set the threshold value for image binarization."
            )

        # Adjustment tooltips
        if hasattr(self, "rotate_angle_entry"):
            self.rotate_angle_entry.setToolTip(
                "Set the rotation angle for image alignment."
            )
        if hasattr(self, "baseline_entry"):
            self.baseline_entry.setToolTip("Set the baseline offset for analysis.")

        # Manual baseline tooltips
        if hasattr(self, "Baseline_tf_checkbox"):
            self.Baseline_tf_checkbox.setToolTip(
                "Enable or disable manual baseline adjustment."
            )
        if hasattr(self, "manual_baseline_entry"):
            self.manual_baseline_entry.setToolTip("Set the manual baseline height.")

    def _setup_roi_control_tooltips(self) -> None:
        """Set up tooltips for ROI control widgets."""
        if hasattr(self, "left_roi_spinbox"):
            self.left_roi_spinbox.setToolTip(
                "Set the left boundary of the region of interest (ROI) in pixels."
            )
        if hasattr(self, "right_roi_spinbox"):
            self.right_roi_spinbox.setToolTip(
                "Set the right boundary of the region of interest (ROI) in pixels."
            )
        if hasattr(self, "top_roi_spinbox"):
            self.top_roi_spinbox.setToolTip(
                "Set the top boundary of the region of interest (ROI) in pixels."
            )
        if hasattr(self, "bottom_roi_spinbox"):
            self.bottom_roi_spinbox.setToolTip(
                "Set the bottom boundary of the region of interest (ROI) in pixels."
            )

    def _setup_preview_area_tooltips(self) -> None:
        """Set up tooltips for preview area widgets."""
        if hasattr(self, "canvas_result"):
            self.canvas_result.setToolTip(
                "Displays the result of the analysis or processing."
            )

    def _setup_stats_section_tooltips(self) -> None:
        """Set up tooltips for statistics section widgets."""
        if hasattr(self, "adv_angle_label"):
            self.adv_angle_label.setToolTip("Shows the advancing contact angle.")
        if hasattr(self, "rec_angle_label"):
            self.rec_angle_label.setToolTip("Shows the receding contact angle.")
        if hasattr(self, "width_label"):
            self.width_label.setToolTip("Shows the measured width of the object in mm.")
        if hasattr(self, "height_label"):
            self.height_label.setToolTip(
                "Shows the measured height of the object in mm."
            )
        if hasattr(self, "ellipse_diameter_label"):
            self.ellipse_diameter_label.setToolTip(
                "Shows the ellipse diameter calculated from width and height "
                "(d = sqrt(w*h))."
            )
        if hasattr(self, "center_label"):
            self.center_label.setToolTip("Shows the center position (X/Y) in pixels.")
        if hasattr(self, "velocity_value"):
            self.velocity_value.setToolTip("Shows the calculated velocity in mm/s.")
        if hasattr(self, "area_diameter_label"):
            self.area_diameter_label.setToolTip(
                "Shows the diameter calculated from detected area (d = sqrt(4*A/π))."
            )

    def main(self) -> None:
        """Start main processing thread."""
        logger.info("Starting main analysis processing")
        # Check if already processing
        if self.is_processing:
            logger.warning("Analysis already in progress, ignoring request")
            return

        # Clear preview mode flag for main analysis
        self.is_in_preview_mode = False

        # Set processing flag
        self.is_processing = True

        # Clear previous frame data for new analysis
        self._clear_frame_data()

        # Set the preview_button and analyze_button as disabled
        #         self.analyze_button.setEnabled(False)
        #         self.preview_button.setEnabled(False)

        # Disable batch process button to prevent starting multiple processes
        #         self.process_batch_btn.setEnabled(False)
        #         self.add_folders_btn.setEnabled(False)

        # Disable folder context menu items during processing
        #         self.folder_list.setEnabled(False)

        # Enable pause/stop buttons
        #         self.pause_resume_btn.setEnabled(True)
        self.pause_resume_btn.setIcon(
            QIcon.fromTheme("media-playback-pause", QIcon(":/icons/pause.png"))
        )
        self.pause_resume_btn.setToolTip("Pause processing")
        #         self.stop_btn.setEnabled(True)

        self.overall_progress.setValue(0)  # Use overall_progress instead of progress

        # Reset last_changed_param when starting main analysis
        self.last_changed_param = None

        # Reset context-sensitive preview flag for main analysis
        self.should_show_context_preview = False

        # Clear previous preview images when starting a new run
        self.preview_images = {"original": [], "contour": [], "result": []}
        self.total_frames = 0
        # Reset image slider state
        self._update_slider_state()

        # Use the main folder for analysis if available,
        # otherwise use the current folder path
        folder_path = (
            self.controller.main_folder_path
            if self.controller.main_folder_path
            else self.controller.folder_path
        )

        # Set the current folder to the main folder if it's available
        if self.controller.main_folder_path:
            self.controller.set_folder_path(self.controller.main_folder_path)
            # Remove reference to non-existent folder_path_entry

        # Check if folder path exists
        if not folder_path or not os.path.isdir(folder_path):
            logger.error(f"Invalid or missing folder path: {folder_path}")
            #             self.analyze_button.setEnabled(True)
            #             self.preview_button.setEnabled(True)
            self.folder_counter.setText("0/0")  # Reset folder counter
            #             self.pause_resume_btn.setEnabled(False)
            #             self.stop_btn.setEnabled(False)
            return

        logger.info(f"Creating analysis thread for folder: {folder_path}")
        # Create and configure the thread
        self.main_thread = AnalysisThread(
            self.controller,
            save_files=True,
            preview_middle=False,
            use_first_as_background=False,
        )

        self.main_thread.progress_signal.connect(self._update_stats)
        self.main_thread.finished_signal.connect(self._process_results)
        self.main_thread.error_signal.connect(self._handle_error)
        self.main_thread.finished.connect(self._enable_buttons)

        # Start the thread

        self.main_thread.start()

    def _auto_preview(self) -> None:
        """Triggered by timer to run preview after parameter changes."""
        # Only run if we have a valid folder and aren't already processing
        if (
            self.controller.folder_path
            and os.path.isdir(self.controller.folder_path)
            and self.analyze_button.isEnabled()
            and self.preview_button.isEnabled()
        ):
            self.preview()

    def _trigger_preview_update(self, param_type: Optional[str] = None) -> None:
        """Start the debounce timer to trigger preview update.

        Records parameter type.
        """
        # Skip all preview updates during initialization
        if getattr(self, "is_initializing", False):
            return

        # Store the parameter type that was changed
        self.last_changed_param = param_type
        logger.debug(f"Parameter changed: {param_type}")

        # Enable context-sensitive preview when a parameter is changed
        self.should_show_context_preview = True

        # Cancel any existing context preview timer to extend the preview duration
        if self.context_preview_timer:
            self.context_preview_timer.stop()

        # Show immediate preview dialog for different parameter types
        if param_type == "roi":
            self._show_roi_preview()
            # Reset the flag to prevent _show_roi_image from showing another preview
            self.should_show_context_preview = False
        elif param_type == "threshold":
            self._show_threshold_preview()
            self.should_show_context_preview = False
        elif param_type == "rotation":
            self._show_rotation_preview()
            self.should_show_context_preview = False
        elif param_type in ["baseline", "baseline_offset"]:
            self._show_baseline_preview()
            self.should_show_context_preview = False

        self.preview_timer.start()

    def _create_action_controls(self) -> None:
        """Create action buttons and controls."""
        # Add batch processing section - Removed GroupBox
        batch_widget = QWidget()
        batch_layout = QVBoxLayout(batch_widget)
        batch_layout.setContentsMargins(0, 0, 0, 0)

        # Create folder list widget with custom delegate for progress bars
        self.folder_list = QListWidget()
        self.folder_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        # Allow the folder list area to expand (no fixed max height)
        self.folder_list.setMinimumHeight(100)
        # Remove maximum height constraint to let layout stretching work
        # self.folder_list.setMaximumHeight(180)
        self.folder_list.setUniformItemSizes(False)  # Allow non-uniform sizes
        self.folder_delegate = FolderItemDelegate()
        self.folder_list.setItemDelegate(self.folder_delegate)
        # Prepare results scanner thread and worker attributes (started later)
        self._results_scanner_thread = None
        self._results_scanner_worker = None
        self.folder_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.folder_list.customContextMenuRequested.connect(
            self._show_folder_context_menu
        )
        batch_layout.addWidget(self.folder_list)

        # Add a very thin progress bar below the folder list
        self.batch_progress = QProgressBar()
        self.batch_progress.setRange(0, 100)
        self.batch_progress.setValue(0)
        self.batch_progress.setFixedHeight(3)  # Very thin progress bar
        self.batch_progress.setTextVisible(False)
        self.batch_progress.setStyleSheet(
            """
            QProgressBar {
                border: none;
                background-color: #e0e0e0;
                border-radius: 1px;
            }
            QProgressBar::chunk {
                background-color: #4CAF50;
                border-radius: 1px;
            }
        """
        )
        batch_layout.addWidget(self.batch_progress)

        # Create combined control and progress layout in a single horizontal line
        # Order: Add Folders > Drag/drop > ? > process mode > pause > stop > skip
        combined_controls_layout = QHBoxLayout()
        combined_controls_layout.setContentsMargins(0, 0, 0, 0)
        combined_controls_layout.setSpacing(5)

        # Create Add Folders button (first in line)
        self.add_folders_btn = QPushButton("Add Folders")
        self.add_folders_btn.clicked.connect(self.add_folders_to_batch)
        self.add_folders_btn.setFixedHeight(32)
        self.add_folders_btn.setMinimumWidth(100)  # Slightly smaller to fit inline
        self.add_folders_btn.setToolTip(
            "Add one or more folders to the batch processing queue. "
            "The application will automatically find subfolders containing data."
        )
        combined_controls_layout.addWidget(self.add_folders_btn)

        # Create drag-and-drop zone (second in line). Make it fixed and compact
        self.drop_zone = FolderDropZone()
        self.drop_zone.folders_dropped.connect(self._handle_dropped_folders)
        # Give the drop zone a fixed width so it doesn't expand and create gaps
        try:
            self.drop_zone.setFixedWidth(130)
        except Exception:
            # Fall back to minimum width if setFixedWidth unavailable
            self.drop_zone.setMinimumWidth(90)
        # Add without stretch so it doesn't take remaining space
        combined_controls_layout.addWidget(self.drop_zone)

        # Create help button with question mark icon (third in line)
        self.help_btn = QPushButton()
        self.help_btn.setText("?")
        self.help_btn.setFixedSize(32, 32)
        self.help_btn.setToolTip("Click to learn about folder detection")
        self.help_btn.clicked.connect(self._show_folder_detection_help)
        # Style the help button as a gray circle with white question mark
        self.help_btn.setStyleSheet(
            """
            QPushButton {
                background-color: #808080;
                color: white;
                border-radius: 16px;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #606060;
            }
            QPushButton:pressed {
                background-color: #404040;
            }
        """
        )
        combined_controls_layout.addWidget(self.help_btn)

        # Create split button for processing options (main button + dropdown)
        split_button_widget = QWidget()
        split_button_layout = QHBoxLayout(split_button_widget)
        split_button_layout.setContentsMargins(0, 0, 0, 0)
        split_button_layout.setSpacing(0)

        # Main button (larger area) - executes the current mode
        self.process_batch_btn = QPushButton("Process Undone")
        self.process_batch_btn.clicked.connect(self.process_selected_folders)
        self.process_batch_btn.setMinimumWidth(120)

        # Dropdown button (smaller area) - opens mode selection
        self.mode_dropdown_btn = QPushButton("▼")
        self.mode_dropdown_btn.setMaximumWidth(20)
        self.mode_dropdown_btn.setMinimumWidth(20)

        # Create dropdown menu for processing options
        process_menu = QMenu(self)

        # Process Undone action (default)
        process_undone_action = process_menu.addAction("Process Undone")
        process_undone_action.setToolTip(
            "Process only folders that don't have results_raw.xlsx file (default)"
        )
        process_undone_action.triggered.connect(
            lambda: self._set_process_mode("undone")
        )

        # Process All action
        process_all_action = process_menu.addAction("Process All")
        process_all_action.setToolTip(
            "Process all folders independent from done-status"
        )
        process_all_action.triggered.connect(lambda: self._set_process_mode("all"))

        # Set up the dropdown menu only on the dropdown button
        self.mode_dropdown_btn.setMenu(process_menu)

        # Add both buttons to the split button layout
        split_button_layout.addWidget(self.process_batch_btn)
        split_button_layout.addWidget(self.mode_dropdown_btn)

        # Store the processing mode (default is "undone")
        self.processing_mode = "undone"

        # Add process mode split button to combined layout
        combined_controls_layout.addWidget(split_button_widget)

        # Set initial processing mode
        self._set_process_mode("undone")

        # Create pause/resume button with icon
        self.pause_resume_btn = QPushButton()
        self.pause_resume_btn.setIcon(
            QIcon.fromTheme("media-playback-pause", QIcon(":/icons/pause.png"))
        )
        self.pause_resume_btn.setToolTip("Pause processing")
        #         self.pause_resume_btn.setEnabled(False)  # Disabled by default
        self.pause_resume_btn.clicked.connect(self._toggle_pause_resume)
        # Match the preview navigation button size (30x30)
        self.pause_resume_btn.setFixedSize(30, 30)
        self.pause_resume_btn.setIconSize(QSize(20, 20))
        combined_controls_layout.addWidget(self.pause_resume_btn)

        # Create stop button with icon
        self.stop_btn = QPushButton()
        self.stop_btn.setIcon(
            QIcon.fromTheme("media-playback-stop", QIcon(":/icons/stop.png"))
        )
        self.stop_btn.setToolTip("Stop processing")
        #         self.stop_btn.setEnabled(False)  # Disabled by default
        self.stop_btn.clicked.connect(self._stop_processing)
        # Match the preview navigation button size (30x30)
        self.stop_btn.setFixedSize(30, 30)
        self.stop_btn.setIconSize(QSize(20, 20))
        combined_controls_layout.addWidget(self.stop_btn)

        # Create hidden folder counter for compatibility (not visible to user)
        self.folder_counter = QLabel("0/0")
        self.folder_counter.hide()  # Hide it completely

        # Create hidden overall progress bar for compatibility (not visible to user)
        self.overall_progress = QProgressBar()
        self.overall_progress.setRange(0, 100)
        self.overall_progress.setValue(0)
        self.overall_progress.hide()  # Hide it completely

        # Store the combined controls layout to be added to preview area later
        self.combined_controls_layout = combined_controls_layout

        # Don't add controls to batch layout - they'll be added to preview area

        # Add batch (folder list) widget with stretch factor 1
        # (main content added with stretch 2 for 1:2 ratio)
        self.main_layout.addWidget(batch_widget, 1)

        # Create attributes for removed legacy buttons (placeholders)
        self.preview_button = QPushButton()
        self.analyze_button = QPushButton()

    def _toggle_pause_resume(self):
        """Toggle between pause and resume states."""
        if self.pause_resume_btn.toolTip() == "Pause processing":
            self._pause_processing()
        else:
            self._resume_processing()

    def _pause_processing(self):
        """Pause the current processing."""
        # Check which thread is running and pause it
        if self.main_thread and self.main_thread.isRunning():
            self.main_thread.pause()
        elif (
            hasattr(self, "batch_thread")
            and self.batch_thread
            and self.batch_thread.isRunning()
        ):
            self.batch_worker.pause()

        # Update button icon and tooltip
        self.pause_resume_btn.setIcon(
            QIcon.fromTheme("media-playback-start", QIcon(":/icons/play.png"))
        )
        self.pause_resume_btn.setToolTip("Resume processing")

    def _resume_processing(self):
        """Resume the paused processing."""
        # Check which thread is running and resume it
        if self.main_thread and self.main_thread.isRunning():
            self.main_thread.resume()
        elif (
            hasattr(self, "batch_thread")
            and self.batch_thread
            and self.batch_thread.isRunning()
        ):
            self.batch_worker.resume()

        # Update button icon and tooltip
        self.pause_resume_btn.setIcon(
            QIcon.fromTheme("media-playback-pause", QIcon(":/icons/pause.png"))
        )
        self.pause_resume_btn.setToolTip("Pause processing")

    def _stop_processing(self):
        """Stop the current processing."""
        # Check which thread is running and stop it
        # Record that the user requested a stop that should prevent saving
        self._user_requested_stop_no_save = True
        if self.main_thread and self.main_thread.isRunning():
            self.main_thread.stop()
        elif (
            hasattr(self, "batch_thread")
            and self.batch_thread
            and self.batch_thread.isRunning()
        ):
            self.batch_worker.stop()

    def _create_parameter_section(self, parent_widget=None) -> None:
        """Create parameter configuration area with collapsible dropdown groups."""
        # Main parameters container
        params_widget = parent_widget or QWidget()
        params_layout = QVBoxLayout(params_widget)
        params_layout.setContentsMargins(0, 0, 0, 0)
        params_layout.setSpacing(4)

        # 1. Video Calibration dropdown (collapsed by default)
        self.video_calibration_group = CollapsibleGroupBox(
            "Video Calibration", collapsed=True
        )
        self._add_video_calibration_content()
        params_layout.addWidget(self.video_calibration_group)

        # 2. ROI dropdown (collapsed by default)
        self.roi_group = CollapsibleGroupBox("Region of Interest", collapsed=True)
        self._add_roi_content()
        params_layout.addWidget(self.roi_group)

        # 3. Baseline dropdown (collapsed by default, hidden in certain modes)
        self.baseline_group = CollapsibleGroupBox("Baseline", collapsed=True)
        self._add_baseline_content()

        # Hide baseline in certain modes
        analysis_mode = getattr(self.controller, "analysis_mode", "")
        if analysis_mode in ["free_sedimentation", "structured_packing"]:
            self.baseline_group.hide()
        else:
            params_layout.addWidget(self.baseline_group)

        # 4. Angle Method dropdown (collapsed by default)
        self.angle_method_group = CollapsibleGroupBox("Angle Method", collapsed=True)
        self._add_angle_method_content()
        params_layout.addWidget(self.angle_method_group)

        # Reset to Default button (not in dropdown)
        self.reset_defaults_btn = QPushButton("Reset to Default")
        self.reset_defaults_btn.setToolTip(
            "Reset parameters to mode-specific default values and load the test folder"
        )
        self.reset_defaults_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.reset_defaults_btn.clicked.connect(self._on_reset_defaults_clicked)
        params_layout.addWidget(self.reset_defaults_btn)

        # Add stretch to push all widgets to the top
        params_layout.addStretch(1)

        # Initialize ROI spinboxes and UI states
        self._initialize_roi_spinboxes()
        self._on_baseline_checkbox_change()

        # Conditionally hide groups for certain modes
        if self.controller.analysis_mode in [
            "free_sedimentation",
            "structured_packing",
        ] and hasattr(self, "angle_method_group"):
            self.angle_method_group.hide()

        if parent_widget is None:
            self.main_layout.addWidget(params_widget)

    def _add_video_calibration_content(self) -> None:
        """Add content to Video Calibration dropdown."""
        # Create grid layout for consistent alignment
        grid_widget = QWidget()
        grid_layout = QGridLayout(grid_widget)
        grid_layout.setContentsMargins(8, 4, 8, 4)
        grid_layout.setSpacing(4)

        # FPS
        fps_label = QLabel("FPS:")
        fps_label.setAlignment(Qt.AlignLeft)
        self.FPS_entry = QSpinBox()
        self.FPS_entry.setRange(1, 1000)
        self.FPS_entry.setValue(self.controller.fps)
        self.FPS_entry.setFixedWidth(100)
        self.FPS_entry.setAlignment(Qt.AlignRight)
        self.FPS_entry.valueChanged.connect(self.controller.set_fps)
        grid_layout.addWidget(fps_label, 0, 0, Qt.AlignLeft)
        grid_layout.addWidget(self.FPS_entry, 0, 1, Qt.AlignRight)

        # Pixel
        pixel_label = QLabel("Pixel:")
        pixel_label.setAlignment(Qt.AlignLeft)
        self.PIXEL_entry = QDoubleSpinBox()
        self.PIXEL_entry.setRange(0, 100)
        self.PIXEL_entry.setSingleStep(0.01)
        self.PIXEL_entry.setValue(self.controller.pixel)
        self.PIXEL_entry.setFixedWidth(100)
        self.PIXEL_entry.setAlignment(Qt.AlignRight)
        self.PIXEL_entry.valueChanged.connect(self.controller.set_pixel)
        grid_layout.addWidget(pixel_label, 1, 0, Qt.AlignLeft)
        grid_layout.addWidget(self.PIXEL_entry, 1, 1, Qt.AlignRight)

        # Threshold
        threshold_label = QLabel("Threshold:")
        threshold_label.setAlignment(Qt.AlignLeft)
        self.threshold_entry = QSpinBox()
        self.threshold_entry.setRange(0, 255)
        self.threshold_entry.setValue(self.controller.threshold)
        self.threshold_entry.setFixedWidth(100)
        self.threshold_entry.setAlignment(Qt.AlignRight)
        self.threshold_entry.valueChanged.connect(self.controller.set_threshold)
        self.threshold_entry.valueChanged.connect(
            lambda: self._trigger_preview_update("threshold")
        )
        grid_layout.addWidget(threshold_label, 2, 0, Qt.AlignLeft)
        grid_layout.addWidget(self.threshold_entry, 2, 1, Qt.AlignRight)

        # Rotate (hidden in packing and free sedimentation modes)
        rotate_label = QLabel("Rotate:")
        rotate_label.setAlignment(Qt.AlignLeft)
        self.rotate_angle_entry = QDoubleSpinBox()
        self.rotate_angle_entry.setRange(-360, 360)
        self.rotate_angle_entry.setSingleStep(0.1)
        self.rotate_angle_entry.setValue(self.controller.rotate_angle)
        self.rotate_angle_entry.setFixedWidth(100)
        self.rotate_angle_entry.setAlignment(Qt.AlignRight)
        self.rotate_angle_entry.valueChanged.connect(self.controller.set_rotate_angle)
        self.rotate_angle_entry.valueChanged.connect(
            lambda: self._trigger_preview_update("rotation")
        )

        # Hide rotation in certain modes
        analysis_mode = getattr(self.controller, "analysis_mode", "")
        if analysis_mode in ["free_sedimentation", "structured_packing"]:
            rotate_label.hide()
            self.rotate_angle_entry.hide()
        else:
            grid_layout.addWidget(rotate_label, 3, 0, Qt.AlignLeft)
            grid_layout.addWidget(self.rotate_angle_entry, 3, 1, Qt.AlignRight)

        # Set column stretches for proper alignment
        grid_layout.setColumnStretch(0, 1)  # Labels expand
        grid_layout.setColumnStretch(1, 0)  # Controls fixed width

        self.video_calibration_group.add_widget(grid_widget)

    def _add_baseline_content(self) -> None:
        """Add content to Baseline dropdown."""
        # Create grid layout for consistent alignment
        grid_widget = QWidget()
        grid_layout = QGridLayout(grid_widget)
        grid_layout.setContentsMargins(8, 4, 8, 4)
        grid_layout.setSpacing(4)

        # Baseline Offset
        baseline_offset_label = QLabel("Offset:")
        baseline_offset_label.setAlignment(Qt.AlignLeft)
        self.baseline_entry = QSpinBox()
        self.baseline_entry.setRange(-1000, 1000)
        self.baseline_entry.setValue(self.controller.baseline)
        self.baseline_entry.setFixedWidth(100)
        self.baseline_entry.setAlignment(Qt.AlignRight)
        self.baseline_entry.valueChanged.connect(self.controller.set_baseline)
        self.baseline_entry.valueChanged.connect(
            lambda: self._trigger_preview_update("baseline_offset")
        )
        grid_layout.addWidget(baseline_offset_label, 0, 0, Qt.AlignLeft)
        grid_layout.addWidget(self.baseline_entry, 0, 1, Qt.AlignRight)

        # Enable Manual Baseline
        manual_enable_label = QLabel("Manual:")
        manual_enable_label.setAlignment(Qt.AlignLeft)
        self.Baseline_tf_checkbox = QCheckBox()
        self.Baseline_tf_checkbox.setChecked(self.controller.baseline_tf)
        self.Baseline_tf_checkbox.stateChanged.connect(self.controller.set_baseline_tf)
        self.Baseline_tf_checkbox.stateChanged.connect(
            self._on_baseline_checkbox_change
        )
        self.Baseline_tf_checkbox.stateChanged.connect(
            lambda: self._trigger_preview_update("baseline")
        )
        grid_layout.addWidget(manual_enable_label, 1, 0, Qt.AlignLeft)
        grid_layout.addWidget(self.Baseline_tf_checkbox, 1, 1, Qt.AlignRight)

        # Manual Baseline Height
        manual_height_label = QLabel("Height:")
        manual_height_label.setAlignment(Qt.AlignLeft)
        self.manual_baseline_entry = QSpinBox()
        self.manual_baseline_entry.setRange(0, 1000)
        self.manual_baseline_entry.setValue(self.controller.manual_baseline)
        self.manual_baseline_entry.setFixedWidth(100)
        self.manual_baseline_entry.setAlignment(Qt.AlignRight)
        self.manual_baseline_entry.valueChanged.connect(
            self.controller.set_manual_baseline
        )
        self.manual_baseline_entry.valueChanged.connect(
            lambda: self._trigger_preview_update("baseline")
        )
        grid_layout.addWidget(manual_height_label, 2, 0, Qt.AlignLeft)
        grid_layout.addWidget(self.manual_baseline_entry, 2, 1, Qt.AlignRight)

        # Set column stretches for proper alignment
        grid_layout.setColumnStretch(0, 1)  # Labels expand
        grid_layout.setColumnStretch(1, 0)  # Controls fixed width

        self.baseline_group.add_widget(grid_widget)

    def _add_angle_method_content(self) -> None:
        """Add content to Angle Method dropdown."""
        # Create grid layout for consistent alignment
        grid_widget = QWidget()
        grid_layout = QGridLayout(grid_widget)
        grid_layout.setContentsMargins(8, 4, 8, 4)
        grid_layout.setSpacing(4)

        # Mode
        mode_label = QLabel("Mode:")
        mode_label.setAlignment(Qt.AlignLeft)
        self.polynom_entry = QComboBox()
        self.polynom_entry.addItems(["Arc", "Tangent", "Polynom", "Ellipse"])
        self.polynom_entry.setCurrentText(self.controller.fitting_mode)
        self.polynom_entry.setFixedWidth(100)
        self.polynom_entry.currentTextChanged.connect(self.controller.set_fitting_mode)
        self.polynom_entry.currentTextChanged.connect(self._on_fitting_mode_changed)
        grid_layout.addWidget(mode_label, 0, 0, Qt.AlignLeft)
        grid_layout.addWidget(self.polynom_entry, 0, 1, Qt.AlignRight)

        # Degree
        deg_label = QLabel("Degree:")
        deg_label.setAlignment(Qt.AlignLeft)
        self.polynom_entry_spin = QSpinBox()
        self.polynom_entry_spin.setRange(1, 10)
        self.polynom_entry_spin.setValue(self.controller.polynom)
        self.polynom_entry_spin.setFixedWidth(100)
        self.polynom_entry_spin.setAlignment(Qt.AlignRight)
        self.polynom_entry_spin.valueChanged.connect(self.controller.set_polynom)
        self.polynom_entry_spin.valueChanged.connect(
            lambda: self._trigger_preview_update("fitting")
        )
        grid_layout.addWidget(deg_label, 1, 0, Qt.AlignLeft)
        grid_layout.addWidget(self.polynom_entry_spin, 1, 1, Qt.AlignRight)

        # Set column stretches for proper alignment
        grid_layout.setColumnStretch(0, 1)  # Labels expand
        grid_layout.setColumnStretch(1, 0)  # Controls fixed width

        self.angle_method_group.add_widget(grid_widget)

        # Set initial enabled state of degree spinbox
        try:
            mode_text = str(getattr(self.controller, "fitting_mode", ""))
            is_polynom = mode_text.strip().lower() == "polynom"
            self.polynom_entry_spin.setEnabled(is_polynom)
        except Exception:
            pass

    def _add_roi_content(self) -> None:
        """Add content to ROI dropdown."""
        # Select ROI Visually button (full width)
        roi_button = QPushButton("Select Visually")
        roi_button.setToolTip("Select region of interest visually")
        roi_button.clicked.connect(self.open_roi_selector)
        self.roi_group.add_widget(roi_button)

        # Create grid layout for ROI controls
        grid_widget = QWidget()
        grid_layout = QGridLayout(grid_widget)
        grid_layout.setContentsMargins(8, 4, 8, 4)
        grid_layout.setSpacing(4)

        # Left
        left_label = QLabel("Left:")
        left_label.setAlignment(Qt.AlignLeft)
        self.left_roi_spinbox = QSpinBox()
        self.left_roi_spinbox.setSingleStep(20)
        self.left_roi_spinbox.setSuffix(" px")
        self.left_roi_spinbox.setFixedWidth(100)
        self.left_roi_spinbox.setAlignment(Qt.AlignRight)
        self.left_roi_spinbox.valueChanged.connect(self.controller.set_x_img)
        self.left_roi_spinbox.valueChanged.connect(
            lambda value: self._trigger_preview_update("roi")
        )
        grid_layout.addWidget(left_label, 0, 0, Qt.AlignLeft)
        grid_layout.addWidget(self.left_roi_spinbox, 0, 1, Qt.AlignRight)

        # Right
        right_label = QLabel("Right:")
        right_label.setAlignment(Qt.AlignLeft)
        self.right_roi_spinbox = QSpinBox()
        self.right_roi_spinbox.setSingleStep(20)
        self.right_roi_spinbox.setSuffix(" px")
        self.right_roi_spinbox.setFixedWidth(100)
        self.right_roi_spinbox.setAlignment(Qt.AlignRight)
        self.right_roi_spinbox.valueChanged.connect(self.controller.set_w_img)
        self.right_roi_spinbox.valueChanged.connect(
            lambda value: self._trigger_preview_update("roi")
        )
        grid_layout.addWidget(right_label, 1, 0, Qt.AlignLeft)
        grid_layout.addWidget(self.right_roi_spinbox, 1, 1, Qt.AlignRight)

        # Top
        top_label = QLabel("Top:")
        top_label.setAlignment(Qt.AlignLeft)
        self.top_roi_spinbox = QSpinBox()
        self.top_roi_spinbox.setSingleStep(20)
        self.top_roi_spinbox.setSuffix(" px")
        self.top_roi_spinbox.setFixedWidth(100)
        self.top_roi_spinbox.setAlignment(Qt.AlignRight)
        self.top_roi_spinbox.valueChanged.connect(self.controller.set_y_img)
        self.top_roi_spinbox.valueChanged.connect(
            lambda value: self._trigger_preview_update("roi")
        )
        grid_layout.addWidget(top_label, 2, 0, Qt.AlignLeft)
        grid_layout.addWidget(self.top_roi_spinbox, 2, 1, Qt.AlignRight)

        # Bottom
        bottom_label = QLabel("Bottom:")
        bottom_label.setAlignment(Qt.AlignLeft)
        self.bottom_roi_spinbox = QSpinBox()
        self.bottom_roi_spinbox.setSingleStep(20)
        self.bottom_roi_spinbox.setSuffix(" px")
        self.bottom_roi_spinbox.setFixedWidth(100)
        self.bottom_roi_spinbox.setAlignment(Qt.AlignRight)
        self.bottom_roi_spinbox.valueChanged.connect(self.controller.set_h_img)
        self.bottom_roi_spinbox.valueChanged.connect(
            lambda value: self._trigger_preview_update("roi")
        )
        grid_layout.addWidget(bottom_label, 3, 0, Qt.AlignLeft)
        grid_layout.addWidget(self.bottom_roi_spinbox, 3, 1, Qt.AlignRight)

        # Set column stretches for proper alignment
        grid_layout.setColumnStretch(0, 1)  # Labels expand
        grid_layout.setColumnStretch(1, 0)  # Controls fixed width

        self.roi_group.add_widget(grid_widget)

    def preview(self) -> None:
        """Start preview processing thread.

        Uses average background for the middle image analysis.
        """
        logger.info("Starting preview processing")
        # Check if already processing
        if self.is_processing:
            return

        # Set preview mode flag to prevent progress bar updates
        self.is_in_preview_mode = True

        # Set processing flag
        self.is_processing = True

        # Set the preview_button and analyze_button as disabled
        #         self.preview_button.setEnabled(False)
        #         self.analyze_button.setEnabled(False)

        # Disable batch process button to prevent starting multiple processes
        #         self.process_batch_btn.setEnabled(False)
        #         self.add_folders_btn.setEnabled(False)

        # Disable folder context menu items during processing
        #         self.folder_list.setEnabled(False)

        # Enable pause/stop buttons for preview too
        #         self.pause_resume_btn.setEnabled(True)
        self.pause_resume_btn.setIcon(
            QIcon.fromTheme("media-playback-pause", QIcon(":/icons/pause.png"))
        )
        self.pause_resume_btn.setToolTip("Pause processing")
        #         self.stop_btn.setEnabled(True)

        self.overall_progress.setValue(0)  # Use overall_progress instead of progress

        # Save current parameter type before starting preview
        saved_param_type = self.last_changed_param
        # Force showing results for preview button
        self.last_changed_param = "preview"

        # If this preview is NOT called from _auto_preview (parameter change),
        # then disable context-sensitive preview
        if not self.should_show_context_preview:
            # This is a manual preview call, not from parameter change
            self.should_show_context_preview = False

        # Use the main folder for analysis if available,
        # otherwise use the current folder path
        folder_path = (
            self.controller.main_folder_path
            if self.controller.main_folder_path
            else self.controller.folder_path
        )

        # Set the current folder to the main folder if it's available
        if self.controller.main_folder_path:
            self.controller.set_folder_path(self.controller.main_folder_path)
            # No need to update folder_path_entry since it doesn't exist

        # Check if folder path exists
        if not folder_path or not os.path.isdir(folder_path):
            logger.error(f"Invalid or missing folder path for preview: {folder_path}")
            #             self.analyze_button.setEnabled(True)
            #             self.preview_button.setEnabled(True)
            self.folder_counter.setText("0/0")  # Reset folder counter
            #             self.pause_resume_btn.setEnabled(False)
            #             self.stop_btn.setEnabled(False)
            return

        logger.info(f"Creating preview thread for folder: {folder_path}")
        # Create and configure the thread
        self.preview_thread = AnalysisThread(
            self.controller,
            save_files=False,
            preview_middle=True,
            use_first_as_background=False,
        )  # Changed to False to create average background

        self.preview_thread.progress_signal.connect(
            lambda q, a, r, c, result_images, result_lists=None: (
                self._update_stats_with_param(
                    q, a, r, c, result_images, result_lists, saved_param_type
                )
            )
        )
        self.preview_thread.error_signal.connect(self._handle_error)
        self.preview_thread.finished.connect(self._enable_buttons)

        # Start the thread

        self.preview_thread.start()

    def _initialize_roi_spinboxes(self):
        """Initialize ROI spinboxes with values from the controller."""
        # Block signals BEFORE setting ranges to prevent triggering valueChanged
        # when range changes force value adjustments
        self.left_roi_spinbox.blockSignals(True)
        self.right_roi_spinbox.blockSignals(True)
        self.top_roi_spinbox.blockSignals(True)
        self.bottom_roi_spinbox.blockSignals(True)

        # Set ranges based on image dimensions (or defaults if no image available)
        self._update_roi_ranges_from_image()

        # Set values from controller
        self.left_roi_spinbox.setValue(self.controller.x_img)
        self.right_roi_spinbox.setValue(self.controller.w_img)
        self.top_roi_spinbox.setValue(self.controller.y_img)
        self.bottom_roi_spinbox.setValue(self.controller.h_img)

        # Re-enable signals
        self.left_roi_spinbox.blockSignals(False)
        self.right_roi_spinbox.blockSignals(False)
        self.top_roi_spinbox.blockSignals(False)
        self.bottom_roi_spinbox.blockSignals(False)

    def open_roi_selector(self):
        """Open the ROI selector dialog with the middle image from the folder.

        Limits ROI spinboxes to rotated image size.
        """
        logger.info("Opening ROI selector dialog")
        # Check if we have a valid folder path
        if not self.controller.folder_path or not os.path.isdir(
            self.controller.folder_path
        ):
            logger.warning("No valid folder path for ROI selection")
            return

        # Find all images in the folder
        image_extensions = ["*.jpg", "*.jpeg", "*.png", "*.bmp", "*.tiff"]
        image_files = []
        for ext in image_extensions:
            image_files.extend(
                glob.glob(os.path.join(self.controller.folder_path, ext))
            )

        if not image_files:
            logger.warning("No images found in folder for ROI selection")
            return

        # Sort files and get the middle one
        image_files.sort()
        middle_idx = len(image_files) // 2
        middle_image = image_files[middle_idx]

        # Get rotation angle from controller
        rotation_angle = (
            self.controller.rotate_angle
            if hasattr(self.controller, "rotate_angle")
            else 0.0
        )

        # Load and rotate the image to get its size
        orig_img = cv2.imread(middle_image)

        temp_roi_image = rotate_image(orig_img, rotation_angle)
        if temp_roi_image is None:
            logger.error(f"Failed to load/rotate image for ROI ranges: {middle_image}")
            self._set_default_roi_ranges()
            return

        if temp_roi_image is None:
            logger.error(f"Failed to load/rotate image for ROI ranges: {middle_image}")
            self._set_default_roi_ranges()
            return
        if temp_roi_image is None:
            logger.error(
                f"Failed to load/rotate image for ROI selector: {middle_image}"
            )
            return

        # Limit spinboxes to rotated image size
        self.left_roi_spinbox.setRange(0, temp_roi_image.shape[1] - 1)
        self.right_roi_spinbox.setRange(1, temp_roi_image.shape[1])
        self.top_roi_spinbox.setRange(0, temp_roi_image.shape[0] - 1)
        self.bottom_roi_spinbox.setRange(1, temp_roi_image.shape[0])

        # Clamp current values to new bounds
        self.left_roi_spinbox.setValue(
            min(max(self.controller.x_img, 0), temp_roi_image.shape[1] - 1)
        )
        self.right_roi_spinbox.setValue(
            min(max(self.controller.w_img, 1), temp_roi_image.shape[1])
        )
        self.top_roi_spinbox.setValue(
            min(max(self.controller.y_img, 0), temp_roi_image.shape[0] - 1)
        )
        self.bottom_roi_spinbox.setValue(
            min(max(self.controller.h_img, 1), temp_roi_image.shape[0])
        )

        # Create and show the ROI selector
        roi_dialog = ROISelector(self, middle_image, rotation_angle)
        roi_dialog.set_roi(
            self.left_roi_spinbox.value(),
            self.top_roi_spinbox.value(),
            self.right_roi_spinbox.value(),
            self.bottom_roi_spinbox.value(),
        )

        # Connect the signal
        roi_dialog.roi_selected.connect(self.apply_selected_roi)

        # Show the dialog modally
        roi_dialog.exec()

    def apply_selected_roi(self, left, top, right, bottom):
        """Apply the selected ROI to the controller."""
        logger.info(
            "Applying selected ROI: left=%s, top=%s, right=%s, bottom=%s",
            left,
            top,
            right,
            bottom,
        )
        # Update the controller values
        self.controller.set_h_img(bottom)  # Bottom
        self.controller.set_w_img(right)  # Right
        self.controller.set_y_img(top)  # Top
        self.controller.set_x_img(left)  # Left

        # Update spinboxes
        self.left_roi_spinbox.blockSignals(True)
        self.top_roi_spinbox.blockSignals(True)
        self.right_roi_spinbox.blockSignals(True)
        self.bottom_roi_spinbox.blockSignals(True)

        self.left_roi_spinbox.setValue(left)
        self.top_roi_spinbox.setValue(top)
        self.right_roi_spinbox.setValue(right)
        self.bottom_roi_spinbox.setValue(bottom)

        self.left_roi_spinbox.blockSignals(False)
        self.top_roi_spinbox.blockSignals(False)
        self.right_roi_spinbox.blockSignals(False)
        self.bottom_roi_spinbox.blockSignals(False)

        # Trigger preview update with 'roi' as the parameter type
        self._trigger_preview_update("roi")

    def _show_roi_preview(self):
        """Show the ROI preview dialog with current ROI settings (optimized)."""
        if not self.controller.folder_path or not os.path.isdir(
            self.controller.folder_path
        ):
            return

        # Use optimized preview generation with debouncing
        def generate_roi_preview():
            roi_params = (
                self.controller.x_img,
                self.controller.y_img,
                self.controller.w_img,
                self.controller.h_img,
            )
            return self.optimized_preview.generate_roi_preview(
                self.controller.folder_path,
                roi_params,
                self.controller.rotate_angle,
                self.controller.analysis_mode,
            )

        self.optimized_preview.debounced_preview_update(
            "roi", generate_roi_preview, delay_ms=25
        )

    def _show_threshold_preview(self):
        """Show threshold preview with background subtraction (optimized)."""
        if not self.controller.folder_path or not os.path.isdir(
            self.controller.folder_path
        ):
            return

        # Use optimized preview generation with debouncing
        def generate_threshold_preview():
            crop_params = (
                self.controller.x_img,
                self.controller.w_img,
                self.controller.y_img,
                self.controller.h_img,
            )
            return self.optimized_preview.generate_threshold_preview(
                self.controller.folder_path,
                self.controller.threshold,
                self.controller.rotate_angle,
                crop_params,
                self.controller.analysis_mode,
            )

        self.optimized_preview.debounced_preview_update(
            "threshold", generate_threshold_preview, delay_ms=25
        )

    def _show_rotation_preview(self):
        """Show rotation preview with orientation lines."""
        try:
            # Get the original image and apply rotation
            image = self._get_original_image()
            if image is None:
                return

            rotation_angle = getattr(self.controller, "rotate_angle", 0.0)
            rotated_image = rotate_image(image, rotation_angle)

            # Draw orientation lines
            h, w = rotated_image.shape[:2]
            line_image = rotated_image.copy()

            # Draw subtle vertical lines (every 5% of width)
            for i in range(1, 20):  # 20 vertical lines
                x = int(w * i / 20)
                cv2.line(line_image, (x, 0), (x, h), (100, 100, 100), 1)

            # Draw subtle horizontal lines (every 5% of height)
            for i in range(1, 20):  # 20 horizontal lines
                y = int(h * i / 20)
                cv2.line(line_image, (0, y), (w, y), (100, 100, 100), 1)

            # Show the rotation preview
            show_preview(line_image, self)

        except Exception as e:
            logger.error(f"Error showing rotation preview: {e}")
            pass

    def _show_baseline_preview(self):
        """Show baseline preview with rotated, cropped image and baseline.

        Uses optimized preview generation.
        """
        if not self.controller.folder_path or not os.path.isdir(
            self.controller.folder_path
        ):
            return

        # Use optimized preview generation with debouncing
        def generate_baseline_preview():
            crop_params = (
                self.controller.x_img,
                self.controller.w_img,
                self.controller.y_img,
                self.controller.h_img,
            )
            manual_baseline = (
                self.controller.manual_baseline if self.controller.baseline_tf else None
            )
            return self.optimized_preview.generate_baseline_preview(
                self.controller.folder_path,
                self.controller.baseline,
                manual_baseline,
                self.controller.rotate_angle,
                crop_params,
                self.controller.analysis_mode,
            )

        self.optimized_preview.debounced_preview_update(
            "baseline", generate_baseline_preview, delay_ms=25
        )

    def _get_original_image(self):
        """Get the original middle image from the folder."""
        try:
            if not self.controller.folder_path or not os.path.isdir(
                self.controller.folder_path
            ):
                return None

            # Find all images in the folder
            image_extensions = ["*.jpg", "*.jpeg", "*.png", "*.bmp", "*.tiff"]
            image_files = []
            for ext in image_extensions:
                image_files.extend(
                    glob.glob(os.path.join(self.controller.folder_path, ext))
                )

            if not image_files:
                return None

            # Sort files and get the middle one
            image_files.sort()
            middle_idx = len(image_files) // 2
            middle_image = image_files[middle_idx]

            # Load the image
            image = cv2.imread(middle_image)
            return image

        except Exception as e:
            logger.error(f"Error loading original image: {e}")
            return None

    def _create_preview_area(self, parent_widget=None) -> None:
        """Create the image preview area with controls above and canvases."""
        # Use parent widget if provided, otherwise create new
        preview_widget = parent_widget or QWidget()

        # Create layout for the widget
        preview_layout = QVBoxLayout(preview_widget)
        preview_layout.setContentsMargins(0, 0, 0, 0)

        # Add the combined controls layout above the canvas if it exists
        if hasattr(self, "combined_controls_layout"):
            preview_layout.addLayout(self.combined_controls_layout)

        # Create canvas container with stats overlay
        canvas_container = self._create_canvas_with_stats_overlay()
        preview_layout.addWidget(canvas_container)

        # Create and add the image slider control
        slider_widget = self._create_image_slider()
        preview_layout.addWidget(slider_widget)

        # If parent_widget was not provided, add to main layout
        if not parent_widget:
            self.main_layout.addWidget(preview_widget, 1)

    def _create_canvas_with_stats_overlay(self) -> QWidget:
        """Create the canvas container with stats overlay on top of image."""
        # Create canvas with stats icon (this will be the main container)
        canvas_wrapper = self._create_canvas_wrapper()

        # Create stats overlay as a child of canvas_wrapper (positioned on top)
        self.stats_overlay = self._create_stats_overlay(canvas_wrapper)

        return canvas_wrapper

    def _create_canvas_wrapper(self) -> QWidget:
        """Create canvas wrapper with stats icon positioned at top-left."""
        wrapper = QWidget()
        wrapper.setMinimumSize(400, 140)
        wrapper.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # Create canvas
        self.canvas_result = QLabel(wrapper)
        self.canvas_result.setAlignment(Qt.AlignCenter)
        self.canvas_result.setText("Result")
        self.canvas_result.setFrameShape(QFrame.Box)
        self.canvas_result.setFrameShadow(QFrame.Sunken)
        self.canvas_result.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # Create stats icon button with custom bar chart icon
        self.stats_icon_btn = QPushButton(wrapper)

        # Create custom bar chart icon
        icon_size = 24
        pixmap = QPixmap(icon_size, icon_size)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QColor(60, 60, 60))
        painter.setPen(Qt.NoPen)

        # Draw 5 bars of different heights
        bar_width = 3
        bar_spacing = 1
        heights = [8, 12, 16, 10, 14]  # Different heights for variation
        start_x = 2

        for i, height in enumerate(heights):
            x = start_x + i * (bar_width + bar_spacing)
            y = icon_size - 4 - height
            painter.drawRect(x, y, bar_width, height)

        painter.end()

        self.stats_icon_btn.setIcon(QIcon(pixmap))
        self.stats_icon_btn.setFixedSize(32, 32)
        self.stats_icon_btn.setStyleSheet(
            """
            QPushButton {
                background-color: rgba(100, 100, 100, 200);
                border: 2px solid #666;
                border-radius: 16px;
                font-size: 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: rgba(150, 150, 150, 255);
                border-color: #777;
            }
            QPushButton:pressed {
                background-color: rgba(80, 80, 80, 255);
            }
        """
        )
        self.stats_icon_btn.setToolTip("Toggle statistics overlay")
        self.stats_icon_btn.clicked.connect(self._toggle_stats_overlay)

        # Position stats icon at top-left (will be updated in resizeEvent)
        self.stats_icon_btn.move(10, 10)

        # Make stats icon always on top
        self.stats_icon_btn.raise_()

        # Override resize event to keep canvas sized correctly,
        # icon positioned, and overlay positioned
        def resize_wrapper():
            canvas_geometry = wrapper.rect()
            self.canvas_result.setGeometry(canvas_geometry)

            # Position icon based on overlay visibility
            if hasattr(self, "stats_overlay_visible") and self.stats_overlay_visible:
                # When overlay is open, position icon to the right of overlay
                self.stats_icon_btn.move(260, 10)  # 250px overlay width + 10px margin
            else:
                # When overlay is closed, keep icon at top-left
                self.stats_icon_btn.move(10, 10)

            # Position overlay at top-left corner if it exists
            if hasattr(self, "stats_overlay") and self.stats_overlay:
                self.stats_overlay.move(0, 0)
                # Ensure overlay is on top
                self.stats_overlay.raise_()
                self.stats_icon_btn.raise_()  # Keep icon on top of everything

        def wrapper_resize_event(event):
            resize_wrapper()
            wrapper.__class__.resizeEvent(wrapper, event)

        wrapper.resizeEvent = wrapper_resize_event

        return wrapper

    def _create_stats_overlay(self, parent) -> QWidget:
        """Create the semi-transparent stats overlay on top of image."""
        overlay = QWidget(parent)

        # Set size based on analysis mode - made more compact
        analysis_mode = getattr(self.controller, "analysis_mode", "")
        if analysis_mode in ["free_sedimentation", "structured_packing"]:
            overlay.setFixedSize(250, 100)  # More compact for these modes
        else:
            overlay.setFixedSize(250, 130)  # More compact than before
        overlay.move(0, 0)  # Position at top-left corner
        overlay.setStyleSheet(
            """
            QWidget {
                background-color: rgba(0, 0, 0, 120);  /* 47% transparency */
                border: 1px solid rgba(150, 150, 150, 180);
                border-radius: 6px;
            }
            QLabel {
                color: white;
                font-weight: bold;
                font-size: 11px;
                font-family: 'Consolas', 'Monaco', monospace;
                padding: 2px;
                background: transparent;
                border: none;
                line-height: 1.4;
            }
        """
        )

        # Create layout for stats
        layout = QVBoxLayout(overlay)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(3)

        # Create stats labels with proper spacing formatting
        analysis_mode = getattr(self.controller, "analysis_mode", "")
        show_contact_angles = analysis_mode not in [
            "free_sedimentation",
            "structured_packing",
        ]

        if show_contact_angles:
            self.overlay_adv_angle_label = QLabel("Advancing angle    |  --°")
            self.overlay_rec_angle_label = QLabel("Receding angle     |  --°")
        else:
            # Create dummy labels for compatibility but hide them
            self.overlay_adv_angle_label = QLabel("")
            self.overlay_rec_angle_label = QLabel("")
            self.overlay_adv_angle_label.hide()
            self.overlay_rec_angle_label.hide()

        self.overlay_contour_label = QLabel("Contour (W/H)      |  -- mm/-- mm")
        self.overlay_ellipse_diameter_label = QLabel("Contour diameter   |  -- mm")
        self.overlay_ellipse_diameter_label.setToolTip(
            "Ellipse diameter formula: d = sqrt(w*h)"
        )
        self.overlay_area_label = QLabel("Area               |  -- mm²")
        self.overlay_area_diameter_label = QLabel("Area diameter      |  -- mm")
        self.overlay_area_diameter_label.setToolTip(
            "Area diameter formula: d = sqrt(4*A/pi)"
        )
        self.overlay_velocity_label = QLabel("Velocity           |  -- mm/s")

        # Add labels to layout
        if show_contact_angles:
            layout.addWidget(self.overlay_adv_angle_label)
            layout.addWidget(self.overlay_rec_angle_label)
        layout.addWidget(self.overlay_contour_label)
        layout.addWidget(self.overlay_ellipse_diameter_label)
        layout.addWidget(self.overlay_area_label)
        layout.addWidget(self.overlay_area_diameter_label)
        layout.addWidget(self.overlay_velocity_label)

        # Add stretch to push stats to top
        layout.addStretch(1)

        # Store overlay visibility state (visible by default)
        self.stats_overlay_visible = True

        # Make sure overlay is on top
        overlay.raise_()

        # Initialize with default values to verify overlay is working
        try:
            # For debugging - set some test values to ensure overlay is visible
            self.overlay_adv_angle_label.setText("Advancing angle    |  --°")
            self.overlay_rec_angle_label.setText("Receding angle     |  --°")
            self.overlay_contour_label.setText("Contour (W/H)      |  -- mm/-- mm")
            self.overlay_ellipse_diameter_label.setText("Contour diameter   |  -- mm")
            self.overlay_area_label.setText("Area               |  -- mm²")
            self.overlay_area_diameter_label.setText("Area diameter      |  -- mm")
            self.overlay_velocity_label.setText("Velocity           |  -- mm/s")
        except Exception as e:
            logger.error(f"Error initializing overlay labels: {e}")

        return overlay

    def _toggle_stats_overlay(self):
        """Toggle the visibility of the stats overlay."""
        self.stats_overlay_visible = not self.stats_overlay_visible
        self.stats_overlay.setVisible(self.stats_overlay_visible)

        # Reposition the icon based on overlay visibility
        if self.stats_overlay_visible:
            # Position icon to the right of the overlay when open
            self.stats_icon_btn.move(260, 10)  # 250px overlay width + 10px margin
        else:
            # Move icon back to top-left when overlay is closed
            self.stats_icon_btn.move(10, 10)

    def _update_stats_overlay(self):
        """Update the stats overlay with current analysis data."""
        try:
            # Check if overlay exists and is visible
            if not hasattr(self, "stats_overlay") or not self.stats_overlay:
                return

            # Get current frame index for stats
            current_index = getattr(self, "current_frame_index", 0)

            # Try to use frame-specific data first
            if hasattr(self, "frame_data") and self.frame_data:
                self._update_overlay_from_frame_data(current_index)
            else:
                # Fallback to extracting from existing labels or use default values
                self._update_overlay_from_current_labels()

        except Exception as e:
            logger.error(f"Error updating stats overlay: {e}")
            # Set default values on error
            self._set_overlay_defaults()

    def _update_overlay_from_current_labels(self):
        """Update overlay from current main stats labels."""
        try:
            # Extract values directly from label text - simplified approach
            adv_val = self._extract_numeric_value(
                getattr(self, "adv_angle_label", None)
            )
            rec_val = self._extract_numeric_value(
                getattr(self, "rec_angle_label", None)
            )
            width_val = self._extract_numeric_value(getattr(self, "width_label", None))
            height_val = self._extract_numeric_value(
                getattr(self, "height_label", None)
            )
            ellipse_val = self._extract_numeric_value(
                getattr(self, "ellipse_diameter_label", None)
            )
            area_diameter_val = self._extract_numeric_value(
                getattr(self, "area_diameter_label", None)
            )
            velocity_val = self._extract_numeric_value(
                getattr(self, "velocity_value", None)
            )

            # Update overlay labels
            self._update_overlay_labels_simple(
                adv_val,
                rec_val,
                width_val,
                height_val,
                ellipse_val,
                area_diameter_val,
                velocity_val,
            )
        except Exception as e:
            logger.error(f"Error updating overlay from labels: {e}")
            self._set_overlay_defaults()

    def _extract_numeric_value(self, label):
        """Extract numeric value from a QLabel text."""
        if not label or not hasattr(label, "text"):
            return "--"
        try:
            text = label.text()
            if not text or "--" in text:
                return "--"
            # Simple regex to find numbers (including decimals)
            import re

            match = re.search(r"([0-9]+\.?[0-9]*)", text)
            return match.group(1) if match else "--"
        except Exception:
            return "--"

    def _update_overlay_labels_simple(
        self,
        adv_val,
        rec_val,
        width_val,
        height_val,
        ellipse_val,
        area_diameter_val,
        velocity_val,
    ):
        """Update overlay labels with simple string values."""
        # Update contact angles if visible
        if (
            hasattr(self, "overlay_adv_angle_label")
            and self.overlay_adv_angle_label.isVisible()
        ):
            self.overlay_adv_angle_label.setText(f"Advancing angle    |  {adv_val}°")
        if (
            hasattr(self, "overlay_rec_angle_label")
            and self.overlay_rec_angle_label.isVisible()
        ):
            self.overlay_rec_angle_label.setText(f"Receding angle     |  {rec_val}°")

        # Update dimensions
        if width_val != "--" and height_val != "--":
            contour_text = f"Contour (W/H)      |  {width_val} mm/{height_val} mm"
        else:
            contour_text = "Contour (W/H)      |  -- mm/-- mm"
        self.overlay_contour_label.setText(contour_text)

        # Update diameters
        self.overlay_ellipse_diameter_label.setText(
            f"Contour diameter   |  {ellipse_val} mm"
        )
        self.overlay_area_diameter_label.setText(
            f"Area diameter      |  {area_diameter_val} mm"
        )

        # Update velocity
        self.overlay_velocity_label.setText(
            f"Velocity           |  {velocity_val} mm/s"
        )

        # Calculate and update area if we have width and height
        if width_val != "--" and height_val != "--":
            try:
                w = float(width_val)
                h = float(height_val)
                import math

                area = math.pi * (w / 2) * (h / 2)
                self.overlay_area_label.setText(f"Area               |  {area:.2f} mm²")
            except (ValueError, TypeError):
                self.overlay_area_label.setText("Area               |  -- mm²")
        else:
            self.overlay_area_label.setText("Area               |  -- mm²")

    def _set_overlay_defaults(self):
        """Set default values for overlay when no data is available."""
        try:
            if (
                hasattr(self, "overlay_adv_angle_label")
                and self.overlay_adv_angle_label.isVisible()
            ):
                self.overlay_adv_angle_label.setText("Advancing angle    |  --°")
            if (
                hasattr(self, "overlay_rec_angle_label")
                and self.overlay_rec_angle_label.isVisible()
            ):
                self.overlay_rec_angle_label.setText("Receding angle     |  --°")
            self.overlay_contour_label.setText("Contour (W/H)      |  -- mm/-- mm")
            self.overlay_ellipse_diameter_label.setText("Contour diameter   |  -- mm")
            self.overlay_area_label.setText("Area               |  -- mm²")
            self.overlay_area_diameter_label.setText("Area diameter      |  -- mm")
            self.overlay_velocity_label.setText("Velocity           |  -- mm/s")
        except Exception as e:
            logger.error(f"Error setting overlay defaults: {e}")

    def _update_overlay_from_realtime_data(
        self,
        advancing_contact_angles,
        receding_contact_angles,
        center_points_px,
        result_images,
        result_lists,
    ):
        """Update overlay directly from real-time analysis data."""
        try:
            if not hasattr(self, "stats_overlay") or not self.stats_overlay:
                return

            # Get the latest contact angle values
            latest_adv = (
                advancing_contact_angles[-1]
                if advancing_contact_angles
                else float("nan")
            )
            latest_rec = (
                receding_contact_angles[-1] if receding_contact_angles else float("nan")
            )

            # Get dimensions from result_images first, then fallback to result_lists
            width_mm = self._get_latest_value(
                "rect_width_mm", result_images, result_lists
            )
            height_mm = self._get_latest_value(
                "rect_height_mm", result_images, result_lists
            )
            ellipse_diameter_mm = self._get_latest_value(
                "ellipse_diameter_mm", result_images, result_lists
            )

            # Calculate ellipse diameter if not available but width/height are
            if (
                np.isnan(ellipse_diameter_mm)
                and not np.isnan(width_mm)
                and not np.isnan(height_mm)
                and width_mm > 0
                and height_mm > 0
            ):
                ellipse_diameter_mm = (width_mm * height_mm) ** 0.5
            area_diameter_mm = self._get_latest_value(
                "area_diameter_mm", result_images, result_lists
            )
            velocity = self._get_latest_value("velocity", result_images, result_lists)

            # Update overlay with the real-time data
            self._set_overlay_values(
                latest_adv,
                latest_rec,
                width_mm,
                height_mm,
                ellipse_diameter_mm,
                area_diameter_mm,
                velocity,
            )

        except Exception as e:
            logger.error(f"Error updating overlay from real-time data: {e}")

    def _get_latest_value(self, key, result_images, result_lists):
        """Get the latest value from result_images or result_lists."""
        # Try result_images first
        if key in result_images:
            return result_images[key]

        # Fallback to result_lists
        if result_lists.get(key):
            values = result_lists[key]
            if values and len(values) > 0:
                return values[-1]

        return float("nan")

    def _update_overlay_from_frame_data(self, index: int):
        """Update overlay from stored frame data."""
        try:

            def _safe_get(key: str, idx: int, default):
                lst = self.frame_data.get(key, [])
                return lst[idx] if 0 <= idx < len(lst) else default

            # Get values for current frame
            adv_angle = _safe_get("advancing_contact_angles", index, float("nan"))
            rec_angle = _safe_get("receding_contact_angles", index, float("nan"))
            width_mm = _safe_get("rect_width_mm", index, float("nan"))
            height_mm = _safe_get("rect_height_mm", index, float("nan"))
            ellipse_diameter_mm = _safe_get("ellipse_diameter_mm", index, float("nan"))
            area_diameter_mm = _safe_get("area_diameter_mm", index, float("nan"))
            velocity = _safe_get("velocity", index, float("nan"))

            # Update overlay labels with numeric values
            self._set_overlay_values(
                adv_angle,
                rec_angle,
                width_mm,
                height_mm,
                ellipse_diameter_mm,
                area_diameter_mm,
                velocity,
            )
        except Exception as e:
            logger.error(f"Error updating overlay from frame data: {e}")
            self._set_overlay_defaults()

    def _set_overlay_values(
        self,
        adv_angle,
        rec_angle,
        width_mm,
        height_mm,
        ellipse_diameter_mm,
        area_diameter_mm,
        velocity,
    ):
        """Set overlay values from numeric data."""
        import numpy as np

        # Format values or show "--" for NaN
        adv_str = f"{adv_angle:.1f}" if not np.isnan(adv_angle) else "--"
        rec_str = f"{rec_angle:.1f}" if not np.isnan(rec_angle) else "--"
        width_str = f"{width_mm:.2f}" if not np.isnan(width_mm) else "--"
        height_str = f"{height_mm:.2f}" if not np.isnan(height_mm) else "--"
        ellipse_str = (
            f"{ellipse_diameter_mm:.2f}" if not np.isnan(ellipse_diameter_mm) else "--"
        )
        area_diameter_str = (
            f"{area_diameter_mm:.2f}" if not np.isnan(area_diameter_mm) else "--"
        )
        velocity_str = f"{velocity:.2f}" if not np.isnan(velocity) else "--"

        # Update overlay labels with consistent spacing formatting
        if (
            hasattr(self, "overlay_adv_angle_label")
            and self.overlay_adv_angle_label.isVisible()
        ):
            self.overlay_adv_angle_label.setText(f"Advancing angle    |  {adv_str}°")
        if (
            hasattr(self, "overlay_rec_angle_label")
            and self.overlay_rec_angle_label.isVisible()
        ):
            self.overlay_rec_angle_label.setText(f"Receding angle     |  {rec_str}°")
        self.overlay_contour_label.setText(
            f"Contour (W/H)      |  {width_str} mm/{height_str} mm"
        )
        self.overlay_ellipse_diameter_label.setText(
            f"Contour diameter   |  {ellipse_str} mm"
        )
        self.overlay_area_diameter_label.setText(
            f"Area diameter      |  {area_diameter_str} mm"
        )
        self.overlay_velocity_label.setText(
            f"Velocity           |  {velocity_str} mm/s"
        )

        # Calculate area if both width and height are available
        if (
            not np.isnan(width_mm)
            and not np.isnan(height_mm)
            and width_mm > 0
            and height_mm > 0
        ):
            # Approximate area as ellipse: A = π * (w/2) * (h/2)
            area_mm2 = np.pi * (width_mm / 2) * (height_mm / 2)
            self.overlay_area_label.setText(f"Area               |  {area_mm2:.2f} mm²")
        else:
            self.overlay_area_label.setText("Area               |  -- mm²")

    def _create_image_slider(self) -> QWidget:
        """Create a professional image slider for navigating through result images.

        Returns
        -------
        QWidget
            The complete slider widget with controls and display.

        """
        # Main container with single horizontal layout
        slider_widget = QWidget()
        slider_layout = QHBoxLayout(slider_widget)
        slider_layout.setContentsMargins(5, 5, 5, 5)
        slider_layout.setSpacing(10)

        # Previous frame button with skip backward icon
        self.btn_prev_frame = QPushButton()
        self.btn_prev_frame.setFixedSize(30, 30)
        self.btn_prev_frame.setIconSize(QSize(20, 20))
        # Try to get skip backward icon, fall back to text
        skip_back_icon = QIcon.fromTheme("media-skip-backward")
        if skip_back_icon.isNull():
            # Create custom skip backward icon
            size = 24
            pixmap = QPixmap(size, size)
            pixmap.fill(Qt.transparent)
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setBrush(QColor(60, 60, 60))
            painter.setPen(Qt.NoPen)
            tri1 = QPolygon([QPoint(20, 4), QPoint(12, 12), QPoint(20, 20)])
            tri2 = QPolygon([QPoint(12, 4), QPoint(4, 12), QPoint(12, 20)])
            painter.drawPolygon(tri1)
            painter.drawPolygon(tri2)
            painter.end()
            skip_back_icon = QIcon(pixmap)
        self.btn_prev_frame.setIcon(skip_back_icon)
        self.btn_prev_frame.setToolTip("Previous frame (Left Arrow)")
        self.btn_prev_frame.clicked.connect(self._navigate_to_previous_frame)
        self.btn_prev_frame.setEnabled(False)

        # Play/Pause button with pause/resume icons
        self.btn_play_pause = QPushButton()
        self.btn_play_pause.setFixedSize(30, 30)
        self.btn_play_pause.setIconSize(QSize(20, 20))
        self.btn_play_pause.setIcon(
            QIcon.fromTheme("media-playback-start", QIcon(":/icons/play.png"))
        )
        self.btn_play_pause.setToolTip("Auto-play frames (Space)")
        self.btn_play_pause.clicked.connect(self._toggle_auto_play)
        self.btn_play_pause.setEnabled(False)

        # Next frame button with skip forward icon
        self.btn_next_frame = QPushButton()
        self.btn_next_frame.setFixedSize(30, 30)
        self.btn_next_frame.setIconSize(QSize(20, 20))
        # Try to get skip forward icon, fall back to custom
        skip_forward_icon = QIcon.fromTheme("media-skip-forward")
        if skip_forward_icon.isNull():
            # Create custom skip forward icon (reuse from batch processing)
            size = 24
            pixmap = QPixmap(size, size)
            pixmap.fill(Qt.transparent)
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setBrush(QColor(60, 60, 60))
            painter.setPen(Qt.NoPen)
            tri1 = QPolygon([QPoint(4, 4), QPoint(12, 12), QPoint(4, 20)])
            tri2 = QPolygon([QPoint(12, 4), QPoint(20, 12), QPoint(12, 20)])
            painter.drawPolygon(tri1)
            painter.drawPolygon(tri2)
            painter.end()
            skip_forward_icon = QIcon(pixmap)
        self.btn_next_frame.setIcon(skip_forward_icon)
        self.btn_next_frame.setToolTip("Next frame (Right Arrow)")
        self.btn_next_frame.clicked.connect(self._navigate_to_next_frame)
        self.btn_next_frame.setEnabled(False)

        # Speed control slider (10x slower to 2x faster than real-life)
        # Range: 1-21 where 1=0.1x (10x slower), 11=1.0x (real speed),
        # 21=2.0x (2x faster)
        self.speed_slider = QSlider(Qt.Horizontal)
        self.speed_slider.setRange(1, 21)
        self.speed_slider.setValue(11)  # Default to real-life speed (1.0x)
        self.speed_slider.setFixedWidth(100)
        self.speed_slider.setToolTip("Playback speed (0.1x to 2.0x real-life speed)")

        # Connect slider events for dynamic speed indicator
        self.speed_slider.sliderPressed.connect(self._on_speed_slider_pressed)
        self.speed_slider.sliderMoved.connect(self._on_speed_slider_moved)
        self.speed_slider.sliderReleased.connect(self._on_speed_slider_released)
        self.speed_slider.valueChanged.connect(self._on_speed_slider_changed)

        # Speed indicator label (static, to the left of slider)
        self.speed_label = QLabel("1.0x")
        self.speed_label.setFixedWidth(35)
        self.speed_label.setAlignment(Qt.AlignCenter)
        self.speed_label.setStyleSheet("font-weight: bold; color: #333;")
        self.speed_label.setToolTip("Current playback speed multiplier")
        # Position will be set dynamically when shown

        # Main slider for frame navigation (expandable)
        self.image_slider = QSlider(Qt.Horizontal)
        self.image_slider.setMinimum(0)
        self.image_slider.setMaximum(0)
        self.image_slider.setValue(0)
        self.image_slider.setTickPosition(QSlider.TicksBelow)
        self.image_slider.setTickInterval(1)
        self.image_slider.setEnabled(False)
        self.image_slider.valueChanged.connect(self._on_slider_value_changed)
        self.image_slider.setToolTip("Navigate through result frames")

        # Assemble inline layout: controls on left, slider on right (expandable)
        slider_layout.addWidget(self.btn_prev_frame)
        slider_layout.addWidget(self.btn_play_pause)
        slider_layout.addWidget(self.btn_next_frame)
        slider_layout.addWidget(self.speed_label)
        slider_layout.addWidget(self.speed_slider)
        slider_layout.addWidget(self.image_slider, 1)  # Expandable

        # If the overall progress bar exists, try to match its width to the image slider
        try:
            if hasattr(self, "overall_progress") and self.image_slider:
                # Use the image slider's size hint to set a reasonable minimum width
                pw = max(200, self.image_slider.sizeHint().width())
                self.overall_progress.setMinimumWidth(pw)
                # Set a consistent height similar to the slider
                ph = max(16, self.image_slider.sizeHint().height() + 6)
                self.overall_progress.setFixedHeight(ph)
        except Exception:
            pass

        # Initialize slider state
        self.current_frame_index = 0
        self.is_auto_playing = False
        self.auto_play_timer = QTimer()
        self.auto_play_timer.timeout.connect(self._auto_advance_frame)

        # Initialize speed label
        self._update_speed_label()

        return slider_widget

    # Image Slider Navigation Methods
    # ================================

    def _navigate_to_previous_frame(self) -> None:
        """Navigate to the previous frame in the image slider."""
        if self.current_frame_index > 0:
            self.current_frame_index -= 1
            self.image_slider.setValue(self.current_frame_index)
            self._display_frame_at_index(self.current_frame_index)
            self._update_frame_info()
            # Update stats overlay when navigating frames
            self._update_stats_overlay()

    def _navigate_to_next_frame(self) -> None:
        """Navigate to the next frame in the image slider."""
        max_index = len(self.preview_images.get("result", [])) - 1
        if self.current_frame_index < max_index:
            self.current_frame_index += 1
            self.image_slider.setValue(self.current_frame_index)
            self._display_frame_at_index(self.current_frame_index)
            self._update_frame_info()
            # Update stats overlay when navigating frames
            self._update_stats_overlay()

    def _toggle_auto_play(self) -> None:
        """Toggle auto-play mode for the image slider."""
        if not self.preview_images.get("result"):
            return

        self.is_auto_playing = not self.is_auto_playing

        if self.is_auto_playing:
            self.btn_play_pause.setIcon(
                QIcon.fromTheme("media-playback-pause", QIcon(":/icons/pause.png"))
            )
            self.btn_play_pause.setToolTip("Pause auto-play (Space)")

            # Calculate interval based on FPS and speed multiplier
            fps = getattr(self.controller, "fps", 30)  # Default 30 FPS if not available
            real_life_interval = 1000.0 / fps  # Real-life interval in milliseconds

            # Convert speed slider value to multiplier (1-21 -> 0.1x to 2.0x)
            speed_value = self.speed_slider.value()
            if speed_value <= 11:
                # 1-11 maps to 0.1x-1.0x (10x slower to real speed)
                speed_multiplier = (speed_value + 9) / 20.0
            else:
                # 12-21 maps to 1.1x-2.0x (faster than real speed)
                speed_multiplier = 1.0 + (speed_value - 11) / 10.0

            # Calculate final interval
            # (slower = higher interval, faster = lower interval)
            interval = int(real_life_interval / speed_multiplier)
            interval = max(10, interval)  # Minimum 10ms to prevent system overload

            self.auto_play_timer.start(interval)
        else:
            self.btn_play_pause.setIcon(
                QIcon.fromTheme("media-playback-start", QIcon(":/icons/play.png"))
            )
            self.btn_play_pause.setToolTip("Auto-play frames (Space)")
            self.auto_play_timer.stop()

    def _auto_advance_frame(self) -> None:
        """Automatically advance to the next frame during auto-play."""
        max_index = len(self.preview_images.get("result", [])) - 1

        if self.current_frame_index < max_index:
            self._navigate_to_next_frame()
        else:
            # Loop back to the beginning
            self.current_frame_index = 0
            self.image_slider.setValue(0)
            self._display_frame_at_index(0)
            self._update_frame_info()
            # Update stats overlay when auto-advancing
            self._update_stats_overlay()

    def _on_speed_slider_changed(self) -> None:
        # Handle speed slider changes and update auto-play interval if active
        if self.is_auto_playing:
            # Restart auto-play with new speed
            self.auto_play_timer.stop()

            # Calculate new interval based on FPS and speed multiplier
            fps = getattr(self.controller, "fps", 30)  # Default 30 FPS
            real_life_interval = 1000.0 / fps  # Real-life interval in milliseconds

            # Convert speed slider value to multiplier
            speed_value = self.speed_slider.value()
            multiplier = (
                (speed_value + 9) / 20.0
                if speed_value <= 11
                else 1.0 + (speed_value - 11) / 10.0
            )

            # Calculate final interval and restart timer
            interval = int(real_life_interval / multiplier)
            interval = max(10, interval)  # Minimum 10ms
            self.auto_play_timer.start(interval)

    def _on_speed_slider_pressed(self) -> None:
        """Show speed indicator when user starts sliding."""
        pass  # No action needed for static label

    def _on_speed_slider_moved(self, value: int) -> None:
        """Update speed indicator while user is sliding."""
        self._update_speed_label(value)

    def _on_speed_slider_released(self) -> None:
        """Hide speed indicator when user stops sliding."""
        pass  # No action needed for static label

    def _on_slider_value_changed(self, value: int) -> None:
        """Handle slider value changes from direct user interaction."""
        if value != self.current_frame_index:
            self.current_frame_index = value
            self._display_frame_at_index(value)
            self._update_frame_info()
            # Update stats overlay when slider changes
            self._update_stats_overlay()

    def _update_speed_label(self, value=None):
        # Update the speed label to show current multiplier
        if not hasattr(self, "speed_label"):
            return

        if value is None:
            value = self.speed_slider.value()

        # Convert slider value to speed multiplier
        # 1-11 maps to 0.0x-1.0x; 12-21 maps to 1.1x-2.0x
        multiplier = value / 10.0 - 0.1 if value <= 11 else 1.0 + (value - 11) / 10.0

        # Set the text using character concatenation
        multiplier_str = str(round(multiplier, 1))
        suffix = chr(120)  # ASCII for 'x'
        self.speed_label.setText(multiplier_str + suffix)

    def _display_frame_at_index(self, index: int) -> None:
        """Display the image at the specified index and update stats.

        Parameters
        ----------
        index : int
            The frame index to display.

        """
        try:
            result_images = self.preview_images.get("result", [])
            if 0 <= index < len(result_images):
                image = result_images[index]
                if image is not None:
                    self.display_image_in_canvas(image, self.canvas_result)
                    # Update stats for current frame
                    self._update_frame_specific_stats(index)
                    # Ensure overlay stays on top after image update
                    if hasattr(self, "stats_overlay") and self.stats_overlay:
                        self.stats_overlay.raise_()
                        if hasattr(self, "stats_icon_btn"):
                            self.stats_icon_btn.raise_()
                else:
                    logger.warning(f"Image at index {index} is None")
        except Exception as e:
            logger.error(f"Error displaying frame at index {index}: {e}")

    def _update_frame_info(self) -> None:
        """Update the frame information display.

        Note: Frame count display has been removed per user request.
        This method is kept for compatibility but does nothing.
        """
        pass

    def _update_frame_specific_stats(self, index: int) -> None:
        """Update stats display for a specific frame.

        Parameters
        ----------
        index : int
            The frame index to display stats for.

        """
        # Minimal prechecks and linear flow to reduce cyclomatic complexity
        if not getattr(self, "frame_data", None):
            return

        total_frames = len(self.frame_data.get("advancing_contact_angles", []))
        if index < 0 or index >= total_frames:
            return

        def _safe_get(key: str, idx: int, default: Any):
            lst = self.frame_data.get(key, [])
            return lst[idx] if idx < len(lst) else default

        try:
            adv_angle = _safe_get("advancing_contact_angles", index, float("nan"))
            rec_angle = _safe_get("receding_contact_angles", index, float("nan"))
            # Center position is handled visually, no text update needed
            velocity = _safe_get("velocity", index, float("nan"))
            width_mm = _safe_get("rect_width_mm", index, float("nan"))
            height_mm = _safe_get("rect_height_mm", index, float("nan"))
            ellipse_diameter_mm = _safe_get("ellipse_diameter_mm", index, float("nan"))
            area_diameter_mm = _safe_get("area_diameter_mm", index, float("nan"))

            # Prepare mapping of overlay label attributes to their display texts
            label_updates = {
                "overlay_adv_angle_label": (
                    f"Advancing angle    |  {adv_angle:.1f}°",
                    "Advancing angle    |  --°",
                    not np.isnan(adv_angle),
                ),
                "overlay_rec_angle_label": (
                    f"Receding angle     |  {rec_angle:.1f}°",
                    "Receding angle     |  --°",
                    not np.isnan(rec_angle),
                ),
                "overlay_contour_label": (
                    f"Contour (W/H)      |  {width_mm:.2f} mm/{height_mm:.2f} mm",
                    "Contour (W/H)      |  -- mm/-- mm",
                    not np.isnan(width_mm) and not np.isnan(height_mm),
                ),
                "overlay_ellipse_diameter_label": (
                    f"Contour diameter   |  {ellipse_diameter_mm:.2f} mm",
                    "Contour diameter   |  -- mm",
                    not np.isnan(ellipse_diameter_mm),
                ),
                "overlay_velocity_label": (
                    f"Velocity           |  {velocity:.2f} mm/s",
                    "Velocity           |  -- mm/s",
                    not np.isnan(velocity),
                ),
                "overlay_area_diameter_label": (
                    f"Area diameter      |  {area_diameter_mm:.2f} mm",
                    "Area diameter      |  -- mm",
                    not np.isnan(area_diameter_mm),
                ),
            }

            for attr, (text_if, text_else, has_value) in label_updates.items():
                lbl = getattr(self, attr, None)
                if lbl is not None:
                    lbl.setText(text_if if has_value else text_else)

            # Center position is shown visually on the image, no text label needed

            # Update stats overlay with frame-specific data
            self._update_stats_overlay()

        except Exception as e:
            logger.error(f"Error updating frame-specific stats: {e}")

    def _store_frame_data(self, result_lists: dict[str, Any]) -> None:
        """Store frame data for slider navigation stats display.

        Parameters
        ----------
        result_lists : dict
            Dictionary containing analysis results for all frames.

        """
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
                "filenames": result_lists.get("filenames", []),
            }
            frame_count = len(self.frame_data.get("advancing_contact_angles", []))
            logger.info(
                "Stored frame data for %d frames",
                frame_count,
            )
        except Exception as e:
            logger.error(f"Error storing frame data: {e}")
            # Initialize empty frame data on error
            self.frame_data = {
                "advancing_contact_angles": [],
                "receding_contact_angles": [],
                "center_points_px": [],
                "center_points_mm": [],
                "velocity": [],
                "rect_width_mm": [],
                "rect_height_mm": [],
                "filenames": [],
            }

    def _clear_frame_data(self) -> None:
        """Clear frame data when starting new analysis."""
        self.frame_data = {
            "advancing_contact_angles": [],
            "receding_contact_angles": [],
            "center_points_px": [],
            "center_points_mm": [],
            "velocity": [],
            "rect_width_mm": [],
            "rect_height_mm": [],
            "filenames": [],
        }
        # Also clear preview images
        self.preview_images = {"original": [], "result": []}
        logger.debug("Cleared frame data and preview images")

    def _update_slider_state(self) -> None:
        """Update the slider state when new images are loaded."""
        # Safety check: ensure slider components exist
        if not hasattr(self, "image_slider") or self.image_slider is None:
            return

        total_frames = len(self.preview_images.get("result", []))

        if total_frames > 1:
            # Enable slider and controls
            self.image_slider.setEnabled(True)
            self.image_slider.setMaximum(total_frames - 1)
            self.btn_prev_frame.setEnabled(True)
            self.btn_next_frame.setEnabled(True)
            self.btn_play_pause.setEnabled(True)

            # Reset to first frame
            self.current_frame_index = 0
            self.image_slider.setValue(0)
            self._update_frame_info()

            # Stop auto-play if it was running
            if self.is_auto_playing:
                self._toggle_auto_play()

        else:
            # Disable slider and controls
            self.image_slider.setEnabled(False)
            self.image_slider.setMaximum(0)
            self.btn_prev_frame.setEnabled(False)
            self.btn_next_frame.setEnabled(False)
            self.btn_play_pause.setEnabled(False)
            self.current_frame_index = 0
            self._update_frame_info()

    def _setup_slider_keyboard_shortcuts(self) -> None:
        """Set up keyboard shortcuts for the image slider."""
        # Add keyboard shortcuts for navigation
        if hasattr(self, "image_slider") and self.image_slider is not None:
            # Left arrow for previous frame
            self.shortcut_prev = QShortcut(QKeySequence(Qt.Key_Left), self)
            self.shortcut_prev.activated.connect(self._navigate_to_previous_frame)

            # Right arrow for next frame
            self.shortcut_next = QShortcut(QKeySequence(Qt.Key_Right), self)
            self.shortcut_next.activated.connect(self._navigate_to_next_frame)

            # Space bar for play/pause
            self.shortcut_play = QShortcut(QKeySequence(Qt.Key_Space), self)
            self.shortcut_play.activated.connect(self._toggle_auto_play)

    # End of Image Slider Methods
    # ============================

    def _on_baseline_checkbox_change(self) -> None:
        """Handle baseline checkbox state change."""
        is_checked = self.Baseline_tf_checkbox.isChecked()
        self.controller.set_baseline_tf(is_checked)

        # Enable/disable manual baseline vs baseline offset
        try:
            # manual_baseline_entry should be enabled when manual baseline is checked
            if hasattr(self, "manual_baseline_entry"):
                self.manual_baseline_entry.setEnabled(is_checked)

            # baseline_entry should be disabled when manual baseline is checked
            if hasattr(self, "baseline_entry"):
                self.baseline_entry.setEnabled(not is_checked)
        except Exception:
            # Best-effort: avoid crashing UI if controls not present
            logger.exception("Failed toggling baseline controls based on checkbox")

    def _on_fitting_mode_changed(self, *args) -> None:
        """Enable degree spinbox only when fitting mode is 'Polynom'."""
        try:
            mode_text = ""

            # Prefer controller value at startup (more authoritative)
            try:
                mode_text = str(getattr(self.controller, "fitting_mode", ""))
            except Exception:
                mode_text = ""

            # Fallback to combobox text if controller doesn't have it
            if (
                not mode_text
                and hasattr(self, "polynom_entry")
                and isinstance(self.polynom_entry, QComboBox)
            ):
                try:
                    mode_text = str(self.polynom_entry.currentText())
                except Exception:
                    mode_text = ""

            # Last resort: use callback arg
            if not mode_text and args:
                try:
                    mode_text = str(args[0])
                except Exception:
                    mode_text = ""

            # Normalize and check
            is_polynom = str(mode_text).strip().lower() == "polynom"

            if hasattr(self, "polynom_entry_spin"):
                self.polynom_entry_spin.setEnabled(is_polynom)
        except Exception:
            logger.exception(
                "Failed toggling polynom degree control based on fitting mode"
            )

    def _on_reset_defaults_clicked(self) -> None:
        """Handle Reset to Default button click: reset controller and update UI."""
        # Show confirmation dialog
        msg_box = QMessageBox(self)
        msg_box.setIcon(QMessageBox.Warning)
        msg_box.setWindowTitle("Reset to Defaults")
        msg_box.setText(
            "Are you sure you want to reset all parameters to default values?"
        )
        msg_box.setInformativeText(
            "This will:\n"
            "• Reset all analysis parameters (FPS, Pixel, Threshold, etc.)\n"
            "• Clear the current folder list\n"
            "• Load the default test folder for the current analysis mode\n"
            "• Reset ROI settings to default values\n\n"
            "All current parameter configurations will be lost."
        )
        msg_box.setStandardButtons(QMessageBox.Yes | QMessageBox.Cancel)
        msg_box.setDefaultButton(QMessageBox.Cancel)

        # Execute the dialog and check the result
        result = msg_box.exec()
        if result != QMessageBox.Yes:
            return  # User cancelled, do nothing

        try:
            if hasattr(self.controller, "reset_to_defaults"):
                self.controller.reset_to_defaults()
            else:
                logger.warning("Controller has no reset_to_defaults method")

            # Clear current folder list and add the mode-specific test folder
            try:
                # This helper clears controller paths and will add the test
                # folder for the current analysis mode when the list is empty.
                self.clear_folder_list()
            except Exception:
                logger.exception("Failed to clear and reset folder list")

            # Update UI controls to reflect controller values
            self._apply_controller_values_to_ui()

        except Exception as e:
            logger.error(f"Error resetting defaults: {e}")

    def _apply_controller_values_to_ui(self) -> None:
        """Update all parameter controls from controller values.

        Without triggering auto-preview callbacks.
        """
        try:
            controls = self._gather_ui_controls()
            # Block signals while updating to avoid triggering previews
            self._block_ui_controls(controls, True)
            try:
                self._set_ui_values_from_controller()
            except Exception as e:
                logger.error(f"Failed to apply controller values to UI: {e}")
            finally:
                # Unblock signals after update
                self._block_ui_controls(controls, False)
        except Exception as e:
            logger.error(f"Error updating UI from controller: {e}")

    def _gather_ui_controls(self) -> list:
        """Return a list of UI controls to be updated from the controller."""
        controls: list = []
        # Basic controls
        for name in (
            "FPS_entry",
            "PIXEL_entry",
            "threshold_entry",
            "rotate_angle_entry",
            "baseline_entry",
            "Baseline_tf_checkbox",
            "manual_baseline_entry",
            "polynom_entry",
            "polynom_entry_spin",
        ):
            if hasattr(self, name):
                controls.append(getattr(self, name))

        # ROI controls (may or may not exist)
        controls.extend(
            [
                getattr(self, "left_roi_spinbox", None),
                getattr(self, "right_roi_spinbox", None),
                getattr(self, "top_roi_spinbox", None),
                getattr(self, "bottom_roi_spinbox", None),
            ]
        )
        # Filter out None values
        return [c for c in controls if c is not None]

    def _block_ui_controls(self, controls: list, block: bool) -> None:
        """Block or unblock signals for a list of controls."""
        for c in controls:
            try:
                c.blockSignals(block)
            except Exception:
                # Best-effort: ignore controls that do not support blocking
                pass

    def _set_ui_values_from_controller(self) -> None:
        """Set values on UI controls from controller properties."""
        # Delegate to smaller helpers to reduce McCabe complexity
        self._apply_basic_mappings()
        self._apply_checkbox_and_combobox()
        self._apply_roi_mappings()

    def _apply_basic_mappings(self) -> None:
        """Apply simple numeric mappings from controller to UI controls."""
        mappings = [
            ("FPS_entry", "fps", int, "setValue"),
            ("PIXEL_entry", "pixel", float, "setValue"),
            ("threshold_entry", "threshold", int, "setValue"),
            ("rotate_angle_entry", "rotate_angle", float, "setValue"),
            ("baseline_entry", "baseline", int, "setValue"),
            ("manual_baseline_entry", "manual_baseline", int, "setValue"),
            ("polynom_entry_spin", "polynom", int, "setValue"),
        ]

        for ui_name, ctrl_name, caster, method in mappings:
            ui_ctrl = getattr(self, ui_name, None)
            if ui_ctrl is None or not hasattr(self.controller, ctrl_name):
                continue
            try:
                value = getattr(self.controller, ctrl_name)
                getattr(ui_ctrl, method)(caster(value))
            except Exception:
                continue

    def _apply_checkbox_and_combobox(self) -> None:
        """Apply checkbox and combobox values from controller."""
        if hasattr(self, "Baseline_tf_checkbox") and hasattr(
            self.controller, "baseline_tf"
        ):
            try:
                self.Baseline_tf_checkbox.setChecked(bool(self.controller.baseline_tf))
            except Exception:
                pass

        if hasattr(self, "polynom_entry") and isinstance(self.polynom_entry, QComboBox):
            try:
                self.polynom_entry.setCurrentText(
                    str(getattr(self.controller, "fitting_mode", ""))
                )
            except Exception:
                pass

        # Ensure dependent controls reflect current settings
        try:
            # Toggle baseline/manual baseline controls
            if hasattr(self, "_on_baseline_checkbox_change"):
                self._on_baseline_checkbox_change()
        except Exception:
            pass

        try:
            # Toggle polynom degree control according to current fitting mode
            if hasattr(self, "_on_fitting_mode_changed"):
                self._on_fitting_mode_changed()
        except Exception:
            pass

    def _apply_roi_mappings(self) -> None:
        """Apply ROI spinbox values from controller."""
        roi_mappings = [
            ("left_roi_spinbox", "x_img"),
            ("right_roi_spinbox", "w_img"),
            ("top_roi_spinbox", "y_img"),
            ("bottom_roi_spinbox", "h_img"),
        ]
        for ui_name, ctrl_name in roi_mappings:
            ui_ctrl = getattr(self, ui_name, None)
            if ui_ctrl is None or not hasattr(self.controller, ctrl_name):
                continue
            try:
                ui_ctrl.setValue(int(getattr(self.controller, ctrl_name)))
            except Exception:
                pass

    def display_image_in_canvas(self, img: Any, canvas: QLabel) -> None:
        """Display an OpenCV image in a Qt label properly scaled to fit."""
        if img is None:
            return

        try:
            # Enhanced type checking
            if not isinstance(img, np.ndarray):
                return

            h, w = img.shape[:2]

            # Convert to RGB format if needed (ensure we handle color format correctly)
            if len(img.shape) == 3:
                # Make a copy to avoid modifying the source image
                display_img = img.copy()
                if img.shape[2] == 3:  # BGR to RGB
                    display_img = cv2.cvtColor(display_img, cv2.COLOR_BGR2RGB)
            else:
                # Convert grayscale to RGB
                display_img = cv2.cvtColor(img.copy(), cv2.COLOR_GRAY2RGB)

            # Convert to QImage
            h, w, ch = display_img.shape
            bytes_per_line = ch * w
            q_img = QImage(display_img.data, w, h, bytes_per_line, QImage.Format_RGB888)
            pixmap = QPixmap.fromImage(q_img)

            # Get canvas size
            canvas_width = canvas.width()
            canvas_height = canvas.height()

            # Check if the canvas has a valid size
            if canvas_width <= 1 or canvas_height <= 1:
                # Use the minimum size as fallback
                canvas_width = canvas.minimumWidth()
                canvas_height = canvas.minimumHeight()

            # Scale the image to fit within the canvas while maintaining aspect ratio
            if w > 0 and h > 0 and canvas_width > 0 and canvas_height > 0:
                scaled_pixmap = pixmap.scaled(
                    canvas_width,
                    canvas_height,
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation,
                )
                canvas.setPixmap(scaled_pixmap)
            else:
                # Fallback if dimensions are invalid
                canvas.setPixmap(pixmap)

            # Center the image in the canvas
            canvas.setAlignment(Qt.AlignCenter)

        except Exception as e:
            logger.error(f"Failed to display image in canvas: {e}")
            pass

    def _enable_buttons(self) -> None:
        """Re-enable buttons after thread completion."""
        # Reset processing flag
        self.is_processing = False

        # Clear preview mode flag
        self.is_in_preview_mode = False

        #         self.analyze_button.setEnabled(True)
        #         self.preview_button.setEnabled(True)

        # Re-enable batch buttons
        #         self.process_batch_btn.setEnabled(True)
        #         self.add_folders_btn.setEnabled(True)

        # Re-enable the folder list
        #         self.folder_list.setEnabled(True)

        # Disable pause/stop buttons
        #         self.pause_resume_btn.setEnabled(False)
        #         self.stop_btn.setEnabled(False)

        # Also reset the pause button state for next time
        self.pause_resume_btn.setIcon(
            QIcon.fromTheme("media-playback-pause", QIcon(":/icons/pause.png"))
        )
        self.pause_resume_btn.setToolTip("Pause processing")

        # Reset folder counter to default state if not in batch processing
        if not (
            hasattr(self, "batch_thread")
            and self.batch_thread
            and self.batch_thread.isRunning()
        ):
            self.folder_counter.setText("0/0")

    def _handle_error(self) -> None:
        """Handle errors from processing thread."""
        logger.error("Error occurred during processing, cleaning up")
        self._enable_buttons()

        # Also reset the pause button state
        self.pause_resume_btn.setIcon(
            QIcon.fromTheme("media-playback-pause", QIcon(":/icons/pause.png"))
        )
        self.pause_resume_btn.setToolTip("Pause processing")

    def _ensure_velocity(self, result_lists: dict, time, time_int) -> None:
        """Calculate velocities if missing or all NaN in the provided results.

        Updates `result_lists` in-place.
        """
        vel = result_lists.get("velocity")
        if not vel or all(np.isnan(v) for v in vel):
            try:
                fps_val = getattr(self.controller, "_fps", None)
                if fps_val is None:
                    fps_val = getattr(self.controller, "fps", None)

                result_lists["velocity"] = calculate_velocities(
                    result_lists.get("center_points_px", []),
                    getattr(self.controller, "pixel", None),
                    fps_val,
                    time_int,
                )
            except Exception as e:
                logger.error(f"Failed to calculate velocity: {e}")
                # Leave velocity as-is (likely NaNs)

    def _build_save_parameters(self) -> dict:
        """Build parameters dict for saving results from controller attributes."""
        params = {
            "pixel": getattr(self.controller, "pixel", None),
            "fps": getattr(self.controller, "fps", None),
            "threshold": getattr(self.controller, "threshold", None),
            "rotate_angle": getattr(self.controller, "rotate_angle", None),
            "baseline": getattr(self.controller, "baseline", None),
            "fitting_mode": getattr(self.controller, "fitting_mode", None),
            "polynom": getattr(self.controller, "polynom", None),
            "baseline_tf": getattr(self.controller, "baseline_tf", None),
            "manual_baseline": getattr(self.controller, "manual_baseline", None),
            "x_img": getattr(self.controller, "x_img", None),
            "y_img": getattr(self.controller, "y_img", None),
            "w_img": getattr(self.controller, "w_img", None),
            "h_img": getattr(self.controller, "h_img", None),
        }

        # Omit unused parameters in Free Sedimentation and Structured Packing
        try:
            mode = getattr(self.controller, "analysis_mode", None)
            if mode in ("free_sedimentation", "structured_packing"):
                exclude_keys = {
                    "rotate_angle",
                    "baseline",
                    "fitting_mode",
                    "polynom",
                    "baseline_tf",
                    "manual_baseline",
                }
                params = {k: v for k, v in params.items() if k not in exclude_keys}
        except Exception:
            pass

        return params

    def _find_representative_file_names(self, output_dir: str):
        """Find representative image files in `output_dir`. Returns list or None."""
        try:
            exts = ["*.jpg", "*.jpeg", "*.png", "*.bmp", "*.tiff"]
            file_names = []
            for e in exts:
                file_names.extend(glob.glob(os.path.join(output_dir, e)))
            if file_names:
                file_names.sort()
                return file_names
        except Exception:
            pass
        return None

    def _process_results(self, results: tuple) -> None:
        """Process and save the results from analysis."""
        logger.info("Processing analysis results")
        try:
            # Check if we received the new format (3 values)
            # or the old format (13 values)
            if len(results) == 3:
                # New format: time, time_int, result_lists
                time, time_int, result_lists = results

                # Make sure all required fields exist in the dictionary
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
                    "area_diameter_px",
                    "area_diameter_mm",
                    "center_points_px",
                    "center_points_mm",
                    "contact_line_px",
                    "contact_line_mm",
                ]

                # Initialize missing fields with NaN values
                for field in required_fields:
                    if field not in result_lists or result_lists[field] is None:
                        result_lists[field] = [float("nan")] * len(time)

                # Extract values for processing
                advancing_contact_angles = result_lists["advancing_contact_angles"]
                receding_contact_angles = result_lists["receding_contact_angles"]
                rect_width_px = result_lists["rect_width_px"]
                rect_height_px = result_lists["rect_height_px"]
                rect_width_mm = result_lists["rect_width_mm"]
                rect_height_mm = result_lists["rect_height_mm"]
                velocity = result_lists["velocity"]
                center_points_px = result_lists["center_points_px"]
                center_points_mm = result_lists["center_points_mm"]

                # Store frame data for slider navigation stats
                self._store_frame_data(result_lists)
            else:
                # Original format with 13 values (legacy support)
                (
                    time,
                    time_int,
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

                # Create a result_lists dictionary for the save_results function
                result_lists = {
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
                    "contact_line_px": [float("nan")]
                    * len(time),  # Initialize if not available
                    "contact_line_mm": [float("nan")]
                    * len(time),  # Initialize if not available
                }

                # Store frame data for slider navigation stats (legacy format)
                self._store_frame_data(result_lists)

            # Ensure velocity exists (calculate if missing)
            self._ensure_velocity(result_lists, time, time_int)

            # If we have a folder path, save the results directly into it
            if self.controller.folder_path:
                output_dir = self.controller.folder_path
                logger.info(f"Saving results into folder: {output_dir}")

                # Build parameters dict and folder/file info
                parameters = self._build_save_parameters()
                folder_name = os.path.basename(output_dir or "")
                file_names = self._find_representative_file_names(output_dir)

                # If the user explicitly requested a stop/skip that should
                # prevent saving (set by _stop_processing),
                # do not save results for this run. Reset the flag after honoring it.
                if getattr(self, "_user_requested_stop_no_save", False):
                    logger.info(
                        "User requested stop — skipping saving results_raw.xlsx"
                    )
                    # Reset the flag so subsequent runs can save normally
                    self._user_requested_stop_no_save = False
                else:
                    save_results(
                        output_dir,
                        time,
                        result_lists,
                        parameters=parameters,
                        folder_name=folder_name,
                        file_names=file_names,
                    )
            else:
                logger.warning("No folder path available, results not saved")

        except ValueError as e:
            # Handle case where there's a mismatch in the number of return values
            logger.error(f"Failed to process results due to value error: {e}")
            pass
        except Exception as e:
            logger.error(f"Failed to process results: {e}")
            pass

        self.overall_progress.setValue(100)
        self.batch_progress.setValue(100)  # Sync batch progress

        # Reset folder counter after processing is done
        self.folder_counter.setText("0/0")
        logger.info("Analysis results processing completed")

    def _update_stats(
        self,
        q: float,
        advancing_contact_angles: list[float],
        receding_contact_angles: list[float],
        center_points_px: list[tuple[float, float]],
        result_images: dict[str, Any],
        result_lists: Optional[dict[str, Any]] = None,
    ) -> None:
        """Update UI with current processing results."""
        # Only update progress bars when NOT in preview mode
        if not self.is_in_preview_mode:
            # Update progress bar
            progress_value = int(q * 100)
            self.overall_progress.setValue(progress_value)
            # Note: batch_progress is only updated by folder completion

            # Update folder progress if we're analyzing a main folder
            self._update_folder_progress(q)

        # Update images and UI elements
        self._update_result_images(result_images)

        # Update statistics labels
        self._update_statistics_labels(
            advancing_contact_angles,
            receding_contact_angles,
            center_points_px,
            result_images,
            result_lists or {},
        )

        # Update stats overlay directly with real-time data during analysis
        self._update_overlay_from_realtime_data(
            advancing_contact_angles,
            receding_contact_angles,
            center_points_px,
            result_images,
            result_lists or {},
        )

    def _update_result_images(self, result_images: dict[str, Any]) -> None:
        """Update result images and internal preview image storage."""
        try:
            # Only store images if this is from the main analysis (not preview)
            is_main_analysis = (
                self.main_thread is not None and self.main_thread.isRunning()
            )

            # Result image with baseline, intersection points, and contact angles
            if "result" in result_images:
                # Display the result image
                self.display_image_in_canvas(
                    result_images["result"], self.canvas_result
                )
                # Only store if this is main analysis
                if is_main_analysis:
                    self.preview_images["result"].append(result_images["result"])
                    # Update slider state when new images are added
                    self._update_slider_state()

            # Update internal frame count only for main analysis
            if is_main_analysis:
                self.total_frames = len(self.preview_images["original"])

            # Force UI update
            QCoreApplication.processEvents()

        except Exception as e:
            logger.error(f"Failed to update UI: {e}")

    def _update_statistics_labels(
        self,
        advancing_contact_angles: list[float],
        receding_contact_angles: list[float],
        center_points_px: list[tuple[float, float]],
        result_images: dict[str, Any],
        result_lists: dict[str, Any],
    ) -> None:
        """Update all statistics labels with current values."""
        try:
            self._update_contact_angle_labels(
                advancing_contact_angles, receding_contact_angles
            )
            self._update_dimension_labels(result_images, result_lists)
            self._update_position_labels(center_points_px, result_images, result_lists)

        except Exception as e:
            logger.error(f"Failed to update statistics: {e}")

    def _update_contact_angle_labels(
        self,
        advancing_contact_angles: list[float],
        receding_contact_angles: list[float],
    ) -> None:
        """Update contact angle labels."""
        # Get the latest values
        latest_adv = (
            advancing_contact_angles[-1] if advancing_contact_angles else float("NaN")
        )
        latest_rec = (
            receding_contact_angles[-1] if receding_contact_angles else float("NaN")
        )

        # Update contact angle labels
        if hasattr(self, "overlay_adv_angle_label"):
            self.overlay_adv_angle_label.setText(
                f"Advancing angle    |  {latest_adv:.1f}°"
                if not np.isnan(latest_adv)
                else "Advancing angle    |  --°"
            )
        if hasattr(self, "overlay_rec_angle_label"):
            self.overlay_rec_angle_label.setText(
                f"Receding angle     |  {latest_rec:.1f}°"
                if not np.isnan(latest_rec)
                else "Receding angle     |  --°"
            )

        # Only show contact angle stats if they exist and mode allows it
        analysis_mode = getattr(self.controller, "analysis_mode", "")
        if (
            analysis_mode not in ["free_sedimentation", "structured_packing"]
            and hasattr(self, "overlay_adv_angle_label")
            and hasattr(self, "overlay_rec_angle_label")
        ):
            self.overlay_adv_angle_label.show()
            self.overlay_rec_angle_label.show()

    def _update_dimension_labels(
        self,
        result_images: dict[str, Any],
        result_lists: dict[str, Any],
    ) -> None:
        """Update width, height, and ellipse diameter labels."""
        # Dispatch to smaller helpers to reduce cyclomatic complexity
        if "rect_width_mm" in result_images and "rect_height_mm" in result_images:
            self._update_dimension_labels_from_result_images(result_images)
        elif (
            result_lists
            and "rect_width_mm" in result_lists
            and "rect_height_mm" in result_lists
        ):
            self._update_dimension_labels_from_result_lists(result_lists)
        else:
            self._set_dimension_labels_defaults()

    def _update_dimension_labels_from_result_images(
        self, result_images: dict[str, Any]
    ) -> None:
        """Update labels using values from the realtime `result_images` dict."""
        width_mm = result_images.get("rect_width_mm", float("nan"))
        height_mm = result_images.get("rect_height_mm", float("nan"))

        if hasattr(self, "overlay_contour_label"):
            width_str = f"{width_mm:.2f}" if not np.isnan(width_mm) else "--"
            height_str = f"{height_mm:.2f}" if not np.isnan(height_mm) else "--"
            self.overlay_contour_label.setText(
                f"Contour (W/H)      |  {width_str} mm/{height_str} mm"
            )

        if (
            not np.isnan(width_mm)
            and not np.isnan(height_mm)
            and width_mm > 0
            and height_mm > 0
        ):
            ellipse_diameter_mm = (width_mm * height_mm) ** 0.5
            if hasattr(self, "overlay_ellipse_diameter_label"):
                self.overlay_ellipse_diameter_label.setText(
                    f"Contour diameter   |  {ellipse_diameter_mm:.2f} mm"
                )
        else:
            if hasattr(self, "overlay_ellipse_diameter_label"):
                self.overlay_ellipse_diameter_label.setText(
                    "Contour diameter   |  -- mm"
                )

    def _update_dimension_labels_from_result_lists(
        self, result_lists: dict[str, Any]
    ) -> None:
        """Update labels using values from the `result_lists` fallback structure."""
        width_list = result_lists.get("rect_width_mm", [])
        height_list = result_lists.get("rect_height_mm", [])
        ellipse_diameter_list = result_lists.get("ellipse_diameter_mm", [])

        width_mm = (
            width_list[-1] if width_list and len(width_list) > 0 else float("nan")
        )
        height_mm = (
            height_list[-1] if height_list and len(height_list) > 0 else float("nan")
        )
        ellipse_diameter_mm = (
            ellipse_diameter_list[-1]
            if ellipse_diameter_list and len(ellipse_diameter_list) > 0
            else float("nan")
        )

        if hasattr(self, "overlay_contour_label"):
            width_str = f"{width_mm:.2f}" if not np.isnan(width_mm) else "--"
            height_str = f"{height_mm:.2f}" if not np.isnan(height_mm) else "--"
            self.overlay_contour_label.setText(
                f"Contour (W/H)      |  {width_str} mm/{height_str} mm"
            )

        if hasattr(self, "overlay_ellipse_diameter_label"):
            self.overlay_ellipse_diameter_label.setText(
                f"Contour diameter   |  {ellipse_diameter_mm:.2f} mm"
                if not np.isnan(ellipse_diameter_mm)
                else "Contour diameter   |  -- mm"
            )

    def _set_dimension_labels_defaults(self) -> None:
        """Set default text for dimension/ellipse labels when no data available."""
        if hasattr(self, "overlay_contour_label"):
            self.overlay_contour_label.setText("Contour (W/H)      |  -- mm/-- mm")
        if hasattr(self, "overlay_ellipse_diameter_label"):
            self.overlay_ellipse_diameter_label.setText("Contour diameter   |  -- mm")

    def _update_position_labels(
        self,
        center_points_px: list[tuple[float, float]],
        result_images: dict[str, Any],
        result_lists: Optional[dict[str, Any]] = None,
    ) -> None:
        """Update center position, velocity, and area diameter labels."""
        # Update center point and velocity if available
        # Note: Center position is shown visually on the image, no text label needed
        if center_points_px and len(center_points_px) > 0:
            # Center position display is handled visually, no text update needed
            pass

        if "velocity" in result_images:
            velocity = result_images["velocity"]
            if hasattr(self, "overlay_velocity_label"):
                self.overlay_velocity_label.setText(
                    f"Velocity           |  {velocity:.2f} mm/s"
                    if not np.isnan(velocity)
                    else "Velocity           |  -- mm/s"
                )

        # Update area diameter if available in result_images (real-time) or result_lists
        if "area_diameter_mm" in result_images:
            area_diameter_mm = result_images["area_diameter_mm"]
            if hasattr(self, "overlay_area_diameter_label"):
                self.overlay_area_diameter_label.setText(
                    f"Area diameter      |  {area_diameter_mm:.2f} mm"
                    if not np.isnan(area_diameter_mm)
                    else "Area diameter      |  -- mm"
                )
        elif result_lists and "area_diameter_mm" in result_lists:
            area_diameter_list = result_lists["area_diameter_mm"]
            area_diameter_mm = (
                area_diameter_list[-1]
                if area_diameter_list and len(area_diameter_list) > 0
                else float("nan")
            )
            if hasattr(self, "overlay_area_diameter_label"):
                self.overlay_area_diameter_label.setText(
                    f"Area diameter      |  {area_diameter_mm:.2f} mm"
                    if not np.isnan(area_diameter_mm)
                    else "Area diameter      |  -- mm"
                )
        else:
            if hasattr(self, "overlay_area_diameter_label"):
                self.overlay_area_diameter_label.setText("Area diameter      |  -- mm")

    def _update_folder_progress(self, progress: float) -> None:
        """Update progress for the currently analyzing folder."""
        # Find the main folder in the folder list and update its progress
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

    def add_folders_to_batch(self) -> None:
        """Add multiple folders to the batch processing queue."""
        logger.info("Opening folder selection dialog for batch processing")
        folder_dialog = QFileDialog()
        folder_dialog.setFileMode(QFileDialog.Directory)
        folder_dialog.setOption(QFileDialog.DontUseNativeDialog, True)

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
            self._process_selected_folders(folders)
        else:
            pass

    def _show_folder_detection_help(self):
        """Show help dialog explaining the folder detection."""
        from PySide6.QtWidgets import QMessageBox

        msg = QMessageBox(self)
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

    def _handle_dropped_folders(self, folder_paths: list[str]) -> None:
        """Handle folders dropped onto the drop zone."""
        logger.info(f"User dropped {len(folder_paths)} folders")
        self._process_selected_folders(folder_paths)

    def _validate_and_convert_paths(self, folders: list[str]) -> list[str]:
        """Validate folder paths and convert special characters if approved by user.

        Args:
        ----
            folders: List of folder paths to validate

        Returns:
        -------
            list[str]: List of validated/converted folder paths, or empty if cancelled

        """
        # Check which folders have special characters
        problematic_folders, valid_folders = self._categorize_folders(folders)

        # If no problematic folders, return all as-is
        if not problematic_folders:
            return folders

        # Check if user has already made a choice for "Apply to All"
        if self._apply_to_all_paths and self._path_validation_choice is not None:
            if self._path_validation_choice == "yes":
                # Create simple mappings and convert
                path_mappings = {
                    folder: normalize_path_for_ascii(folder)
                    for folder in problematic_folders
                }
                return self._convert_folder_paths(folders, path_mappings)
            else:
                # User previously chose "No" for all - skip these folders
                return []

        # Show validation dialog and get user choice
        dialog = PathValidationDialog(self)
        dialog.set_paths(problematic_folders)

        if dialog.exec() == QDialog.Accepted and dialog.user_choice == "yes":
            # Store user choice for future use (if/when an "apply to all"
            # option is added to the dialog). For now, only honor 'yes'.
            self._path_validation_choice = "yes"
            self._apply_to_all_paths = True

            return self._convert_folder_paths(folders, dialog.path_mappings)

        # User cancelled or declined conversion. Do NOT set
        # `_apply_to_all_paths` here so the dialog can reappear for future
        # folder selections. Return empty to indicate no converted paths.
        return []

    def _categorize_folders(self, folders: list[str]) -> tuple[list[str], list[str]]:
        """Categorize folders into problematic and valid ones."""
        problematic_folders = []
        valid_folders = []

        for folder in folders:
            try:
                folder.encode("ascii")
                valid_folders.append(folder)
            except UnicodeEncodeError:
                problematic_folders.append(folder)

        return problematic_folders, valid_folders

    def _convert_folder_paths(
        self, folders: list[str], path_mappings: dict
    ) -> list[str]:
        """Convert folder paths using the provided mappings."""
        converted_folders = []

        for folder in folders:
            if folder in path_mappings:
                converted_path = self._create_converted_directory(
                    folder, path_mappings[folder]
                )
                converted_folders.append(converted_path)
            else:
                converted_folders.append(folder)

        return converted_folders

    def _create_converted_directory(
        self, original_path: str, converted_path: str
    ) -> str:
        """Rename the directory and its contents to remove special characters."""
        try:
            # If paths are the same, no conversion needed
            if original_path == converted_path:
                return original_path

            # Check if converted path already exists
            if os.path.exists(converted_path):
                logger.warning(f"Converted path already exists: {converted_path}")
                return converted_path

            # First, rename all files and subdirectories within the folder
            self._rename_folder_contents(original_path)

            # Then rename the main folder
            os.rename(original_path, converted_path)
            logger.info(f"Renamed folder: {original_path} -> {converted_path}")
            return converted_path

        except Exception as e:
            logger.error(f"Failed to rename folder {original_path}: {e}")
            # Return original path if rename fails
            QMessageBox.warning(
                self,
                "Folder Rename Failed",
                f"Failed to rename folder:\n{original_path}\n\n"
                f"Using original path instead. Error: {e}",
            )
            return original_path

    def _rename_folder_contents(self, folder_path: str):
        """Recursively rename all files and subdirectories to remove special chars."""
        try:
            # Get all items in the folder
            items = os.listdir(folder_path)

            # Process files and subdirectories
            for item in items:
                original_item_path = os.path.join(folder_path, item)
                normalized_name = normalize_path_for_ascii(item)
                new_item_path = os.path.join(folder_path, normalized_name)

                # Only rename if the name actually changed
                if item != normalized_name and not os.path.exists(new_item_path):
                    try:
                        # If it's a directory, recursively rename its contents first
                        if os.path.isdir(original_item_path):
                            self._rename_folder_contents(original_item_path)

                        # Rename the item
                        os.rename(original_item_path, new_item_path)
                        logger.debug(f"Renamed: {item} -> {normalized_name}")

                    except Exception as e:
                        logger.warning(f"Failed to rename {original_item_path}: {e}")

                # If it's a subdirectory (whether renamed or not), process its contents
                current_path = (
                    new_item_path
                    if os.path.exists(new_item_path)
                    else original_item_path
                )
                if os.path.isdir(current_path):
                    self._rename_folder_contents(current_path)

        except Exception as e:
            logger.error(f"Failed to process folder contents in {folder_path}: {e}")

    def _find_data_folders(self, parent_folder: str) -> list[str]:
        """Find all subfolders containing data (images or videos).

        Criteria:
        - At least 3 image files (jpg, jpeg, png, bmp, tiff) OR
        - At least 1 video file (mp4, avi, mov, mkv, wmv)

        Args:
        ----
            parent_folder: Path to the parent folder to search

        Returns:
        -------
            list[str]: List of folder paths containing data

        """
        data_folders = []

        # Image extensions
        image_extensions = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif"}
        # Video extensions
        video_extensions = {".mp4", ".avi", ".mov", ".mkv", ".wmv", ".m4v", ".flv"}

        try:
            # Check if the parent folder itself contains data
            if self._folder_contains_data(
                parent_folder, image_extensions, video_extensions
            ):
                data_folders.append(parent_folder)

            # Walk through all subdirectories
            for root, _, _ in os.walk(parent_folder):
                # Skip the parent folder itself (already checked above)
                if root == parent_folder:
                    continue

                if self._folder_contains_data(root, image_extensions, video_extensions):
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

    def _folder_contains_data(
        self, folder_path: str, image_exts: set, video_exts: set
    ) -> bool:
        """Check if a folder contains sufficient data files.

        Args:
        ----
            folder_path: Path to check
            image_exts: Set of image file extensions
            video_exts: Set of video file extensions

        Returns:
        -------
            bool: True if folder contains at least 3 images or 1 video

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

    def _process_selected_folders(self, folders: list[str]):
        """Process selected folders, validating paths and adding to the list.

        Args:
        ----
            folders: List of folder paths selected by user

        """
        # Validate and convert initial paths
        validated_folders = self._validate_and_convert_paths(folders)
        if not validated_folders:
            return

        # Expand to data-containing subfolders (deduplicated)
        unique_data_folders = self._expand_to_data_folders(validated_folders)
        logger.info(f"Found {len(unique_data_folders)} unique data folders")

        # Validate the detected subfolders for special characters
        validated_data_folders = self._validate_and_convert_paths(unique_data_folders)
        if not validated_data_folders:
            return

        # Add validated data folders to the UI and controller
        self._add_folders_to_list(validated_data_folders)

    def _expand_to_data_folders(self, folders: list[str]) -> list[str]:
        """Return deduplicated list of data-containing folders from given roots."""
        all_data_folders = []
        for folder in folders:
            if os.path.isdir(folder):
                data_folders = self._find_data_folders(folder)
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

    def _add_folders_to_list(self, folders: list[str]) -> None:
        """Add folders to controller and folder_list widget, updating scanner."""
        for folder in folders:
            if not folder or folder in self.controller.folder_paths:
                continue
            self.controller.add_folder_path(folder)
            display_path = os.path.abspath(folder)
            item = QListWidgetItem(display_path)
            # Store absolute path in the item data so actions receive a usable path
            item.setData(Qt.UserRole, display_path)
            item.setToolTip(display_path)
            item.setSizeHint(QSize(300, 32))
            self.folder_list.addItem(item)

            # Immediately check this folder for results (fast feedback)
            # Defer checking this folder for results to avoid blocking
            QTimer.singleShot(0, lambda: self._scan_single_folder_results(display_path))

    def remove_selected_folders(self) -> None:
        """Remove selected folders from the batch list."""
        selected_items = self.folder_list.selectedItems()
        if not selected_items:
            return

        logger.info(f"Removing {len(selected_items)} folders from batch list")
        for item in selected_items:
            # Get the full path from item data instead of display text
            folder_path = item.data(Qt.UserRole)

            self.controller.remove_folder_path(folder_path)
            row = self.folder_list.row(item)
            self.folder_list.takeItem(row)

        # If the list became empty after removal, add the mode-specific test
        # folder so the user always has at least the example dataset available.
        try:
            if self.folder_list.count() == 0:
                mode = getattr(self.controller, "analysis_mode", "")
                test_map = {
                    "free_sedimentation": "tests/free_sedimentation (BuAc_d_large)",
                    "channel": "tests/channel (BuAc_d_large)",
                    "structured_packing": "tests/structured_packing (BuAc_d_large)",
                    "contact_angle": "tests/contact_wall (BuAc_d_large)",
                }
                rel = test_map.get(mode, "tests/contact_wall (BuAc_d_large)")
                default_test = os.path.abspath(rel)
                if os.path.isdir(default_test):
                    self._add_folders_to_list([default_test])
        except Exception:
            logger.exception("Failed to add default test folder after removals")

    def clear_folder_list(self) -> None:
        """Clear all folders from the batch list."""
        logger.info("Clearing all folders from batch list")
        self.controller.clear_folder_paths()
        self.folder_list.clear()
        self.folder_list.clear()
        # Clear stored presence info
        try:
            self.folder_delegate.clear_results_presence()
            if self._results_scanner_worker is not None:
                self._results_scanner_worker.set_folder_paths([])
        except Exception:
            pass
        # Also clear any main/current folder references so the UI does not
        # continue to show a 'last preview' folder when the list is empty.
        try:
            # Clear main folder and current folder path in controller
            if hasattr(self.controller, "set_main_folder_path"):
                self.controller.set_main_folder_path("")
            if hasattr(self.controller, "set_folder_path"):
                self.controller.set_folder_path("")
        except Exception:
            pass
        # Reset folder counter and preview images to reflect empty state
        try:
            self.folder_counter.setText("0/0")
            self.preview_images = {"original": [], "contour": [], "result": []}
            self.total_frames = 0
            # Reset image slider state
            self._update_slider_state()
            # Ensure main folder highlight is updated
            self._update_main_folder_highlight()
        except Exception:
            pass

        # If the list is empty after clearing, add the default test folder
        try:
            if hasattr(self, "folder_list") and self.folder_list.count() == 0:
                mode = getattr(self.controller, "analysis_mode", "")
                test_map = {
                    "free_sedimentation": "tests/free_sedimentation (BuAc_d_large)",
                    "channel": "tests/channel (BuAc_d_large)",
                    "structured_packing": "tests/structured_packing (BuAc_d_large)",
                    # fallback/default for contact_angle and others
                    "contact_angle": "tests/contact_wall (BuAc_d_large)",
                }
                rel = test_map.get(mode, "tests/contact_wall (BuAc_d_large)")
                default_test = os.path.abspath(rel)
                if os.path.isdir(default_test):
                    # Use existing helper to add folder and update UI
                    self._add_folders_to_list([default_test])
        except Exception:
            pass

    def _set_process_mode(self, mode: str) -> None:
        """Set the processing mode and update button text."""
        self.processing_mode = mode
        if mode == "undone":
            self.process_batch_btn.setText("Process Undone")
            self.process_batch_btn.setToolTip(
                "Process only folders that don't have results_raw.xlsx file"
            )
        else:  # mode == "all"
            self.process_batch_btn.setText("Process All")
            self.process_batch_btn.setToolTip(
                "Process all folders independent from done-status"
            )

        # Update dropdown button tooltip to show current mode
        self.mode_dropdown_btn.setToolTip(
            f"Current mode: {mode}. Click to change processing mode."
        )

        logger.info(f"Processing mode set to: {mode}")

    def process_selected_folders(self) -> None:
        """Process folders based on the selected mode (all or undone only)."""
        if self.processing_mode == "undone":
            self._process_undone_folders()
        else:  # mode == "all"
            self.process_all_folders()

    def _process_undone_folders(self) -> None:
        """Process only folders that don't have results_raw.xlsx file."""
        logger.info("Starting batch processing of undone folders only")
        # Check if already processing
        if self.is_processing:
            logger.warning("Processing already in progress, ignoring batch request")
            return

        # Get list of folders that don't have results_raw.xlsx
        undone_folders = []
        undone_indices = []

        for i in range(self.folder_list.count()):
            item = self.folder_list.item(i)
            folder_path = item.data(Qt.UserRole)

            # Check if results file exists
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

        # Start processing with filtered folder list
        self._start_batch_processing(undone_folders, undone_indices)

    def process_all_folders(self) -> None:
        """Process all folders in the batch list sequentially."""
        logger.info("Starting batch processing of all folders")
        # Check if already processing
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
            folder_path = item.data(Qt.UserRole)
            all_folders.append(folder_path)
            all_indices.append(i)

        logger.info(f"Starting batch processing of {len(all_folders)} folders")

        # Start processing with all folders
        self._start_batch_processing(all_folders, all_indices)

    def _start_batch_processing(self, folder_paths: list, folder_indices: list) -> None:
        """Start batch processing with the given folders and indices."""
        # Set processing flag
        self.is_processing = True

        # Reset progress for all folders in the list (not just the ones being processed)
        for i in range(self.folder_list.count()):
            self.folder_delegate.set_progress(i, 0)
            # Update each item individually instead of the whole list
            self.folder_list.update(self.folder_list.model().index(i, 0))

        # Reset overall progress
        self.overall_progress.setValue(0)
        self.folder_counter.setText(f"0/{len(folder_paths)}")

        # Disable UI buttons during processing
        #         self.process_batch_btn.setEnabled(False)
        #         self.add_folders_btn.setEnabled(False)
        #         self.analyze_button.setEnabled(False)

        # Enable pause/stop buttons and RESET the state of the pause button
        #         self.pause_resume_btn.setEnabled(True)
        self.pause_resume_btn.setIcon(
            QIcon.fromTheme("media-playback-pause", QIcon(":/icons/pause.png"))
        )
        self.pause_resume_btn.setToolTip("Pause processing")
        #         self.stop_btn.setEnabled(True)

        # Clear previous preview images
        self.preview_images = {"original": [], "contour": [], "result": []}
        self.total_frames = 0
        # Reset image slider state
        self._update_slider_state()

        # Create and start the batch processing thread with filtered folders
        self.batch_thread = QThread()
        self.batch_worker = BatchProcessingWorker(
            self.controller,
            folder_paths,  # Use filtered folder list
            self._update_batch_progress,
        )

        # Store the mapping of processing indices to UI indices for progress updates
        self.processing_to_ui_index_map = {
            processing_idx: ui_idx
            for processing_idx, ui_idx in enumerate(folder_indices)
        }

        self.batch_worker.moveToThread(self.batch_thread)
        self.batch_thread.started.connect(self.batch_worker.process_folders)
        self.batch_worker.progress_updated.connect(self._update_batch_progress)
        self.batch_worker.folder_completed.connect(self._on_folder_completed)
        self.batch_worker.overall_progress_updated.connect(
            self._update_overall_progress
        )
        self.batch_worker.all_completed.connect(self._on_batch_completed)
        self.batch_worker.error_occurred.connect(self._handle_batch_error)

        # Connect the new preview image signal to update our preview display
        self.batch_worker.preview_image_updated.connect(self._update_stats)

        self.batch_thread.start()

    def _update_batch_progress(self, folder_index, folder_path, progress_percent):
        """Update UI with batch processing progress."""
        # Map processing index to UI index
        ui_index = self.processing_to_ui_index_map.get(folder_index, folder_index)

        # Update progress bar for this folder
        self.folder_delegate.set_progress(ui_index, progress_percent)
        # Update the specific item rather than the whole list
        self.folder_list.update(self.folder_list.model().index(ui_index, 0))

    def _on_folder_completed(self, folder_index, folder_path, success):
        """Handle completion of a single folder in the batch."""
        # Map processing index to UI index
        ui_index = self.processing_to_ui_index_map.get(folder_index, folder_index)

        if success:
            # Set progress to 100% for success
            self.folder_delegate.set_progress(ui_index, 100)
        else:
            # For failure, set a specific value that can be styled differently
            self.folder_delegate.set_progress(
                ui_index, -1
            )  # Using -1 to indicate error

        # Update the specific item
        self.folder_list.update(self.folder_list.model().index(ui_index, 0))

    def _on_batch_completed(self):
        """Handle completion of the entire batch process."""
        # Reset processing flag
        self.is_processing = False

        # Re-enable UI buttons
        #         self.process_batch_btn.setEnabled(True)
        #         self.add_folders_btn.setEnabled(True)
        #         self.analyze_button.setEnabled(True)

        # Disable pause/stop buttons
        #         self.pause_resume_btn.setEnabled(False)
        #         self.stop_btn.setEnabled(False)

        # Reset the pause button state for next time
        self.pause_resume_btn.setIcon(
            QIcon.fromTheme("media-playback-pause", QIcon(":/icons/pause.png"))
        )
        self.pause_resume_btn.setToolTip("Pause processing")

        # Clean up thread
        self.batch_thread.quit()
        self.batch_thread.wait()

    def _handle_batch_error(self, folder_index, folder_path, error_msg):
        """Handle errors during batch processing."""
        logger.error(f"Batch processing error for folder {folder_path}: {error_msg}")
        # Mark as errored in the progress bar
        self.folder_delegate.set_progress(
            folder_index, -1
        )  # Using -1 to indicate error
        self.folder_list.repaint()

        # Reset the pause button state
        self.pause_resume_btn.setIcon(
            QIcon.fromTheme("media-playback-pause", QIcon(":/icons/pause.png"))
        )
        self.pause_resume_btn.setToolTip("Pause processing")

    def _update_folder_list(self, folder_paths):
        """Update the folder list widget when paths in controller change."""
        self.folder_list.clear()
        for path in folder_paths:
            # Display the absolute path and store the original full path as data
            display_path = os.path.abspath(path)
            item = QListWidgetItem(display_path)
            # Store the absolute path as data so actions like 'Open in Explorer'
            # get a valid filesystem path regardless of how it was added.
            item.setData(Qt.UserRole, display_path)
            item.setToolTip(display_path)
            # Set size hint for proper display of progress bars
            item.setSizeHint(QSize(300, 32))  # Fixed size for progress bars
            self.folder_list.addItem(item)

        # Reset progress data when updating the list
        self.folder_delegate.progress_data = {}

        # Reset results presence and defer scan to avoid blocking startup
        try:
            self.folder_delegate.clear_results_presence()
            # Defer the immediate scan to avoid blocking GUI creation
            QTimer.singleShot(100, self._immediate_scan_folder_results)
        except Exception:
            logger.exception("Error setting up folder results scanning during update")

        # Ensure main folder is highlighted
        self._update_main_folder_highlight()

        # If no main folder is selected but we have folders, set the first one
        if not self.controller.main_folder_path and folder_paths:
            self.controller.set_main_folder_path(folder_paths[0])
            self._update_main_folder_highlight()

        # Delay setting the horizontal scrollbar value to the right side
        # Use QCoreApplication.processEvents() to ensure we're in the main thread
        try:
            from PySide6.QtCore import QCoreApplication

            QCoreApplication.processEvents()
            if hasattr(self, "folder_list") and self.folder_list:
                QTimer.singleShot(
                    0,
                    lambda: (
                        self.folder_list.horizontalScrollBar().setValue(
                            self.folder_list.horizontalScrollBar().maximum()
                        )
                        if hasattr(self, "folder_list") and self.folder_list
                        else None
                    ),
                )
        except Exception:
            # If timer fails, set scroll position directly
            try:
                if hasattr(self, "folder_list") and self.folder_list:
                    self.folder_list.horizontalScrollBar().setValue(
                        self.folder_list.horizontalScrollBar().maximum()
                    )
            except Exception:
                pass

    def _update_stats_with_param(
        self,
        q,
        advancing_angles,
        receding_angles,
        center_points,
        result_images,
        result_lists,
        param_type,
    ):
        """Update stats while preserving the original parameter type."""
        # Temporarily save current param type
        current_param = self.last_changed_param

        # Don't override context_menu_preview parameter type
        if current_param != "context_menu_preview":
            # Set to the saved one from when preview was started
            self.last_changed_param = param_type

        # Call the regular update stats method
        self._update_stats(
            q,
            advancing_angles,
            receding_angles,
            center_points,
            result_images,
            result_lists,
        )

        # Restore the original in case it changed (unless it's context_menu_preview)
        if current_param != "context_menu_preview":
            self.last_changed_param = current_param

    def _update_overall_progress(self, current_folder, total_folders, progress_percent):
        """Update the batch progress bar based on folder progress."""
        # Calculate folder-based progress (current folder / total folders)
        if total_folders > 0:
            folder_progress = int((current_folder / total_folders) * 100)
            self.batch_progress.setValue(folder_progress)
        else:
            self.batch_progress.setValue(0)

        # Update the hidden folder counter for compatibility
        self.folder_counter.setText(f"{current_folder}/{total_folders}")

    def _show_folder_context_menu(self, position):
        """Show context menu for folder list."""
        menu = QMenu(self.folder_list)

        # Add the Preview and Start Analysis actions at the top of the menu
        selected_items = self.folder_list.selectedItems()
        if selected_items and len(selected_items) == 1:
            # Get the full path from the item's data
            full_path = selected_items[0].data(Qt.UserRole)

            # Create preview action with tooltip showing full path
            preview_action = menu.addAction("Preview")
            preview_action.setToolTip(full_path)
            preview_action.triggered.connect(
                lambda: self.preview_selected_folder(full_path)
            )

            # Create analyze action
            analyze_action = menu.addAction("Start Analysis")
            analyze_action.setToolTip(full_path)
            analyze_action.triggered.connect(
                lambda: self.analyze_selected_folder(full_path)
            )

            menu.addSeparator()

            # Add 'Open Folder' action for convenience (renamed from
            # 'Open in Explorer')
            open_action = menu.addAction("Open Folder")
            open_action.setToolTip(full_path)
            open_action.triggered.connect(
                lambda: self.open_folder_in_explorer(full_path)
            )

            # If this folder has results (results_raw.xlsx) add an action to
            # open the results directly. We prefer checking for the results
            # file existence to decide visibility.
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

    def _update_main_folder_highlight(self):
        """Update the highlighting of the main folder in the list."""
        main_path = self.controller.main_folder_path

        # Find the index of the main folder in the list
        for i in range(self.folder_list.count()):
            # Compare with the full path stored in data, not the display text
            if self.folder_list.item(i).data(Qt.UserRole) == main_path:
                break

        # Update the list display
        self.folder_list.viewport().update()

    def show_event(self, event):
        """Handle show event."""
        super().show_event(event)
        # Set horizontal scrollbar to maximum safely
        try:
            from PySide6.QtCore import QCoreApplication

            QCoreApplication.processEvents()
            if hasattr(self, "folder_list") and self.folder_list:
                QTimer.singleShot(
                    50,
                    lambda: (
                        self.folder_list.horizontalScrollBar().setValue(
                            self.folder_list.horizontalScrollBar().maximum()
                        )
                        if hasattr(self, "folder_list") and self.folder_list
                        else None
                    ),
                )
        except Exception:
            # If timer fails, set scroll position directly
            try:
                if hasattr(self, "folder_list") and self.folder_list:
                    self.folder_list.horizontalScrollBar().setValue(
                        self.folder_list.horizontalScrollBar().maximum()
                    )
            except Exception:
                pass

    def preview_selected_folder(self, folder_path: str) -> None:
        """Run preview on a specific folder and set it as the main folder."""
        # Check if already processing
        if self.is_processing:
            logger.warning("Processing already in progress, ignoring preview request")
            return

        # Set the selected folder as the main folder path
        self.controller.set_main_folder_path(folder_path)

        # Update the main folder highlight
        self._update_main_folder_highlight()

        # Set a special parameter for context menu preview
        # This will ensure we always display the contour image
        self.last_changed_param = "context_menu_preview"

        # Run preview
        self.preview()

    def analyze_selected_folder(self, folder_path: str) -> None:
        """Run analysis on a specific folder and set it as the main folder."""
        # Check if already processing
        if self.is_processing:
            return

        # Set the selected folder as the main folder path
        self.controller.set_main_folder_path(folder_path)

        # Update the main folder highlight
        self._update_main_folder_highlight()

        # Run analysis
        self.main()

    def open_folder_in_explorer(self, folder_path: str) -> None:
        """Open the given folder in the system file explorer."""
        import subprocess

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
        """Open the results file (`results_raw.xlsx`) in the system default app."""
        import subprocess

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

    def _update_roi_ranges_from_image(self):
        """Update ROI spinbox ranges based on the rotated image dimensions."""
        # Check if we have a valid folder path
        if not self.controller.folder_path or not os.path.isdir(
            self.controller.folder_path
        ):
            # If no folder, use default large ranges
            self._set_default_roi_ranges()
            return

        # Find all images in the folder
        image_extensions = ["*.jpg", "*.jpeg", "*.png", "*.bmp", "*.tiff"]
        image_files = []
        for ext in image_extensions:
            image_files.extend(
                glob.glob(os.path.join(self.controller.folder_path, ext))
            )

        if not image_files:
            # If no images, use default large ranges
            self._set_default_roi_ranges()
            return

        # Sort files and get the middle one
        image_files.sort()
        middle_idx = len(image_files) // 2
        middle_image = image_files[middle_idx]

        # Get rotation angle from controller
        rotation_angle = (
            self.controller.rotate_angle
            if hasattr(self.controller, "rotate_angle")
            else 0.0
        )

        # Load and rotate the image to get its size
        # Load image and attempt rotation; handle failures gracefully
        orig_img = cv2.imread(middle_image)
        temp_roi_image = rotate_image(orig_img, rotation_angle)
        if temp_roi_image is None:
            logger.error(f"Failed to load/rotate image for ROI ranges: {middle_image}")
            # Use default ranges instead of crashing
            self._set_default_roi_ranges()
            return

        # Block signals to prevent triggering valueChanged when range changes
        self.left_roi_spinbox.blockSignals(True)
        self.right_roi_spinbox.blockSignals(True)
        self.top_roi_spinbox.blockSignals(True)
        self.bottom_roi_spinbox.blockSignals(True)

        # Set ranges based on rotated image dimensions
        self.left_roi_spinbox.setRange(0, temp_roi_image.shape[1] - 1)
        self.right_roi_spinbox.setRange(1, temp_roi_image.shape[1])
        self.top_roi_spinbox.setRange(0, temp_roi_image.shape[0] - 1)
        self.bottom_roi_spinbox.setRange(1, temp_roi_image.shape[0])

        # Clamp current values to new bounds if necessary
        current_left = self.left_roi_spinbox.value()
        current_right = self.right_roi_spinbox.value()
        current_top = self.top_roi_spinbox.value()
        current_bottom = self.bottom_roi_spinbox.value()

        clamped_left = min(max(current_left, 0), temp_roi_image.shape[1] - 1)
        clamped_right = min(max(current_right, 1), temp_roi_image.shape[1])
        clamped_top = min(max(current_top, 0), temp_roi_image.shape[0] - 1)
        clamped_bottom = min(max(current_bottom, 1), temp_roi_image.shape[0])

        # Update values if they were clamped
        if clamped_left != current_left:
            self.left_roi_spinbox.setValue(clamped_left)
            self.controller.set_x_img(clamped_left)
        if clamped_right != current_right:
            self.right_roi_spinbox.setValue(clamped_right)
            self.controller.set_w_img(clamped_right)
        if clamped_top != current_top:
            self.top_roi_spinbox.setValue(clamped_top)
            self.controller.set_y_img(clamped_top)
        if clamped_bottom != current_bottom:
            self.bottom_roi_spinbox.setValue(clamped_bottom)
            self.controller.set_h_img(clamped_bottom)

        # Re-enable signals
        self.left_roi_spinbox.blockSignals(False)
        self.right_roi_spinbox.blockSignals(False)
        self.top_roi_spinbox.blockSignals(False)
        self.bottom_roi_spinbox.blockSignals(False)

    def _update_existing_scanner(self):
        """Update the existing scanner with current folder paths."""
        try:
            paths = [
                self.folder_list.item(i).data(Qt.UserRole)
                for i in range(self.folder_list.count())
            ]
            self._results_scanner_worker.set_folder_paths(paths)
        except Exception:
            pass

    def _get_folder_paths_for_scanner(self):
        """Get folder paths for scanner initialization."""
        try:
            return [
                self.folder_list.item(i).data(Qt.UserRole)
                for i in range(self.folder_list.count())
            ]
        except Exception:
            return []

    def _immediate_scan_folder_results(self):
        """Immediately scan all folders for results files (synchronous)."""
        try:
            for i in range(self.folder_list.count()):
                item = self.folder_list.item(i)
                if item:
                    folder_path = item.data(Qt.UserRole)
                    if folder_path and isinstance(folder_path, str):
                        try:
                            results_file = os.path.join(folder_path, "results_raw.xlsx")
                            has_results = (
                                os.path.exists(folder_path)
                                and os.path.isdir(folder_path)
                                and os.path.exists(results_file)
                            )
                            self.folder_delegate.set_results_presence(i, has_results)
                            # Update each item individually
                            if hasattr(self, "folder_list") and self.folder_list:
                                self.folder_list.update(
                                    self.folder_list.model().index(i, 0)
                                )
                        except (OSError, PermissionError, FileNotFoundError):
                            self.folder_delegate.set_results_presence(i, False)
                        except Exception:
                            self.folder_delegate.set_results_presence(i, False)

        except Exception as e:
            logger.error(f"Failed to scan folder results immediately: {e}")

    def _scan_single_folder_results(self, folder_path: str):
        """Scan a single folder for results (for deferred scanning)."""
        try:
            # Find the index of this folder in the list
            folder_index = None
            for i in range(self.folder_list.count()):
                item = self.folder_list.item(i)
                if item and item.data(Qt.UserRole) == folder_path:
                    folder_index = i
                    break

            if folder_index is not None:
                results_file = os.path.join(folder_path, "results_raw.xlsx")
                has_results = (
                    os.path.exists(folder_path)
                    and os.path.isdir(folder_path)
                    and os.path.exists(results_file)
                )
                self.folder_delegate.set_results_presence(folder_index, has_results)
                # Update the item
                if hasattr(self, "folder_list") and self.folder_list:
                    self.folder_list.update(
                        self.folder_list.model().index(folder_index, 0)
                    )

                # Update scanner worker if it exists
                if self._results_scanner_worker is not None:
                    paths = [
                        self.folder_list.item(i).data(Qt.UserRole)
                        for i in range(self.folder_list.count())
                    ]
                    self._results_scanner_worker.set_folder_paths(paths)
        except Exception:
            pass

    def _create_scan_result_callback(self):
        """Create callback function for scan results.

        The returned callback safely locates the current list item matching
        a scanned `folder_path` and updates the delegate. This avoids using
        stale indices when the user adds/removes folders while the scanner
        is running.
        """

        # Keep callback minimal by delegating to class helper methods below.
        def _on_scan_result(idx, folder_path, has):
            # If delegate is missing there's nothing to do
            if not getattr(self, "folder_delegate", None):
                return

            list_widget = getattr(self, "folder_list", None)

            # If list widget is missing, try to update delegate directly and return
            if list_widget is None:
                try:
                    delegate = getattr(self, "folder_delegate", None)
                    if delegate is not None and hasattr(
                        delegate, "set_results_presence"
                    ):
                        delegate.set_results_presence(idx, has)
                    else:
                        logger.debug(
                            "No folder_list and no usable folder_delegate to update for"
                        )
                except Exception:
                    logger.exception(
                        "Failed to update folder_delegate directly for index %s",
                        idx,
                    )
                return

            target_index = self._find_list_index_by_path(list_widget, folder_path)
            if target_index is None:
                return

            self._update_delegate_and_refresh(
                list_widget, target_index, has, folder_path
            )

        return _on_scan_result

    def _find_list_index_by_path(self, list_widget, folder_path):
        """Return the list index whose `Qt.UserRole` equals `folder_path`.

        Returns `None` if not found. Skips items that raise when accessed.
        """
        # Defensive search: iterate and compare stored Qt.UserRole data
        if list_widget is None:
            return None

        try:
            count = list_widget.count()
        except Exception:
            logger.exception("Failed to get count from folder_list")
            return None

        for i in range(count):
            try:
                item = list_widget.item(i)
                if item is None:
                    continue
                data = item.data(Qt.UserRole)
                if data == folder_path:
                    return i
            except Exception:
                logger.debug(
                    "Skipping list item while scanning for path: %s",
                    folder_path,
                )
                continue

        return None

    def _update_delegate_and_refresh(self, list_widget, target_index, has, folder_path):
        """Set results presence on delegate and refresh the list item if possible."""
        try:
            if getattr(self, "folder_delegate", None) is not None:
                self.folder_delegate.set_results_presence(target_index, has)
        except Exception:
            logger.exception(
                "Failed to set results presence for index %s",
                target_index,
            )

        try:
            if list_widget is None:
                logger.debug("No folder_list available to refresh for path")
                return
            model = list_widget.model()
            if model is None:
                logger.debug("Folder list model is None, cannot update item")
                return
            idx = model.index(target_index, 0)
            if idx.isValid():
                list_widget.update(idx)
            else:
                logger.debug("Model index invalid for target index")
        except Exception:
            logger.exception("Unexpected error while updating list widget for path")

    def _start_results_scanner(self):
        """Start a background `ResultsScannerWorker` in its own QThread."""
        # If worker is already running, just update its folder paths
        if self._results_scanner_worker is not None:
            self._update_existing_scanner()
            return

        try:
            from src.helpers.batch import ResultsScannerWorker

            self._results_scanner_thread = QThread(self)
            # Use longer interval (5 seconds) to reduce system load
            self._results_scanner_worker = ResultsScannerWorker(interval_ms=5000)

            paths = self._get_folder_paths_for_scanner()
            self._results_scanner_worker.set_folder_paths(paths)

            self._results_scanner_worker.moveToThread(self._results_scanner_thread)
            self._results_scanner_thread.started.connect(
                self._results_scanner_worker.start_scanning
            )
            self._results_scanner_worker.finished.connect(
                self._results_scanner_thread.quit
            )
            # Ensure thread is cleaned up after finishing
            self._results_scanner_thread.finished.connect(
                self._results_scanner_thread.deleteLater
            )

            scan_callback = self._create_scan_result_callback()
            self._results_scanner_worker.scan_result.connect(scan_callback)

            self._results_scanner_thread.start()
            logger.debug("Background results scanner started successfully")

        except Exception as e:
            logger.error(f"Failed to start background results scanner: {e}")
            # Clean up if initialization failed
            self._results_scanner_thread = None
            self._results_scanner_worker = None

    def _stop_results_scanner(self):
        """Stop the background results scanner if it exists."""
        try:
            if self._results_scanner_worker is not None:
                logger.debug("Stopping background results scanner...")
                self._results_scanner_worker.stop()

            if self._results_scanner_thread is not None:
                self._results_scanner_thread.quit()
                # Use shorter timeout to avoid blocking UI
                if not self._results_scanner_thread.wait(500):  # 500ms max
                    logger.warning("Results scanner thread did not stop gracefully")
                    # Don't call terminate() - just continue cleanup

                # Clean up references
                self._results_scanner_thread = None
                self._results_scanner_worker = None
                logger.debug("Background results scanner stopped successfully")

        except Exception as e:
            logger.error(f"Failed to stop results scanner: {e}")
            # Force cleanup even if there was an error
            self._results_scanner_thread = None
            self._results_scanner_worker = None

    def cleanup_all_threads(self):
        """Clean up all threads associated with this AnalysisGUI."""
        logger.debug("Starting AnalysisGUI thread cleanup")
        try:
            # Stop results scanner
            self._stop_results_scanner()

            # Stop main analysis thread
            if hasattr(self, "main_thread") and self.main_thread:
                self.main_thread.stop()
                if not self.main_thread.wait(1000):
                    logger.warning("Main thread did not stop gracefully")

            # Stop preview thread
            if hasattr(self, "preview_thread") and self.preview_thread:
                self.preview_thread.stop()
                if not self.preview_thread.wait(1000):
                    logger.warning("Preview thread did not stop gracefully")

            # Stop batch processing thread
            if hasattr(self, "batch_thread") and self.batch_thread:
                if hasattr(self, "batch_worker"):
                    self.batch_worker.stop()
                self.batch_thread.quit()
                if not self.batch_thread.wait(1000):
                    logger.warning("Batch thread did not stop gracefully")

            logger.debug("AnalysisGUI thread cleanup completed")
        except Exception as e:
            logger.error(f"Error during AnalysisGUI thread cleanup: {e}")

    def closeEvent(self, event):  # noqa: N802 - Qt requires closeEvent signature
        """Ensure scanner thread is stopped when widget is closed."""
        try:
            # Attempt comprehensive thread cleanup
            self.cleanup_all_threads()
        except Exception as e:
            logger.exception("Error stopping threads during closeEvent: %s", e)

        # Accept the event and call parent implementation
        if event:
            event.accept()
        return super().closeEvent(event)

    def _set_default_roi_ranges(self):
        """Set default large ranges for ROI spinboxes."""
        # Block signals to prevent triggering valueChanged when range changes
        self.left_roi_spinbox.blockSignals(True)
        self.right_roi_spinbox.blockSignals(True)
        self.top_roi_spinbox.blockSignals(True)
        self.bottom_roi_spinbox.blockSignals(True)

        # Set default large ranges
        self.left_roi_spinbox.setRange(0, 9999)
        self.right_roi_spinbox.setRange(1, 10000)
        self.top_roi_spinbox.setRange(0, 9999)
        self.bottom_roi_spinbox.setRange(1, 10000)

        # Re-enable signals
        self.left_roi_spinbox.blockSignals(False)
        self.right_roi_spinbox.blockSignals(False)
        self.top_roi_spinbox.blockSignals(False)
        self.bottom_roi_spinbox.blockSignals(False)
