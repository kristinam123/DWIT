"""Parameter panel widgets for the DWIT application."""

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QLocale, Qt
from PySide6.QtGui import QValidator
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QGridLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from src.utilities.core_utils import get_logger

logger = get_logger(__name__)


class FlexibleDoubleSpinBox(QDoubleSpinBox):
    """QDoubleSpinBox that accepts both comma and dot as decimal separators.

    This helps users in locales where comma is the decimal separator and
    also accepts pasted values with commas.
    """

    def validate(self, text, pos):
        """Validate input, accepting both comma and dot as decimal separators."""
        # Normalize comma to dot for validation
        t = text.replace(",", ".")
        # Allow empty and partial input
        if t in ("", "-", "+"):
            return QValidator.Intermediate
        try:
            float(t)
            return QValidator.Acceptable
        except Exception:
            return QValidator.Invalid

    def valueFromText(self, text: str) -> float:  # noqa: N802
        """Convert text to float, accepting both comma and dot as decimal separators."""
        # Replace comma with dot and try parsing as float
        t = text.replace(",", ".")
        try:
            return float(t)
        except Exception:
            # Fall back to base implementation which uses locale
            return super().valueFromText(text)


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

        # Style the header button to ensure left alignment and add focus color
        self.header_btn.setStyleSheet(
            """
            QPushButton {
                text-align: left;
            }
            QPushButton:focus {
                background-color: #2d8cf0;
                color: white;
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
        arrow = "▲" if not self.collapsed else "▶"
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


class ParameterPanel(QWidget):
    """Parameter configuration panel with collapsible sections.

    This widget provides a comprehensive parameter configuration interface
    with collapsible dropdown groups for:
    - Video Calibration (FPS, Pixel, Threshold, Rotation)
    - Region of Interest (ROI)
    - Baseline settings
    - Angle Method (fitting mode)

    Parameters
    ----------
    parent : QWidget | None, optional
        Parent widget, by default None
    controller : Any
        Controller object with analysis parameters
    on_preview_trigger : Callable[[str | None], None] | None, optional
        Callback when parameter changes (receives parameter type)
    on_roi_select : Callable[[], None] | None, optional
        Callback when "Select Visually" ROI button is clicked
    on_reset_defaults : Callable[[], None] | None, optional
        Callback when "Reset to Default" button is clicked

    """

    def __init__(
        self,
        parent: QWidget | None = None,
        controller: Any = None,
        on_preview_trigger: Callable[[str | None], None] | None = None,
        on_roi_select: Callable[[], None] | None = None,
        on_reset_defaults: Callable[[], None] | None = None,
    ):
        """Initialize the ParameterPanel widget."""
        super().__init__(parent)

        # Store references
        self.controller = controller
        self._on_preview_trigger = on_preview_trigger
        self._on_roi_select = on_roi_select
        self._on_reset_defaults = on_reset_defaults

        # Create main layout
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(4)

        # Create parameter groups
        self._create_video_calibration_group()
        self._create_roi_group()
        self._create_baseline_group()
        self._create_angle_method_group()
        self._create_reset_button()

        # Add stretch to push all widgets to the top
        self.main_layout.addStretch(1)

        # Initialize states
        self._initialize_ui_states()

    def _create_video_calibration_group(self) -> None:
        """Create Video Calibration collapsible group."""
        self.video_calibration_group = CollapsibleGroupBox(
            "Video Calibration", collapsed=True
        )

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
        self.PIXEL_entry = FlexibleDoubleSpinBox()
        self.PIXEL_entry.setRange(0, 100)
        self.PIXEL_entry.setSingleStep(0.01)
        try:
            self.PIXEL_entry.setLocale(QLocale.system())
        except Exception:
            pass
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
            lambda: self._trigger_preview("threshold")
        )
        grid_layout.addWidget(threshold_label, 2, 0, Qt.AlignLeft)
        grid_layout.addWidget(self.threshold_entry, 2, 1, Qt.AlignRight)

        # Rotate (hidden in packing and free sedimentation modes)
        rotate_label = QLabel("Rotate:")
        rotate_label.setAlignment(Qt.AlignLeft)
        self.rotate_angle_entry = FlexibleDoubleSpinBox()
        self.rotate_angle_entry.setRange(-360, 360)
        self.rotate_angle_entry.setSingleStep(0.1)
        try:
            self.rotate_angle_entry.setLocale(QLocale.system())
        except Exception:
            pass
        self.rotate_angle_entry.setValue(self.controller.rotate_angle)
        self.rotate_angle_entry.setFixedWidth(100)
        self.rotate_angle_entry.setAlignment(Qt.AlignRight)
        self.rotate_angle_entry.valueChanged.connect(self.controller.set_rotate_angle)
        self.rotate_angle_entry.valueChanged.connect(
            lambda: self._trigger_preview("rotation")
        )

        # Store rotate widgets for conditional hiding
        self.rotate_label = rotate_label

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
        self.main_layout.addWidget(self.video_calibration_group)

    def _create_roi_group(self) -> None:
        """Create Region of Interest collapsible group."""
        self.roi_group = CollapsibleGroupBox("Region of Interest", collapsed=True)

        # Select ROI Visually button (full width)
        roi_button = QPushButton("Select Visually")
        roi_button.setToolTip("Select region of interest visually")
        roi_button.clicked.connect(self._handle_roi_select)
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
        self.left_roi_spinbox.valueChanged.connect(lambda: self._trigger_preview("roi"))
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
            lambda: self._trigger_preview("roi")
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
        self.top_roi_spinbox.valueChanged.connect(lambda: self._trigger_preview("roi"))
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
            lambda: self._trigger_preview("roi")
        )
        grid_layout.addWidget(bottom_label, 3, 0, Qt.AlignLeft)
        grid_layout.addWidget(self.bottom_roi_spinbox, 3, 1, Qt.AlignRight)

        # Set column stretches for proper alignment
        grid_layout.setColumnStretch(0, 1)  # Labels expand
        grid_layout.setColumnStretch(1, 0)  # Controls fixed width

        self.roi_group.add_widget(grid_widget)
        self.main_layout.addWidget(self.roi_group)

    def _create_baseline_group(self) -> None:
        """Create Baseline collapsible group."""
        self.baseline_group = CollapsibleGroupBox("Baseline", collapsed=True)

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
            lambda: self._trigger_preview("baseline_offset")
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
            lambda: self._trigger_preview("baseline")
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
            lambda: self._trigger_preview("baseline")
        )
        grid_layout.addWidget(manual_height_label, 2, 0, Qt.AlignLeft)
        grid_layout.addWidget(self.manual_baseline_entry, 2, 1, Qt.AlignRight)

        # Set column stretches for proper alignment
        grid_layout.setColumnStretch(0, 1)  # Labels expand
        grid_layout.setColumnStretch(1, 0)  # Controls fixed width

        self.baseline_group.add_widget(grid_widget)

        # Hide baseline in certain modes
        analysis_mode = getattr(self.controller, "analysis_mode", "")
        if analysis_mode in ["free_sedimentation", "structured_packing"]:
            self.baseline_group.hide()
        else:
            self.main_layout.addWidget(self.baseline_group)

    def _create_angle_method_group(self) -> None:
        """Create Angle Method collapsible group."""
        self.angle_method_group = CollapsibleGroupBox("Angle Method", collapsed=True)

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
            lambda: self._trigger_preview("fitting")
        )
        grid_layout.addWidget(deg_label, 1, 0, Qt.AlignLeft)
        grid_layout.addWidget(self.polynom_entry_spin, 1, 1, Qt.AlignRight)

        # Set column stretches for proper alignment
        grid_layout.setColumnStretch(0, 1)  # Labels expand
        grid_layout.setColumnStretch(1, 0)  # Controls fixed width

        self.angle_method_group.add_widget(grid_widget)

        # Conditionally hide for certain modes
        analysis_mode = getattr(self.controller, "analysis_mode", "")
        if analysis_mode in ["free_sedimentation", "structured_packing"]:
            self.angle_method_group.hide()
        else:
            self.main_layout.addWidget(self.angle_method_group)

    def _create_reset_button(self) -> None:
        """Create Reset to Default button."""
        self.reset_defaults_btn = QPushButton("Reset to Default")
        self.reset_defaults_btn.setToolTip(
            "Reset parameters to mode-specific default values and load test folder"
        )
        self.reset_defaults_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.reset_defaults_btn.clicked.connect(self._handle_reset_defaults)
        self.main_layout.addWidget(self.reset_defaults_btn)

    def _initialize_ui_states(self) -> None:
        """Initialize UI control states."""
        # Initialize baseline checkbox state
        self._on_baseline_checkbox_change()

        # Initialize fitting mode state
        self._on_fitting_mode_changed()

    def _trigger_preview(self, param_type: str | None = None) -> None:
        """Trigger preview update callback.

        Parameters
        ----------
        param_type : str | None
            Type of parameter that changed

        """
        if self._on_preview_trigger:
            self._on_preview_trigger(param_type)

    def _handle_roi_select(self) -> None:
        """Handle ROI visual selection button click."""
        if self._on_roi_select:
            self._on_roi_select()

    def _handle_reset_defaults(self) -> None:
        """Handle Reset to Default button click."""
        if self._on_reset_defaults:
            self._on_reset_defaults()

    def _on_baseline_checkbox_change(self) -> None:
        """Handle baseline checkbox state change."""
        is_checked = self.Baseline_tf_checkbox.isChecked()

        try:
            # manual_baseline_entry enabled when manual baseline is checked
            if hasattr(self, "manual_baseline_entry"):
                self.manual_baseline_entry.setEnabled(is_checked)

            # baseline_entry disabled when manual baseline is checked
            if hasattr(self, "baseline_entry"):
                self.baseline_entry.setEnabled(not is_checked)
        except Exception:
            logger.exception("Failed toggling baseline controls")

    def _on_fitting_mode_changed(self, *args) -> None:
        """Enable degree spinbox only when fitting mode is 'Polynom'."""
        try:
            mode_text = ""

            # Prefer controller value
            try:
                mode_text = str(getattr(self.controller, "fitting_mode", ""))
            except Exception:
                mode_text = ""

            # Fallback to combobox text
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
            logger.exception("Failed toggling polynom degree control")

    def initialize_roi_spinboxes(self, x: int, y: int, w: int, h: int) -> None:
        """Initialize ROI spinboxes with values.

        Parameters
        ----------
        x : int
            Left coordinate
        y : int
            Top coordinate
        w : int
            Right coordinate
        h : int
            Bottom coordinate

        """
        # Block signals to prevent triggering valueChanged
        self.left_roi_spinbox.blockSignals(True)
        self.right_roi_spinbox.blockSignals(True)
        self.top_roi_spinbox.blockSignals(True)
        self.bottom_roi_spinbox.blockSignals(True)

        # Set values
        self.left_roi_spinbox.setValue(x)
        self.right_roi_spinbox.setValue(w)
        self.top_roi_spinbox.setValue(y)
        self.bottom_roi_spinbox.setValue(h)

        # Re-enable signals
        self.left_roi_spinbox.blockSignals(False)
        self.right_roi_spinbox.blockSignals(False)
        self.top_roi_spinbox.blockSignals(False)
        self.bottom_roi_spinbox.blockSignals(False)
