"""Executable build script for packaging MesszelleApp for distribution."""

import os
import subprocess
import sys


def build_executable():
    """Build the MesszelleApp executable using PyInstaller."""
    print("Building MesszelleApp executable...")
    # Define PyInstaller command
    command = [
        "pyinstaller",
        "--name=MesszelleApp",
        "--onefile",
        "--windowed",
        "--icon=resources/icons/avt.ico",
        "--add-data=resources;resources",
        "--add-data=config;config",
        # Core modules
        "--hidden-import=src.core.cell_core",
        "--hidden-import=src.core.analysis_core",
        "--hidden-import=src.core.camera_core",
        "--hidden-import=src.core.dosage_core",
        "--hidden-import=src.core.pump_core",
        "--hidden-import=src.core.table_core",
        # Widgets
        "--hidden-import=src.widgets.cell_widgets",
        "--hidden-import=src.widgets.analysis_widgets",
        "--hidden-import=src.widgets.camera_widgets",
        "--hidden-import=src.widgets.dosage_widgets",
        "--hidden-import=src.widgets.pump_widgets",
        "--hidden-import=src.widgets.table_widgets",
        # Main modules
        "--hidden-import=src.main.cell",
        "--hidden-import=src.main.analysis",
        "--hidden-import=src.main.camera",
        "--hidden-import=src.main.dosage",
        "--hidden-import=src.main.pump",
        "--hidden-import=src.main.table",
        # Threads
        "--hidden-import=src.threads.cell_threads",
        "--hidden-import=src.threads.analysis_threads",
        "--hidden-import=src.threads.camera_threads",
        "--hidden-import=src.threads.dosage_threads",
        # Utilities
        "--hidden-import=src.utilities.port",
        "--hidden-import=src.utilities.image",
        "--hidden-import=src.utilities.logging_manager",
        "--hidden-import=src.utilities.roi",
        "--hidden-import=src.utilities.overlays",
        "--hidden-import=src.utilities.XsCamera",
        "--hidden-import=src.utilities.conversion",
        # Helpers
        "--hidden-import=src.helpers.area_calculation",
        "--hidden-import=src.helpers.baseline",
        "--hidden-import=src.helpers.batch",
        "--hidden-import=src.helpers.contact_angle",
        "--hidden-import=src.helpers.contact_detection",
        "--hidden-import=src.helpers.contour",
        "--hidden-import=src.helpers.drawing",
        "--hidden-import=src.helpers.initialisation",
        "--hidden-import=src.helpers.intersection",
        "--hidden-import=src.helpers.packing",
        "--hidden-import=src.helpers.preview",
        "--hidden-import=src.helpers.save_results",
        "--hidden-import=src.helpers.velocity",
        # SciPy and dependencies
        "--hidden-import=scipy._cyutility",
        "--collect-submodules=scipy",
        "--collect-data=scipy",
        # Excel writer
        "--hidden-import=xlsxwriter",
        "app.py",
    ]

    # Windows specific path format
    if sys.platform.startswith("win"):
        command[5] = "--add-data=resources;resources"
        command[6] = "--add-data=config;config"
    else:
        command[5] = "--add-data=resources:resources"
        command[6] = "--add-data=config:config"

    # Run PyInstaller
    subprocess.call(command)

    # Check if executable was created
    exe_path = os.path.join("dist", "MesszelleApp.exe")
    if os.path.exists(exe_path):
        print(f"\nExecutable successfully created at: {os.path.abspath(exe_path)}")
        print(
            "You can distribute this executable file to run the application "
            "without Python installed."
        )
    else:
        print("\nError: Executable creation failed.")
        print("Check the PyInstaller output above for errors.")


if __name__ == "__main__":
    build_executable()
