"""Camera GUI widgets.

For image acquisition and experiment control in Droplet Wall Interaction Tool (DWIT).
"""

import os

from PySide6.QtCore import QSize, Qt, Slot
from PySide6.QtGui import QIcon, QImage, QKeyEvent, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QStyle,
    QVBoxLayout,
    QWidget,
)

from src.utilities.logging_manager import get_logger

# Setup logger for this module
logger = get_logger(__name__)


class CameraGUI(QWidget):
    """Modern camera interface with live feed, recording, and ROI selection."""

    def __init__(self, parent, controller):
        """Initialize the CameraGUI with parent and controller."""
        logger.debug("Initializing CameraGUI")
        super().__init__(parent)
        self.controller = controller
        self.widget_state = True

        # Load custom icons from resources folder
        icons_path = os.path.join("resources", "icons")
        self.play_icon = QIcon(os.path.join(icons_path, "play.ico"))
        self.pause_icon = QIcon(os.path.join(icons_path, "pause.ico"))
        self.stop_icon = QIcon(os.path.join(icons_path, "stop.ico"))
        self.record_icon = QIcon(os.path.join(icons_path, "record.ico"))

        # Fallback to standard icons if custom icons not found
        if self.play_icon.isNull():

            self.play_icon = self.style().standardIcon(QStyle.SP_MediaPlay)
        if self.pause_icon.isNull():

            self.pause_icon = self.style().standardIcon(QStyle.SP_MediaPause)
        if self.stop_icon.isNull():

            self.stop_icon = self.style().standardIcon(QStyle.SP_MediaStop)
        if self.record_icon.isNull():

            self.record_icon = self.style().standardIcon(QStyle.SP_MediaPlay)

        # Create UI components
        self._create_widgets()

        # Connect controller signals
        self.controller.image_updated.connect(self.update_display)
        self.controller.live_state_changed.connect(self.update_live_button_state)
        self.controller.recording_state_changed.connect(self.update_record_button_state)
        self.controller.fps_changed.connect(self._update_fps_from_controller)
        self.controller.exp_changed.connect(self._update_exp_from_controller)
        logger.debug("CameraGUI initialization completed")

    def _create_widgets(self):
        """Create and arrange all UI elements."""
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(5)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # Camera control section
        self.frame_main = QFrame()
        main_layout.addWidget(self.frame_main)
        frame_main_layout = QVBoxLayout(self.frame_main)
        frame_main_layout.setSpacing(5)

        # Create horizontal layout for controls and settings
        top_layout = QHBoxLayout()
        top_layout.setSpacing(5)

        # Add control panels side by side
        top_layout.addWidget(self._create_buttons_panel(), 3)
        top_layout.addWidget(self._create_settings_panel(), 2)

        # Add horizontal layout to main vertical layout
        frame_main_layout.addLayout(top_layout)

        # Add preview panel below
        frame_main_layout.addWidget(self._create_preview_panel())

    def _create_buttons_panel(self):
        """Create the panel with camera control buttons."""
        # Button panel
        buttons_group = QWidget()
        buttons_layout = QHBoxLayout(buttons_group)
        buttons_layout.setContentsMargins(0, 0, 0, 0)

        # Left side buttons in horizontal layout
        button_container = QWidget()
        button_container_layout = QHBoxLayout(button_container)
        button_container_layout.setContentsMargins(0, 0, 0, 0)
        button_container_layout.setSpacing(5)

        # Record button
        self.record_button = QPushButton()
        self.record_button.setIcon(self.record_icon)
        self.record_button.setIconSize(QSize(24, 24))
        self.record_button.setFixedWidth(80)
        self.record_button.setObjectName("primary-button")
        self.record_button.setToolTip("Start/Stop Recording")
        self.record_button.clicked.connect(self.toggle_recording)

        # Live feed button
        self.live_button = QPushButton()
        self.live_button.setIcon(self.play_icon)
        self.live_button.setIconSize(QSize(24, 24))
        self.live_button.setFixedWidth(80)
        self.live_button.setObjectName("action-button")
        self.live_button.setToolTip("Start/Stop Live Feed")
        self.live_button.clicked.connect(self.toggle_live_feed)

        button_container_layout.addWidget(self.record_button)
        button_container_layout.addWidget(self.live_button)
        buttons_layout.addWidget(button_container)

        # NEW: Add another vertical line to the right of the buttons
        vertical_line = QFrame()
        vertical_line.setFrameShape(QFrame.VLine)
        vertical_line.setFrameShadow(QFrame.Sunken)
        vertical_line.setFixedWidth(2)
        buttons_layout.addWidget(vertical_line)

        return buttons_group

    def _create_settings_panel(self):
        """Create the camera settings panel."""
        settings_group = QWidget()

        # Use a horizontal layout for the entire settings panel
        main_settings_layout = QHBoxLayout(settings_group)
        main_settings_layout.setSpacing(10)
        main_settings_layout.setContentsMargins(0, 0, 0, 0)

        # Create three columns: Left/Right, Top/Bottom, FPS/Exposure
        # First column: Left/Right
        left_right_widget = QWidget()
        left_right_layout = QVBoxLayout(left_right_widget)
        left_right_layout.setContentsMargins(0, 0, 0, 0)
        left_right_layout.setSpacing(5)

        # Create grid layout for params
        left_right_params = QGridLayout()
        left_right_params.setContentsMargins(0, 0, 0, 0)
        left_right_params.setVerticalSpacing(8)
        left_right_params.setHorizontalSpacing(5)
        left_right_params.setColumnStretch(1, 1)

        # Left control
        self.left_label = QLabel("Left:")
        self.left_label.setToolTip(
            "Left edge of the region of interest (ROI) in pixels."
        )
        self.left_spinbox = QSpinBox()
        self.left_spinbox.setRange(0, self.controller.cam_max_width - 1)
        self.left_spinbox.setSingleStep(1)
        self.left_spinbox.setValue(self.controller.x1_var.get())
        self.left_spinbox.setToolTip("Left edge of ROI (press Enter to apply)")
        self.left_spinbox.setSuffix(" px")
        self.left_spinbox.setMinimumWidth(100)
        left_right_params.addWidget(self.left_label, 0, 0)
        left_right_params.addWidget(self.left_spinbox, 0, 1)

        # Right control
        self.right_label = QLabel("Right:")
        self.right_label.setToolTip(
            "Right edge of the region of interest (ROI) in pixels."
        )
        self.right_spinbox = QSpinBox()
        self.right_spinbox.setRange(1, self.controller.cam_max_width)
        self.right_spinbox.setSingleStep(1)
        self.right_spinbox.setValue(self.controller.x2_var.get())
        self.right_spinbox.setToolTip(
            "Right edge of ROI | Max: 5120 (press Enter to apply)"
        )
        self.right_spinbox.setSuffix(" px")
        self.right_spinbox.setMinimumWidth(100)
        left_right_params.addWidget(self.right_label, 1, 0)
        left_right_params.addWidget(self.right_spinbox, 1, 1)

        left_right_layout.addLayout(left_right_params)

        # Second column: Top/Bottom
        top_bottom_widget = QWidget()
        top_bottom_layout = QVBoxLayout(top_bottom_widget)
        top_bottom_layout.setContentsMargins(0, 0, 0, 0)
        top_bottom_layout.setSpacing(5)

        # Create grid layout for params
        top_bottom_params = QGridLayout()
        top_bottom_params.setContentsMargins(0, 0, 0, 0)
        top_bottom_params.setVerticalSpacing(8)
        top_bottom_params.setHorizontalSpacing(5)
        top_bottom_params.setColumnStretch(1, 1)

        # Top control
        self.top_label = QLabel("Top:")
        self.top_label.setToolTip("Top edge of the region of interest (ROI) in pixels.")
        self.top_spinbox = QSpinBox()
        self.top_spinbox.setRange(0, self.controller.cam_max_height - 1)
        self.top_spinbox.setSingleStep(1)
        self.top_spinbox.setValue(self.controller.y1_var.get())
        self.top_spinbox.setToolTip("Top edge of ROI (press Enter to apply)")
        self.top_spinbox.setSuffix(" px")
        self.top_spinbox.setMinimumWidth(100)
        top_bottom_params.addWidget(self.top_label, 0, 0)
        top_bottom_params.addWidget(self.top_spinbox, 0, 1)

        # Bottom control
        self.bottom_label = QLabel("Bottom:")
        self.bottom_label.setToolTip(
            "Bottom edge of the region of interest (ROI) in pixels."
        )
        self.bottom_spinbox = QSpinBox()
        self.bottom_spinbox.setRange(1, self.controller.cam_max_height)
        self.bottom_spinbox.setSingleStep(1)
        self.bottom_spinbox.setValue(self.controller.y2_var.get())
        self.bottom_spinbox.setToolTip(
            "Bottom edge of ROI | Max: 2880 (press Enter to apply)"
        )
        self.bottom_spinbox.setSuffix(" px")
        self.bottom_spinbox.setMinimumWidth(100)
        top_bottom_params.addWidget(self.bottom_label, 1, 0)
        top_bottom_params.addWidget(self.bottom_spinbox, 1, 1)

        top_bottom_layout.addLayout(top_bottom_params)

        # Create a vertical line to the right of top and bottom
        vertical_line = QFrame()
        vertical_line.setFrameShape(QFrame.VLine)
        vertical_line.setFrameShadow(QFrame.Sunken)
        vertical_line.setFixedWidth(2)

        # Third column: Frame Rate/Exposure
        camera_settings_widget = QWidget()
        camera_settings_layout = QVBoxLayout(camera_settings_widget)
        camera_settings_layout.setContentsMargins(0, 0, 0, 0)
        camera_settings_layout.setSpacing(5)

        # Create grid layout for params
        camera_params = QGridLayout()
        camera_params.setContentsMargins(0, 0, 0, 0)
        camera_params.setVerticalSpacing(8)
        camera_params.setHorizontalSpacing(5)
        camera_params.setColumnStretch(1, 1)

        # Frame rate control
        self.rate_label = QLabel("Frame Rate:")
        self.rate_label.setToolTip("Set the camera's frame rate (frames per second).")
        self.rate_spinbox = QSpinBox()
        self.rate_spinbox.setRange(self.controller.min_fps, self.controller.max_fps)
        self.rate_spinbox.setSingleStep(10)
        self.rate_spinbox.setValue(self.controller.fps)
        self.rate_spinbox.setToolTip(
            f"Range: {self.controller.min_fps}-{self.controller.max_fps} FPS"
        )
        self.rate_spinbox.valueChanged.connect(self._on_fps_changed)
        self.rate_spinbox.setSuffix(" fps")
        self.rate_spinbox.setMinimumWidth(100)
        camera_params.addWidget(self.rate_label, 0, 0)
        camera_params.addWidget(self.rate_spinbox, 0, 1)

        # Exposure control
        self.exposure_label = QLabel("Exposure Time:")
        self.exposure_label.setToolTip(
            "Set the camera's exposure time in microseconds (μs)."
        )
        self.exposure_spinbox = QSpinBox()
        min_exp = int(self.controller.min_exp / 1000)
        max_exp = int(self.controller.max_exp / 1000)
        self.exposure_spinbox.setRange(min_exp, max_exp)
        self.exposure_spinbox.setSingleStep(1000)
        self.exposure_spinbox.setValue(self.controller.exp)
        self.exposure_spinbox.setToolTip(f"Range: {min_exp}-{max_exp} μs")
        self.exposure_spinbox.valueChanged.connect(self._on_exp_changed)
        self.exposure_spinbox.setSuffix(" μs")
        self.exposure_spinbox.setMinimumWidth(100)
        camera_params.addWidget(self.exposure_label, 1, 0)
        camera_params.addWidget(self.exposure_spinbox, 1, 1)

        camera_settings_layout.addLayout(camera_params)

        # Add the three columns to the main layout
        main_settings_layout.addWidget(left_right_widget)
        main_settings_layout.addWidget(top_bottom_widget)
        main_settings_layout.addWidget(vertical_line)  # Add the vertical line
        main_settings_layout.addWidget(camera_settings_widget)

        return settings_group

    def _create_preview_panel(self):
        """Create the image preview panel."""
        preview_group = QWidget()
        preview_layout = QVBoxLayout(preview_group)
        preview_layout.setContentsMargins(0, 0, 0, 0)

        # Image preview label
        self.image_preview_frame = QLabel()
        self.image_preview_frame.setToolTip("Live preview of the camera image.")
        self.image_preview_frame.setMinimumSize(230, 230)
        self.image_preview_frame.setAlignment(Qt.AlignCenter)
        self.image_preview_frame.setText("No Image Available")
        self.image_preview_frame.setFrameShape(QFrame.Box)
        self.image_preview_frame.setFrameShadow(QFrame.Sunken)
        self.image_preview_frame.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Expanding
        )

        preview_layout.addWidget(self.image_preview_frame)

        return preview_group

    def _on_fps_changed(self, value):
        """Handle frame rate changes from the UI."""
        self.controller.set_fps(value)
        self.controller.update_fps()

    def _on_exp_changed(self, value):
        """Handle exposure time changes from the UI."""
        self.controller.set_exp(value)
        self.controller.update_exp()

    def display_image_on_canvas(self):
        """Update the image display with the current camera image."""
        if not self.controller.current_image:

            self.image_preview_frame.setText("No Image Available")
            return

        pil_img = self.controller.current_image

        try:
            # Convert PIL image to QImage based on mode
            if pil_img.mode == "L":
                img_data = pil_img.tobytes("raw")
                qimg = QImage(
                    img_data,
                    pil_img.width,
                    pil_img.height,
                    pil_img.width,
                    QImage.Format_Grayscale8,
                )
            elif pil_img.mode == "RGB":
                img_data = pil_img.tobytes("raw")
                qimg = QImage(
                    img_data,
                    pil_img.width,
                    pil_img.height,
                    pil_img.width * 3,
                    QImage.Format_RGB888,
                )
            else:
                pil_img = pil_img.convert("RGB")
                img_data = pil_img.tobytes("raw")
                qimg = QImage(
                    img_data,
                    pil_img.width,
                    pil_img.height,
                    pil_img.width * 3,
                    QImage.Format_RGB888,
                )

            # Convert to pixmap and scale to fit
            pixmap = QPixmap.fromImage(qimg)
            label_size = self.image_preview_frame.size()
            scaled_pixmap = pixmap.scaled(
                label_size, Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            self.image_preview_frame.setPixmap(scaled_pixmap)

        except Exception as e:
            logger.error(f"Error displaying image: {e}")
            pass

    @Slot(bool)
    def update_live_button_state(self, is_live):
        """Update live button appearance based on state."""
        if is_live:
            self.live_button.setIcon(self.pause_icon)
        #             self.record_button.setEnabled(False)
        else:
            self.live_button.setIcon(self.play_icon)

    #             self.record_button.setEnabled(True)

    @Slot(bool)
    def update_record_button_state(self, is_recording):
        """Update record button appearance based on state."""
        if is_recording:
            self.record_button.setIcon(self.stop_icon)
        else:
            self.record_button.setIcon(self.record_icon)

    def _toggle_widget_state(self):
        """Toggle enabled state of all UI controls."""
        self.widget_state = not self.widget_state

    def _apply_roi_changes(self):
        """Apply ROI changes when Enter is pressed."""
        # Get values from spinboxes
        x1 = self.left_spinbox.value()
        x2 = self.right_spinbox.value()
        y1 = self.top_spinbox.value()
        y2 = self.bottom_spinbox.value()

        # Validate values
        if x1 >= x2 or y1 >= y2:
            return

        # Update controller variables
        self.controller.x1_var.set(x1)
        self.controller.x2_var.set(x2)
        self.controller.y1_var.set(y1)
        self.controller.y2_var.set(y2)

        # Apply ROI change to controller
        self.controller.change_roi(x2 - x1, y2 - y1)

    def key_press_event(self, event: QKeyEvent):
        """Handle key press events, specifically Enter to apply ROI changes."""
        if event.key() == Qt.Key_Return or event.key() == Qt.Key_Enter:
            # Apply ROI changes immediately when Enter is pressed
            self._apply_roi_changes()
            event.accept()
        else:
            super().key_press_event(event)

    def toggle_live_feed(self):
        """Toggle camera live feed state."""
        logger.info(f"Toggling live feed - current state: {self.controller.live_feed}")
        if self.controller.live_feed:

            self.controller.stop_live()
        else:

            self.controller.start_live()

    def toggle_recording(self):
        """Toggle camera recording state."""
        logger.info(f"Toggling recording - current state: {self.controller.recording}")
        if self.controller.recording:

            self.controller.stop_record()
        else:

            self.controller.start_record()

    @Slot(int)
    def _update_fps_from_controller(self, value):
        """Update FPS spinbox from controller signals."""
        self.rate_spinbox.setValue(value)

    @Slot(int)
    def _update_exp_from_controller(self, value):
        """Update exposure spinbox from controller signals."""
        self.exposure_spinbox.setValue(value)

    @Slot()
    def update_display(self):
        """Update the image display when a new frame is available."""
        self.display_image_on_canvas()
