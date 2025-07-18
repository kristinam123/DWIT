"""Core logic for dosage control in MesszelleApp."""

import time
from typing import Optional

import serial
from PySide6.QtCore import QObject, QSettings, Signal

from src.utilities.logging_manager import get_logger
from src.utilities.port import PortManager, SharedPortManager

# Setup logger for this module
logger = get_logger(__name__)


class DosageCore(QObject):
    """Core functionality for dosage system control via serial connection.

    Handles communication, value management, and port settings.
    """

    steps_value_changed = Signal(int)
    time_value_changed = Signal(int)
    status_changed = Signal(str)
    error_occurred = Signal(str)
    port_changed = Signal(str)  # New signal for port changes

    # Constants
    BAUD_RATE = 9600
    TIMEOUT = 2
    DEFAULT_STEPS = 2085

    # Component name for port management
    COMPONENT_NAME = "dosage"

    def __init__(self):
        """Initialize the DosageCore instance."""
        logger.debug("Initializing DosageCore instance")
        super().__init__()

        try:
            self.widget_state = True
            self.port_manager = PortManager()
            self.shared_port_manager = SharedPortManager()
            self.settings = QSettings("MeasurementCellApp", "Dosage")

            # Load saved settings for steps and time
            self._steps_value = self.settings.value("steps", 1, int)
            self._time_value = self.settings.value("time", 4, int)
            logger.debug(
                f"Loaded saved settings - steps: {self._steps_value}, "
                f"time: {self._time_value}"
            )

            self.com_port = ""

            # Listen for port status changes
            self.shared_port_manager.port_status_changed.connect(
                self._on_port_status_changed
            )

            logger.debug("DosageCore initialization completed successfully")

        except Exception as e:
            logger.error(f"Error during DosageCore initialization: {e}")
            raise

    def _on_port_status_changed(self):
        """Handle changes in port availability."""
        # If our port is now used by another component, release it
        if (
            self.com_port
            and self.com_port
            not in self.shared_port_manager.get_available_ports_for_component(
                self.COMPONENT_NAME, False
            )
        ):
            old_port = self.com_port
            logger.warning(
                f"Port {old_port} is now in use by another component, releasing"
            )
            self.com_port = ""
            self.port_changed.emit("")
            self.error_occurred.emit(
                f"Port {old_port} is now in use by another component"
            )

    # Add the missing property getter and setter methods
    @property
    def steps_value(self) -> int:
        """Return the current steps value."""
        return self._steps_value

    def set_steps_value(self, value: int) -> None:
        """Set the steps value."""
        if self._steps_value != value:
            self._steps_value = value
            try:
                self.settings.setValue("steps", value)
                logger.debug(f"Steps value updated and saved to settings: {value}")
                self.steps_value_changed.emit(value)
            except Exception as e:
                logger.error(f"Error saving steps value to settings: {e}")
                raise

    @property
    def time_value(self) -> int:
        """Return the current time value."""
        return self._time_value

    def set_time_value(self, value: int) -> None:
        """Set the time value."""
        if self._time_value != value:
            self._time_value = value
            try:
                self.settings.setValue("time", value)
                logger.info(f"Time value updated and saved to settings: {value}")
                self.time_value_changed.emit(value)
            except Exception as e:
                logger.error(f"Error saving time value to settings: {e}")
                raise

    def populate_ports(self) -> tuple[list[str], str]:
        """Get available ports.

        Returns
        -------
            list of available ports.

        """
        try:
            available_ports = (
                self.shared_port_manager.get_available_ports_for_component(
                    self.COMPONENT_NAME
                )
            )
            logger.info(
                f"Found {len(available_ports)} available ports: {available_ports}"
            )
            return (available_ports, "")
        except Exception as e:
            logger.error(f"Error populating ports: {e}")
            return ([], "Error getting ports")

    def set_port(self, selected_port: str) -> bool:
        """Set the communication port for the dosage system.

        Args:
        ----
            selected_port: The port name to use.

        Returns:
        -------
            bool: True if port was set successfully, False otherwise.

        """
        logger.info(f"Setting dosage port from '{self.com_port}' to '{selected_port}'")

        try:
            # Unregister old port if any
            if self.com_port:
                self.shared_port_manager.register_port_use(self.COMPONENT_NAME, "")

            if selected_port:
                self.com_port = selected_port
                self.settings.setValue("last_port", selected_port)

                # Register with shared manager
                self.shared_port_manager.register_port_use(
                    self.COMPONENT_NAME, selected_port
                )
                logger.info(
                    f"Successfully registered port {selected_port} for dosage component"
                )
                self.port_changed.emit(selected_port)
                return True
            else:
                logger.info("Empty port selected, clearing current port")
                self.com_port = ""
                self.port_changed.emit("")
                self.status_changed.emit("No port selected")
                return True  # Empty selection is valid

        except Exception as e:
            logger.error(f"Error setting dosage port: {e}")
            return False

    def _send_command(self, command: str) -> Optional[str]:
        """Send a command to the dosage system via serial port.

        Args:
        ----
            command: The command string to send.

        Returns:
        -------
            Optional[str]: Response string if successful, None if failed.

        """
        if not self.com_port:
            error_msg = "No COM port selected"
            logger.error(error_msg)
            self.error_occurred.emit(error_msg)
            return None

        try:
            with serial.Serial(
                self.com_port,
                self.BAUD_RATE,
                timeout=self.TIMEOUT,
                bytesize=7,
                parity="O",
                stopbits=1,
                xonxoff=0,
                rtscts=0,
            ) as ser:
                self.status_changed.emit(f"Sending command: {command}")
                ser.write(bytes(command + "\r", "utf-8"))
                time.sleep(2)

                response = str(ser.readline(), "utf-8")
                logger.info(
                    f"Received response from dosage system: '{response.strip()}'"
                )
                return response

        except serial.SerialException as e:
            error_msg = f"Serial communication error: {e}"
            logger.error(error_msg)
            self.error_occurred.emit(error_msg)
            return None

        except Exception as e:
            error_msg = f"Error in communication: {e}"
            logger.error(error_msg)
            self.error_occurred.emit(error_msg)
            return None

    def initialise(self) -> Optional[str]:
        """Initialize the dosage system.

        Returns
        -------
            Optional[str]: Response from system or None if failed.

        """
        logger.info("Initializing dosage system")
        self.status_changed.emit("Initializing dosage system...")
        response = self._send_command("1a")

        if response:
            final_response = self._send_command(":XR")
            if final_response:
                logger.info("Dosage system initialization completed successfully")
            else:
                logger.warning("Execute command failed after successful initialization")
            return final_response

        logger.error("Failed to initialize dosage system")
        self.error_occurred.emit("Failed to initialize dosage system")
        return None

    def resolution(self, address: str, full: str = "1") -> Optional[str]:
        """Set the resolution for the specified address.

        Args:
        ----
            address: The device address.
            full: Resolution value (default: "1").

        Returns:
        -------
            Optional[str]: Response from system or None if failed.

        """
        logger.info(f"Setting resolution for address {address} to {full}")
        self.status_changed.emit(f"Setting resolution for address {address}...")

        command = f"{address}YSM{full}"
        response = self._send_command(command)

        if response:
            logger.info(f"Resolution set successfully for address {address}")
        else:
            logger.error(f"Failed to set resolution for address {address}")

        return response

    def refill(self, address: str, steps: Optional[str] = None) -> Optional[str]:
        """Refill the system at the specified address.

        Args:
        ----
            address: The device address.
            steps: Number of steps (default: DEFAULT_STEPS).

        Returns:
        -------
            Optional[str]: Response from system or None if failed.

        """
        if steps is None:
            steps = str(self.DEFAULT_STEPS)

        logger.info(f"Refilling system at address {address} with {steps} steps")
        self.status_changed.emit(f"Refilling system at address {address}...")

        command = f"{address}IM{steps}R"
        response = self._send_command(command)

        if response:
            logger.info(f"Refill completed successfully for address {address}")
        else:
            logger.error(f"Failed to refill system at address {address}")

        return response

    def stroke(
        self,
        address: str,
        steps: Optional[str] = None,
        valve_pos: str = "O",
        direction: str = "D",
        time_stroke: Optional[str] = None,
    ) -> Optional[str]:
        """Perform a stroke operation.

        Args:
        ----
            address: The device address.
            steps: Number of steps (default: current steps value).
            valve_pos: Valve position (default: "O").
            direction: Direction (default: "D").
            time_stroke: Stroke time (default: current time value).

        Returns:
        -------
            Optional[str]: Response from system or None if failed.

        """
        if steps is None:
            steps = str(self._steps_value)

        if time_stroke is None:
            time_stroke = str(self._time_value)

        command = f"{address}{valve_pos}{direction}{steps}S{time_stroke}R"
        logger.info(
            f"Executing stroke operation at address {address}: {steps} steps "
            f"in {time_stroke} time, valve={valve_pos}, direction={direction}"
        )
        self.status_changed.emit(
            f"Executing stroke: {steps} steps in {time_stroke} time"
        )
        response = self._send_command(command)

        if response:
            logger.info(
                f"Stroke operation completed successfully for address {address}"
            )
        else:
            logger.error(f"Failed to execute stroke operation at address {address}")

        return response

    def close_port(self) -> bool:
        """Close the current port and unregister it from the port manager.

        Returns
        -------
            bool: True if port was closed successfully, False if no port was open.

        """
        logger.info("Closing dosage port connection")

        if self.com_port:
            old_port = self.com_port

            # Clear internal port reference
            self.com_port = ""

            # Unregister from shared port manager
            try:
                self.shared_port_manager.register_port_use(self.COMPONENT_NAME, "")
            except Exception as e:
                logger.warning(f"Error unregistering port from shared manager: {e}")

            # Emit signal that port changed
            self.port_changed.emit("")
            logger.info(f"Port {old_port} closed and unregistered successfully")

            return True
        else:
            return False


# Explicitly mark public API methods as used for static analysis
# These methods are called dynamically by GUI threads and external controllers
_ = (DosageCore.initialise, DosageCore.resolution, DosageCore.refill, DosageCore.stroke)
