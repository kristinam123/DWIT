"""Port utilities for serial device management in MesszelleApp."""

import serial.tools.list_ports
from PySide6.QtCore import QObject, Signal

from src.utilities.logging_manager import get_logger

# Setup logger for this module
logger = get_logger(__name__)


class SharedPortManager(QObject):
    """Centralized port manager that tracks which ports are in use.

    Tracks usage across different components of the application.
    """

    port_status_changed = Signal()

    _instance = None

    def __new__(cls):
        """Create or return the singleton instance of SharedPortManager."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        """Initialize the SharedPortManager instance."""
        if self._initialized:
            return

        logger.info("Initializing SharedPortManager")
        super().__init__()
        self._initialized = True
        self.port_manager = PortManager()
        self.used_ports = {}  # component_name -> port_name

    def get_available_ports(self, include_empty=True):
        """Get list of available ports, optionally including an empty entry.

        Args:
        ----
            include_empty: Whether to include an empty entry in the list

        Returns:
        -------
            list: Available ports, excluding those already in use

        """
        try:
            all_ports = self.port_manager.get_ports()

            # Create the list with special options
            ports = []

            # Add empty entry option if requested
            if include_empty:
                ports.append("")

            # Add the actual ports
            ports.extend(all_ports)

            logger.info(
                "Available ports list created with %d entries (include_empty=%s)",
                len(ports),
                include_empty,
            )
            return ports

        except Exception as e:
            logger.error(f"Error getting available ports: {e}")
            # Return minimal list as fallback
            fallback_ports = [""] if include_empty else []
            return fallback_ports

    def get_available_ports_for_component(self, component_name, include_empty=True):
        """Get list of available ports for a specific component.

        Excludes ports used by other components.

        Args:
        ----
            component_name: Name of the component requesting ports
            include_empty: Whether to include an empty entry

        Returns:
        -------
            list: Available ports for this component

        """
        try:
            all_ports = self.get_available_ports(include_empty)

            # Filter out ports used by other components
            available_ports = [
                p
                for p in all_ports
                if not self._is_port_used_by_other(p, component_name)
            ]

            used_by_others = set(all_ports) - set(available_ports)
            if used_by_others:
                logger.info(
                    f"Component '{component_name}' has {len(available_ports)} "
                    f"available ports, {len(used_by_others)} ports used by others"
                )
            else:
                logger.info(
                    f"Component '{component_name}' has access to all "
                    f"{len(available_ports)} available ports"
                )

            return available_ports

        except Exception as e:
            logger.error(
                f"Error getting available ports for component '{component_name}': {e}"
            )
            # Return minimal fallback
            fallback_ports = [""] if include_empty else []
            return fallback_ports

    def register_port_use(self, component_name, port_name):
        """Register that a component is using a specific port.

        Args:
        ----
            component_name: Name of the component
            port_name: Port being used

        """
        try:
            if not port_name:  # Empty port selection means port was released
                if component_name in self.used_ports:
                    old_port = self.used_ports[component_name]
                    del self.used_ports[component_name]
                    logger.info(
                        f"Component '{component_name}' released port '{old_port}'"
                    )
                    self.port_status_changed.emit()
                return

            # Record the port as being used by this component
            old_port = self.used_ports.get(component_name)
            if old_port != port_name:
                self.used_ports[component_name] = port_name
                if old_port:
                    logger.info(
                        f"Component '{component_name}' changed from port "
                        f"'{old_port}' to '{port_name}'"
                    )
                else:
                    logger.info(
                        f"Component '{component_name}' registered use of port "
                        f"'{port_name}'"
                    )
                self.port_status_changed.emit()

        except Exception as e:
            logger.error(
                f"Error registering port use for component '{component_name}', "
                f"port '{port_name}': {e}"
            )

    def _is_port_used_by_other(self, port_name, requesting_component):
        """Check if a port is being used by another component.

        Args:
        ----
            port_name: Port to check
            requesting_component: Component requesting the check

        Returns:
        -------
            bool: True if port is used by another component

        """
        # Empty port is always available
        if not port_name:
            return False

        # Check if any other component is using this port
        for component, used_port in self.used_ports.items():
            if component != requesting_component and used_port == port_name:
                return True
        return False


class PortManager:
    """Manager for serial port operations."""

    def __init__(self):
        """Initialize the port manager."""
        logger.info("Initializing PortManager")

    def get_ports(self):
        """Get a list of available serial ports.

        Returns
        -------
            list: list of available port names

        """
        ports = []
        try:
            port_list = list(serial.tools.list_ports.comports())

            for port in sorted(port_list):
                port_name = port.device
                ports.append(port_name)

            logger.info(
                f"Successfully enumerated {len(ports)} available serial ports: {ports}"
            )
            return ports

        except Exception as e:
            logger.error(f"Error enumerating serial ports: {e}")
            return []
