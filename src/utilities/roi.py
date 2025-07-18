"""ROI selection and manipulation utilities for image analysis in MesszelleApp."""

import cv2
from PySide6.QtCore import QRect, Qt, Signal
from PySide6.QtGui import QColor, QCursor, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QDialog, QLabel, QVBoxLayout

from src.utilities.image import rotate_image
from src.utilities.logging_manager import get_logger

# Setup logger for this module
logger = get_logger(__name__)


class ROISelector(QDialog):
    """Dialog for selecting a region of interest on an image."""

    # Signal to emit when selection is confirmed with the coordinates
    roi_selected = Signal(int, int, int, int)  # Left, Top, Right, Bottom

    def __init__(self, parent=None, image_path=None, rotation_angle=0.0):
        """Initialize the ROISelector dialog."""
        super().__init__(parent)

        # Set up window properties like PreviewDialog
        self.setWindowTitle("Select Region of Interest")
        self.setWindowFlags(
            Qt.Tool  # Makes it a tool window (minimal decoration)
            | Qt.FramelessWindowHint  # Remove window frame
            | Qt.WindowStaysOnTopHint  # Keep on top
        )

        # Make the dialog opaque and fully interactive (not click-through)
        self.setWindowOpacity(1.0)

        # Store parameters
        self.image_path = image_path
        self.rotation_angle = rotation_angle
        self.original_image = None
        self.rotated_image = None

        # Initialize selection rectangle
        self.current_selection = None

        # Setup minimal UI like PreviewDialog
        self.setup_ui()

        # Load and process image
        if image_path:
            logger.info(f"Loading and rotating image for ROI selection: {image_path}")
            self.load_and_rotate_image()
        else:
            logger.warning(
                "No image path provided, ROISelector initialized without image"
            )

    def _install_label_mouse_events(self):
        """Install mouse event handlers for drag-and-drop ROI selection."""
        self._drag_start = None
        self._drag_current = None
        self.image_label.mousePressEvent = self._label_mouse_press_event
        self.image_label.mouseMoveEvent = self._label_mouse_move_event
        self.image_label.mouseReleaseEvent = self._label_mouse_release_event

    def _label_mouse_press_event(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_start = event.pos()
            self._drag_current = event.pos()
            self._dragging = True
        event.accept()

    def _label_mouse_move_event(self, event):
        if hasattr(self, "_dragging") and self._dragging and self._drag_start:
            self._drag_current = event.pos()
            # Update current_selection as QRect
            x1, y1 = self._drag_start.x(), self._drag_start.y()
            x2, y2 = self._drag_current.x(), self._drag_current.y()
            left, right = sorted([x1, x2])
            top, bottom = sorted([y1, y2])
            self.current_selection = QRect(left, top, right - left, bottom - top)
            self.update_display()
        event.accept()

    def _label_mouse_release_event(self, event):
        if hasattr(self, "_dragging") and self._dragging and self._drag_start:
            self._drag_current = event.pos()
            x1, y1 = self._drag_start.x(), self._drag_start.y()
            x2, y2 = self._drag_current.x(), self._drag_current.y()
            left, right = sorted([x1, x2])
            top, bottom = sorted([y1, y2])
            self.current_selection = QRect(left, top, right - left, bottom - top)
            self.update_display()
            self._dragging = False
        event.accept()

    def eventFilter(self, obj, event):  # noqa: N802
        """Intercept mouse events on the image label to handle button clicks."""
        from PySide6.QtCore import QEvent

        if obj == self.image_label and event.type() == QEvent.MouseButtonRelease:
            pos = event.pos()
            label_size = self.image_label.size()
            button_y = label_size.height() - 50
            button_spacing = 20
            total_button_width = 100 + 140 + button_spacing
            start_x = (label_size.width() - total_button_width) // 2
            cancel_rect = QRect(start_x, button_y, 100, 30)
            confirm_rect = QRect(start_x + 100 + button_spacing, button_y, 140, 30)
            if cancel_rect.contains(pos):
                self.reject()  # Close dialog as cancel
                return True
            if confirm_rect.contains(pos):
                # If no ROI selected, emit full image or default
                if self.current_selection:
                    # Convert display coordinates back to image coordinates
                    left, top, width, height = self.current_selection.getRect()
                    # Reverse the scaling and centering math
                    display_width = self.image_label.width() - 4
                    display_height = self.image_label.height() - 4
                    img_h, img_w = self.rotated_image.shape[:2]
                    scale_x = display_width / img_w
                    scale_y = display_height / img_h
                    scale = min(scale_x, scale_y)
                    scaled_width = int(img_w * scale)
                    scaled_height = int(img_h * scale)
                    center_x = (display_width - scaled_width) // 2 + 2
                    center_y = (display_height - scaled_height) // 2 + 2
                    img_left = int((left - center_x) / scale)
                    img_top = int((top - center_y) / scale)
                    img_right = int((left + width - center_x) / scale)
                    img_bottom = int((top + height - center_y) / scale)
                else:
                    # No selection, use full image
                    img_left, img_top = 0, 0
                    img_right = self.rotated_image.shape[1]
                    img_bottom = self.rotated_image.shape[0]
                self.roi_selected.emit(img_left, img_top, img_right, img_bottom)
                self.accept()
                return True
            # If not clicking a button, do not consume the event
            return False
        return super().eventFilter(obj, event)

    def set_roi(self, left, top, right, bottom):
        """Set the ROI selection rectangle in image coordinates and update display."""
        if self.rotated_image is None:
            logger.warning("Cannot set ROI: no rotated image available")
            return

        try:
            # Get image dimensions
            height, width = self.rotated_image.shape[:2]

            # Calculate scale factor used for display
            display_width = self.image_label.width() - 4  # Account for 2px border
            display_height = self.image_label.height() - 4

            # Calculate scaling to fit image in label while maintaining aspect ratio
            scale_x = display_width / width
            scale_y = display_height / height
            scale = min(scale_x, scale_y)

            # Calculate actual display size
            scaled_width = int(width * scale)
            scaled_height = int(height * scale)

            # Calculate centering offsets
            center_x = (display_width - scaled_width) // 2 + 2  # +2 for border
            center_y = (display_height - scaled_height) // 2 + 2

            # Convert from image coordinates to display coordinates
            display_left = int(left * scale) + center_x
            display_top = int(top * scale) + center_y
            display_right = int(right * scale) + center_x
            display_bottom = int(bottom * scale) + center_y

            # Create selection rectangle in display coordinates
            self.current_selection = QRect(
                display_left,
                display_top,
                display_right - display_left,
                display_bottom - display_top,
            )

            logger.info(
                f"ROI set successfully in display coordinates: "
                f"x={display_left}, y={display_top}, "
                f"w={display_right - display_left}, h={display_bottom - display_top}"
            )
            self.update_display()

        except Exception as e:
            logger.error(f"Error setting ROI: {e}")
            self.current_selection = None

    def setup_ui(self):
        """Set up the minimal user interface like PreviewDialog."""
        # Create layout with minimal margins (2-pixel frame)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)  # 2-pixel frame
        layout.setSpacing(0)

        # Image display label with 2-pixel border
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setStyleSheet(
            """
            QLabel {
                border: 2px solid #666666;
                background-color: transparent;
            }
        """
        )
        self.image_label.setScaledContents(False)  # We'll handle scaling manually
        self.image_label.setMouseTracking(True)
        self.image_label.setCursor(QCursor(Qt.CrossCursor))
        self.image_label.installEventFilter(self)

        self._install_label_mouse_events()

        layout.addWidget(self.image_label)

        # Set initial size - will be updated when image loads
        self.setFixedSize(100, 100)

    def load_and_rotate_image(self):
        """Load the image, apply rotation, and auto-size the dialog."""
        try:
            # Load the original image
            self.original_image = cv2.imread(self.image_path)
            if self.original_image is None:
                logger.error(f"Failed to load image from path: {self.image_path}")
                return

            # Apply rotation using the same logic as PreviewDialog
            self.rotated_image = rotate_image(self.original_image, self.rotation_angle)

            # Get rotated image dimensions
            rot_height, rot_width = self.rotated_image.shape[:2]
            logger.info(
                f"Image rotated by {self.rotation_angle}°: {rot_width}x{rot_height}"
            )

            # Auto-size the dialog to fit the image
            self.auto_size_dialog()

            # Update the display
            self.update_display()

        except Exception as e:
            logger.error(f"Error loading and rotating image: {e}")

    def auto_size_dialog(self):
        """Auto-size dialog with responsive layout based on monitor dimensions.

        Scales image to 90% of the monitor's corresponding side.
        """
        if self.rotated_image is None:
            return
        try:
            height, width = self.rotated_image.shape[:2]

            # Get screen geometry
            if hasattr(self, "parent") and self.parent():
                screen = (
                    self.parent().screen() if hasattr(self.parent(), "screen") else None
                )
            else:
                screen = QApplication.primaryScreen()

            if screen:
                screen_geometry = screen.availableGeometry()
                screen_width = screen_geometry.width()
                screen_height = screen_geometry.height()
            else:
                screen_width, screen_height = 1920, 1080  # Fallback

            # Calculate scale so that the image side most likely to touch
            # the monitor covers 90% of the corresponding monitor side
            scale_w = screen_width * 0.9 / width
            scale_h = screen_height * 0.9 / height
            scale_factor = min(scale_w, scale_h)

            # Calculate display dimensions maintaining aspect ratio
            display_width = int(width * scale_factor)
            display_height = int(height * scale_factor)

            # Add padding for the 2-pixel border and margins
            # (2px border + 2px margin each side = 8px total)
            dialog_width = display_width + 8
            dialog_height = display_height + 8

            # Set the dialog size
            self.setFixedSize(dialog_width, dialog_height)

            # Set the label size to match the image
            self.image_label.setFixedSize(display_width, display_height)

            # Position the dialog for perfect centering
            self.position_dialog_centered()
        except Exception as e:
            logger.error(f"Error auto-sizing dialog: {e}")

    def position_dialog_centered(self):
        """Center the dialog on the screen both horizontally and vertically."""
        try:
            # Get the screen that contains the parent window
            if self.parent():
                if hasattr(self.parent(), "screen"):
                    screen = self.parent().screen()
                else:
                    # Find which screen contains the parent window
                    parent_geometry = self.parent().geometry()
                    parent_center = parent_geometry.center()

                    screen = None
                    for available_screen in QApplication.screens():
                        if available_screen.geometry().contains(parent_center):
                            screen = available_screen
                            break

                    # Fallback to primary screen if not found
                    if screen is None:
                        screen = QApplication.primaryScreen()
            else:
                screen = QApplication.primaryScreen()

            if screen:
                screen_geometry = screen.availableGeometry()

                # Calculate perfect center position
                x = screen_geometry.center().x() - self.width() // 2
                y = screen_geometry.center().y() - self.height() // 2

                # Ensure dialog stays within screen bounds
                # (should not be needed with our sizing logic)
                x = max(
                    screen_geometry.left(),
                    min(x, screen_geometry.right() - self.width()),
                )
                y = max(
                    screen_geometry.top(),
                    min(y, screen_geometry.bottom() - self.height()),
                )

                self.move(x, y)

        except Exception as e:
            logger.error(f"Error positioning dialog: {e}")

    def mouse_press_event(self, event):
        """Handle mouse press events on the dialog itself."""
        # Allow interactions with the preview dialog itself
        # This overrides the click-through behavior for the dialog area
        super().mouse_press_event(event)

    def close_event(self, event):
        """Handle dialog close event."""
        # Stop the timer when closing
        self.auto_close_timer.stop()
        super().close_event(event)

    def __del__(self):
        """Destructor to ensure cleanup."""
        try:
            if hasattr(self, "auto_close_timer") and self.auto_close_timer:
                self.auto_close_timer.stop()
        except Exception as e:
            logger.error(f"Error in ROISelector destructor: {e}")
            pass  # Ignore cleanup errors

    def update_display(self):
        """Update the image display with ROI overlay and buttons."""
        if self.rotated_image is None:
            return

        try:
            # Convert OpenCV image to Qt format
            height, width = self.rotated_image.shape[:2]
            rotated_rgb = cv2.cvtColor(self.rotated_image, cv2.COLOR_BGR2RGB)
            bytes_per_line = 3 * width
            q_image = QImage(
                rotated_rgb.data, width, height, bytes_per_line, QImage.Format_RGB888
            )

            # Scale image to fit in the label while maintaining aspect ratio
            label_size = self.image_label.size()
            scaled_pixmap = QPixmap.fromImage(
                q_image.scaled(
                    label_size.width() - 4,  # Account for 2px border on each side
                    label_size.height() - 4,
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation,
                )
            )

            # Create a pixmap for the label with centered image
            label_pixmap = QPixmap(label_size)
            label_pixmap.fill(QColor(0, 0, 0, 0))  # Transparent background

            painter = QPainter(label_pixmap)

            # Calculate position to center the image
            x = (label_size.width() - scaled_pixmap.width()) // 2
            y = (label_size.height() - scaled_pixmap.height()) // 2

            # Draw the scaled image
            painter.drawPixmap(x, y, scaled_pixmap)

            # Draw the selection rectangle if it exists
            if self.current_selection and not self.current_selection.isEmpty():
                painter.setPen(QPen(QColor(0, 120, 215), 2, Qt.SolidLine))
                painter.setBrush(QColor(0, 120, 215, 40))  # Semi-transparent blue
                painter.drawRect(self.current_selection)

            # Draw overlay buttons at the bottom
            button_y = label_size.height() - 50
            button_spacing = 20
            total_button_width = (
                100 + 140 + button_spacing
            )  # Cancel + Confirm + spacing
            start_x = (label_size.width() - total_button_width) // 2

            # Draw Cancel button
            cancel_rect = QRect(start_x, button_y, 100, 30)
            painter.fillRect(cancel_rect, QColor(68, 68, 68))
            painter.setPen(QPen(QColor(102, 102, 102), 1))
            painter.drawRect(cancel_rect)
            painter.setPen(QColor(255, 255, 255))
            painter.drawText(cancel_rect, Qt.AlignCenter, "Cancel")

            # Draw Confirm button
            confirm_rect = QRect(start_x + 100 + button_spacing, button_y, 140, 30)
            painter.fillRect(confirm_rect, QColor(0, 120, 212))
            painter.setPen(QPen(QColor(0, 90, 158), 1))
            painter.drawRect(confirm_rect)
            painter.setPen(QColor(255, 255, 255))
            painter.drawText(confirm_rect, Qt.AlignCenter, "Confirm Selection")

            painter.end()
            self.image_label.setPixmap(label_pixmap)

        except Exception as e:
            logger.error(f"Error updating display: {e}")


class RoiVar:
    """Simple variable class to mimic Tkinter variables for ROI dialog."""

    def __init__(self, value=0):
        """Initialize the RoiVar with an optional value."""
        self._value = value

    def get(self):
        """Return the current value of the RoiVar."""
        return self._value

    def set(self, value):
        """Set the value of the RoiVar."""
        self._value = value


# Explicitly mark RoiVar as used for static analysis - class is used in camera_core.py
_ = RoiVar
