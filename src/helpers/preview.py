"""Preview utilities.

For displaying images and analysis results 
in Droplet Wall Interaction Tool (DWIT).
"""

import cv2
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QApplication, QDialog, QLabel, QVBoxLayout

from src.utilities.logging_manager import get_logger

_preview_dialog = None
_preview_timer = None

# Opacity for the floating preview dialog (0.0 fully transparent, 1.0 opaque)
# Reduced from 0.8 to 0.55 to make it more see-through per user request.
PREVIEW_DIALOG_OPACITY = 0.8


# Setup logger for this module
logger = get_logger(__name__)


def _convert_to_pixmap(image):
    """Convert numpy array to QPixmap.

    Args:
    ----
        image: Image as numpy array

    Returns:
    -------
        QPixmap object

    """
    # Convert to pixmap
    arr = image
    # Convert grayscale to RGB
    if len(arr.shape) == 2:
        arr = cv2.cvtColor(arr, cv2.COLOR_GRAY2RGB)
    elif arr.shape[2] == 4:
        arr = cv2.cvtColor(arr, cv2.COLOR_BGRA2RGB)
    elif arr.shape[2] == 3:
        arr = cv2.cvtColor(arr, cv2.COLOR_BGR2RGB)

    h, w, ch = arr.shape
    bytes_per_line = ch * w
    qimg = QImage(arr.data, w, h, bytes_per_line, QImage.Format_RGB888)
    return QPixmap.fromImage(qimg)


def _get_target_screen(parent):
    """Get the screen where the preview should be displayed.

    Args:
    ----
        parent: Parent widget

    Returns:
    -------
        Tuple of (screen, screen_geometry)

    """
    if parent is not None and hasattr(parent, "window"):
        parent_window = parent.window()
    else:
        parent_window = parent

    if parent_window is not None and hasattr(parent_window, "screen"):
        screen = parent_window.screen()
    else:
        screen = QApplication.primaryScreen()

    screen_geometry = screen.availableGeometry() if screen else None
    if screen_geometry is None:
        # Fallback
        logger.warning("Could not get screen geometry, using fallback values")
        screen_width, screen_height = 1920, 1080
        return None, (screen_width, screen_height)
    else:
        screen_width = screen_geometry.width()
        screen_height = screen_geometry.height()
        return screen, screen_geometry


def _calculate_scaled_pixmap(pixmap, screen_geometry):
    """Calculate and create scaled pixmap.

    Args:
    ----
        pixmap: Original QPixmap
        screen_geometry: Screen geometry object or tuple of (width, height)

    Returns:
    -------
        Scaled QPixmap

    """
    # Get screen dimensions
    if isinstance(screen_geometry, tuple):
        screen_width, screen_height = screen_geometry
    else:
        screen_width = screen_geometry.width()
        screen_height = screen_geometry.height()

    # Calculate target size
    img_width = pixmap.width()
    img_height = pixmap.height()
    scale_w = screen_width * 0.9 / img_width
    scale_h = screen_height * 0.9 / img_height
    scale = min(scale_w, scale_h)
    target_width = int(img_width * scale)
    target_height = int(img_height * scale)

    return pixmap.scaled(
        target_width, target_height, Qt.KeepAspectRatio, Qt.SmoothTransformation
    )


def _update_existing_dialog(scaled_pixmap, screen_geometry):
    """Update existing preview dialog.

    Args:
    ----
        scaled_pixmap: Scaled QPixmap to display
        screen_geometry: Screen geometry object or tuple

    Returns:
    -------
        None

    """
    global _preview_dialog
    # Update label pixmap and resize instantly
    label = _preview_dialog.findChild(QLabel)
    if label:
        label.setPixmap(scaled_pixmap)

    _preview_dialog.setFixedSize(scaled_pixmap.width(), scaled_pixmap.height())

    # Center dialog on screen
    if not isinstance(screen_geometry, tuple):
        screen_width = screen_geometry.width()
        screen_height = screen_geometry.height()
        x = screen_geometry.left() + (screen_width - _preview_dialog.width()) // 2
        y = screen_geometry.top() + (screen_height - _preview_dialog.height()) // 2
        _preview_dialog.move(x, y)

    if not _preview_dialog.isVisible():
        _preview_dialog.show()


def _create_new_dialog(scaled_pixmap, parent, screen_geometry):
    """Create new preview dialog.

    Args:
    ----
        scaled_pixmap: Scaled QPixmap to display
        parent: Parent widget
        screen_geometry: Screen geometry object or tuple

    Returns:
    -------
        None

    """
    global _preview_dialog

    logger.info("Creating new preview dialog")
    _preview_dialog = QDialog(parent)
    _preview_dialog.setWindowTitle("Preview")
    _preview_dialog.setWindowFlags(
        Qt.Tool
        | Qt.FramelessWindowHint
        | Qt.WindowStaysOnTopHint
        | Qt.WindowTransparentForInput
        | Qt.WindowDoesNotAcceptFocus
    )
    _preview_dialog.setWindowOpacity(PREVIEW_DIALOG_OPACITY)
    label = QLabel(_preview_dialog)
    label.setPixmap(scaled_pixmap)
    label.setAlignment(Qt.AlignCenter)
    label.setStyleSheet("background: transparent;")
    layout = QVBoxLayout(_preview_dialog)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(label)
    _preview_dialog.setFixedSize(scaled_pixmap.width(), scaled_pixmap.height())

    # Center dialog on screen
    if not isinstance(screen_geometry, tuple):
        screen_width = screen_geometry.width()
        screen_height = screen_geometry.height()
        x = screen_geometry.left() + (screen_width - _preview_dialog.width()) // 2
        y = screen_geometry.top() + (screen_height - _preview_dialog.height()) // 2
        _preview_dialog.move(x, y)

    _preview_dialog.show()
    logger.info("New preview dialog created and shown")


def _setup_auto_close_timer():
    """Set up timer for auto-closing the preview.

    Returns
    -------
        None

    """
    global _preview_timer

    # Use a single timer to auto-close after 3s, restarting on every update
    if _preview_timer is None:
        _preview_timer = QTimer()
        _preview_timer.setSingleShot(True)

        def close_dialog():
            global _preview_dialog
            if _preview_dialog is not None:
                _preview_dialog.close()

        _preview_timer.timeout.connect(close_dialog)

    _preview_timer.stop()
    _preview_timer.start(3000)


def show_preview(image, parent):
    """Show a click-through, see-through preview of the given image.

    Displays QPixmap, QImage, or numpy array on the same monitor as the parent widget.

    The preview is centered and the longest side is 50% of the corresponding
    monitor side. The preview auto-closes after 3 seconds, but is instantly
    updated if a new image is pushed.
    """
    global _preview_dialog, _preview_timer

    if image is None:
        logger.warning("show_preview called with None image")
        return

    # Step 1: Convert the image to a pixmap
    pixmap = _convert_to_pixmap(image)

    # Step 2: Get the target screen
    screen, screen_geometry = _get_target_screen(parent)

    # Step 3: Calculate the scaled pixmap
    scaled_pixmap = _calculate_scaled_pixmap(pixmap, screen_geometry)

    # Step 4: Create or update the preview dialog
    if _preview_dialog is not None:
        _update_existing_dialog(scaled_pixmap, screen_geometry)
    else:
        _create_new_dialog(scaled_pixmap, parent, screen_geometry)

    # Step 5: Setup the auto-close timer
    _setup_auto_close_timer()
