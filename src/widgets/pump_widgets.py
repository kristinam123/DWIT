"""Pump GUI widgets for experiment control in MesszelleApp."""

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from src.utilities.logging_manager import get_logger

# Constants
MIN_FLOW_LPH = 0
MAX_FLOW_LPH = 88
MIN_FLOW_HZ = 0
MAX_FLOW_HZ = 40
LPH_TO_HZ_RATIO = 2.2  # Conversion factor from L/h to Hz


# Setup logger for this module
logger = get_logger(__name__)


class PumpGUI(QWidget):
    """Modern pump control interface with improved layout and feedback."""

    def __init__(self, parent, controller):
        """Initialize the PumpGUI with parent and controller."""
        logger.debug("Initializing PumpGUI")
        super().__init__(parent)
        self.controller = controller
        self.widget_state = True
        self.slidespin_value = 0
        self.current_unit = "L/h"  # Default unit
        self.current_port = ""  # Track currently selected port
        self.parent_refresh_callback = (
            None  # Will hold reference to parent refresh method
        )

        # Setup UI
        self._setup_ui()

        QTimer.singleShot(500, self._safe_populate_ports)
        logger.debug("PumpGUI initialization completed")

        # Create but don't start timer - disable automatic refreshes for stability
        self.port_refresh_timer = QTimer(self)
        self.port_refresh_timer.timeout.connect(self._populate_ports)
        # Don't start automatic refresh - rely on manual refresh only

    def _safe_populate_ports(self):
        """Safely populate ports with proper error handling."""
        try:
            self._populate_ports()

            # Check if no port is initially selected and disable widgets if needed
            if not self.pump_port_combobox.currentText():
                self._toggle_widget_state(enabled=False)
        #                 self.pump_port_combobox.setEnabled(True)
        except Exception as e:
            logger.error(f"Error populating ports: {e}")
            pass

    def _setup_ui(self):
        """Create and arrange UI elements."""
        # Set size policy for consistent sizing
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(5)
        main_layout.setContentsMargins(5, 5, 5, 5)

        # Add title bar with "Pump" title and port selection on the right
        title_bar = QHBoxLayout()
        title_bar.setSpacing(5)

        # Title label with standard font
        title_label = QLabel("Pump")
        title_label.setStyleSheet("font-weight: bold;")
        title_label.setToolTip("Pump control panel for the experiment.")
        title_bar.addWidget(title_label)

        # Stretch to push port selection to the right
        title_bar.addStretch(1)

        # Port selection layout - vertical to include buttons below
        port_section_layout = QVBoxLayout()
        port_section_layout.setSpacing(5)

        # Port selection row
        port_row_layout = QHBoxLayout()
        port_row_layout.setSpacing(5)

        port_label = QLabel("COM Port:")
        port_label.setToolTip("Select the serial port for the pump device.")
        port_row_layout.addWidget(port_label)

        self.pump_port_combobox = QComboBox()
        self.pump_port_combobox.setMinimumWidth(120)
        self.pump_port_combobox.setToolTip("Available COM ports for the pump device.")
        port_row_layout.addWidget(self.pump_port_combobox)

        # Add port row to port section
        port_section_layout.addLayout(port_row_layout)

        # Action buttons row under port selection
        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(5)

        self.apply_button = QPushButton("Apply")
        self.apply_button.setToolTip("Apply the selected flow rate to the pump.")
        buttons_layout.addWidget(self.apply_button)

        self.stop_button = QPushButton("Stop")
        self.stop_button.setToolTip("Stop the pump (set flow rate to zero).")
        buttons_layout.addWidget(self.stop_button)

        # Add buttons row to port section
        port_section_layout.addLayout(buttons_layout)

        # Add port section to title bar
        title_bar.addLayout(port_section_layout)

        # Add title bar to main layout
        main_layout.addLayout(title_bar)

        # Add separator line
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setFrameShadow(QFrame.Sunken)
        main_layout.addWidget(separator)

        # Flow rate panel
        control_group = QWidget()
        control_layout = QFormLayout(control_group)
        control_layout.setContentsMargins(5, 5, 5, 5)

        # Unit selection - make more compact
        unit_layout = QHBoxLayout()
        unit_layout.setSpacing(5)
        self.unit_group = QButtonGroup(self)

        # L/h radio button
        self.lph_radio = QRadioButton("L/h")
        self.lph_radio.setChecked(True)  # Default to L/h
        self.lph_radio.setToolTip("Set flow rate in liters per hour (L/h).")
        self.unit_group.addButton(self.lph_radio)
        unit_layout.addWidget(self.lph_radio)

        # Hz radio button
        self.hz_radio = QRadioButton("Hz")
        self.hz_radio.setToolTip("Set flow rate in Hertz (Hz).")
        self.unit_group.addButton(self.hz_radio)
        unit_layout.addWidget(self.hz_radio)

        # Add unit selection to layout
        unit_label = QLabel("Unit:")
        unit_label.setToolTip(
            "Select the unit for the flow rate: liters per hour (L/h) or Hertz (Hz)."
        )
        control_layout.addRow(unit_label, unit_layout)

        # Connect unit change signals
        self.lph_radio.toggled.connect(self._on_unit_changed)
        self.hz_radio.toggled.connect(self._on_unit_changed)

        # Flow rate input with label
        self.setpoint_spinbox = QDoubleSpinBox()
        self.setpoint_spinbox.setMinimum(MIN_FLOW_LPH)
        self.setpoint_spinbox.setMaximum(MAX_FLOW_LPH)
        self.setpoint_spinbox.setValue(self.slidespin_value)
        self.setpoint_spinbox.setDecimals(1)
        self.setpoint_spinbox.setSingleStep(0.1)
        # Set alignment for consistency
        self.setpoint_spinbox.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        # Set suffix to show unit in spinbox
        self.setpoint_spinbox.setSuffix(" L/h")
        self.setpoint_spinbox.setToolTip(
            "Set the desired flow rate for the pump. Unit depends on selection above."
        )
        flowrate_label = QLabel("Flow Rate:")
        flowrate_label.setToolTip("Set the desired flow rate for the pump.")
        control_layout.addRow(flowrate_label, self.setpoint_spinbox)

        # Add panel to the main layout
        main_layout.addWidget(control_group)

        # Add stretch to push everything up
        main_layout.addStretch(1)

        # Connect signals
        self.pump_port_combobox.currentTextChanged.connect(self._on_port_selected)
        self.apply_button.clicked.connect(self.update_setpoint)
        self.stop_button.clicked.connect(self.stop)
        self.controller.port_changed.connect(self._on_port_changed)

    def _toggle_widget_state(self, enabled=None):
        """Enable or disable interactive widgets."""
        if enabled is not None:
            self.widget_state = enabled
        else:
            self.widget_state = not self.widget_state

    #         self.stop_button.setEnabled(self.widget_state)
    #         self.apply_button.setEnabled(self.widget_state)
    #         self.setpoint_spinbox.setEnabled(self.widget_state)
    #         self.pump_port_combobox.setEnabled(self.widget_state)
    #         self.lph_radio.setEnabled(self.widget_state)
    #         self.hz_radio.setEnabled(self.widget_state)

    def refresh_ports(self, ports=None):
        """Refresh ports and trigger parent refresh to sync both widgets."""
        try:
            if self.parent_refresh_callback:
                # Use parent's central refresh method to update all ports
                self.parent_refresh_callback()
            else:
                # Fallback to local refresh if parent callback not available
                self.refresh_ports_internal(ports)
        except Exception as e:
            logger.error(f"Error refreshing ports: {e}")
            pass

    def refresh_ports_internal(self, ports=None):
        """Refresh only this widget's ports."""
        try:
            if ports is None:
                try:
                    ports = self.controller.get_available_ports()
                except Exception as e:
                    logger.error(f"Error refreshing ports: {e}")
                    return

            current_port = self.pump_port_combobox.currentText()

            # Block signals to prevent triggering selection change during refresh
            self.pump_port_combobox.blockSignals(True)
            try:
                self.pump_port_combobox.clear()
                self.pump_port_combobox.addItems(ports)

                # Try to restore previously selected port if still in dropdown
                if current_port in ports:
                    self.pump_port_combobox.setCurrentText(current_port)
            finally:
                # Ensure signals are unblocked even if an exception occurs
                self.pump_port_combobox.blockSignals(False)

        except Exception as e:
            logger.error(f"Error refreshing ports: {e}")
            pass

    # Update _populate_ports to use the internal method
    def _populate_ports(self):
        """Fill port dropdown with available ports."""
        try:
            # Call refresh through parent to sync both widgets
            if self.parent_refresh_callback:
                self.parent_refresh_callback()
            else:
                # Fallback to local refresh
                self.refresh_ports_internal()
        except Exception as e:
            logger.error(f"Error populating ports: {e}")
            pass

    def _on_port_changed(self, port):
        """Update UI when port changes from controller side."""
        if port != self.pump_port_combobox.currentText():
            self.refresh_ports()
            self.pump_port_combobox.setCurrentText(port)

    def _on_port_selected(self, port):
        """Handle port selection."""
        logger.info(f"Pump port selection changed to: {port}")
        try:
            # If we had a port selected before, release it
            old_port = self.current_port
            if old_port and old_port != port and hasattr(self.controller, "close_port"):
                self.controller.close_port()  # Make sure to close the old port

            self.current_port = port

            # Rest of the method unchanged
            if not port:

                # Disable all interactive elements but keep the port combobox enabled
                self._toggle_widget_state(enabled=False)
                # Keep the port combobox enabled
                #                 self.pump_port_combobox.setEnabled(True)

                # Auto-refresh ports list after changing selection
                QTimer.singleShot(200, self.refresh_ports)
                return

            # Attempt to set the port in the controller
            success = self.controller.set_port(port)
            if not success:
                self.current_port = ""  # Clear current port on failure

                # Auto-refresh ports list after failed attempt
                QTimer.singleShot(200, self.refresh_ports)
            else:
                # No longer need to notify other components
                self._toggle_widget_state(enabled=True)

                # Auto-refresh ports list after successful connection
                QTimer.singleShot(200, self.refresh_ports)
        except Exception as e:
            logger.error(f"Error selecting port: {e}")
            self.current_port = ""
            self._toggle_widget_state(enabled=False)
            #             self.pump_port_combobox.setEnabled(True)

            # Auto-refresh ports list after error
            QTimer.singleShot(200, self.refresh_ports)

    def _on_unit_changed(self, checked):
        """Handle unit change between L/h and Hz."""
        # Only process when a radio button is checked (not when unchecked)
        if not checked:
            return

        # Get current value before changing units
        current_value = self.setpoint_spinbox.value()

        # Determine which unit is now selected
        new_unit = "L/h" if self.lph_radio.isChecked() else "Hz"

        # Only process if unit actually changed
        if new_unit == self.current_unit:
            return

        logger.info(f"Changing pump units from {self.current_unit} to {new_unit}")

        # Convert the current value to the new unit
        if new_unit == "L/h" and self.current_unit == "Hz":
            # Convert from Hz to L/h
            converted_value = current_value * LPH_TO_HZ_RATIO
            self.setpoint_spinbox.setMinimum(MIN_FLOW_LPH)
            self.setpoint_spinbox.setMaximum(MAX_FLOW_LPH)
            # Update suffix to show L/h in the spinbox
            self.setpoint_spinbox.setSuffix(" L/h")
        else:
            # Convert from L/h to Hz
            converted_value = current_value / LPH_TO_HZ_RATIO
            self.setpoint_spinbox.setMinimum(MIN_FLOW_HZ)
            self.setpoint_spinbox.setMaximum(MAX_FLOW_HZ)
            # Update suffix to show Hz in the spinbox
            self.setpoint_spinbox.setSuffix(" Hz")

        # Update the spinbox with the converted value
        self.setpoint_spinbox.setValue(converted_value)

        # Update current unit
        self.current_unit = new_unit

    def _get_lph_value(self):
        """Get the current value in L/h regardless of display unit."""
        if self.current_unit == "L/h":
            return self.setpoint_spinbox.value()
        else:
            # Convert from Hz to L/h
            return self.setpoint_spinbox.value() * LPH_TO_HZ_RATIO

    def update_setpoint(self):
        """Apply the flow rate setpoint to the pump."""
        logger.info(
            f"User clicked 'Apply' button. Requested setpoint: "
            f"{self.setpoint_spinbox.value()} {self.current_unit}"
        )
        try:
            # Always convert to L/h for the controller
            lph_value = self._get_lph_value()

            # Convert to pump value
            _ = self.controller.convert_user_setpoint_to_pump_value(lph_value)

        except Exception as e:
            logger.error(f"Error updating setpoint: {e}")
            pass

    def stop(self):
        """Stop the pump by setting flow rate to zero."""
        logger.info(
            "User clicked 'Stop' button. Stopping pump (setting flow rate to zero)."
        )
        logger.info("Stopping pump by setting flow rate to zero")
        self.setpoint_spinbox.setValue(0)
        self.update_setpoint()
