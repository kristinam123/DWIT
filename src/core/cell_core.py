"""Core logic for cell analysis and control in MesszelleApp."""

import time
from typing import Optional

import pandas as pd
from PySide6.QtCore import Property, QObject, QSettings, Signal, Slot

from src.threads.cell_threads import AutomatisationThread, StopEvent
from src.utilities.logging_manager import get_logger

TIME_TO_STABILIZE_FLOW = 5 * 60  # 5 minutes
TIME_AFTER_INJECTION = 15  # 15 seconds


# Setup logger for this module
logger = get_logger(__name__)


class CellCore(QObject):
    """Core functionality for Measurement Cell control and automation."""

    # Signal definitions
    prompt_changed = Signal(str)
    progress_changed = Signal(int)
    folder_path_changed = Signal(str)
    error_occurred = Signal(str)
    status_changed = Signal(str)

    def __init__(self):
        """Initialize the CellCore instance."""
        logger.debug("Initializing CellCore instance")
        super().__init__()

        try:
            # Settings and paths
            self.settings = QSettings("MeasurementCellApp", "Cell")
            self._folder_path = self.settings.value("last_folder_path", "")
            logger.debug(f"Loaded last folder path: {self._folder_path}")

            # GUI component references
            self.camera_gui = None
            self.pump_gui = None
            self.dosage_gui = None
            self.table_gui = None

            # State variables
            self.dosage_initialised = False
            self.prompt_done = True
            self.angle_change = False
            self.cannula_change = False

            # Experiment parameters - current
            self.current_substance: Optional[str] = None
            self.current_trials: Optional[int] = None
            self.current_cannula_diameter: Optional[float] = None
            self.current_tilt_angle: Optional[float] = None
            self.current_flow: Optional[float] = None
            self.current_step: Optional[int] = None
            self.current_tps: Optional[int] = None

            # Experiment parameters - previous
            self.previous_cannula_diameter: Optional[float] = None
            self.previous_tilt_angle: Optional[float] = None
            self.previous_flow: Optional[float] = None

            # Thread control
            self.stop_event = StopEvent()
            self.automatisation_thread = None

            # Results
            self.file_name = None
            self.table = None

            logger.debug("CellCore initialization completed successfully")

        except Exception as e:
            logger.error(f"Error during CellCore initialization: {e}")
            raise

    def get_folder_path(self) -> str:
        """Get the current folder path."""
        return self._folder_path

    def set_folder_path(self, value: str) -> None:
        """Set the folder path and save to settings."""
        if self._folder_path != value:
            self._folder_path = value
            try:
                self.settings.setValue("last_folder_path", value)
                logger.debug(f"Folder path updated and saved to settings: {value}")
                self.folder_path_changed.emit(value)
                self.status_changed.emit(f"Folder path updated to: {value}")
            except Exception as e:
                logger.error(f"Error saving folder path to settings: {e}")
                raise

    # Qt Property for folder path
    folder_path = Property(
        str, get_folder_path, set_folder_path, notify=folder_path_changed
    )

    @Slot(str)
    def select_folder(self, folder_selected: str) -> None:
        """Handle folder selection and propagate to components."""
        logger.info(f"Folder selected: {folder_selected}")
        if folder_selected:
            self.set_folder_path(folder_selected)
            self.status_changed.emit(f"Working folder set to: {folder_selected}")
            logger.info(f"Working folder successfully set to: {folder_selected}")
        else:
            logger.warning("Empty folder path selected, ignoring")

    def _check_for_changes(self) -> str:
        """Check for changes in angle or cannula settings."""
        angle_changed = self.current_tilt_angle != self.previous_tilt_angle
        cannula_changed = (
            self.current_cannula_diameter != self.previous_cannula_diameter
        )

        self.angle_change = angle_changed
        self.cannula_change = cannula_changed
        self.prompt_done = not (angle_changed or cannula_changed)

        logger.info(
            f"Change detection result - angle_change: {self.angle_change}, "
            f"cannula_change: {self.cannula_change}, prompt_done: {self.prompt_done}"
        )

        if angle_changed and cannula_changed:
            prompt_msg = (
                f"CHANGE: angle: {int(self.current_tilt_angle)}°, "
                f"cannula: {self.current_cannula_diameter}mm"
            )
            logger.warning(f"Both angle and cannula changed: {prompt_msg}")
            return prompt_msg
        elif angle_changed:
            prompt_msg = f"CHANGE: angle: {int(self.current_tilt_angle)}°"
            logger.warning(f"Angle changed: {prompt_msg}")
            return prompt_msg
        elif cannula_changed:
            prompt_msg = f"CHANGE: cannula: {self.current_cannula_diameter}mm"
            logger.warning(f"Cannula changed: {prompt_msg}")
            return prompt_msg
        else:
            return ""

    def run_cell(self, trial_index: int) -> None:
        """Run a single experiment cell."""
        logger.info(f"Starting cell experiment run for trial {trial_index}")

        try:
            # Determine if we can skip the flow stabilization wait
            skip_wait = (
                self.current_tilt_angle != 0
                and self.current_flow == self.previous_flow
                and trial_index > 0
            )

            # Start pump with current flow
            logger.info(f"Setting pump flow to {self.current_flow} L/h")
            self.status_changed.emit(f"Setting pump flow to {self.current_flow} L/h")
            self.pump_gui.slidespin.set(int(self.current_flow))
            self.pump_gui.update_setpoint()

            # Wait for flow stabilization if needed
            if not skip_wait:
                logger.info("Waiting for flow to stabilize (5 minutes)")
                self.status_changed.emit("Waiting for flow to stabilize (15s)")
                time.sleep(TIME_TO_STABILIZE_FLOW)
            else:
                logger.info("Skipping flow stabilization due to matching conditions")
                self.status_changed.emit("Skipping flow stabilization")

            # Start camera recording
            logger.info("Starting camera recording")
            self.status_changed.emit("Starting camera recording")
            self.camera_gui.start_record()
            self.camera_gui.is_recording = True
            time.sleep(2)

            # Inject droplet
            logger.info(
                f"Injecting droplet: {self.current_step} steps "
                f"at {self.current_tps} TpS"
            )
            self.status_changed.emit(
                f"Injecting: {self.current_step} steps at {self.current_tps} TpS"
            )
            self.dosage_gui.write_button("Inject")
            time.sleep(TIME_AFTER_INJECTION)

            # Stop camera recording
            logger.info("Stopping camera recording")
            self.status_changed.emit("Stopping camera recording")
            self.camera_gui.is_recording = False
            self.camera_gui.stop_record()
            self.status_changed.emit("Waiting for camera to save recording...")

            # Wait for saving to complete
            while self.camera_gui.is_saving:
                time.sleep(1)
                if self.stop_event.is_set():
                    logger.warning(
                        "Operation cancelled while waiting for camera "
                        "to finish saving"
                    )
                    self.status_changed.emit(
                        "Operation cancelled while waiting for camera"
                    )
                    break
            logger.info("Camera save operation completed")

            # Flush cell if needed - skip if flow rates match regardless of tilt angle
            if self.current_tilt_angle == 0 and self.current_flow != self.previous_flow:
                logger.info(
                    "Flushing cell due to horizontal position "
                    "and different flow rate"
                )
                self.status_changed.emit("Flushing cell")
                self.pump_gui.slidespin.set(88)
                self.pump_gui.update_setpoint()
                time.sleep(20)
            else:
                if self.current_flow == self.previous_flow:
                    logger.info(
                        "Skipping flush - same flow rate as previous experiment"
                    )
                    self.status_changed.emit(
                        "Skipping flush - same flow rate as previous experiment"
                    )
                else:
                    logger.info("Skipping flush cycle due to tilted cell position")
                    self.status_changed.emit("Skipping flush cycle")

            logger.info(f"Cell experiment trial {trial_index} completed successfully")

        except Exception as e:
            error_msg = f"Error during cell execution: {e!s}"
            logger.error(error_msg)
            self.error_occurred.emit(error_msg)
            self.error_occurred.emit(error_msg)

    def start_automation(self) -> None:
        """Create and start the automation thread."""
        logger.info("Starting automation process")

        if (
            self.automatisation_thread is None
            or not self.automatisation_thread.isRunning()
        ):
            self.stop_event.clear()
            self.automatisation_thread = AutomatisationThread(self)

            # Connect signals
            self.automatisation_thread.prompt_signal.connect(self.prompt_changed)
            self.automatisation_thread.progress_signal.connect(self.progress_changed)

            # Start thread
            self.automatisation_thread.start()
            self.status_changed.emit("Automation started")
            logger.info("Automation thread started successfully")
        else:
            logger.warning("Automation thread already running, ignoring start request")

    def stop_automation(self) -> None:
        """Stop the automation thread gracefully."""
        logger.info("Stopping automation process")

        if self.automatisation_thread and self.automatisation_thread.isRunning():
            self.status_changed.emit("Stopping automation...")
            self.stop_event.set()
            success = self.automatisation_thread.wait(5000)  # 5 seconds timeout

            if not success:
                logger.error("Automation thread did not stop within timeout period")
                self.error_occurred.emit("Automation thread did not stop in time")
            else:
                logger.info("Automation thread stopped successfully")
                self.status_changed.emit("Automation stopped successfully")

            self.stop_event.clear()
        else:
            logger.warning("No running automation thread to stop")

    def _prepare_experiment_table(self) -> str:
        """Prepare and validate the experiment table.

        Returns
        -------
            Empty string if successful, error message otherwise

        """
        if self.table_gui.results is None:
            logger.error("No experiment table loaded for automation")
            self.error_occurred.emit("No experiment table loaded")
            return "Please load a table first!"

        # Create DataFrame from results
        self.table = pd.DataFrame(self.table_gui.results)
        logger.info(f"Loaded experiment table with {len(self.table)} rows")

        # Add previous columns for comparison
        prev_columns = {col: f"prev_{col}" for col in self.table.columns}
        for col, prev_col in prev_columns.items():
            self.table[prev_col] = self.table[col].shift(1)

        return ""

    def _update_experiment_parameters(self, row) -> None:
        """Update current and previous experiment parameters from table row.

        Args:
        ----
            row: DataFrame row containing experiment parameters

        """
        for col in self.table.columns:
            if col.startswith("prev_"):
                continue

            # Convert column name to attribute name
            attr_name = (
                col.lower()
                .replace(" ", "_")
                .replace("(", "")
                .replace(")", "")
                .replace("/", "_")
            )

            # Set current and previous values
            setattr(self, f"current_{attr_name}", row[col])
            prev_col = f"prev_{col}"
            prev_val = (
                row[prev_col]
                if prev_col in row and not pd.isna(row[prev_col])
                else None
            )
            setattr(self, f"previous_{attr_name}", prev_val)

    def _update_ui_components(self) -> None:
        """Update UI components with current experiment parameters."""
        self.pump_gui.slidespin.set(int(self.current_flow))
        self.dosage_gui.steps_spinbox_var.set(int(self.current_step))
        self.dosage_gui.time_spinbox_var.set(int(self.current_tps))
        logger.info(
            f"UI updated - flow: {self.current_flow}, "
            f"steps: {self.current_step}, tps: {self.current_tps}"
        )

    def _wait_for_dosage_initialization(self) -> str:
        """Wait for dosage system to be initialized.

        Returns
        -------
            Empty string if successful, error message otherwise

        """
        # Check if dosage system is initialized
        if not self.dosage_initialised:
            logger.warning("Dosage system not initialized, prompting user")
            self.prompt_done = False
            return "Make sure dosage is initialised and full!"

        # Wait for dosage initialization
        while not self.dosage_initialised:
            if self.stop_event.is_set():
                logger.warning(
                    "Automation stopped while waiting for dosage initialization"
                )
                return "Automation stopped by user"
            time.sleep(1)
        return ""

    def _wait_for_user_acknowledgment(self) -> str:
        """Wait for user to acknowledge parameter changes.

        Returns
        -------
            Empty string if successful, error message otherwise

        """
        # Check for setup changes needed
        prompt_text = self._check_for_changes()
        if prompt_text:
            logger.warning(
                f"Parameter changes detected, user intervention required: "
                f"{prompt_text}"
            )
            return prompt_text

        # Wait for user to acknowledge changes
        while not (
            self.prompt_done and not self.angle_change and not self.cannula_change
        ):
            if self.stop_event.is_set():
                logger.warning(
                    "Automation stopped while waiting for user acknowledgment"
                )
                return "Automation stopped by user"
            time.sleep(1)
        return ""

    def _setup_recording_path(self) -> None:
        """Set up file name and path for recording."""
        self.file_name = (
            f"{self.current_substance}/"
            f"{int(self.current_step)}/"
            f"{int(self.current_trials)}/"
            f"cd{self.current_cannula_diameter}mm_"
            f"{int(self.current_tilt_angle)}deg_"
            f"{int(self.current_flow)}Lph_"
            f"{int(self.current_step)}_"
            f"{int(self.current_tps)}"
        )
        self.camera_gui.save_as = f"{self._folder_path}/{self.file_name}"
        logger.info(f"Recording file path set: {self.camera_gui.save_as}")

    def _run_experiment_trials(self, config_index: int, total_configs: int) -> str:
        """Run all trials for the current experiment configuration.

        Args:
        ----
            config_index: Current configuration index (0-based)
            total_configs: Total number of configurations

        Returns:
        -------
            Empty string if successful, error message otherwise

        """
        # Run trials for current configuration
        self.status_changed.emit(
            f"Running {self.current_trials} trials for configuration "
            f"{config_index+1}/{total_configs}"
        )
        logger.info(
            f"Starting {self.current_trials} trials for configuration {config_index+1}"
        )

        for i in range(int(self.current_trials)):
            if self.stop_event.is_set():
                logger.warning("Automation stopped during trial execution")
                return "Automation stopped by user"

            self.status_changed.emit(f"Trial {i+1}/{int(self.current_trials)}")
            self.run_cell(i)

        # Brief pause between configurations
        time.sleep(1)
        return ""

    def _process_experiment_configuration(
        self, index: int, row, total_rows: int
    ) -> str:
        """Process a single experiment configuration.

        Args:
        ----
            index: Configuration index
            row: DataFrame row with experiment parameters
            total_rows: Total number of configurations

        Returns:
        -------
            Empty string if successful, error message otherwise

        """
        logger.info(f"Processing experiment configuration {index+1}/{total_rows}")

        # Check if stop requested
        if self.stop_event.is_set():
            logger.warning("Automation stopped by user request")
            return "Automation stopped by user"

        # Update progress
        progress_pct = int((index / total_rows) * 100)
        self.progress_changed.emit(progress_pct)

        # Update parameters
        self._update_experiment_parameters(row)

        # Update UI
        self._update_ui_components()

        # Wait for dosage initialization
        result = self._wait_for_dosage_initialization()
        if result:
            return result

        # Wait for user acknowledgment
        result = self._wait_for_user_acknowledgment()
        if result:
            return result

        # Setup recording
        self._setup_recording_path()

        # Run trials
        return self._run_experiment_trials(index, total_rows)

    def _automatisation(self) -> str:
        """Run experiments based on table data."""
        logger.info("Starting automated experiment sequence")

        try:
            # Prepare experiment table
            result = self._prepare_experiment_table()
            if result:
                return result

            # Process each row (experiment configuration)
            total_rows = len(self.table)
            logger.info(f"Processing {total_rows} experiment configurations")

            for index, row in self.table.iterrows():
                result = self._process_experiment_configuration(index, row, total_rows)
                if result:
                    return result

            # Complete successfully
            self.progress_changed.emit(100)
            logger.info("Automation sequence completed successfully")
            return "Automation completed successfully"

        except Exception as e:
            error_msg = f"Error in automation: {e!s}"
            logger.error(error_msg)
            self.error_occurred.emit(error_msg)
            return f"Error: {e!s}"


# Explicitly mark _automatisation as used for static analysis
# called by AutomatisationThread
_ = CellCore._automatisation
