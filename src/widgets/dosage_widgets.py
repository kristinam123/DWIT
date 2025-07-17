"""Dosage GUI widgets for experiment setup and control in MesszelleApp."""

from PySide6.QtCore import Qt, QTimer, Slot
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from src.threads.dosage_threads import DosageButtonThread
from src.utilities.logging_manager import get_logger

# Setup logger for this module
logger = get_logger(__name__)


class DosageGUI(QWidget):
    """Modern dosage control interface with improved layout and feedback."""

    # Remove port coordination signals

    def __init__(self, parent, controller):
        """Initialize the DosageGUI with parent and controller."""
        logger.info("Initializing DosageGUI")
        super().__init__(parent)
        self.controller = controller
        self.max_steps = 2085  # Maximum steps for progress calculation
        self.current_port = ""  # Track currently selected port
        self.parent_refresh_callback = (
            None  # Will hold reference to parent refresh method
        )

        # Create UI components
        self._create_widgets()

        # Don't call _populate_ports directly in initialization
        # Instead, use a timer to delay it slightly but only once
        QTimer.singleShot(500, self._safe_populate_ports)

        # Connect port signals with a delay
        QTimer.singleShot(800, self._connect_signals)

        # Thread reference
        self.button_thread = None
        logger.info("DosageGUI initialization completed")

    def _safe_populate_ports(self):
        """Safely populate ports with proper error handling."""
        try:
            self._populate_ports()

            # Check if no port is initially selected and disable widgets if needed
            if not self.dosage_port_combobox.currentText():
                self._toggle_widget_state(enabled=False)
                # Keep the port combobox enabled
        #                 self.dosage_port_combobox.setEnabled(True)
        except Exception as e:
            logger.error(f"Error populating ports: {e}")
            pass

    def _create_widgets(self):
        """Create and arrange all UI widgets."""
        # Set size policy for consistent width handling
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(5)
        main_layout.setContentsMargins(5, 5, 5, 5)

        # Add title bar with "Dosage" title and port selection on the right
        title_bar = QHBoxLayout()
        title_bar.setSpacing(5)

        # Title label with standard font
        title_label = QLabel("Dosage")
        title_label.setStyleSheet("font-weight: bold;")
        title_label.setToolTip("Dosage control panel for the experiment.")
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
        port_label.setToolTip("Select the serial port for the dosage device.")
        port_row_layout.addWidget(port_label)

        self.dosage_port_combobox = QComboBox()
        self.dosage_port_combobox.setMinimumWidth(120)
        self.dosage_port_combobox.setToolTip(
            "Available COM ports for the dosage device."
        )
        port_row_layout.addWidget(self.dosage_port_combobox)

        # Add port row to port section
        port_section_layout.addLayout(port_row_layout)

        # Action buttons row under port selection
        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(5)

        # Initialize button
        self.init_button = QPushButton("Initialize")
        self.init_button.setToolTip(
            "Initialize the dosage device and prepare for operation."
        )
        buttons_layout.addWidget(self.init_button)

        # Now add Inject and Refill buttons
        self.inject_button = QPushButton("Inject")
        self.inject_button.setToolTip("Start the injection process.")
        buttons_layout.addWidget(self.inject_button)

        self.refill_button = QPushButton("Refill")
        self.refill_button.setToolTip("Refill the dosage device.")
        buttons_layout.addWidget(self.refill_button)

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

        # Control panel
        control_group = QWidget()
        control_layout = QFormLayout(control_group)
        control_layout.setContentsMargins(5, 5, 5, 5)

        # Create progress bar
        self.steps_progress_bar = QProgressBar()
        self.steps_progress_bar.setRange(0, self.max_steps)
        self.steps_progress_bar.setValue(0)
        self.steps_progress_bar.setTextVisible(True)
        self.steps_progress_bar.setFixedHeight(20)
        self.steps_progress_bar.setToolTip(
            "Shows the progress of the current dosage operation."
        )
        progress_label = QLabel("Progress:")
        progress_label.setToolTip("Shows the progress of the current dosage operation.")
        control_layout.addRow(progress_label, self.steps_progress_bar)

        # Create the steps spinbox
        self.steps_spinbox = QSpinBox()
        self.steps_spinbox.setRange(1, self.max_steps)
        self.steps_spinbox.setValue(int(self.controller.steps_value))
        # Set alignment for consistency
        self.steps_spinbox.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        # Add suffix for consistency
        self.steps_spinbox.setSuffix(" steps")
        self.steps_spinbox.setToolTip(
            "Set the number of steps for the dosage operation."
        )

        # Label for steps with proper formatting
        self.steps_left_label = QLabel("0")
        self.steps_left_label.setVisible(False)  # Hidden tracking label

        # Add steps with clear label
        steps_label = QLabel("Steps:")
        steps_label.setToolTip("Set the number of steps for the dosage operation.")
        control_layout.addRow(steps_label, self.steps_spinbox)

        # Add time spinbox
        self.time_spinbox = QSpinBox()
        self.time_spinbox.setRange(4, 40)
        self.time_spinbox.setValue(int(self.controller.time_value))
        # Set alignment for consistency
        self.time_spinbox.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        # Add suffix for clarity
        self.time_spinbox.setSuffix(" (0.1s)")
        self.time_spinbox.setToolTip(
            "Set the time per stroke in tenths of a second (e.g., 10 = 1s)."
        )
        time_label = QLabel("Time per stroke:")
        time_label.setToolTip(
            "Set the time per stroke in tenths of a second (e.g., 10 = 1s)."
        )
        control_layout.addRow(time_label, self.time_spinbox)

        # Add control panel to the main layout
        main_layout.addWidget(control_group)

        # Add stretch to push everything up
        main_layout.addStretch(1)

        # Connect signals
        self.dosage_port_combobox.currentTextChanged.connect(self._on_port_selected)
        self.init_button.clicked.connect(lambda: self.threaded_button("Init."))
        self.inject_button.clicked.connect(lambda: self.threaded_button("Inject"))
        self.refill_button.clicked.connect(lambda: self.threaded_button("Refill"))
        self.steps_spinbox.valueChanged.connect(self.controller.set_steps_value)
        self.time_spinbox.valueChanged.connect(self.controller.set_time_value)

        # Set initial widget states
        self._toggle_widget_state(enabled=self.controller.widget_state)

    # All other methods remain the same
    def _toggle_widget_state(self, enabled=None):
        """Enable or disable interactive widgets."""
        if enabled is not None:
            self.controller.widget_state = enabled
        else:
            self.controller.widget_state = not self.controller.widget_state

    def refresh_ports(self, ports=None):
        """Public method to refresh ports that syncs with other widgets."""
        try:
            if self.parent_refresh_callback:
                # Use parent's central refresh method to update all ports
                self.parent_refresh_callback()
            else:
                # Fallback to local refresh if parent callback not available
                self._refresh_ports_internal(ports)
        except Exception as e:
            logger.error(f"Error refreshing ports: {e}")
            pass

    def refresh_ports_internal(self, ports=None):
        """Refresh only this widget's ports."""
        try:
            if ports is None:
                try:
                    ports, _ = self.controller.populate_ports()
                except Exception as e:
                    logger.error(f"Error refreshing ports: {e}")
                    return

            # Save current selection if exists
            current_port = self.dosage_port_combobox.currentText()

            # Block signals to prevent triggering selection change during refresh
            self.dosage_port_combobox.blockSignals(True)
            try:
                self.dosage_port_combobox.clear()
                self.dosage_port_combobox.addItems(ports)

                # Restore selection if possible
                if current_port in ports:
                    self.dosage_port_combobox.setCurrentText(current_port)
            finally:
                # Ensure signals are unblocked even if an exception occurs
                self.dosage_port_combobox.blockSignals(False)

        except Exception as e:
            logger.error(f"Error refreshing ports: {e}")
            pass

    def _populate_ports(self):
        """Refresh and populate the available COM ports."""
        try:
            # Call refresh through parent to sync both widgets
            if self.parent_refresh_callback:
                self.parent_refresh_callback()
            else:
                # Fallback to local refresh
                self._refresh_ports_internal()
        except Exception as e:
            logger.error(f"Error populating ports: {e}")
            pass

    def _on_port_selected(self, port):
        """Handle port selection changes."""
        logger.info(f"Port selection changed to: {port}")
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
                #                 self.dosage_port_combobox.setEnabled(True)

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
            #             self.dosage_port_combobox.setEnabled(True)

            # Auto-refresh ports list after error
            QTimer.singleShot(200, self.refresh_ports)

    def _connect_signals(self):
        """Connect controller signals to UI handlers."""
        self.controller.port_changed.connect(self._on_port_changed)

    def _on_port_changed(self, port):
        """Update UI when port changes from controller side."""
        if port != self.dosage_port_combobox.currentText():
            self._populate_ports()
            self.dosage_port_combobox.setCurrentText(port)

    def threaded_button(self, button_type):
        """Start a threaded operation for the selected action."""
        logger.info(f"Starting threaded dosage operation: {button_type}")
        # Disable buttons during operation
        self._toggle_widget_state(enabled=False)

        # Create and configure thread
        self.button_thread = DosageButtonThread(
            self.controller,
            button_type,
            self.controller.steps_value,
            self.controller.time_value,
        )

        # Connect signals
        self.button_thread.finished.connect(self._on_button_operation_finished)
        self.button_thread.steps_left_update.connect(self._update_steps_left)

        # Start the thread

        self.button_thread.start()

    @Slot(str)
    def _update_steps_left(self, value):
        """Update the steps left indicator."""
        try:
            # Update the hidden numeric display for tracking
            self.steps_left_label.setText(value)

            # Update the steps label with current/total format
            steps_value = int(value)
            self.steps_label.setText(f"Steps ({steps_value} / {self.max_steps}):")

            # Update progress bar
            self.steps_progress_bar.setValue(steps_value)

            # Change color based on progress
            progress_percentage = (steps_value / self.max_steps) * 100
            if progress_percentage > 66:
                color = "#4CAF50"  # Green
            elif progress_percentage > 33:
                color = "#FFC107"  # Yellow/amber
            else:
                color = "#F44336"  # Red

            # Update progress bar color
            self.steps_progress_bar.setStyleSheet(
                f"""
                QProgressBar#steps-progress {{
                    border: 1px solid #CCCCCC;
                    border-radius: 5px;
                    background-color: #F0F0F0;
                    text-align: center;
                }}
                QProgressBar#steps-progress::chunk {{
                    background-color: {color};
                    border-radius: 5px;
                }}
            """
            )
        except ValueError:
            # Handle non-integer values
            pass

    @Slot()
    def _on_button_operation_finished(self):
        """Handle completion of threaded operation."""
        logger.info("Dosage operation completed, re-enabling UI")
        self._toggle_widget_state(enabled=True)
