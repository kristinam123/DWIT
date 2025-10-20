"""Widgets for preview canvas and statistics overlay used by DWIT.

This module provides two Qt widgets used by the DWIT application:

- StatsOverlay: a semi-transparent overlay that displays real-time analysis
    statistics such as contact angles, contour dimensions, area, velocity and
    derived values. The overlay adapts its content based on analysis mode.

- PreviewCanvas: a canvas widget for displaying OpenCV images (BGR or
    grayscale) converted to QPixmap with proper scaling, centering and a
    toggleable statistics icon that integrates with StatsOverlay.

Both widgets are implemented with PySide6 and intended for embedding in the
DWIT GUI to present live or stored analysis results.

Image slider widget for the DWIT application.

This module provides a comprehensive image slider widget for navigating through
analyzed frames with playback controls, speed adjustment, and frame-specific
statistics display.
"""

from collections.abc import Callable

import cv2
import numpy as np
from PySide6.QtCore import QPoint, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QIcon,
    QImage,
    QKeySequence,
    QPainter,
    QPixmap,
    QPolygon,
    QShortcut,
)
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from src.utilities.core_utils import get_logger

# Setup logger for this module
logger = get_logger(__name__)


class ImageSlider(QWidget):
    """Professional image slider widget for navigating through result images.

    This widget provides controls for:
    - Frame navigation (previous/next)
    - Auto-play with adjustable speed
    - Direct frame selection via slider
    - Keyboard shortcuts for navigation

    Signals
    -------
    frame_changed : Signal(int)
        Emitted when the current frame changes, passing the new frame index.
    """

    frame_changed = Signal(int)

    def __init__(
        self,
        parent: QWidget | None = None,
        on_frame_changed: Callable[[int], None] | None = None,
        get_fps: Callable[[], float] | None = None,
    ):
        """Initialize the ImageSlider.

        Parameters
        ----------
        parent : QWidget, optional
            The parent widget.
        on_frame_changed : callable, optional
            Callback function called when frame changes.
            Receives the frame index as the single parameter.
        get_fps : callable, optional
            Callback function that returns the current FPS value for speed calculations.

        """
        super().__init__(parent)

        self._on_frame_changed_callback = on_frame_changed
        self._get_fps_callback = get_fps

        # State variables
        self.current_frame_index = 0
        self.total_frames = 0
        self.is_auto_playing = False
        self.is_focused = False

        # Set focus policy to enable focus events
        self.setFocusPolicy(Qt.StrongFocus)

        # Create UI components
        self._create_widgets()
        self._setup_layout()
        self._connect_signals()
        self._setup_keyboard_shortcuts()
        self._apply_transparent_style()

        # Initialize state
        self._update_button_states()
        self._update_speed_label()

    def _create_widgets(self) -> None:
        """Create all UI widgets for the slider."""
        # Previous frame button with skip backward icon
        self.btn_prev_frame = QPushButton()
        self.btn_prev_frame.setFixedSize(30, 30)
        self.btn_prev_frame.setIconSize(QSize(20, 20))
        self.btn_prev_frame.setIcon(self._create_skip_backward_icon())
        self.btn_prev_frame.setToolTip("Previous frame (Left Arrow)")
        self.btn_prev_frame.setEnabled(False)

        # Play/Pause button
        self.btn_play_pause = QPushButton()
        self.btn_play_pause.setFixedSize(30, 30)
        self.btn_play_pause.setIconSize(QSize(20, 20))
        self.btn_play_pause.setIcon(
            QIcon.fromTheme("media-playback-start", QIcon(":/icons/play.png"))
        )
        self.btn_play_pause.setToolTip("Auto-play frames (Space)")
        self.btn_play_pause.setEnabled(False)

        # Next frame button with skip forward icon
        self.btn_next_frame = QPushButton()
        self.btn_next_frame.setFixedSize(30, 30)
        self.btn_next_frame.setIconSize(QSize(20, 20))
        self.btn_next_frame.setIcon(self._create_skip_forward_icon())
        self.btn_next_frame.setToolTip("Next frame (Right Arrow)")
        self.btn_next_frame.setEnabled(False)

        # Speed control slider with custom steps
        self._speed_steps = [
            0.1,
            0.2,
            0.3,
            0.4,
            0.5,
            0.6,
            0.7,
            0.8,
            0.9,
            1,
            1.5,
            2,
            2.5,
            3,
            3.5,
            4,
        ]
        self.speed_slider = QSlider(Qt.Horizontal)
        self.speed_slider.setRange(0, len(self._speed_steps) - 1)
        self.speed_slider.setValue(self._speed_steps.index(1))  # Default to 1.0x
        self.speed_slider.setFixedWidth(120)
        self.speed_slider.setToolTip("Playback speed (0.1x to 4.0x real-life speed)")

        # Speed indicator label
        self.speed_label = QLabel("1.0x")
        self.speed_label.setFixedWidth(35)
        self.speed_label.setAlignment(Qt.AlignCenter)
        self.speed_label.setStyleSheet("font-weight: bold; color: white;")
        self.speed_label.setToolTip("Current playback speed multiplier")

        # Main slider for frame navigation
        self.image_slider = QSlider(Qt.Horizontal)
        self.image_slider.setMinimum(0)
        self.image_slider.setMaximum(0)
        self.image_slider.setValue(0)
        self.image_slider.setTickPosition(QSlider.NoTicks)  # Remove tick marks
        self.image_slider.setEnabled(False)
        self.image_slider.setToolTip("Navigate through result frames")

        # Auto-play timer
        self.auto_play_timer = QTimer()

    def _setup_layout(self) -> None:
        """Set up the widget layout."""
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(5, 5, 5, 5)
        main_layout.setSpacing(10)

        main_layout.addWidget(self.btn_prev_frame)
        main_layout.addWidget(self.btn_play_pause)
        main_layout.addWidget(self.btn_next_frame)
        main_layout.addWidget(self.speed_label)
        main_layout.addWidget(self.speed_slider)
        main_layout.addWidget(self.image_slider, 1)  # Expandable

    def _apply_transparent_style(self) -> None:
        """Apply transparent styling to the widget."""
        self.setStyleSheet(
            """
            ImageSlider {
                background-color: rgba(0, 0, 0, 50);
                border: 1px solid rgba(150, 150, 150, 80);
                border-radius: 4px;
            }
            QPushButton {
                background-color: rgba(60, 60, 60, 100);
                border: 1px solid rgba(100, 100, 100, 100);
                border-radius: 4px;
                color: rgba(255, 255, 255, 150);
            }
            QPushButton:hover {
                background-color: rgba(80, 80, 80, 150);
                border-color: rgba(120, 120, 120, 150);
            }
            QLabel {
                color: rgba(255, 255, 255, 150);
            }
        """
        )

    def _apply_focused_style(self) -> None:
        """Apply opaque styling when widget is focused."""
        self.setStyleSheet(
            """
            ImageSlider {
                background-color: rgba(40, 40, 40, 220);
                border: 1px solid rgba(150, 150, 150, 200);
                border-radius: 4px;
            }
            QPushButton {
                background-color: rgba(60, 60, 60, 255);
                border: 1px solid rgba(100, 100, 100, 255);
                border-radius: 4px;
                color: rgba(255, 255, 255, 255);
            }
            QPushButton:hover {
                background-color: rgba(80, 80, 80, 255);
                border-color: rgba(120, 120, 120, 255);
            }
            QLabel {
                color: rgba(255, 255, 255, 255);
            }
        """
        )

    def focusInEvent(self, event) -> None:  # noqa: N802
        """Handle focus in event - make widget opaque."""
        self.is_focused = True
        self._apply_focused_style()
        super().focusInEvent(event)

    def focusOutEvent(self, event) -> None:  # noqa: N802
        """Handle focus out event - make widget transparent."""
        self.is_focused = False
        self._apply_transparent_style()
        super().focusOutEvent(event)

    def enterEvent(self, event) -> None:  # noqa: N802
        """Handle mouse enter event - make widget opaque."""
        self._apply_focused_style()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        """Handle mouse leave event - make widget transparent if not focused."""
        if not self.is_focused:
            self._apply_transparent_style()
        super().leaveEvent(event)

    def _connect_signals(self) -> None:
        """Connect all widget signals to their handlers."""
        self.btn_prev_frame.clicked.connect(self._navigate_to_previous_frame)
        self.btn_play_pause.clicked.connect(self._toggle_auto_play)
        self.btn_next_frame.clicked.connect(self._navigate_to_next_frame)

        self.speed_slider.sliderPressed.connect(self._on_speed_slider_pressed)
        self.speed_slider.sliderMoved.connect(self._on_speed_slider_moved)
        self.speed_slider.sliderReleased.connect(self._on_speed_slider_released)
        self.speed_slider.valueChanged.connect(self._on_speed_slider_changed)

        self.image_slider.valueChanged.connect(self._on_slider_value_changed)
        self.auto_play_timer.timeout.connect(self._auto_advance_frame)

    def _setup_keyboard_shortcuts(self) -> None:
        """Set up keyboard shortcuts for navigation."""
        # Left arrow for previous frame
        self.shortcut_prev = QShortcut(QKeySequence(Qt.Key_Left), self)
        self.shortcut_prev.activated.connect(self._navigate_to_previous_frame)

        # Right arrow for next frame
        self.shortcut_next = QShortcut(QKeySequence(Qt.Key_Right), self)
        self.shortcut_next.activated.connect(self._navigate_to_next_frame)

        # Space bar for play/pause
        self.shortcut_play = QShortcut(QKeySequence(Qt.Key_Space), self)
        self.shortcut_play.activated.connect(self._toggle_auto_play)

    def _create_skip_backward_icon(self) -> QIcon:
        """Create a custom skip backward icon."""
        icon = QIcon.fromTheme("media-skip-backward")
        if not icon.isNull():
            return icon

        # Create custom icon
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
        return QIcon(pixmap)

    def _create_skip_forward_icon(self) -> QIcon:
        """Create a custom skip forward icon."""
        icon = QIcon.fromTheme("media-skip-forward")
        if not icon.isNull():
            return icon

        # Create custom icon
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
        return QIcon(pixmap)

    def _navigate_to_previous_frame(self) -> None:
        """Navigate to the previous frame."""
        if self.current_frame_index > 0:
            self.set_current_frame(self.current_frame_index - 1)

    def _navigate_to_next_frame(self) -> None:
        """Navigate to the next frame."""
        if self.current_frame_index < self.total_frames - 1:
            self.set_current_frame(self.current_frame_index + 1)

    def _toggle_auto_play(self) -> None:
        """Toggle auto-play mode."""
        if self.total_frames <= 1:
            return

        self.is_auto_playing = not self.is_auto_playing

        if self.is_auto_playing:
            self.btn_play_pause.setIcon(
                QIcon.fromTheme("media-playback-pause", QIcon(":/icons/pause.png"))
            )
            self.btn_play_pause.setToolTip("Pause auto-play (Space)")
            self._start_auto_play()
        else:
            self.btn_play_pause.setIcon(
                QIcon.fromTheme("media-playback-start", QIcon(":/icons/play.png"))
            )
            self.btn_play_pause.setToolTip("Auto-play frames (Space)")
            self.auto_play_timer.stop()

    def _start_auto_play(self) -> None:
        """Start auto-play with current speed settings."""
        # Get FPS from callback or use default
        fps = 30.0
        if self._get_fps_callback:
            try:
                fps = float(self._get_fps_callback())
            except Exception:
                logger.warning("Failed to get FPS from callback, using default 30")

        real_life_interval = 1000.0 / fps  # Real-life interval in milliseconds

        # Use custom speed steps
        idx = self.speed_slider.value()
        speed_multiplier = self._speed_steps[idx]

        # Calculate final interval
        interval = int(real_life_interval / speed_multiplier)
        interval = max(10, interval)  # Minimum 10ms to prevent system overload

        self.auto_play_timer.start(interval)

    def _auto_advance_frame(self) -> None:
        """Automatically advance to the next frame during auto-play."""
        if self.current_frame_index < self.total_frames - 1:
            self._navigate_to_next_frame()
        else:
            # Loop back to the beginning
            self.set_current_frame(0)

    def _on_speed_slider_changed(self) -> None:
        """Handle speed slider changes and update auto-play interval if active."""
        self._update_speed_label()

        if self.is_auto_playing:
            # Restart auto-play with new speed
            self.auto_play_timer.stop()
            self._start_auto_play()

    def _on_speed_slider_pressed(self) -> None:
        """Handle speed slider press event."""
        pass  # No action needed for static label

    def _on_speed_slider_moved(self, value: int) -> None:
        """Update speed indicator while user is sliding."""
        self._update_speed_label(value)

    def _on_speed_slider_released(self) -> None:
        """Handle speed slider release event."""
        pass  # No action needed for static label

    def _on_slider_value_changed(self, value: int) -> None:
        """Handle slider value changes from direct user interaction."""
        if value != self.current_frame_index:
            self.set_current_frame(value, from_slider=True)

    def _update_speed_label(self, value: int | None = None) -> None:
        """Update the speed label to show current multiplier.

        Parameters
        ----------
        value : int, optional
            Speed slider value. If None, uses current slider value.

        """
        if value is None:
            value = self.speed_slider.value()

        # Use custom speed steps
        multiplier = self._speed_steps[value]
        # Format with comma for European style, otherwise dot
        multiplier_str = f"{multiplier:.1f}".replace(".", ",")
        self.speed_label.setText(f"{multiplier_str}x")

    def _update_button_states(self) -> None:
        """Update button enabled states based on current state."""
        has_frames = self.total_frames > 1

        self.image_slider.setEnabled(has_frames)
        self.btn_prev_frame.setEnabled(has_frames)
        self.btn_next_frame.setEnabled(has_frames)
        self.btn_play_pause.setEnabled(has_frames)

    def set_total_frames(self, total: int) -> None:
        """Set the total number of frames.

        Parameters
        ----------
        total : int
            Total number of frames available.

        """
        self.total_frames = total

        if total > 1:
            self.image_slider.setMaximum(total - 1)
        else:
            self.image_slider.setMaximum(0)

        self._update_button_states()

        # Reset to first frame
        if total > 0:
            self.set_current_frame(0)

    def set_current_frame(self, index: int, from_slider: bool = False) -> None:
        """Set the current frame index.

        Parameters
        ----------
        index : int
            Frame index to display.
        from_slider : bool, optional
            Whether the change originated from the slider itself.

        """
        if index < 0 or (self.total_frames > 0 and index >= self.total_frames):
            return

        self.current_frame_index = index

        # Update slider position if change didn't come from slider
        if not from_slider:
            self.image_slider.blockSignals(True)
            self.image_slider.setValue(index)
            self.image_slider.blockSignals(False)

        # Emit signal
        self.frame_changed.emit(index)

        # Call callback if provided
        if self._on_frame_changed_callback:
            try:
                self._on_frame_changed_callback(index)
            except Exception as e:
                logger.error(f"Error in frame changed callback: {e}")

    def get_current_frame(self) -> int:
        """Get the current frame index.

        Returns
        -------
        int
            The current frame index.

        """
        return self.current_frame_index


