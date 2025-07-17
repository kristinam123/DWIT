"""Table GUI widgets for experiment configuration and results display."""

import csv
import locale
import os

from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.utilities.logging_manager import get_logger

# Setup logger for this module
logger = get_logger(__name__)


class TableGUI(QWidget):
    """Modern table interface for experiment configuration and results display."""

    def __init__(self, parent, controller):
        """Initialize the TableGUI with parent and controller."""
        logger.info("Initializing TableGUI")
        super().__init__(parent)
        self.controller = controller
        self.results = None

        # Set up UI components
        self._create_widgets()

        # Load existing data if available
        if (
            self.controller.substance is not None
            and self.controller.droplet_diameters is not None
            and self.controller.counter_flows is not None
            and self.controller.tilts is not None
        ):
            logger.info("Loading existing experiment data")
            self.update_table()

    def _create_widgets(self):
        """Create and arrange all UI widgets with space-efficient layout."""
        main_layout = QHBoxLayout(self)
        main_layout.setSpacing(5)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # Create left panel (inputs)
        left_panel = self._create_left_panel()
        left_panel.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)

        # Create right panel (results table)
        right_panel = self._create_right_panel()
        right_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # Add panels to main layout with better proportions
        main_layout.addWidget(left_panel, 1)
        main_layout.addWidget(right_panel, 3)

    def _create_left_panel(self):
        """Create the left panel with input controls."""
        left_frame = QWidget()
        left_layout = QVBoxLayout(left_frame)
        left_layout.setSpacing(5)
        left_layout.setContentsMargins(5, 5, 5, 5)

        # Add title and status row
        title_layout = QHBoxLayout()
        title_label = QLabel("Experiment Configuration")
        title_label.setStyleSheet("font-weight: bold;")
        title_label.setToolTip("Configure the experiment parameters here.")
        title_layout.addWidget(title_label)
        title_layout.addStretch(1)
        left_layout.addLayout(title_layout)

        # Status label
        self.status_label = QLabel("Ready")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setToolTip(
            "Shows the current status of the table configuration."
        )
        left_layout.addWidget(self.status_label)

        # Add separator line
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setFrameShadow(QFrame.Sunken)
        left_layout.addWidget(separator)

        # Substance selection
        substance_group = QWidget()
        substance_layout = QVBoxLayout(substance_group)
        substance_layout.setContentsMargins(0, 0, 0, 0)
        substance_layout.setSpacing(3)

        substance_label = QLabel("Substance:")
        substance_label.setToolTip("Select the chemical substance for the experiment.")
        substance_layout.addWidget(substance_label)

        self.substance_combo = QComboBox()
        self.substance_combo.addItems(["Butyl Acetate", "Toluene"])
        self.substance_combo.setCurrentText(self.controller.substance)
        self.substance_combo.setToolTip(
            "Choose the substance to be used in the experiment."
        )
        self.substance_combo.currentTextChanged.connect(self.controller.set_substance)
        # Connect combobox activation to update_table
        self.substance_combo.activated.connect(self.update_table)
        substance_layout.addWidget(self.substance_combo)

        left_layout.addWidget(substance_group)

        # Parameters group in grid
        params_group = QWidget()
        params_layout = QGridLayout(params_group)
        params_layout.setContentsMargins(0, 0, 0, 0)
        params_layout.setVerticalSpacing(8)
        params_layout.setHorizontalSpacing(5)
        params_layout.setColumnStretch(1, 1)

        # Droplet diameters
        self.droplet_label = QLabel("Diameters (mm):")
        self.droplet_label.setToolTip(
            "List of droplet diameters in millimeters, separated by commas."
        )
        self.droplet_entry = QLineEdit(self.controller.droplet_diameters)
        self.droplet_entry.setToolTip(
            "Enter droplet diameters separated by commas (e.g., 2.5, 3.0, 3.5)"
        )
        self.droplet_entry.textChanged.connect(self.controller.set_droplet_diameters)
        # Connect returnPressed signal to update_table method
        self.droplet_entry.returnPressed.connect(self.update_table)
        params_layout.addWidget(self.droplet_label, 0, 0)
        params_layout.addWidget(self.droplet_entry, 0, 1)

        # Counter flows
        self.flow_label = QLabel("Flows (L/h):")
        self.flow_label.setToolTip(
            "List of counter flow rates in liters per hour, separated by commas."
        )
        self.flow_entry = QLineEdit(self.controller.counter_flows)
        self.flow_entry.setToolTip(
            "Enter counter flows separated by commas (e.g., 10, 20, 30)"
        )
        self.flow_entry.textChanged.connect(self.controller.set_counter_flows)
        # Connect returnPressed signal to update_table method
        self.flow_entry.returnPressed.connect(self.update_table)
        params_layout.addWidget(self.flow_label, 1, 0)
        params_layout.addWidget(self.flow_entry, 1, 1)

        # Material tilts
        self.tilt_label = QLabel("Tilts (°):")
        self.tilt_label.setToolTip(
            "List of material tilt angles in degrees, separated by commas."
        )
        self.tilt_entry = QLineEdit(self.controller.tilts)
        self.tilt_entry.setToolTip(
            "Enter material tilts separated by commas (e.g., 0, 15, 30)"
        )
        self.tilt_entry.textChanged.connect(self.controller.set_tilts)
        # Connect returnPressed signal to update_table method
        self.tilt_entry.returnPressed.connect(self.update_table)
        params_layout.addWidget(self.tilt_label, 2, 0)
        params_layout.addWidget(self.tilt_entry, 2, 1)

        # Trials
        self.trial_label = QLabel("Trials:")
        self.trial_label.setToolTip(
            "Number of repeated trials for each experiment configuration."
        )
        self.trial_entry = QLineEdit(self.controller.trials or "3")
        self.trial_entry.setToolTip("Enter number of trials for each experiment")
        self.trial_entry.textChanged.connect(self.controller.set_trials)
        # Connect returnPressed signal to update_table method
        self.trial_entry.returnPressed.connect(self.update_table)
        params_layout.addWidget(self.trial_label, 3, 0)
        params_layout.addWidget(self.trial_entry, 3, 1)

        left_layout.addWidget(params_group)

        # Add separator before actions
        separator2 = QFrame()
        separator2.setFrameShape(QFrame.HLine)
        separator2.setFrameShadow(QFrame.Sunken)
        left_layout.addWidget(separator2)

        # Actions group
        actions_group = QWidget()
        actions_layout = QHBoxLayout(actions_group)
        actions_layout.setContentsMargins(0, 0, 0, 0)
        actions_layout.setSpacing(5)

        # Add update button back for better user experience
        self.btn_update = QPushButton("Update Table")
        self.btn_update.setToolTip(
            "Update the experiment table with the current input values."
        )
        self.btn_update.clicked.connect(self.update_table)
        actions_layout.addWidget(self.btn_update)

        # Export button
        self.btn_export = QPushButton("Export Results")
        self.btn_export.setToolTip("Export the current table results to a CSV file.")
        self.btn_export.clicked.connect(self.export_results)
        actions_layout.addWidget(self.btn_export)

        left_layout.addWidget(actions_group)

        # Add stretch to push everything up
        left_layout.addStretch(1)

        return left_frame

    def _create_right_panel(self):
        """Create the right panel with results table."""
        right_frame = QWidget()
        right_layout = QVBoxLayout(right_frame)
        right_layout.setContentsMargins(5, 5, 5, 5)
        right_layout.setSpacing(3)

        # Add title bar
        title_layout = QHBoxLayout()
        title_label = QLabel("Experiment Configuration Table")
        title_label.setStyleSheet("font-weight: bold;")
        title_label.setToolTip(
            "Displays the generated experiment configurations and results."
        )
        title_layout.addWidget(title_label)
        title_layout.addStretch(1)
        right_layout.addLayout(title_layout)

        # Add separator line
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setFrameShadow(QFrame.Sunken)
        right_layout.addWidget(separator)

        # Results table with size policy for proper stretching
        self.table = QTreeWidget()
        self.table.setAlternatingRowColors(True)
        self.table.setRootIsDecorated(False)
        self.table.setSortingEnabled(False)
        self.table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.table.setToolTip(
            "Table showing all experiment configurations and their calculated results."
        )

        # Set headers
        headers = [
            "Substance",
            "Trials",
            "Cannula\nDiameter\n(mm)",
            "Material\nTilt\n(°)",
            "Counter\nFlow\n(L/h)",
            "Steps\n(1)",
            "Time per\nStroke\n(0.1s)",
            "Droplet\nDiameter\n(mm)",
            "Resulting\nDiameter\n(mm)",
        ]
        self.table.setHeaderLabels(headers)
        self.table.setColumnCount(len(headers))

        # Configure header to distribute space more appropriately
        header = self.table.header()
        header.setSectionResizeMode(QHeaderView.ResizeToContents)
        # Set the substance column to be auto-sized
        header.setSectionResizeMode(0, QHeaderView.Stretch)

        right_layout.addWidget(self.table)

        return right_frame

    def forward_settings_to_controller(self):
        """Forward all input values to controller."""
        self.controller.set_substance(self.substance_combo.currentText())
        self.controller.set_droplet_diameters(self.droplet_entry.text())
        self.controller.set_counter_flows(self.flow_entry.text())
        self.controller.set_tilts(self.tilt_entry.text())
        self.controller.set_trials(self.trial_entry.text())

    @Slot()
    def update_table(self):
        """Process data and update the table with results."""
        logger.info("Starting table update process")
        self.forward_settings_to_controller()

        # Validate inputs
        if not all(
            [
                self.controller.substance,
                self.controller.droplet_diameters,
                self.controller.counter_flows,
                self.controller.tilts,
            ]
        ):
            logger.warning("Invalid or missing input parameters for table update")
            return

        # Process data
        success, error_msg = self.controller.process_data(
            self.controller.substance,
            self.controller.droplet_diameters,
            self.controller.counter_flows,
            self.controller.tilts,
        )

        if not success:
            logger.error(f"Data processing failed: {error_msg}")
            QMessageBox.critical(self, "Invalid Input", error_msg)
            return

        logger.info("Data processing completed successfully")
        # Update table with results
        self.results = self.controller.results
        self.table.clear()

        for result in self.results:
            item = QTreeWidgetItem(self.table)
            for i, value in enumerate(result.values()):
                item.setText(i, str(value))

        logger.info("Table update completed successfully")

    #         self.btn_export.setEnabled(len(self.results) > 0)

    @Slot()
    def export_results(self):
        """Export results to CSV file."""
        logger.info("Starting CSV export process")

        if not self.results:
            logger.warning("No results available for export")
            QMessageBox.warning(
                self, "No Results", "No results to export. Please generate data first."
            )
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Results",
            os.path.expanduser("~/experiment_table.csv"),
            "CSV Files (*.csv)",
        )

        if not file_path:
            logger.info("CSV export cancelled by user")
            return

        logger.info(f"Exporting results to: {file_path}")
        try:
            # Get system CSV settings (just need delimiter, won't change decimal format)
            _, delimiter = self._get_system_csv_settings()

            # Create a copy of the results with updated keys for the CSV export
            csv_results = []
            for result in self.results:
                fixed_result = {}
                for key, value in result.items():
                    if key == "TpS (1/s)":
                        fixed_result["Time per Stroke (0.1s)"] = value
                    elif key == "Steps":
                        fixed_result["Steps (1)"] = value
                    else:
                        fixed_result[key] = value
                csv_results.append(fixed_result)

            with open(file_path, "w", newline="", encoding="utf-8") as csvfile:
                writer = csv.DictWriter(
                    csvfile, fieldnames=list(csv_results[0].keys()), delimiter=delimiter
                )
                writer.writeheader()

                # Write rows without any type conversion - keep everything as strings
                writer.writerows(csv_results)

            logger.info("CSV export completed successfully")

        except Exception as e:
            logger.error(f"Error exporting results: {e}")
            QMessageBox.critical(
                self, "Export Error", f"Failed to export results: {e!s}"
            )

    def _get_system_csv_settings(self):
        """Detect system CSV settings (decimal separator and delimiter).

        Returns
        -------
            tuple: (decimal_separator, delimiter)

        """
        # Get current locale settings
        current_locale = locale.getlocale(locale.LC_NUMERIC)

        # Try to determine decimal separator from locale
        try:
            # Set locale to user's default
            locale.setlocale(locale.LC_NUMERIC, "")
            # Get decimal point from locale
            decimal_separator = locale.localeconv()["decimal_point"]
            # Reset locale
            locale.setlocale(locale.LC_NUMERIC, current_locale)
        except (locale.Error, KeyError) as e:
            # Default to period if locale settings can't be determined
            logger.warning(f"Could not determine locale settings, using default: {e}")
            decimal_separator = "."

        # Determine delimiter based on decimal separator
        # If decimal separator is comma, use semicolon as delimiter
        # Otherwise use comma as delimiter
        delimiter = ";" if decimal_separator == "," else ","

        return decimal_separator, delimiter
