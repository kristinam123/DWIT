"""Core logic for experiment table management in Droplet Wall Interaction Tool."""

import json
import os
from typing import Any, Optional

from PySide6.QtCore import Property, QObject, QSettings, Signal

from src.utilities.logging_manager import get_logger

# Setup logger for this module
logger = get_logger(__name__)


class TableCore(QObject):
    """Core functionality for experiment table calculations and data management.

    Handles experiment parameter management, calculations, and table generation.
    """

    substance_changed = Signal(str)
    droplet_diameters_changed = Signal(str)
    counter_flows_changed = Signal(str)
    tilts_changed = Signal(str)
    trials_changed = Signal(str)
    error_occurred = Signal(str)
    status_changed = Signal(str)

    def __init__(self):
        """Initialize the TableCore instance."""
        logger.debug("Initializing TableCore instance")
        super().__init__()

        try:
            self.settings = QSettings("DropletWallInteractionTool", "Table")
            self._substance = ""
            self._droplet_diameters = ""
            self._counter_flows = ""
            self._tilts = ""
            self._trials = ""
            self.load_settings()
            self.results = []

            # Initialize experiment parameters
            self.conversion_table = self.load_conversion_table()
            self.res_steps = None
            self.res_TpS = None
            self.res_drop_diam = None
            self.res_flow_freq = None
            self.res_cannula_diameter = None

            logger.debug("TableCore initialization completed successfully")

        except Exception as e:
            logger.error(f"Error during TableCore initialization: {e}")
            raise

    def load_settings(self) -> None:
        """Load saved settings from persistent storage.

        Uses fallback values for first-time users.
        """
        # Use fallback values for first-time users
        self._substance = self.settings.value("substance", "Butyl Acetate", str)
        self._droplet_diameters = self.settings.value("droplet_diameters", "2, 5", str)
        self._counter_flows = self.settings.value("counter_flows", "0, 18", str)
        self._tilts = self.settings.value("tilts", "45, 60", str)
        self._trials = self.settings.value("trials", "10", str)

        logger.debug(
            f"Loaded settings - substance: '{self._substance}', "
            f"droplets: '{self._droplet_diameters}', flows: '{self._counter_flows}', "
            f"tilts: '{self._tilts}', trials: '{self._trials}'"
        )

        # Save default values for first-time users
        if self.settings.value("substance", None) is None:
            self.save_setting("substance", self._substance)
        if self.settings.value("droplet_diameters", None) is None:
            self.save_setting("droplet_diameters", self._droplet_diameters)
        if self.settings.value("counter_flows", None) is None:
            self.save_setting("counter_flows", self._counter_flows)
        if self.settings.value("tilts", None) is None:
            self.save_setting("tilts", self._tilts)
        if self.settings.value("trials", None) is None:
            self.save_setting("trials", self._trials)

    def save_setting(self, key: str, value: str) -> None:
        """Save a setting to persistent storage."""
        try:
            self.settings.setValue(key, value)
        except Exception as e:
            logger.error(f"Error saving setting '{key}': {e}")
            raise

    def get_substance(self) -> str:
        """Get the current substance."""
        return self._substance

    def set_substance(self, value: str) -> None:
        """Set the substance and save to settings."""
        if self._substance != value:
            self._substance = value
            self.save_setting("substance", value)
            self.substance_changed.emit(value)
            logger.info(f"Substance updated to: {value}")

    def get_droplet_diameters(self) -> str:
        """Get the current droplet diameters string."""
        return self._droplet_diameters

    def set_droplet_diameters(self, value: str) -> None:
        """Set the droplet diameters and save to settings."""
        if self._droplet_diameters != value:
            self._droplet_diameters = value
            self.save_setting("droplet_diameters", value)
            self.droplet_diameters_changed.emit(value)
            logger.info(f"Droplet diameters updated to: {value}")

    def get_counter_flows(self) -> str:
        """Get the current counter flows string."""
        return self._counter_flows

    def set_counter_flows(self, value: str) -> None:
        """Set the counter flows and save to settings."""
        if self._counter_flows != value:
            self._counter_flows = value
            self.save_setting("counter_flows", value)
            self.counter_flows_changed.emit(value)
            logger.info(f"Counter flows updated to: {value}")

    def get_tilts(self) -> str:
        """Get the current tilts string."""
        return self._tilts

    def set_tilts(self, value: str) -> None:
        """Set the tilts and save to settings."""
        if self._tilts != value:
            self._tilts = value
            self.save_setting("tilts", value)
            self.tilts_changed.emit(value)
            logger.info(f"Tilts updated to: {value}")

    def get_trials(self) -> str:
        """Get the current trials string."""
        return self._trials

    def set_trials(self, value: str) -> None:
        """Set the trials and save to settings."""
        if self._trials != value:
            self._trials = value
            self.save_setting("trials", value)
            self.trials_changed.emit(value)
            logger.info(f"Trials updated to: {value}")

    # Qt Properties
    substance = Property(str, get_substance, set_substance, notify=substance_changed)
    droplet_diameters = Property(
        str,
        get_droplet_diameters,
        set_droplet_diameters,
        notify=droplet_diameters_changed,
    )
    counter_flows = Property(
        str, get_counter_flows, set_counter_flows, notify=counter_flows_changed
    )
    tilts = Property(str, get_tilts, set_tilts, notify=tilts_changed)
    trials = Property(str, get_trials, set_trials, notify=trials_changed)

    def convert_counter_flow(self, counter_flow_liters_per_hour: float) -> float:
        """Convert counter flow from L/h to the appropriate unit.

        Args:
        ----
            counter_flow_liters_per_hour: Counter flow in L/h.

        Returns:
        -------
            float: Converted counter flow value.

        """
        converted_value = counter_flow_liters_per_hour / 2.2
        return converted_value

    def load_conversion_table(self) -> Optional[dict[str, list[dict[str, Any]]]]:
        """Load the droplet conversion table from JSON file.

        Returns
        -------
            Optional[dict]: Conversion table data or None if loading failed.

        """
        file_path = os.path.abspath(
            os.path.join(
                os.path.dirname(__file__), "../../config/droplet_conversion.json"
            )
        )
        logger.info(f"Loading droplet conversion table from: {file_path}")

        if not os.path.exists(file_path):
            error_msg = "Error: Conversion table JSON file not found."
            logger.error(f"Conversion table file not found at: {file_path}")
            self.error_occurred.emit(error_msg)
            return None

        try:
            with open(file_path) as f:
                conversion_table = json.load(f)
                substances_count = (
                    len(conversion_table.keys()) if conversion_table else 0
                )
                logger.info(
                    f"Conversion table loaded successfully with "
                    f"{substances_count} substances"
                )
                self.status_changed.emit("Conversion table loaded successfully")
                return conversion_table
        except (FileNotFoundError, json.JSONDecodeError) as e:
            error_msg = f"Error loading conversion table: {e}"
            logger.error(error_msg)
            self.error_occurred.emit(error_msg)
            return None

    def find_closest_setpoint(
        self,
        substance: str,
        desired_diameter: float,
        counter_flow_liters_per_hour: float,
    ) -> Optional[dict[str, Any]]:
        """Find the closest setpoint in the conversion table.

        Args:
        ----
            substance: The substance name.
            desired_diameter: Target droplet diameter [mm].
            counter_flow_liters_per_hour: Counter flow in L/h.

        Returns:
        -------
            Optional[dict]: Result parameters or None if not found.

        """
        if not self.conversion_table:
            error_msg = "Error: Conversion table is not loaded."
            logger.error(error_msg)
            self.error_occurred.emit(error_msg)
            return None

        if substance not in self.conversion_table:
            error_msg = (
                f"Error: Substance '{substance}' not found in the conversion table."
            )
            logger.error(error_msg)
            self.error_occurred.emit(error_msg)
            return None

        substance_data = self.conversion_table[substance]

        closest = min(
            substance_data,
            key=lambda x: abs(x["IdealDropletDiameter_mm"] - desired_diameter),
        )

        self.res_steps = closest["Step"]
        self.res_TpS = round(
            (
                closest["TimePerStroke_1_per_s_Min"]
                + closest["TimePerStroke_1_per_s_Max"]
            )
            / 2
        )
        self.res_drop_diam = closest["IdealDropletDiameter_mm"]
        self.res_cannula_diameter = closest["CannulaDiameter_mm"]
        self.res_flow_freq = round(
            self.convert_counter_flow(counter_flow_liters_per_hour)
        )

        result = {
            "res_steps": self.res_steps,
            "res_TpS": self.res_TpS,
            "res_drop_diam": self.res_drop_diam,
            "res_cannula_diameter": self.res_cannula_diameter,
            "res_flow_freq": self.res_flow_freq,
        }

        logger.info(
            f"Setpoint found - steps: {self.res_steps}, TpS: {self.res_TpS}, "
            f"cannula: {self.res_cannula_diameter}mm, "
            f"resulting diameter: {self.res_drop_diam}mm"
        )

        return result

    def process_data(
        self, substance: str, droplet_data: str, flow_data: str, tilt_data: str
    ) -> tuple[bool, Optional[str]]:
        """Process input data and generate experiment table.

        Args:
        ----
            substance: Selected substance.
            droplet_data: Comma-separated droplet diameters.
            flow_data: Comma-separated counter flows.
            tilt_data: Comma-separated material tilts.

        Returns:
        -------
            tuple[bool, Optional[str]]: Success status and error message if failed

        """
        logger.info(f"Processing experiment data for substance: {substance}")

        try:
            droplet_diameters = [float(x.strip()) for x in droplet_data.split(",")]
            counter_flows = [float(x.strip()) for x in flow_data.split(",")]
            material_tilts = [float(x.strip()) for x in tilt_data.split(",")]

            logger.info(
                f"Parsed parameters - droplets: {droplet_diameters}, "
                f"flows: {counter_flows}, tilts: {material_tilts}"
            )

        except ValueError as e:
            error_msg = "Please enter valid comma separated numerical values."
            logger.error(f"Error parsing input data: {e}")
            return False, error_msg
        self.results = []

        total_combinations = (
            len(droplet_diameters) * len(counter_flows) * len(material_tilts)
        )
        logger.info(f"Generating {total_combinations} experiment combinations")

        for droplet in sorted(droplet_diameters):
            for flow in sorted(counter_flows):
                for tilt in sorted(material_tilts):

                    result = self.find_closest_setpoint(substance, droplet, flow)
                    if result:
                        experiment_entry = {
                            "Substance": substance,
                            "Trials": self.trials,
                            "Cannula Diameter (mm)": result["res_cannula_diameter"],
                            "Material Tilt (°)": tilt,
                            "Counter Flow (L/h)": flow,
                            "Steps (1)": result["res_steps"],
                            "Time per Stroke (0.1s)": result["res_TpS"],
                            "Droplet Diameter (mm)": droplet,
                            "Resulting Diameter (mm)": result["res_drop_diam"],
                        }
                        self.results.append(experiment_entry)
                    else:
                        logger.warning(
                            f"Could not find setpoint for combination: "
                            f"droplet={droplet}mm, flow={flow}L/h"
                        )

        # Sort results by priority criteria
        self.results = sorted(
            self.results,
            key=lambda x: (
                x["Droplet Diameter (mm)"] > 4.9,
                x["Material Tilt (°)"],
                x["Counter Flow (L/h)"],
            ),
        )

        logger.info(f"Successfully generated {len(self.results)} experiment entries")
        return True, None