class StatsOverlay(QWidget):
    """Semi-transparent statistics overlay widget.

    Displays real-time analysis statistics including contact angles,
    dimensions, velocity, and calculated values.
    """

    def __init__(
        self,
        parent: QWidget | None = None,
        analysis_mode: str = "",
    ):
        """Initialize the StatsOverlay.

        Parameters
        ----------
        parent : QWidget, optional
            The parent widget (typically the canvas wrapper).
        analysis_mode : str, optional
            The analysis mode to determine which stats to show.

        """
        super().__init__(parent)

        self.analysis_mode = analysis_mode
        self.is_visible_state = True

        # Determine which stats to show based on analysis mode
        self.show_contact_angles = analysis_mode not in [
            "free_sedimentation",
            "structured_packing",
        ]

        self._create_widgets()
        self._setup_layout()
        self._set_defaults()

    def paintEvent(self, event):  # noqa: N802
        """Paint a more transparent background."""
        painter = QPainter(self)
        color = QColor(0, 0, 0, 90)  # More transparent black (alpha 90)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(color)
        painter.setPen(QColor(150, 150, 150, 120))
        painter.drawRoundedRect(self.rect(), 6, 6)
        super().paintEvent(event)

    def _create_widgets(self) -> None:
        """Create all overlay label widgets."""
        # Set size based on analysis mode
        if self.analysis_mode in ["free_sedimentation", "structured_packing"]:
            self.setFixedSize(250, 100)  # Compact for these modes
        else:
            self.setFixedSize(250, 130)  # Standard size

        self.move(0, 0)  # Position at top-left corner
        self.setStyleSheet(
            """
            QWidget {
                background-color: rgba(0, 0, 0, 70);  /* 27% transparency */
                border: 1px solid rgba(150, 150, 150, 120);
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

        # Create stats labels
        if self.show_contact_angles:
            self.adv_angle_label = QLabel("Advancing angle    |  --°")
            self.rec_angle_label = QLabel("Receding angle     |  --°")
        else:
            # Create dummy labels for compatibility but hide them
            self.adv_angle_label = QLabel("")
            self.rec_angle_label = QLabel("")
            self.adv_angle_label.hide()
            self.rec_angle_label.hide()

        self.contour_label = QLabel("Contour (W/H)      |  -- mm/-- mm")
        self.ellipse_diameter_label = QLabel("Contour diameter   |  -- mm")
        self.ellipse_diameter_label.setToolTip(
            "Ellipse diameter formula: d = sqrt(w*h)"
        )
        self.area_label = QLabel("Area               |  -- mm²")
        self.area_diameter_label = QLabel("Area diameter      |  -- mm")
        self.area_diameter_label.setToolTip("Area diameter formula: d = sqrt(4*A/pi)")
        self.velocity_label = QLabel("Velocity           |  -- mm/s")

    def _setup_layout(self) -> None:
        """Set up the widget layout."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(3)

        # Add labels to layout
        if self.show_contact_angles:
            layout.addWidget(self.adv_angle_label)
            layout.addWidget(self.rec_angle_label)
        layout.addWidget(self.contour_label)
        layout.addWidget(self.ellipse_diameter_label)
        layout.addWidget(self.area_label)
        layout.addWidget(self.area_diameter_label)
        layout.addWidget(self.velocity_label)

        # Add stretch to push stats to top
        layout.addStretch(1)

    def _set_defaults(self) -> None:
        """Set default values for all labels."""
        try:
            if self.show_contact_angles:
                self.adv_angle_label.setText("Advancing angle    |  --°")
                self.rec_angle_label.setText("Receding angle     |  --°")
            self.contour_label.setText("Contour (W/H)      |  -- mm/-- mm")
            self.ellipse_diameter_label.setText("Contour diameter   |  -- mm")
            self.area_label.setText("Area               |  -- mm²")
            self.area_diameter_label.setText("Area diameter      |  -- mm")
            self.velocity_label.setText("Velocity           |  -- mm/s")
        except Exception as e:
            logger.error(f"Error setting overlay defaults: {e}")

    def toggle_visibility(self) -> bool:
        """Toggle the overlay visibility.

        Returns
        -------
        bool
            The new visibility state.

        """
        self.is_visible_state = not self.is_visible_state
        self.setVisible(self.is_visible_state)
        return self.is_visible_state

    def update_from_numeric_data(
        self,
        adv_angle: float = float("nan"),
        rec_angle: float = float("nan"),
        width_mm: float = float("nan"),
        height_mm: float = float("nan"),
        ellipse_diameter_mm: float = float("nan"),
        area_diameter_mm: float = float("nan"),
        velocity: float = float("nan"),
        area_mm2: float = float("nan"),
    ) -> None:
        """Update overlay from numeric values.

        Parameters
        ----------
        adv_angle : float, optional
            Advancing contact angle in degrees.
        rec_angle : float, optional
            Receding contact angle in degrees.
        width_mm : float, optional
            Droplet width in mm.
        height_mm : float, optional
            Droplet height in mm.
        ellipse_diameter_mm : float, optional
            Ellipse diameter in mm.
        area_diameter_mm : float, optional
            Area-equivalent diameter in mm.
        velocity : float, optional
            Droplet velocity in mm/s.
        area_mm2 : float, optional
            Droplet area in mm².

        """
        try:
            # Format values or show "--" for NaN
            adv_str = f"{adv_angle:.1f}" if not np.isnan(adv_angle) else "--"
            rec_str = f"{rec_angle:.1f}" if not np.isnan(rec_angle) else "--"
            width_str = f"{width_mm:.2f}" if not np.isnan(width_mm) else "--"
            height_str = f"{height_mm:.2f}" if not np.isnan(height_mm) else "--"
            ellipse_str = (
                f"{ellipse_diameter_mm:.2f}"
                if not np.isnan(ellipse_diameter_mm)
                else "--"
            )
            area_diameter_str = (
                f"{area_diameter_mm:.2f}" if not np.isnan(area_diameter_mm) else "--"
            )
            velocity_str = f"{velocity:.2f}" if not np.isnan(velocity) else "--"

            # Update overlay labels with consistent spacing formatting
            if self.show_contact_angles:
                self.adv_angle_label.setText(f"Advancing angle    |  {adv_str}°")
                self.rec_angle_label.setText(f"Receding angle     |  {rec_str}°")

            contour_text = f"Contour (W/H)      |  {width_str} mm/{height_str} mm"
            self.contour_label.setText(contour_text)
            self.ellipse_diameter_label.setText(
                f"Contour diameter   |  {ellipse_str} mm"
            )
            self.area_diameter_label.setText(
                f"Area diameter      |  {area_diameter_str} mm"
            )
            self.velocity_label.setText(f"Velocity           |  {velocity_str} mm/s")

            logger.debug(f"Set contour_label to: {contour_text}")

            # Use provided area_mm2 if available, otherwise calculate from width/height
            if not np.isnan(area_mm2) and area_mm2 > 0:
                self.area_label.setText(f"Area               |  {area_mm2:.2f} mm²")
            elif (
                not np.isnan(width_mm)
                and not np.isnan(height_mm)
                and width_mm > 0
                and height_mm > 0
            ):
                # Approximate area as ellipse: A = π * (w/2) * (h/2)
                area_mm2 = np.pi * (width_mm / 2) * (height_mm / 2)
                self.area_label.setText(f"Area               |  {area_mm2:.2f} mm²")
            else:
                self.area_label.setText("Area               |  -- mm²")

        except Exception as e:
            logger.error(f"Error updating overlay from numeric data: {e}")
            self._set_defaults()

    def update_from_realtime_data(
        self,
        advancing_contact_angles: list[float],
        receding_contact_angles: list[float],
        result_images: dict,
        result_lists: dict,
    ) -> None:
        """Update overlay from real-time analysis data.

        Parameters
        ----------
        advancing_contact_angles : list[float]
            List of advancing contact angles.
        receding_contact_angles : list[float]
            List of receding contact angles.
        result_images : dict
            Dictionary containing result images with latest values.
        result_lists : dict
            Dictionary containing result lists with all values.

        """
        try:
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

            logger.debug(
                f"Overlay - width_mm: {width_mm}, height_mm: {height_mm}, "
                f"adv: {latest_adv}, rec: {latest_rec}"
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
            area_mm2 = self._get_latest_value("area_mm2", result_images, result_lists)

            # Update overlay with the real-time data
            self.update_from_numeric_data(
                latest_adv,
                latest_rec,
                width_mm,
                height_mm,
                ellipse_diameter_mm,
                area_diameter_mm,
                velocity,
                area_mm2,
            )

        except Exception as e:
            logger.error(f"Error updating overlay from real-time data: {e}")

    def update_from_frame_data(self, frame_data: dict, index: int) -> None:
        """Update overlay from stored frame data.

        Parameters
        ----------
        frame_data : dict
            Dictionary containing frame data arrays.
        index : int
            Frame index to display.

        """
        try:

            def _safe_get(key: str, idx: int, default):
                """Safely retrieve value from frame data list at given index."""
                lst = frame_data.get(key, [])
                return lst[idx] if 0 <= idx < len(lst) else default

            # Get values for current frame
            adv_angle = _safe_get("advancing_contact_angles", index, float("nan"))
            rec_angle = _safe_get("receding_contact_angles", index, float("nan"))
            width_mm = _safe_get("rect_width_mm", index, float("nan"))
            height_mm = _safe_get("rect_height_mm", index, float("nan"))
            ellipse_diameter_mm = _safe_get("ellipse_diameter_mm", index, float("nan"))
            area_diameter_mm = _safe_get("area_diameter_mm", index, float("nan"))
            velocity = _safe_get("velocity", index, float("nan"))
            area_mm2 = _safe_get("area_mm2", index, float("nan"))

            # Update overlay labels with numeric values
            self.update_from_numeric_data(
                adv_angle,
                rec_angle,
                width_mm,
                height_mm,
                ellipse_diameter_mm,
                area_diameter_mm,
                velocity,
                area_mm2,
            )

        except Exception as e:
            logger.error(f"Error updating overlay from frame data: {e}")
            self._set_defaults()

    def reset_to_defaults(self) -> None:
        """Reset all labels to default values."""
        self._set_defaults()

    def _get_latest_value(self, key: str, result_images: dict, result_lists: dict):
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


class PreviewCanvas(QWidget):
    """Canvas widget for displaying analysis results with stats overlay toggle.

    This widget provides:
    - Image display canvas with proper scaling
    - Statistics overlay toggle button
    - Automatic resize handling
    - OpenCV to Qt image conversion

    Parameters
    ----------
    parent : QWidget | None, optional
        Parent widget, by default None
    on_stats_toggle : callable | None, optional
        Callback function when stats icon is clicked, by default None
        Should return bool indicating new visibility state

    """

    def __init__(
        self,
        parent: QWidget | None = None,
        on_stats_toggle: Callable[[], bool] | None = None,
    ):
        """Initialize the PreviewCanvas widget."""
        super().__init__(parent)

        # Store callback
        self._on_stats_toggle = on_stats_toggle
        self._stats_overlay_visible = True

        # Set up widget properties
        self.setMinimumSize(400, 140)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # Create canvas label for image display
        self.canvas = QLabel(self)
        self.canvas.setAlignment(Qt.AlignCenter)
        self.canvas.setText("Result")
        self.canvas.setFrameShape(QFrame.Box)
        self.canvas.setFrameShadow(QFrame.Sunken)
        self.canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # Create stats icon button
        self.stats_icon_btn = self._create_stats_icon_button()

        # Position stats icon at top-left initially
        self.stats_icon_btn.move(10, 10)

        # Make stats icon always on top
        self.stats_icon_btn.raise_()

        # Reference to image slider (will be set externally)
        self.image_slider = None

    def _create_stats_icon_button(self) -> QPushButton:
        """Create the stats icon button with custom bar chart icon.

        Returns
        -------
        QPushButton
            Configured stats toggle button with icon

        """
        btn = QPushButton(self)

        # Create custom bar chart icon
        icon_size = 24
        pixmap = QPixmap(icon_size, icon_size)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        # Use a much lighter color for the bars (almost white)
        painter.setBrush(QColor(230, 230, 230))
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

        btn.setIcon(QIcon(pixmap))
        btn.setFixedSize(32, 32)
        btn.setStyleSheet(
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
        btn.setToolTip("Toggle statistics overlay")
        btn.clicked.connect(self._handle_stats_toggle)

        return btn

    def _handle_stats_toggle(self) -> None:
        """Handle stats icon button click."""
        if self._on_stats_toggle:
            # Call callback and get new visibility state
            is_visible = self._on_stats_toggle()
            self._stats_overlay_visible = is_visible
            self._update_icon_position()

    def _update_icon_position(self) -> None:
        """Update stats icon position based on overlay visibility."""
        if self._stats_overlay_visible:
            # Position icon to the right of the overlay when open
            self.stats_icon_btn.move(260, 10)  # 250px overlay width + 10px margin
        else:
            # Move icon back to top-left when overlay is closed
            self.stats_icon_btn.move(10, 10)

    def set_stats_overlay_visible(self, visible: bool) -> None:
        """Set the stats overlay visibility state.

        This method should be called when the overlay visibility changes
        externally (not via the button click).

        Parameters
        ----------
        visible : bool
            Whether the overlay is visible

        """
        self._stats_overlay_visible = visible
        self._update_icon_position()

    def display_image(self, img: np.ndarray | None) -> None:
        """Display an OpenCV image in the canvas properly scaled to fit.

        Parameters
        ----------
        img : np.ndarray | None
            OpenCV image to display (BGR or grayscale format)

        """
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
            canvas_width = self.canvas.width()
            canvas_height = self.canvas.height()

            # Check if the canvas has a valid size
            if canvas_width <= 1 or canvas_height <= 1:
                # Use the minimum size as fallback
                canvas_width = self.canvas.minimumWidth()
                canvas_height = self.canvas.minimumHeight()

            # Scale the image to fit within the canvas while maintaining aspect ratio
            if w > 0 and h > 0 and canvas_width > 0 and canvas_height > 0:
                scaled_pixmap = pixmap.scaled(
                    canvas_width,
                    canvas_height,
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation,
                )
                self.canvas.setPixmap(scaled_pixmap)
            else:
                # Fallback if dimensions are invalid
                self.canvas.setPixmap(pixmap)

            # Center the image in the canvas
            self.canvas.setAlignment(Qt.AlignCenter)

        except Exception as e:
            logger.error(f"Failed to display image in canvas: {e}")

    def get_canvas_label(self) -> QLabel:
        """Get the internal canvas QLabel widget.

        This is provided for backward compatibility with code that needs
        direct access to the canvas label.

        Returns
        -------
        QLabel
            The canvas label widget

        """
        return self.canvas

    def set_image_slider(self, slider: QWidget) -> None:
        """Set the image slider widget to be positioned at the bottom.

        Parameters
        ----------
        slider : QWidget
            The image slider widget to position

        """
        self.image_slider = slider
        self._position_image_slider()

    def _position_image_slider(self) -> None:
        """Position the image slider at the bottom of the canvas."""
        if not self.image_slider:
            return

        canvas_width = self.width()
        canvas_height = self.height()
        slider_height = self.image_slider.height()

        # Position at bottom with 10px margin from sides and bottom
        margin = 10
        self.image_slider.setGeometry(
            margin,
            canvas_height - slider_height - margin,
            canvas_width - (2 * margin),
            slider_height,
        )
        self.image_slider.raise_()

    def resizeEvent(self, event) -> None:  # noqa: N802
        """Handle resize events to maintain proper layout.

        Parameters
        ----------
        event : QResizeEvent
            The resize event

        """
        # Resize canvas to fill the entire widget
        self.canvas.setGeometry(self.rect())

        # Update icon position based on current overlay state
        self._update_icon_position()

        # Ensure icon stays on top
        self.stats_icon_btn.raise_()

        # Position image slider at bottom
        self._position_image_slider()

        super().resizeEvent(event)
