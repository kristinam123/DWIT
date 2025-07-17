"""Core logic for pump control in MesszelleApp."""

from typing import Union

import serial
from PySide6.QtCore import Property, QObject, QSettings, Signal

from src.utilities.logging_manager import get_logger
from src.utilities.port import PortManager, SharedPortManager

# Setup logger for this module
logger = get_logger(__name__)


class PumpCore(QObject):
    """Core functionality for pump control via serial connection.

    Handles communication, unit conversion, and port management.
    """

    port_changed = Signal(str)
    status_changed = Signal(str)
    error_occurred = Signal(str)

    # Constants for pump and user value ranges
    MAX_PUMP_VALUE = 255
    MAX_USER_VALUE = 88

    # Component name for port management
    COMPONENT_NAME = "pump"

    def __init__(self):
        """Initialize the PumpCore instance."""
        logger.info("Initializing PumpCore instance")
        super().__init__()

        try:
            self._com_port = ""
            self.port_manager = PortManager()
            self.shared_port_manager = SharedPortManager()
            self.settings = QSettings("MeasurementCellApp", "Pump")

            # Listen for port status changes
            self.shared_port_manager.port_status_changed.connect(
                self._on_port_status_changed
            )

            logger.info("PumpCore initialization completed successfully")

        except Exception as e:
            logger.error(f"Error during PumpCore initialization: {e}")
            raise

    def _on_port_status_changed(self):
        """Handle changes in port availability."""
        # If our port is now used by another component, release it
        if (
            self._com_port
            and self._com_port
            not in self.shared_port_manager.get_available_ports_for_component(
                self.COMPONENT_NAME, False
            )
        ):
            old_port = self._com_port
            logger.warning(
                f"Pump port {old_port} is now in use by another component, releasing"
            )
            self._com_port = ""
            self.port_changed.emit("")
            self.error_occurred.emit(
                f"Port {old_port} is now in use by another component"
            )

    def get_available_ports(self) -> list[str]:
        """Get list of available serial ports."""
        try:
            available_ports = (
                self.shared_port_manager.get_available_ports_for_component(
                    self.COMPONENT_NAME
                )
            )
            logger.info(
                f"Found {len(available_ports)} available ports for pump: "
                f"{available_ports}"
            )
            return available_ports
        except Exception as e:
            logger.error(f"Error getting available ports for pump: {e}")
            return []

    def get_port(self) -> str:
        """Get currently selected port."""
        return self._com_port

    def set_port(self, port_name: str) -> bool:
        """Set the serial port for communication.

        Args:
        ----
            port_name: Name of the port to use

        Returns:
        -------
            bool: True if port was changed, False otherwise

        """
        logger.info(f"Setting pump port from '{self._com_port}' to '{port_name}'")

        if self._com_port != port_name:
            try:
                # Unregister old port if any
                if self._com_port:
                    self.shared_port_manager.register_port_use(self.COMPONENT_NAME, "")

                self._com_port = port_name

                if port_name:  # Only register non-empty port selections
                    # Register port with shared manager
                    self.shared_port_manager.register_port_use(
                        self.COMPONENT_NAME, port_name
                    )
                    logger.info(f"Successfully registered pump port: {port_name}")
                else:
                    logger.info("Empty port selected for pump, clearing current port")
                    self.status_changed.emit("No port selected")

                self.port_changed.emit(port_name)
                return True

            except Exception as e:
                logger.error(f"Error setting pump port: {e}")
                return False
        else:
            return False

        # Property for Qt property system

    port = Property(str, get_port, set_port, notify=port_changed)

    def write_setpoint(self, setpoint: Union[int, str]) -> bool:
        """Send setpoint command to the pump.

        Args:
        ----
            setpoint: Pump setpoint value (0-255)

        Returns:
        -------
            bool: True if command sent successfully, False otherwise

        """
        try:
            # Convert to integer if string
            setpoint_int = int(setpoint)

            # Validate range
            if not 0 <= setpoint_int <= self.MAX_PUMP_VALUE:
                error_msg = f"Setpoint out of range (0-{self.MAX_PUMP_VALUE})"
                logger.error(error_msg)
                self.error_occurred.emit(error_msg)
                return False

            # Format command (03 for setting pump + hex value)
            command = f"{3:02x}{setpoint_int:02x}"
            success = self._communicate_with_pump(command=command)

            if success:
                status_msg = f"Setpoint set to {setpoint_int}"
                logger.info(status_msg)
                self.status_changed.emit(status_msg)
            else:
                error_msg = "Failed to communicate with pump"
                logger.error(error_msg)
                self.error_occurred.emit(error_msg)

            return success

        except ValueError as e:
            error_msg = f"Invalid setpoint value: {setpoint} - {e}"
            logger.error(error_msg)
            self.error_occurred.emit("Invalid setpoint value")
            return False
        except Exception as e:
            error_msg = f"Error in write_setpoint: {e}"
            logger.error(error_msg)
            self.error_occurred.emit(f"Error: {e}")
            return False

    def _communicate_with_pump(
        self, command: str, baudrate: int = 9600, timeout: int = 2
    ) -> bool:
        """Send command to the pump over serial.

        Args:
        ----
            command: Hex command string to send
            baudrate: Serial baudrate
            timeout: Serial timeout in seconds

        Returns:
        -------
            bool: True if communication successful, False otherwise

        """
        # Validate port is set
        if not self._com_port:
            error_msg = "No COM port selected"
            logger.error(error_msg)
            self.error_occurred.emit(error_msg)
            return False

        try:
            # Convert hex string to bytes
            command_bytes = bytes.fromhex(command)
            logger.info(f"Sending command to pump on {self._com_port}: {command}")

            # Open serial port and send command
            with serial.Serial(self._com_port, baudrate, timeout=timeout) as ser:
                ser.write(command_bytes)
                logger.info(f"Successfully sent command to pump: {command}")
                return True

        except serial.SerialException as se:
            error_msg = f"Serial error: {se}"
            logger.error(error_msg)
            self.error_occurred.emit(error_msg)
            return False

        except ValueError as ve:
            error_msg = f"Invalid command format: {ve}"
            logger.error(error_msg)
            self.error_occurred.emit(error_msg)
            return False

        except Exception as e:
            error_msg = f"Communication error: {e}"
            logger.error(error_msg)
            self.error_occurred.emit(error_msg)
            return False

    def convert_user_setpoint_to_pump_value(self, user_value: Union[float, str]) -> int:
        """Convert user-friendly flow rate to pump control value.

        Args:
        ----
            user_value: Flow rate in L/h (0-88)

        Returns:
        -------
            int: Corresponding pump value (0-255)

        """
        try:
            # Linear conversion from user scale to pump scale
            pump_value = int(
                round(float(user_value) * self.MAX_PUMP_VALUE / self.MAX_USER_VALUE, 0)
            )
            logger.info(
                f"Converted user value {user_value} L/h to pump value {pump_value} "
                f"(scale: 0-{self.MAX_PUMP_VALUE})"
            )
            return pump_value
        except ValueError as e:
            error_msg = f"Invalid flow rate value: {user_value} - {e}"
            logger.error(error_msg)
            self.error_occurred.emit("Invalid flow rate value")
            return 0
        except Exception as e:
            error_msg = f"Error converting user setpoint: {e}"
            logger.error(error_msg)
            self.error_occurred.emit("Error in value conversion")
            return 0

    def close_port(self) -> bool:
        """Close the current port and unregister it from the port manager.

        Returns
        -------
            bool: True if port was closed successfully, False if no port was open

        """
        logger.info("Closing pump port connection")

        if self._com_port:
            old_port = self._com_port

            # Clear internal port reference
            self._com_port = ""

            # Unregister from shared port manager
            try:
                self.shared_port_manager.register_port_use(self.COMPONENT_NAME, "")
            except Exception as e:
                logger.warning(
                    f"Error unregistering pump port from shared manager: {e}"
                )

            # Emit signal that port changed
            self.port_changed.emit("")
            logger.info(f"Pump port {old_port} closed and unregistered successfully")

            return True
        else:
            return False
