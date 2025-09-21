"""Analysis core functionality.

For droplet and experiment analysis in Droplet Wall Interaction Tool.
"""

import glob
import math
import os
from typing import Any, Callable, Optional

import cv2
import numpy as np
from PySide6.QtCore import Property, QObject, QSettings, Signal

from src.helpers.baseline import find_single_baseline
from src.helpers.contact_angle import (
    calculate_contact_angle_left,
    calculate_contact_angle_right,
    calculate_contact_angles,
    calculate_ellipse_contact_angle,
    calculate_tangent_contact_angles,
    fit_left_polynomial,
    fit_right_polynomial,
    rotate_coordinates_90,
)
from src.helpers.contact_detection import (
    detect_vertical_line_contact,
    draw_contact_indicators,
    get_contact_frame_status,
)
from src.helpers.contour import (
    calculate_drop_area,
    crop_contour_points,
    filter_contour_by_baseline_slope,
    filter_contour_by_vertical_lines,
    process_contour,
)
from src.helpers.drawing import (
    draw_axis_line,
    draw_center_point,
    draw_connection_line,
    draw_dual_baselines,
    draw_filled_contour,
    draw_intersection_points,
    draw_rectangle,
    highlight_interaction_zone,
)
from src.helpers.initialisation import initiate_run, start_run
from src.helpers.intersection import find_intersection_points
from src.helpers.save_results import save_results
from src.helpers.structured_packing import find_vertical_lines
from src.helpers.velocity import calculate_velocities
from src.utilities.image import (
    convert_videos_to_images,
    create_background_image,
    crop_image,
    rotate_image,
)
from src.utilities.logging_manager import get_logger

# Setup logger for this module
logger = get_logger(__name__)


class AnalysisCore(QObject):
    """Core functionality for analysis with improved structure.

    Provides properties, signals, and processing methods for analysis.
    Manages settings persistence and image processing operations.
    """

    def __init__(
        self,
        folder_path: Optional[str] = None,
        analysis_mode: str = "free_sedimentation",
    ):
        """Initialize the core with an optional folder path and analysis mode.

        Args:
        ----
            folder_path: Optional initial folder path
            analysis_mode: The mode of analysis (e.g., "contact_angle",
                "free_sedimentation")

        """
        super().__init__()
        logger.debug(f"Initializing AnalysisCore with mode: {analysis_mode}")

        try:
            self.analysis_mode = analysis_mode

            # Initialize settings with mode-specific group
            settings_group = f"Analysismode_{self.analysis_mode}"
            self.settings = QSettings("CellSettings", settings_group)

            # Load settings from persistent storage
            self.load_settings()

            # Force rotate and baseline to 0 for free_sedimentation and channel
            if self.analysis_mode in [
                "free_sedimentation",
                "channel",
                "structured_packing",
            ]:
                logger.debug(
                    f"Analysis mode '{self.analysis_mode}' detected - "
                    f"forcing rotation and baseline to 0"
                )
                self.set_baseline(0)
                self.set_baseline_tf(True)
                self.set_manual_baseline(0)
            if self.analysis_mode in [
                "free_sedimentation",
                "structured_packing",
            ]:
                self.set_rotate_angle(0.0)

            # Set folder path if provided
            if folder_path is not None:
                self.set_folder_path(folder_path)
                # If no folders in the list, add this one
                if folder_path not in self._folder_paths:
                    self.add_folder_path(folder_path)

            # Constant values
            self.image_extensions = [
                "*.jpg",
                "*.jpeg",
                "*.png",
                "*.bmp",
                "*.gif",
                "*.tiff",
            ]

            # Initialize contour tracking for area/diameter calculations
            self._current_contour = None

            # Calculated values - output_path is the folder where results are written
            self.output_path = self._folder_path if self._folder_path else ""

            logger.debug(
                f"AnalysisCore initialization completed successfully for mode: "
                f"{analysis_mode}"
            )

        except Exception as e:
            logger.error(f"Failed to initialize AnalysisCore: {e}")
            logger.error(f"Analysis mode: {analysis_mode}")
            logger.error(f"Folder path: {folder_path}")
            raise

    # region SIGNALS
    folder_path_changed = Signal(str)
    baseline_changed = Signal(bool)
    pixel_per_mm_changed = Signal(float)
    fps_changed = Signal(int)
    y_img_changed = Signal(int)
    h_img_changed = Signal(int)
    x_img_changed = Signal(int)
    w_img_changed = Signal(int)
    threshold_changed = Signal(int)
    manual_baseline_changed = Signal(int)
    polynom_changed = Signal(int)
    rotate_angle_changed = Signal(float)
    baseline_changed = Signal(int)
    fitting_mode_changed = Signal(str)
    error_occurred = Signal(str)
    image_processed = Signal(int, dict)
    folder_paths_changed = Signal(list)
    main_folder_path_changed = Signal(str)
    # endregion

    # region SETTERS
    def update_parameters(
        self,
        fitting_mode=None,
        polynom=None,
        baseline_tf=None,
        fps=None,
        pixel=None,
        h_img=None,
        y_img=None,
        w_img=None,
        x_img=None,
        manual_baseline=None,
        rotate_angle=None,
        baseline=None,
        threshold=None,
    ):
        """Update analysis parameters from thread/controller."""
        param_map = [
            ("fitting_mode", fitting_mode),
            ("polynom", polynom),
            ("baseline_tf", baseline_tf),
            ("fps", fps),
            ("pixel", pixel),
            ("h_img", h_img),
            ("y_img", y_img),
            ("w_img", w_img),
            ("x_img", x_img),
            ("manual_baseline", manual_baseline),
            ("rotate_angle", rotate_angle),
            ("baseline", baseline),
            ("threshold", threshold),
        ]
        for attr, value in param_map:
            if value is not None:
                setattr(self, attr, value)

    def save_setting(self, key: str, value: Any) -> None:
        """Save a specific setting for the current analysis_mode."""
        try:
            self.settings.beginGroup(f"Analysismode_{self.analysis_mode}")
            self.settings.setValue(key, value)
            self.settings.endGroup()
            self.settings.sync()  # Ensure data is written to disk
        except Exception as e:
            logger.error(f"Failed to save setting '{key}': {e}")

    def add_folder_path(self, folder_path: str) -> None:
        """Add a folder path to the list if it's not already there."""
        if folder_path and folder_path not in self._folder_paths:
            self._folder_paths.append(folder_path)
            logger.info(f"Added new folder path: {folder_path}")
            self.save_setting("folderPaths", self._folder_paths)

            # If this is the first folder or we don't have a main folder, set it as main
            if not self._main_folder_path:
                logger.info(
                    f"Setting {folder_path} as main folder (first folder added)"
                )
                self._main_folder_path = folder_path
                self.save_setting("mainFolderPath", folder_path)
                self.main_folder_path_changed.emit(folder_path)

            self.folder_paths_changed.emit(self._folder_paths)

    def remove_folder_path(self, folder_path: str) -> None:
        """Remove a folder path from the list."""
        if folder_path in self._folder_paths:
            self._folder_paths.remove(folder_path)
            logger.info(f"Removed folder path: {folder_path}")
            # If removing the main folder, clear it
            if folder_path == self._main_folder_path:
                logger.warning(f"Removing main folder path: {folder_path}")
                self._main_folder_path = ""
                self.save_setting("mainFolderPath", "")
                self.main_folder_path_changed.emit("")
            self.save_setting("folderPaths", self._folder_paths)
            self.folder_paths_changed.emit(self._folder_paths)
        else:
            logger.warning(
                f"Attempted to remove non-existent folder path: {folder_path}"
            )

    def clear_folder_paths(self) -> None:
        """Clear all folder paths from the list."""
        logger.info("Clearing all folder paths")
        self._folder_paths = []
        self.save_setting("folderPaths", [])
        self.folder_paths_changed.emit([])

    def set_folder_path(self, value: str) -> None:
        """Set the folder path and update settings."""
        # Protect against invalid paths
        if not value or not isinstance(value, str):
            logger.warning(f"Invalid folder path provided: {value}")
            return

        if self._folder_path != value:
            logger.info(f"Folder path changed from '{self._folder_path}' to '{value}'")
            self._folder_path = value

            # Reset vertical lines when folder changes (for structured_packing mode)
            if self.analysis_mode == "structured_packing":
                self._vertical_left = None
                self._vertical_right = None
                logger.debug(
                    "Reset vertical lines for new folder in structured_packing mode"
                )

            # Save to settings
            self.save_setting("folderPath", value)
            # Update output path (no 'Output' subfolder)
            self.output_path = value if value else ""
            self.folder_path_changed.emit(value)

    def set_baseline_tf(self, value: bool) -> None:
        """Set the baseline toggle flag value."""
        if self._baseline_tf != value:
            self._baseline_tf = value
            self.save_setting("baselineTF", value)
            self.baseline_changed.emit(value)

    def set_pixel(self, value: float) -> None:
        """Set the pixel per millimeter calibration value."""
        if self._pixel != value:
            self._pixel = value
            self.save_setting("pixel_per_mm", value)
            self.pixel_per_mm_changed.emit(value)

    def set_fps(self, value: int) -> None:
        """Set the frames per second value."""
        if self._fps != value:
            self._fps = value
            self.save_setting("fps", value)
            self.fps_changed.emit(value)

    def set_y_img(self, value: int) -> None:
        """Set the Y coordinate for image cropping."""
        if self._y_img != value:
            self._y_img = value
            self.save_setting("yImg", value)
            self.y_img_changed.emit(value)

    def set_h_img(self, value: int) -> None:
        """Set the height for image cropping."""
        if self._h_img != value:
            self._h_img = value
            self.save_setting("hImg", value)
            self.h_img_changed.emit(value)

    def set_x_img(self, value: int) -> None:
        """Set the X coordinate for image cropping."""
        if self._x_img != value:
            self._x_img = value
            self.save_setting("xImg", value)
            self.x_img_changed.emit(value)

    def set_w_img(self, value: int) -> None:
        """Set the width for image cropping."""
        if self._w_img != value:
            self._w_img = value
            self.save_setting("wImg", value)
            self.w_img_changed.emit(value)

    def set_threshold(self, value: int) -> None:
        """Set the threshold value for image analysis."""
        if self._threshold != value:
            self._threshold = value
            self.save_setting("threshold", value)
            self.threshold_changed.emit(value)

    def set_manual_baseline(self, value: int) -> None:
        """Set the manual baseline height value."""
        if self._manual_baseline != value:
            self._manual_baseline = value
            self.save_setting("manual_baseline", value)
            self.manual_baseline_changed.emit(value)

    def set_polynom(self, value: int) -> None:
        """Set the polynomial fitting degree value."""
        if self._polynom != value:
            self._polynom = value
            self.save_setting("polynom", value)
            self.polynom_changed.emit(value)

    def set_rotate_angle(self, value: float) -> None:
        """Set the image rotation angle value."""
        if self._rotate_angle != value:
            self._rotate_angle = value
            self.save_setting("rotateAngle", value)
            self.rotate_angle_changed.emit(value)

    def set_baseline(self, value: int) -> None:
        """Set the baseline detection parameter value."""
        if self._baseline != value:
            self._baseline = value
            self.save_setting("baseline", value)
            self.baseline_changed.emit(value)

    def set_fitting_mode(self, value: str) -> None:
        """Set the fitting mode value."""
        if self._fitting_mode != value:
            self._fitting_mode = value
            self.save_setting("fitting_mode", value)
            self.fitting_mode_changed.emit(value)

    def set_folder_paths(self, value: list) -> None:
        """Set the list of folder paths."""
        if self._folder_paths != value:
            self._folder_paths = value
            self.save_setting("folderPaths", value)
            self.folder_paths_changed.emit(value)

    def set_main_folder_path(self, value: str) -> None:
        """Set the main folder path for analysis."""
        if self._main_folder_path != value:
            self._main_folder_path = value
            self.save_setting("mainFolderPath", value)
            self.main_folder_path_changed.emit(value)

    # endregion SETTERS

    # region GETTERS
    def load_settings(self) -> None:
        """Load settings from persistent storage for the current analysis mode.

        This method orchestrates three smaller helpers to keep complexity low:
        - _load_common_settings: loads values shared across modes
        - _load_mode_specific_settings: loads mode-dependent defaults
        - _validate_and_clean_folder_paths: ensures folder lists are valid
        """
        logger.info(f"Loading settings for analysis mode: {self.analysis_mode}")

        try:
            # Load settings under the analysis-mode group
            self.settings.beginGroup(f"Analysismode_{self.analysis_mode}")
            self._load_common_settings()
            self._load_mode_specific_settings()
            self.settings.endGroup()

            # Validate and persist cleaned folder paths (may re-open group)
            self._validate_and_clean_folder_paths()

        except Exception as e:
            logger.error(f"Failed to load settings for {self.analysis_mode}: {e}")
            raise

    def _load_common_settings(self) -> None:
        """Load settings that apply regardless of analysis mode."""
        self._pixel = self.settings.value("pixel_per_mm", 55.00, type=float)
        self._fps = self.settings.value("fps", 100, type=int)
        self._manual_baseline = self.settings.value("manual_baseline", 0, type=int)
        self._rotate_angle = self.settings.value("rotateAngle", 0.0, type=float)
        self._baseline = self.settings.value("baseline", 0, type=int)
        self._fitting_mode = self.settings.value("fitting_mode", "Arc", type=str)
        self._polynom = self.settings.value("polynom", 3, type=int)

        # Structured packing vertical lines (detected once, used for all images)
        self._vertical_left = None
        self._vertical_right = None

    def _load_mode_specific_settings(self) -> None:
        """Load settings that depend on the selected analysis mode."""
        if self.analysis_mode == "free_sedimentation":
            self._y_img = self.settings.value("yImg", 300, type=int)
            self._h_img = self.settings.value("hImg", 800, type=int)
            self._x_img = self.settings.value("xImg", 0, type=int)
            self._w_img = self.settings.value("wImg", 2900, type=int)
            # Use absolute paths for default test folders so the UI shows
            # the full path instead of a shortened/relative one.
            default = os.path.abspath(
                self.settings.value(
                    "folderPath", "tests/free_sedimentation (BuAc_d_large)"
                )
            )
            self._folder_path = self.settings.value("folderPath", default)
            default_list = [
                os.path.abspath(p)
                for p in self.settings.value(
                    "folderPaths",
                    ["tests/free_sedimentation (BuAc_d_large)"],
                    type=list,
                )
            ]
            self._folder_paths = self.settings.value(
                "folderPaths", default_list, type=list
            )
            self._main_folder_path = self.settings.value(
                "mainFolderPath", default, type=str
            )
            self._baseline_tf = self.settings.value("baselineTF", True, type=bool)
            self._threshold = self.settings.value("threshold", 20, type=int)
            self._rotate_angle = self.settings.value("rotateAngle", 0.0, type=float)

        elif self.analysis_mode == "channel":
            self._y_img = self.settings.value("yImg", 900, type=int)
            self._h_img = self.settings.value("hImg", 1200, type=int)
            self._x_img = self.settings.value("xImg", 0, type=int)
            self._w_img = self.settings.value("wImg", 2500, type=int)
            default = os.path.abspath(
                self.settings.value("folderPath", "tests/channel (BuAc_d_large)")
            )
            self._folder_path = self.settings.value("folderPath", default)
            default_list = [
                os.path.abspath(p)
                for p in self.settings.value(
                    "folderPaths", ["tests/channel (BuAc_d_large)"], type=list
                )
            ]
            self._folder_paths = self.settings.value(
                "folderPaths", default_list, type=list
            )
            self._main_folder_path = self.settings.value(
                "mainFolderPath", default, type=str
            )
            self._baseline_tf = self.settings.value("baselineTF", False, type=bool)
            self._threshold = self.settings.value("threshold", 50, type=int)
            self._rotate_angle = self.settings.value("rotateAngle", 45.60, type=float)

        elif self.analysis_mode == "structured_packing":
            self._y_img = self.settings.value("yImg", 900, type=int)
            self._h_img = self.settings.value("hImg", 1300, type=int)
            self._x_img = self.settings.value("xImg", 0, type=int)
            self._w_img = self.settings.value("wImg", 2900, type=int)
            default = os.path.abspath(
                self.settings.value(
                    "folderPath", "tests/structured_packing (BuAc_d_large)"
                )
            )
            self._folder_path = self.settings.value("folderPath", default)
            default_list = [
                os.path.abspath(p)
                for p in self.settings.value(
                    "folderPaths",
                    ["tests/structured_packing (BuAc_d_large)"],
                    type=list,
                )
            ]
            self._folder_paths = self.settings.value(
                "folderPaths", default_list, type=list
            )
            self._main_folder_path = self.settings.value(
                "mainFolderPath", default, type=str
            )
            self._baseline_tf = self.settings.value("baselineTF", True, type=bool)
            self._threshold = self.settings.value("threshold", 20, type=int)
            self._rotate_angle = self.settings.value("rotateAngle", 0.0, type=float)

        else:
            self._y_img = self.settings.value("yImg", 1300, type=int)
            self._h_img = self.settings.value("hImg", 1700, type=int)
            self._x_img = self.settings.value("xImg", 300, type=int)
            self._w_img = self.settings.value("wImg", 2500, type=int)
            default = os.path.abspath(
                self.settings.value("folderPath", "tests/contact_wall (BuAc_d_large)")
            )
            self._folder_path = self.settings.value("folderPath", default)
            default_list = [
                os.path.abspath(p)
                for p in self.settings.value(
                    "folderPaths", ["tests/contact_wall (BuAc_d_large)"], type=list
                )
            ]
            self._folder_paths = self.settings.value(
                "folderPaths", default_list, type=list
            )
            self._main_folder_path = self.settings.value(
                "mainFolderPath", default, type=str
            )
            self._baseline_tf = self.settings.value("baselineTF", False, type=bool)
            self._threshold = self.settings.value("threshold", 50, type=int)
            self._rotate_angle = self.settings.value("rotateAngle", 42.60, type=float)

    def _validate_and_clean_folder_paths(self) -> None:
        """Validate stored folder paths, persist cleaned results and emit signals."""
        try:
            paths = self._normalize_folder_paths(self._folder_paths)
            cleaned_paths = [p for p in paths if p and os.path.isdir(p)]

            # Log missing entries
            for p in paths:
                if p and p not in cleaned_paths:
                    logger.warning(
                        "Stored folder path does not exist and was " f"removed: {p}"
                    )

            # If nothing changed, emit signals and return
            if cleaned_paths == getattr(self, "_folder_paths", []):
                try:
                    self.folder_paths_changed.emit(self._folder_paths)
                    self.main_folder_path_changed.emit(self._main_folder_path or "")
                except Exception:
                    pass
                return

            # Update internal state and persist changes
            self._folder_paths = cleaned_paths
            self._persist_cleaned_folder_paths()

            try:
                self.folder_paths_changed.emit(self._folder_paths)
                self.main_folder_path_changed.emit(self._main_folder_path or "")
            except Exception:
                pass

        except Exception as e:
            logger.error(f"Error validating stored folder paths: {e}")

    def _normalize_folder_paths(self, paths) -> list:
        """Return a list of folder paths normalized from stored value."""
        if isinstance(paths, str):
            return [paths]
        if isinstance(paths, list):
            return paths
        try:
            return list(paths or [])
        except Exception:
            return []

    def _persist_cleaned_folder_paths(self) -> None:
        """Persist cleaned folder paths and ensure main/folderPath stay valid."""
        try:
            self.settings.beginGroup(f"Analysismode_{self.analysis_mode}")
            self.settings.setValue("folderPaths", self._folder_paths)

            # If main folder no longer exists, set to first or clear
            if not self._main_folder_path or not os.path.isdir(self._main_folder_path):
                if self._folder_paths:
                    self._main_folder_path = self._folder_paths[0]
                    self.settings.setValue("mainFolderPath", self._main_folder_path)
                else:
                    self._main_folder_path = ""
                    self.settings.setValue("mainFolderPath", "")

            # If folderPath (current single folder) is missing, fix it
            if not self._folder_path or not os.path.isdir(self._folder_path):
                if self._main_folder_path:
                    self._folder_path = self._main_folder_path
                    self.settings.setValue("folderPath", self._folder_path)
                else:
                    self._folder_path = ""
                    self.settings.setValue("folderPath", "")

            self.settings.endGroup()
            self.settings.sync()
        except Exception as e:
            logger.error(f"Failed to persist cleaned folder paths: {e}")

    def reset_to_defaults(self) -> None:
        """Reset selected parameters to their mode-specific defaults.

        This method only resets a subset of parameters depending on the
        analysis mode as requested by the UI behavior. It uses the public
        setters so that settings are persisted and change signals are emitted
        to update any bound UI.
        """
        logger.info(f"Resetting parameters to defaults for mode: {self.analysis_mode}")
        try:
            # Common defaults
            self.set_pixel(55.00)
            self.set_fps(100)

            # Mode-specific defaults
            if self.analysis_mode == "free_sedimentation":
                # Reset FPS, pixel, threshold, ROI
                self.set_threshold(20)
                self.set_y_img(300)
                self.set_h_img(800)
                self.set_x_img(0)
                self.set_w_img(2900)

            elif self.analysis_mode == "channel":
                # Reset many parameters for channel
                self.set_threshold(50)
                self.set_rotate_angle(45.60)
                self.set_baseline(0)
                self.set_baseline_tf(False)
                self.set_manual_baseline(0)
                self.set_fitting_mode("Arc")
                self.set_polynom(3)
                self.set_y_img(900)
                self.set_h_img(1200)
                self.set_x_img(0)
                self.set_w_img(2500)

            elif self.analysis_mode == "structured_packing":
                # Reset FPS, pixel, threshold, ROI for structured packing
                self.set_threshold(20)
                self.set_y_img(900)
                self.set_h_img(1300)
                self.set_x_img(0)
                self.set_w_img(2900)

            else:
                # Default (contact_angle and other modes)
                self.set_threshold(50)
                self.set_rotate_angle(42.60)
                self.set_baseline(0)
                self.set_baseline_tf(False)
                self.set_manual_baseline(0)
                self.set_fitting_mode("Arc")
                self.set_polynom(3)
                self.set_y_img(1300)
                self.set_h_img(1700)
                self.set_x_img(300)
                self.set_w_img(2500)

            # Ensure settings are synced to persistent store
            try:
                self.settings.beginGroup(f"Analysismode_{self.analysis_mode}")
                self.settings.sync()
                self.settings.endGroup()
            except Exception:
                pass

        except Exception as e:
            logger.error(f"Failed to reset defaults: {e}")

    # Property getters and setters
    def get_folder_path(self) -> str:
        """Get the current folder path value."""
        return self._folder_path

    def get_baseline_tf(self) -> bool:
        """Get the current baseline toggle flag value."""
        return self._baseline_tf

    def get_pixel(self) -> float:
        """Get the current pixel per millimeter calibration value."""
        return self._pixel

    def get_fps(self) -> int:
        """Get the current frames per second value."""
        return self._fps

    def get_y_img(self) -> int:
        """Get the current Y coordinate for image cropping."""
        return self._y_img

    def get_h_img(self) -> int:
        """Get the current height for image cropping."""
        return self._h_img

    def get_x_img(self) -> int:
        """Get the current X coordinate for image cropping."""
        return self._x_img

    def get_w_img(self) -> int:
        """Get the current width for image cropping."""
        return self._w_img

    def get_threshold(self) -> int:
        """Get the current threshold value for image analysis."""
        return self._threshold

    def get_manual_baseline(self) -> int:
        """Get the current manual baseline height value."""
        return self._manual_baseline

    def get_polynom(self) -> int:
        """Get the current polynomial fitting degree value."""
        return self._polynom

    def get_rotate_angle(self) -> float:
        """Get the current image rotation angle value."""
        return self._rotate_angle

    def get_baseline(self) -> int:
        """Get the current baseline detection parameter value."""
        return self._baseline

    def get_fitting_mode(self) -> str:
        """Get the current fitting mode value."""
        return self._fitting_mode

    def get_folder_paths(self) -> list:
        """Get the list of folder paths."""
        return self._folder_paths

    def get_main_folder_path(self) -> str:
        """Get the main folder path for analysis."""
        return self._main_folder_path

    # endregion GETTERS

    # region PROPERTIES
    folder_path = Property(
        str, get_folder_path, set_folder_path, notify=folder_path_changed
    )
    baseline_tf = Property(
        bool, get_baseline_tf, set_baseline_tf, notify=baseline_changed
    )
    pixel = Property(float, get_pixel, set_pixel, notify=pixel_per_mm_changed)
    fps = Property(int, get_fps, set_fps, notify=fps_changed)
    y_img = Property(int, get_y_img, set_y_img, notify=y_img_changed)
    h_img = Property(int, get_h_img, set_h_img, notify=h_img_changed)
    x_img = Property(int, get_x_img, set_x_img, notify=x_img_changed)
    w_img = Property(int, get_w_img, set_w_img, notify=w_img_changed)
    threshold = Property(int, get_threshold, set_threshold, notify=threshold_changed)
    manual_baseline = Property(
        int, get_manual_baseline, set_manual_baseline, notify=manual_baseline_changed
    )
    polynom = Property(int, get_polynom, set_polynom, notify=polynom_changed)
    rotate_angle = Property(
        float, get_rotate_angle, set_rotate_angle, notify=rotate_angle_changed
    )
    baseline = Property(int, get_baseline, set_baseline, notify=baseline_changed)
    fitting_mode = Property(
        str, get_fitting_mode, set_fitting_mode, notify=fitting_mode_changed
    )
    folder_paths = Property(
        list, get_folder_paths, set_folder_paths, notify=folder_paths_changed
    )
    main_folder_path = Property(
        str, get_main_folder_path, set_main_folder_path, notify=main_folder_path_changed
    )
    # endregion PROPERTIES

    def process_images(
        self,
        progress_callback=None,
        save_files=True,
        preview_middle=False,
        use_first_as_background=False,
    ):
        """Process images using current parameters with improved path handling.

        Args:
        ----
            progress_callback: Function to call with progress updates
            save_files: Whether to save result files (not images)
            preview_middle: If True, only process the middle image for preview
            use_first_as_background: If True, use the first image as the background

        Returns:
        -------
            tuple containing analysis results or None if an error occurred.

        """
        logger.info("Starting image processing")

        # Validate folder path and check for media files
        if not self._validate_folder_path():
            return None

        # Get all available image files
        image_files = self._collect_image_files(progress_callback)
        if image_files is None:
            return None

        # Determine which files to process based on mode
        all_files, process_files = self._select_files_for_processing(
            image_files, preview_middle
        )

        # xlsx_file_path is in the selected output folder under "results_raw.xlsx"
        xlsx_file_path = os.path.join(self.output_path, "results_raw.xlsx")
        # Process images and return results - pass all files for background creation
        return self._main(
            xlsx_file_path,
            process_files,
            save_files,
            progress_callback,
            use_first_as_background,
            background_files=all_files,
        )

    def _validate_folder_path(self) -> bool:
        """Validate the folder path and check for special characters.

        Returns
        -------
            bool: True if folder path is valid, False otherwise

        """
        # First check if the folder path is valid
        if not self._folder_path or not os.path.isdir(self._folder_path):
            logger.error(f"No valid folder selected. Path: {self._folder_path}")
            self.error_occurred.emit(
                "No valid folder selected. Please select a folder before analysis."
            )
            return False

        # Check for special (non-ASCII) characters in the folder path
        try:
            self._folder_path.encode("ascii")
            return True
        except UnicodeEncodeError:
            logger.warning(f"Special characters in folder path: {self._folder_path}")
            self.error_occurred.emit(
                "The selected folder path contains special characters "
                "(e.g., ü, ä, ö, ß). Please use a path with only standard "
                "English letters and numbers."
            )
            logger.warning(
                "The selected folder path contains special characters "
                "(e.g., ü, ä, ö, ß). Please use a path with only standard "
                "English letters and numbers."
            )
            return False

    def _collect_image_files(self, progress_callback) -> list[str] | None:
        """Collect all image files from the folder, including extracted from videos.

        Args:
        ----
            progress_callback: Callback for progress updates during video extraction

        Returns:
        -------
            list[str] | None: List of image file paths or None if no files found

        """
        # Check for at least one image or video file in the folder before proceeding
        if not self._has_media_files():
            return None

        # First check for video files and convert them to images if found
        extracted_images = convert_videos_to_images(
            self._folder_path, progress_callback
        )
        if extracted_images:
            logger.info(
                f"Extracted {len(extracted_images)} images from video files "
                f"for detection."
            )

        # Find image files in the folder with fully qualified paths
        image_files = []
        for ext in self.image_extensions:
            files_found = glob.glob(os.path.join(self._folder_path, ext))
            image_files.extend(files_found)

        # Add extracted images if any were found
        if extracted_images:
            image_files.extend(extracted_images)

        if not image_files:
            logger.error(
                f"No image or video files found in the selected folder "
                f"after extraction. Path: {self._folder_path}"
            )
            self.error_occurred.emit(
                "No image or video files found in the selected folder"
            )
            return None

        # Sort files by name
        image_files.sort()
        return image_files

    def _has_media_files(self) -> bool:
        """Check if the folder contains any media files (images or videos).

        Returns
        -------
            bool: True if media files are found, False otherwise

        """
        has_media = False

        # Check for images
        for ext in self.image_extensions:
            found = glob.glob(os.path.join(self._folder_path, ext))
            if found:
                has_media = True
                break

        # Check for common video extensions if no images found
        if not has_media:
            video_exts = ["*.mp4", "*.avi", "*.mov", "*.mkv", "*.wmv", "*.flv"]
            for vext in video_exts:
                found = glob.glob(os.path.join(self._folder_path, vext))
                if found:
                    has_media = True
                    logger.info(f"Found video file(s) with extension {vext}")
                    break

        if not has_media:
            logger.error(f"No image or video files found in {self._folder_path}")
            self.error_occurred.emit(
                "No image or video files found in the selected folder. "
                "Please select a folder containing supported image or video files."
            )
            return False

        return True

    def _select_files_for_processing(
        self, image_files: list[str], preview_middle: bool
    ) -> tuple[list[str], list[str]]:
        """Select which files to process based on the processing mode.

        Args:
        ----
            image_files: List of all available image files
            preview_middle: Whether to use preview mode

        Returns:
        -------
            tuple: (all_files, process_files) - files for background and processing

        """
        # For preview mode, we need to include at least two images to calculate velocity
        if preview_middle:
            all_files = image_files.copy()
            middle_idx = len(image_files) // 2
            if middle_idx > 0:
                process_files = [image_files[middle_idx - 1], image_files[middle_idx]]
            else:
                if len(image_files) > 1:
                    process_files = [image_files[0], image_files[1]]
                else:
                    process_files = [image_files[0]]
                    logger.warning(
                        "Preview mode: only one image available, "
                        "velocity calculation may be invalid."
                    )
        else:
            all_files = image_files
            process_files = image_files

        return all_files, process_files

    def _main(
        self,
        xlsx_file_path: str,
        files: list[str],
        save_files: bool,
        progress_callback: Optional[Callable] = None,
        use_first_as_background: bool = False,
        background_files: Optional[list[str]] = None,
    ) -> tuple[list, list, list, list, list, list, list, list, list]:
        """Run the main analysis pipeline with clean, consistent image processing."""
        # Setup and initialization
        background, time, time_int, result_lists = self._setup_and_initialize(
            files, save_files
        )

        # Initialize result lists with proper structure and default values
        num_files = len(files)
        self._initialize_result_lists(result_lists, num_files)

        # Background image preparation
        background = self._prepare_background_image(
            background_files, files, use_first_as_background
        )

        # Baseline detection
        baseline_data = self._detect_baselines(files)
        if baseline_data is None:
            return None

        (y1_left, y1_right, vertical_left, vertical_right) = baseline_data

        # Process all images
        preloaded_images = self._preload_images_if_reasonable(files)

        processing_stopped = self._process_all_images(
            files,
            background,
            y1_left,
            y1_right,
            vertical_left,
            vertical_right,
            result_lists,
            save_files,
            progress_callback,
            preloaded_images,
        )

        # Calculate velocities and save results
        self._finalize_results(
            result_lists,
            vertical_left,
            vertical_right,
            save_files,
            processing_stopped,
            progress_callback,
            time,
            files,
        )

        return (time, time_int, result_lists)

    def _setup_and_initialize(self, files, save_files):
        """Set up and initialize the analysis run."""
        try:
            background, _, time, time_int, result_lists = initiate_run(
                files, save_files, self._folder_path, self.fps
            )
            return background, time, time_int, result_lists
        except Exception as e:
            logger.error(f"Error in initiate_run: {e}")
            raise

    def _initialize_result_lists(self, result_lists, num_files):
        """Initialize all result lists with proper structure and default values."""
        result_lists["images"] = [{} for _ in range(num_files)]
        result_lists["filenames"] = []
        result_lists["contour_data"] = [None] * num_files

        scalar_lists = [
            "advancing_contact_angles",
            "receding_contact_angles",
            "left_contact_angle_polynom",
            "right_contact_angle_polynom",
            "area_px",
            "area_mm",
            "diameter_px",
            "diameter_mm",
            "rect_width_px",
            "rect_width_mm",
            "rect_height_px",
            "rect_height_mm",
            "ellipse_diameter_px",
            "ellipse_diameter_mm",
            "velocity",
            "area_diameter_px",
            "area_diameter_mm",
            "contact_line_px",
            "contact_line_mm",
        ]

        for key in scalar_lists:
            # Defensive: always re-initialize if not a list or wrong length
            if (
                key not in result_lists
                or not isinstance(result_lists[key], list)
                or len(result_lists[key]) != num_files
            ):
                result_lists[key] = [float("NaN")] * num_files

        for key in ["center_points_px", "center_points_mm"]:
            if (
                key not in result_lists
                or not isinstance(result_lists[key], list)
                or len(result_lists[key]) != num_files
                or not all(
                    isinstance(item, (list, tuple)) and len(item) == 2
                    for item in result_lists[key]
                )
            ):
                result_lists[key] = [
                    [float("NaN"), float("NaN")] for _ in range(num_files)
                ]

        if self.analysis_mode == "structured_packing":
            result_lists["left_contact_frame"] = None
            result_lists["right_contact_frame"] = None
            result_lists["left_contact_detected"] = [False] * num_files
            result_lists["right_contact_detected"] = [False] * num_files
            result_lists["contact_status"] = [""] * num_files
            result_lists["discontinuous_velocity_px_s"] = [float("NaN")] * num_files
            result_lists["discontinuous_velocity_mm_s"] = [float("NaN")] * num_files
            result_lists["vertical_line_distance_px"] = [float("NaN")] * num_files
            result_lists["vertical_line_distance_mm"] = [float("NaN")] * num_files
            result_lists["contact_time_frames"] = [float("NaN")] * num_files
            result_lists["contact_time_seconds"] = [float("NaN")] * num_files

    def _prepare_background_image(
        self, background_files, files, use_first_as_background
    ):
        """Prepare the background image for analysis."""
        files_for_background = (
            background_files if background_files is not None else files
        )

        try:
            background = create_background_image(
                files_for_background,
                use_first_as_background=use_first_as_background,
                rotate_angle=self.rotate_angle,
                crop_params=(self.x_img, self.w_img, self.y_img, self.h_img),
            )
            return background
        except Exception as e:
            logger.error(f"Error creating background image: {e}")
            raise

    def _detect_baselines(self, files):
        """Detect baselines for different analysis modes."""
        middle_index = len(files) // 2
        middle_file = files[middle_index]

        middle_src = cv2.imread(middle_file)
        if middle_src is None:
            logger.error(
                f"Detection: Failed to load middle image file: "
                f"{os.path.basename(middle_file)}"
            )
            self.error_occurred.emit(
                f"Failed to load middle image file: {os.path.basename(middle_file)}"
            )
            return None

        # Process middle image
        middle_src = self._process_middle_image_for_baseline(middle_src)
        if middle_src is None:
            return None

        # Detect baselines based on analysis mode
        return self._detect_baselines_by_mode(middle_src)

    def _process_middle_image_for_baseline(self, middle_src):
        """Process the middle image for baseline detection."""
        try:
            middle_src = rotate_image(middle_src, self.rotate_angle)
            middle_src = crop_image(
                middle_src, (self.x_img, self.w_img, self.y_img, self.h_img)
            )
        except Exception as e:
            logger.error(f"Error processing middle image: {e}")
            return None

        if middle_src.size == 0 or middle_src.shape[0] == 0 or middle_src.shape[1] == 0:
            logger.error("Image is empty after cropping. Check crop parameters.")
            self.error_occurred.emit(
                "Image is empty after cropping. Check crop parameters."
            )
            return None

        return middle_src

    def _detect_baselines_by_mode(self, middle_src):
        """Detect baselines based on the analysis mode."""
        y1_left, y1_right = None, None
        vertical_left, vertical_right = None, None

        if self.analysis_mode == "structured_packing":
            # For structured packing, detect vertical lines once from middle image
            (self._vertical_left, self._vertical_right) = (
                self._detect_structured_packing_lines(middle_src)
            )
            return None, None, self._vertical_left, self._vertical_right
        elif self.analysis_mode in ["free_sedimentation", "channel"]:
            # No baseline detection for free_sedimentation or channel
            return None, None, None, None
        else:
            y1_left, y1_right = self._detect_single_baseline(middle_src)
            if y1_left is None:
                return None
        return y1_left, y1_right, vertical_left, vertical_right

    def _detect_structured_packing_lines(self, middle_src):
        """Detect vertical lines for structured packing mode."""
        try:
            vertical_left, vertical_right = find_vertical_lines(middle_src)
            if not vertical_left and not vertical_right:
                logger.warning("No vertical lines found in structured_packing mode.")
            return vertical_left, vertical_right
        except Exception as e:
            logger.error(f"Error finding vertical lines: {e}")
            return None, None

    def _detect_single_baseline(self, middle_src):
        """Detect single baseline for other modes."""
        try:
            _, w_middle = middle_src.shape[:2]
            crop_left_baseline = int(w_middle * 0.4)
            crop_right_baseline = int(w_middle * 0.6)
            middle_src_for_baseline = middle_src[
                :, crop_left_baseline:crop_right_baseline
            ]

            if (
                middle_src_for_baseline.size == 0
                or middle_src_for_baseline.shape[0] == 0
                or middle_src_for_baseline.shape[1] == 0
            ):
                logger.error("Image for baseline is too small. Check crop parameters.")
                self.error_occurred.emit(
                    "Image for baseline is too small. Check crop parameters."
                )
                return None, None

            y1_left, y1_right = find_single_baseline(
                middle_src_for_baseline,
                self.baseline,
                self.baseline_tf,
                self.manual_baseline,
            )
            return y1_left, y1_right
        except Exception as e:
            logger.error(f"Error finding baseline: {e}")
            return None, None

    def _preload_images_if_reasonable(self, files):
        """Preload images into memory if the dataset isn't too large."""
        preloaded_images = {}
        num_files = len(files)

        if num_files < 100:  # Only preload for reasonable sized datasets
            for file_path in files:
                img = cv2.imread(file_path)
                if img is not None:
                    preloaded_images[file_path] = img

        return preloaded_images

    def _process_all_images(
        self,
        files,
        background,
        y1_left,
        y1_right,
        vertical_left,
        vertical_right,
        result_lists,
        save_files,
        progress_callback,
        preloaded_images,
    ):
        """Process all images sequentially."""
        for q in range(len(files)):
            q = int(q) if isinstance(q, (int, float)) else q

            if not isinstance(q, int):
                logger.error(f"q is not an integer: {type(q)}, value: {q}")
                q = int(q) if isinstance(q, (int, float)) else 0

            # Load image
            src = self._load_image(files, q, preloaded_images)
            if src is None:
                continue

            filename = os.path.basename(files[q])

            # Process image based on analysis mode
            processing_stopped = self._process_single_file(
                src,
                background,
                y1_left,
                y1_right,
                vertical_left,
                vertical_right,
                q,
                save_files,
                filename,
                result_lists,
                files,
                progress_callback,
            )

            if processing_stopped:
                return True

        return False

    def _load_image(self, files, q, preloaded_images):
        """Load an image from file or preloaded cache."""
        if files[q] in preloaded_images:
            return preloaded_images[files[q]]
        else:
            return cv2.imread(files[q])

    def _process_single_file(
        self,
        src,
        background,
        y1_left,
        y1_right,
        vertical_left,
        vertical_right,
        q,
        save_files,
        filename,
        result_lists,
        files,
        progress_callback,
    ):
        """Process a single file based on analysis mode."""
        if self.analysis_mode in ["free_sedimentation", "channel"]:
            # Use the same minimal processing for both modes
            return self._process_standard_mode_file(
                src,
                background,
                None,
                None,
                vertical_left,
                vertical_right,
                q,
                save_files,
                filename,
                result_lists,
                files,
                progress_callback,
            )
        else:
            return self._process_standard_mode_file(
                src,
                background,
                y1_left,
                y1_right,
                vertical_left,
                vertical_right,
                q,
                save_files,
                filename,
                result_lists,
                files,
                progress_callback,
            )

    def _process_standard_mode_file(
        self,
        src,
        background,
        y1_left,
        y1_right,
        vertical_left,
        vertical_right,
        q,
        save_files,
        filename,
        result_lists,
        files,
        progress_callback,
    ):
        """Process a file in standard mode."""
        _, _, angles, center_point, rect_w, rect_h, result_images = (
            self._process_image_thread(
                src.copy(),
                background.copy(),
                y1_left,
                y1_right,
                q,
                save_files,
                filename,
                vertical_left,
                vertical_right,
            )
        )

        # Store results for standard modes
        self._store_standard_mode_results(
            result_lists,
            filename,
            angles,
            center_point,
            rect_w,
            rect_h,
            result_images,
            q,
        )

        # Handle structured packing specific processing
        if self.analysis_mode == "structured_packing":
            self._handle_structured_packing_results(result_lists, result_images, q)

        # Handle progress callback
        return self._handle_progress_callback_standard(
            progress_callback, q, files, result_lists, result_images, rect_w, rect_h
        )

    def _store_standard_mode_results(
        self,
        result_lists,
        filename,
        angles,
        center_point,
        rect_w,
        rect_h,
        result_images,
        q,
    ):
        """Store results for standard mode processing."""
        result_lists["filenames"].append(filename)
        q = int(q) if isinstance(q, (int, float)) else q

        # Store angle results
        if angles and isinstance(angles, dict) and "left" in angles:
            result_lists["advancing_contact_angles"][q] = angles["left"]
            result_lists["receding_contact_angles"][q] = angles["right"]

        # Store center point and dimensions
        self._store_center_point_and_dimensions(
            result_lists, center_point, rect_w, rect_h, q
        )

        # Store contact line data
        self._store_contact_line_data(result_lists, result_images, q)

    def _store_center_point_and_dimensions(
        self, result_lists, center_point, rect_w, rect_h, q
    ):
        """Store center point and dimension data."""
        center_point = self._normalize_center_point(center_point)
        q = int(q) if isinstance(q, (int, float)) else 0
        self._store_center_point(result_lists, center_point, q)
        self._ensure_rect_lists(result_lists, q)
        self._store_rect_dimensions(result_lists, rect_w, rect_h, q)

    def _normalize_center_point(self, center_point):
        """Ensure center_point is a list/tuple of length 2."""
        if isinstance(center_point, float):
            return [center_point, float("nan")]
        if not (isinstance(center_point, (list, tuple)) and len(center_point) == 2):
            return [float("nan"), float("nan")]
        return center_point

    def _store_center_point(self, result_lists, center_point, q):
        """Store center point in px and mm."""
        if (
            center_point
            and isinstance(center_point, (list, tuple))
            and len(center_point) >= 2
        ):
            result_lists["center_points_px"][q] = center_point
            if self.pixel and self.pixel > 0:
                result_lists["center_points_mm"][q] = [
                    (m / self.pixel if m is not None else float("NaN"))
                    for m in center_point
                ]
            else:
                result_lists["center_points_mm"][q] = [0, 0]
            result_lists["center_point"] = center_point
        else:
            result_lists["center_points_px"][q] = [float("NaN"), float("NaN")]
            result_lists["center_points_mm"][q] = [float("NaN"), float("NaN")]
            result_lists["center_point"] = [float("NaN"), float("NaN")]

    def _ensure_rect_lists(self, result_lists, q):
        """Ensure rectangle dimension lists exist and are long enough.

        Preserving data if possible.

        """
        for key in [
            "rect_width_px",
            "rect_width_mm",
            "rect_height_px",
            "rect_height_mm",
        ]:
            val = result_lists.get(key)
            if not isinstance(val, list):
                logger.error(
                    f"result_lists['{key}'] was not a list, "
                    "converting to list and preserving data."
                )
                # If it's a scalar, preserve it as the first element, fill rest with NaN
                try:
                    scalar_val = float(val)
                    result_lists[key] = [scalar_val] + [float("nan")] * q
                except Exception:
                    result_lists[key] = [float("nan")] * (q + 1)
            if len(result_lists[key]) <= q:
                result_lists[key].extend(
                    [float("nan")] * (q + 1 - len(result_lists[key]))
                )

    def _store_rect_dimensions(self, result_lists, rect_w, rect_h, q):
        """Store rectangle dimensions in px and mm, and calculate area/diameter."""
        if rect_w is not None and not math.isnan(rect_w):
            result_lists["rect_width_px"][q] = rect_w
            result_lists["rect_width_mm"][q] = (
                rect_w / self.pixel if self.pixel and self.pixel > 0 else 0
            )
        if rect_h is not None and not math.isnan(rect_h):
            result_lists["rect_height_px"][q] = rect_h
            result_lists["rect_height_mm"][q] = (
                rect_h / self.pixel if self.pixel and self.pixel > 0 else 0
            )

        # Calculate ellipse diameter: d = 2*sqrt(Width/2 * Height/2)
        ellipse_diameter_px = float("nan")
        ellipse_diameter_mm = float("nan")
        if (
            rect_w is not None
            and rect_h is not None
            and not math.isnan(rect_w)
            and not math.isnan(rect_h)
            and rect_w > 0
            and rect_h > 0
        ):
            # d = 2*sqrt(Width/2 * Height/2) = sqrt(Width*Height)
            ellipse_diameter_px = math.sqrt(rect_w * rect_h)
            ellipse_diameter_mm = (
                ellipse_diameter_px / self.pixel
                if self.pixel and self.pixel > 0
                else float("nan")
            )

        # Store ellipse diameter values
        if isinstance(result_lists.get("ellipse_diameter_px"), list):
            result_lists["ellipse_diameter_px"][q] = ellipse_diameter_px
        if isinstance(result_lists.get("ellipse_diameter_mm"), list):
            result_lists["ellipse_diameter_mm"][q] = ellipse_diameter_mm

        # Calculate area and diameter from current contour or bounding rectangle
        area_px = float("nan")
        diameter_px = float("nan")

        # Try to get contour from _current_contour if available
        if hasattr(self, "_current_contour") and self._current_contour is not None:
            area_px = self._calculate_robust_area(self._current_contour)
            diameter_px = math.sqrt(4 * area_px / math.pi) if area_px > 0 else 0
        elif (
            rect_w is not None
            and rect_h is not None
            and not math.isnan(rect_w)
            and not math.isnan(rect_h)
        ):
            # Fallback: estimate area as ellipse using bounding rectangle
            # A = π * (w/2) * (h/2) = π * w * h / 4
            area_px = math.pi * rect_w * rect_h / 4
            diameter_px = math.sqrt(4 * area_px / math.pi) if area_px > 0 else 0

        # Store area and diameter values
        self._store_area_diameter_values(result_lists, area_px, diameter_px, q)

    def _store_area_diameter_values(self, result_lists, area_px, diameter_px, q):
        """Store area and diameter values in px and mm."""
        # Store pixel values
        if isinstance(result_lists.get("area_px"), list):
            area_value = area_px if not math.isnan(area_px) else float("nan")
            result_lists["area_px"][q] = area_value
        if isinstance(result_lists.get("diameter_px"), list):
            diameter_value = (
                diameter_px if not math.isnan(diameter_px) else float("nan")
            )
            result_lists["diameter_px"][q] = diameter_value

        # Store mm values
        if self.pixel is not None and self.pixel > 0 and not math.isnan(area_px):
            # Area conversion: area_mm = area_px / (pixel^2)
            area_mm = area_px / (self.pixel * self.pixel)
            diameter_mm = diameter_px / self.pixel

            if isinstance(result_lists.get("area_mm"), list):
                result_lists["area_mm"][q] = area_mm
            if isinstance(result_lists.get("diameter_mm"), list):
                result_lists["diameter_mm"][q] = diameter_mm
        else:
            if isinstance(result_lists.get("area_mm"), list):
                result_lists["area_mm"][q] = float("nan")
            if isinstance(result_lists.get("diameter_mm"), list):
                result_lists["diameter_mm"][q] = float("nan")

    def _store_contact_line_data(self, result_lists, result_images, q):
        """Store contact line data from result images."""
        contact_line_px = result_images.get("contact_line_px", float("nan"))
        contact_line_mm = result_images.get("contact_line_mm", float("nan"))

        if contact_line_px is not None and not math.isnan(contact_line_px):
            result_lists["contact_line_px"][q] = contact_line_px
        if contact_line_mm is not None and not math.isnan(contact_line_mm):
            result_lists["contact_line_mm"][q] = contact_line_mm

    def _handle_structured_packing_results(self, result_lists, result_images, q):
        """Handle structured packing specific result processing."""
        left_contact = result_images.get("left_contact_detected", False)
        right_contact = result_images.get("right_contact_detected", False)

        result_lists["left_contact_detected"][q] = left_contact
        result_lists["right_contact_detected"][q] = right_contact

        if left_contact and result_lists["left_contact_frame"] is None:
            result_lists["left_contact_frame"] = q
        if right_contact and result_lists["right_contact_frame"] is None:
            result_lists["right_contact_frame"] = q

        contact_status = get_contact_frame_status(
            result_lists["left_contact_frame"],
            result_lists["right_contact_frame"],
        )
        result_lists["contact_status"][q] = contact_status
        result_images["contact_status"] = contact_status
        result_images["left_contact_frame"] = result_lists["left_contact_frame"]
        result_images["right_contact_frame"] = result_lists["right_contact_frame"]

        # Calculate discontinuous velocity if both contacts are detected
        self._calculate_discontinuous_velocity(result_lists, result_images, q)

    def _calculate_discontinuous_velocity(self, result_lists, result_images, q):
        """Calculate discontinuous velocity for structured_packing mode."""
        vertical_left = result_images.get("vertical_left")
        vertical_right = result_images.get("vertical_right")
        left_contact_frame = result_lists["left_contact_frame"]
        right_contact_frame = result_lists["right_contact_frame"]

        # Store vertical line distance for current frame
        if vertical_left and vertical_right:
            # Calculate distance between vertical lines (horizontal distance)
            x1_left = vertical_left[0]  # x coordinate of left line
            x1_right = vertical_right[0]  # x coordinate of right line
            distance_px = abs(x1_right - x1_left)
            distance_mm = distance_px / self.pixel if self.pixel > 0 else 0

            result_lists["vertical_line_distance_px"][q] = distance_px
            result_lists["vertical_line_distance_mm"][q] = distance_mm

        # Calculate velocity if both contacts have occurred
        if (
            left_contact_frame is not None
            and right_contact_frame is not None
            and vertical_left
            and vertical_right
        ):

            # Calculate time between contacts
            frame_diff = abs(right_contact_frame - left_contact_frame)
            time_seconds = frame_diff / self.fps if self.fps > 0 else 0

            # Calculate distance between lines
            x1_left = vertical_left[0]
            x1_right = vertical_right[0]
            distance_px = abs(x1_right - x1_left)
            distance_mm = distance_px / self.pixel if self.pixel > 0 else 0

            # Calculate velocity
            velocity_px_per_frame = distance_px / frame_diff if frame_diff > 0 else 0
            velocity_px_per_s = velocity_px_per_frame * self.fps if self.fps > 0 else 0
            velocity_mm_per_s = distance_mm / time_seconds if time_seconds > 0 else 0

            # Store results (apply to all frames from first contact onwards)
            start_frame = min(left_contact_frame, right_contact_frame)
            end_frame = len(result_lists["contact_time_frames"])
            for i in range(start_frame, end_frame):
                result_lists["discontinuous_velocity_px_s"][i] = velocity_px_per_s
                result_lists["discontinuous_velocity_mm_s"][i] = velocity_mm_per_s
                result_lists["contact_time_frames"][i] = frame_diff
                result_lists["contact_time_seconds"][i] = time_seconds

    def _handle_progress_callback_standard(
        self, progress_callback, q, files, result_lists, result_images, rect_w, rect_h
    ):
        """Handle progress callback for standard modes."""
        if progress_callback:
            # Update result_lists with dimension data if available
            if (
                rect_w is not None
                and not np.isnan(rect_w)
                and rect_h is not None
                and not np.isnan(rect_h)
            ):
                if "rect_width_mm" not in result_images:
                    rect_width_mm = rect_w / self.pixel if self.pixel > 0 else 0
                    # Don't overwrite the list - this is just for display
                    result_images["rect_width_mm"] = rect_width_mm
                if "rect_height_mm" not in result_images:
                    rect_height_mm = rect_h / self.pixel if self.pixel > 0 else 0
                    # Don't overwrite the list - this is just for display
                    result_images["rect_height_mm"] = rect_height_mm

                # Add area diameter for real-time display
                area_diameter_list = result_lists.get("area_diameter_mm", [])
                if "area_diameter_mm" not in result_images and q < len(
                    area_diameter_list
                ):
                    area_diameter_mm = area_diameter_list[q]
                    if not math.isnan(area_diameter_mm):
                        result_images["area_diameter_mm"] = area_diameter_mm
                        logger.debug(
                            "Added area_diameter_mm to result_images: "
                            f"{area_diameter_mm}"
                        )

            continue_processing = progress_callback(
                (q + 1) / len(files),
                result_lists["advancing_contact_angles"][: q + 1],
                result_lists["receding_contact_angles"][: q + 1],
                result_lists["center_points_px"][: q + 1],
                result_images,
            )
            self.image_processed.emit(q, result_images)

            if continue_processing is False:
                if progress_callback:
                    progress_callback(
                        1.0,
                        result_lists["advancing_contact_angles"][: q + 1],
                        result_lists["receding_contact_angles"][: q + 1],
                        result_lists["center_points_px"][: q + 1],
                        result_images,
                    )
                    self.image_processed.emit(q, result_images)
                return True
        return False

    def _finalize_results(
        self,
        result_lists,
        vertical_left,
        vertical_right,
        save_files,
        processing_stopped,
        progress_callback,
        time,
        files,
    ):
        """Calculate final results, velocities, and save data."""
        # Calculate velocities based on center points
        result_lists["velocity"] = calculate_velocities(
            result_lists["center_points_px"], self.pixel, self.fps
        )

        # Calculate area-based diameter from detected area
        self._calculate_area_based_diameter(result_lists)

        # Calculate discontinuous velocity for structured packing mode
        if self.analysis_mode == "structured_packing":
            self._calculate_discontinuous_velocity(
                result_lists, vertical_left, vertical_right
            )

        # Handle final progress callback and data saving
        self._handle_final_progress_and_save(
            result_lists, save_files, processing_stopped, progress_callback, time, files
        )

    def _calculate_area_based_diameter(self, result_lists):
        """Calculate diameter from detected area for all frames."""
        if "area_px" not in result_lists or "area_diameter_px" not in result_lists:
            return

        for i, area_px in enumerate(result_lists["area_px"]):
            # Calculate diameter from area: d = sqrt(4*A/π)
            if area_px is not None and not math.isnan(area_px) and area_px > 0:
                diameter_px = math.sqrt(4 * area_px / math.pi)
                diameter_mm = (
                    diameter_px / self.pixel
                    if self.pixel and self.pixel > 0
                    else float("nan")
                )
            else:
                diameter_px = float("nan")
                diameter_mm = float("nan")

            # Store the calculated values
            if isinstance(result_lists.get("area_diameter_px"), list) and i < len(
                result_lists["area_diameter_px"]
            ):
                result_lists["area_diameter_px"][i] = diameter_px
            if isinstance(result_lists.get("area_diameter_mm"), list) and i < len(
                result_lists["area_diameter_mm"]
            ):
                result_lists["area_diameter_mm"][i] = diameter_mm

    def _calculate_discontinuous_velocity(
        self, result_lists, vertical_left, vertical_right
    ):
        """Calculate discontinuous velocity for structured packing mode."""
        result_lists["discontinuous_velocity_mm_s"] = float("nan")

        first_right_contact_frame = result_lists.get("right_contact_frame")
        first_left_contact_frame = result_lists.get("left_contact_frame")

        if (
            vertical_left is not None
            and vertical_right is not None
            and first_right_contact_frame is not None
            and first_left_contact_frame is not None
            and first_left_contact_frame > first_right_contact_frame
        ):
            frame_diff = first_left_contact_frame - first_right_contact_frame
            time_taken_sec = (
                frame_diff / self.fps if self.fps and self.fps > 0 else float("nan")
            )

            try:
                if (
                    isinstance(vertical_left, (list, tuple))
                    and len(vertical_left) > 0
                    and isinstance(vertical_right, (list, tuple))
                    and len(vertical_right) > 0
                ):
                    x_coord_left = vertical_left[0]
                    x_coord_right = vertical_right[0]
                    distance_px = abs(x_coord_left - x_coord_right)
                    distance_mm = (
                        distance_px / self.pixel
                        if self.pixel and self.pixel > 0
                        else float("nan")
                    )

                    if (
                        not math.isnan(time_taken_sec)
                        and not math.isnan(distance_px)
                        and time_taken_sec > 0
                    ):
                        calculated_velocity_px_s = distance_px / time_taken_sec
                        result_lists["discontinuous_velocity_px_s"] = (
                            calculated_velocity_px_s
                        )

                    if (
                        not math.isnan(time_taken_sec)
                        and not math.isnan(distance_mm)
                        and time_taken_sec > 0
                    ):
                        calculated_velocity = distance_mm / time_taken_sec
                        result_lists["discontinuous_velocity_mm_s"] = (
                            calculated_velocity
                        )
            except (TypeError, IndexError) as e:
                logger.warning(f"Error calculating distance: {e}")

    def _handle_final_progress_and_save(
        self,
        result_lists,
        save_files,
        processing_stopped,
        progress_callback,
        time,
        files,
    ):
        """Handle final progress callback and save results if needed."""
        was_stopped = False
        if progress_callback:
            was_stopped = (
                progress_callback(
                    1.0,
                    result_lists["advancing_contact_angles"],
                    result_lists["receding_contact_angles"],
                    result_lists["center_points_px"],
                    {},  # result_images not available at this point
                )
                is False
            )

            if len(files) > 0:
                self.image_processed.emit(len(files) - 1, {})

        # Only save results if explicitly requested AND not stopped
        if save_files and not was_stopped and not processing_stopped:
            try:
                # Build parameters dict from core attributes
                parameters = {
                    "pixel": getattr(self, "pixel", None),
                    "fps": getattr(self, "fps", None),
                    "threshold": getattr(self, "threshold", None),
                    "rotate_angle": getattr(self, "rotate_angle", None),
                    "baseline": getattr(self, "baseline", None),
                    "fitting_mode": getattr(self, "fitting_mode", None),
                    "polynom": getattr(self, "polynom", None),
                    "baseline_tf": getattr(self, "baseline_tf", None),
                    "manual_baseline": getattr(self, "manual_baseline", None),
                    "x_img": getattr(self, "x_img", None),
                    "y_img": getattr(self, "y_img", None),
                    "w_img": getattr(self, "w_img", None),
                    "h_img": getattr(self, "h_img", None),
                }

                # For free_sedimentation and structured_packing, exclude unused params
                if self.analysis_mode in [
                    "free_sedimentation",
                    "structured_packing",
                ]:
                    exclude_keys = {
                        "rotate_angle",
                        "baseline",
                        "fitting_mode",
                        "polynom",
                        "baseline_tf",
                        "manual_baseline",
                    }
                    parameters = {
                        k: v for k, v in parameters.items() if k not in exclude_keys
                    }

                folder_name = os.path.basename(
                    self.output_path or self._folder_path or ""
                )
                # files may be a list of paths - join basenames with semicolon
                file_names = None
                try:
                    if files:
                        file_names = ";".join([os.path.basename(f) for f in files])
                except Exception:
                    file_names = None

                save_results(
                    self.output_path,
                    time,
                    result_lists,
                    parameters=parameters,
                    folder_name=folder_name,
                    file_names=file_names,
                )
            except Exception as e:
                logger.error(f"Failed to save results with metadata: {e}")

    def _process_image_thread(
        self,
        src,
        background,
        y1_left,
        y1_right,
        q,
        save_files,
        filename,
        vertical_left=None,
        vertical_right=None,
    ):
        """Process a single image."""
        result_images = {}
        result_lists = {}

        # Process the image using baseline (or not, if free sedimentation)
        processed_img, contours, angles_from_single = self._process_single_image(
            src.copy(),
            background.copy(),
            y1_left,
            y1_right,
            q,
            save_files,
            filename,
            result_images,
            result_lists,
            vertical_left,
            vertical_right,
        )

        # Handle free sedimentation mode
        angles = self._handle_free_sedimentation_angles(angles_from_single)

        # Ensure we have a valid 'original' entry for preview
        if "original" not in result_images:
            result_images["original"] = processed_img.copy()

        # Extract measurements from contours
        (
            center_point,
            rect_width,
            rect_height,
            area_px,
            diameter_px,
        ) = self._extract_contour_measurements(contours, result_lists)

        # Process intersection points and contact line calculations
        contact_line_px, contact_line_mm = self._process_intersection_points(
            y1_left,
            y1_right,
            processed_img,
            contours,
            q,
            result_images,
        )

        # Ensure contact line values are always available
        self._ensure_contact_line_values(
            result_images, contact_line_px, contact_line_mm
        )

        # Calculate center points using drop area
        center_point = self._calculate_center_points(
            y1_left,
            y1_right,
            contours,
            processed_img,
            q,
            result_images,
            result_lists,
            center_point,
        )

        # Calculate velocity for preview mode
        self._calculate_velocity(q, center_point, result_images)

        return (
            processed_img,
            contours if contours and len(contours) > 0 else [],
            angles,
            center_point,
            rect_width,
            rect_height,
            result_images,
        )

    def _handle_free_sedimentation_angles(self, angles_from_single):
        """Handle angle processing for free sedimentation mode."""
        angles = angles_from_single
        if self.analysis_mode == "free_sedimentation":
            # Ensure no contact angles for free sedimentation
            angles = {"left": float("nan"), "right": float("nan")}
        return angles

    def _extract_contour_measurements(self, contours, result_lists):
        """Extract measurements from the largest contour."""
        # Initialize with safe defaults
        center_point = [float("nan"), float("nan")]
        rect_width = float("nan")
        rect_height = float("nan")
        area_px = float("nan")
        diameter_px = float("nan")

        if not contours or contours[0] is None:
            return center_point, rect_width, rect_height, area_px, diameter_px

        # Process any detected contours to extract measurements
        largest_contour = contours[0]

        # Store the contour for later use (for area calculation in other functions)
        # We'll store it temporarily in result_lists if the structure allows
        if hasattr(self, "_current_contour"):
            self._current_contour = largest_contour

        # Calculate contour area with robust handling for open contours
        area_px = self._calculate_robust_area(largest_contour)

        # Calculate diameter using D = sqrt(4*A/pi)
        diameter_px = math.sqrt(4 * area_px / math.pi) if area_px > 0 else 0

        moment = cv2.moments(largest_contour)
        if moment["m00"] != 0 and moment["m00"] is not None:
            cx = int(moment["m10"] / moment["m00"])
            cy = int(moment["m01"] / moment["m00"])
            center_point = [cx, cy]

        # Defensive: ensure center_point is always a list/tuple of length 2
        if isinstance(center_point, float):
            center_point = [center_point, float("nan")]
        elif not (isinstance(center_point, (list, tuple)) and len(center_point) == 2):
            center_point = [float("nan"), float("nan")]
        x, y, w, h = cv2.boundingRect(largest_contour)
        rect_width = w
        rect_height = h

        return center_point, rect_width, rect_height, area_px, diameter_px

    def _process_intersection_points(
        self,
        y1_left,
        y1_right,
        processed_img,
        contours,
        q,
        result_images,
    ):
        """Process intersection points and contact line calculations."""
        contact_line_px = float("nan")
        contact_line_mm = float("nan")

        # Only process if not free sedimentation and we have baselines
        if (
            self.analysis_mode == "free_sedimentation"
            or y1_left is None
            or y1_right is None
            or not contours
            or contours[0] is None
        ):
            return contact_line_px, contact_line_mm

        largest_contour = contours[0]
        intersection_points, intersection_img, _cnt, _, _, _ = find_intersection_points(
            y1_left,
            y1_right,
            processed_img,
            self.threshold,
            q,
            contours=largest_contour,
            pixel=self.pixel,
        )

        if intersection_img is not None:
            # Enhanced visualization for channel mode
            self._enhance_channel_visualization(intersection_img, y1_left, y1_right)

            # Draw and process intersection points
            upper_points, lower_points = draw_intersection_points(
                intersection_img,
                intersection_points,
                y1_left,
                y1_right,
                mode=self.analysis_mode,
            )

            # Handle channel-specific processing
            self._process_channel_intersection_points(
                result_images, upper_points, lower_points, intersection_img
            )

            # Calculate main contact line
            contact_line_px, contact_line_mm = self._calculate_main_contact_line(
                intersection_points, intersection_img, result_images
            )

            result_images["intersection"] = intersection_img
            result_images["intersection_points"] = intersection_points

        return contact_line_px, contact_line_mm

    def _enhance_channel_visualization(self, intersection_img, y1_left, y1_right):
        """Enhance visualization for channel mode with dual baselines."""
        if self.analysis_mode == "channel":
            # Draw dual baselines and axis line
            draw_dual_baselines(
                intersection_img,
                y1_left,
                y1_right,
                color1=(0, 255, 0),
                color2=(0, 0, 255),
                thickness=2,
            )
            axis_y = y1_left
            draw_axis_line(intersection_img, axis_y, color=(255, 255, 0), thickness=1)

    def _process_channel_intersection_points(
        self, result_images, upper_points, lower_points, intersection_img
    ):
        """Process intersection points specifically for channel mode."""
        if self.analysis_mode != "channel":
            return

        result_images["upper_intersection_points"] = upper_points
        result_images["lower_intersection_points"] = lower_points

        # Calculate contact lines for each baseline
        if len(upper_points) >= 2:
            p1, p2 = upper_points[0], upper_points[1]
            upper_contact_line_px = np.sqrt((p2[0] - p1[0]) ** 2 + (p2[1] - p1[1]) ** 2)
            result_images["upper_contact_line_px"] = upper_contact_line_px
            result_images["upper_contact_line_mm"] = (
                upper_contact_line_px / self.pixel if self.pixel > 0 else 0
            )
            # Draw connection line
            draw_connection_line(
                intersection_img, p1, p2, color=(0, 255, 0), thickness=3
            )

        if len(lower_points) >= 2:
            p1, p2 = lower_points[0], lower_points[1]
            lower_contact_line_px = np.sqrt((p2[0] - p1[0]) ** 2 + (p2[1] - p1[1]) ** 2)
            result_images["lower_contact_line_px"] = lower_contact_line_px
            result_images["lower_contact_line_mm"] = (
                lower_contact_line_px / self.pixel if self.pixel > 0 else 0
            )
            # Draw connection line
            draw_connection_line(
                intersection_img, p1, p2, color=(0, 0, 255), thickness=3
            )

    def _calculate_main_contact_line(
        self, intersection_points, intersection_img, result_images
    ):
        """Calculate the main contact line for compatibility."""
        contact_line_px = float("nan")
        contact_line_mm = float("nan")

        if (
            intersection_points
            and len(intersection_points) >= 2
            and all(point is not None for point in intersection_points[:2])
        ):
            point1 = intersection_points[0]
            point2 = intersection_points[1]
            # Calculate Euclidean distance
            contact_line_px = np.sqrt(
                (point2[0] - point1[0]) ** 2 + (point2[1] - point1[1]) ** 2
            )
            # Convert to mm if pixel calibration is available
            contact_line_mm = contact_line_px / self.pixel if self.pixel > 0 else 0

            # Draw a line connecting the intersection points (if not channel mode)
            if self.analysis_mode != "channel":
                draw_connection_line(
                    intersection_img,
                    point1,
                    point2,
                    color=(0, 255, 0),
                    thickness=2,
                )

            # Store the values in result_images
            result_images["contact_line_px"] = contact_line_px
            result_images["contact_line_mm"] = contact_line_mm

        return contact_line_px, contact_line_mm

    def _ensure_contact_line_values(
        self, result_images, contact_line_px, contact_line_mm
    ):
        """Ensure contact line values are always available in result_images."""
        if "contact_line_px" not in result_images:
            result_images["contact_line_px"] = contact_line_px
        if "contact_line_mm" not in result_images:
            result_images["contact_line_mm"] = contact_line_mm

        # Clear intersection data if not applicable
        if (
            self.analysis_mode == "free_sedimentation"
            or "intersection_points" not in result_images
        ):
            result_images.pop("intersection_points", None)
            result_images.pop("intersection", None)

    def _calculate_center_points(
        self,
        y1_left,
        y1_right,
        contours,
        processed_img,
        q,
        result_images,
        result_lists,
        center_point,
    ):
        """Calculate center points using drop area calculation."""
        if not contours or contours[0] is None:
            return center_point

        largest_contour = contours[0]

        # Always calculate center points even if no intersection points
        empty_center_points_px, empty_center_points_mm = [], []
        calculated_center_points_px, _ = calculate_drop_area(
            y1_left,
            y1_right,
            result_images.get("intersection_points"),
            largest_contour,
            processed_img,
            empty_center_points_px,
            empty_center_points_mm,
            q,
            result_images,
            result_lists,
            self.pixel,
        )

        # Use the calculated center if available
        if (
            calculated_center_points_px
            and len(calculated_center_points_px) > 0
            and len(calculated_center_points_px[0]) == 2
        ):
            center_point = calculated_center_points_px[0]

            # Defensive: ensure center_point is always a list/tuple of length 2
            if isinstance(center_point, float):
                center_point = [center_point, float("nan")]
            elif not (
                isinstance(center_point, (list, tuple)) and len(center_point) == 2
            ):
                center_point = [float("nan"), float("nan")]

            # Ensure result_lists is a dictionary before assignment
            if not isinstance(result_lists, dict):
                logger.error(
                    f"result_lists is not a dict: {type(result_lists)}, "
                    f"value: {result_lists}"
                )
                result_lists = {}

            # Always store center point in result_lists
            result_lists["center_point"] = center_point

        # Use any center point from result_lists if available
        if isinstance(result_lists, dict) and "center_point" in result_lists:
            center_point = result_lists["center_point"]
        elif not isinstance(result_lists, dict):
            logger.error(
                f"result_lists corrupted - not a dict: {type(result_lists)}, "
                f"value: {result_lists}"
            )
            result_lists = {}

        return center_point

    def _calculate_velocity(self, q, center_point, result_images):
        """Calculate velocity for preview mode if we have previous center point."""
        if (
            q > 0
            and hasattr(self, "_previous_center_point")
            and self._previous_center_point is not None
        ):
            prev_point = self._previous_center_point
            curr_point = center_point

            # Calculate displacement
            try:
                dx_pixels = curr_point[0] - prev_point[0]
                dy_pixels = curr_point[1] - prev_point[1]

                # Calculate total displacement (2D)
                displacement = np.sqrt(dx_pixels**2 + dy_pixels**2)

                # Convert to mm/s
                time_diff = 1.0 / max(1.0, self.fps)  # Avoid division by zero
                velocity_value = (displacement / max(1.0, self.pixel)) / time_diff
                result_images["velocity"] = velocity_value
            except (TypeError, ValueError, IndexError) as e:
                logger.warning(f"Error calculating velocity: {e}")
                result_images["velocity"] = float("nan")
        else:
            result_images["velocity"] = float("nan")

        # Store current center point for next velocity calculation
        self._previous_center_point = center_point

    def _process_single_image(
        self,
        src,
        background,
        y1_left,
        y1_right,
        q,
        save_files,
        filename,
        result_images=None,
        result_lists=None,
        vertical_left=None,
        vertical_right=None,
    ):
        """Process a single image using pre-determined baseline coordinates.

        Uses vertical lines for structured packing.
        """
        # Initialize result storage
        if result_images is None:
            result_images = {}
        if result_lists is None:
            result_lists = {}

        # Initialize variables from start_run
        init_data = self._initialize_single_image_processing(filename, save_files, src)

        # Process and prepare the image
        processed_img = self._prepare_image(src, result_images)
        background = self._prepare_background(processed_img, background)

        # For structured_packing mode, use pre-detected vertical lines
        if self.analysis_mode == "structured_packing":
            vertical_left, vertical_right = self._vertical_left, self._vertical_right
            # Store vertical lines in result_images for preview
            result_images["vertical_left"] = vertical_left
            result_images["vertical_right"] = vertical_right
        # Create baseline visualization
        self._create_baseline_visualization(
            processed_img, y1_left, y1_right, result_images
        )

        # Find and validate contours
        largest_contour, vis_img = self._find_and_validate_contours(
            processed_img,
            background,
            result_images,
            y1_left,
            y1_right,
            vertical_left if self.analysis_mode == "structured_packing" else None,
            vertical_right if self.analysis_mode == "structured_packing" else None,
        )
        if largest_contour is None:
            return self._handle_no_contour_case(
                processed_img, result_images, vertical_left, vertical_right
            )

        # Process contour measurements and visualization
        cx, cy = self._process_contour_measurements(
            largest_contour,
            vis_img,
            y1_left,
            y1_right,
            result_lists,
            result_images,
            q,
        )

        # Handle structured packing mode - ALWAYS draw vertical lines
        if self.analysis_mode == "structured_packing":
            self._handle_structured_packing_mode(
                largest_contour,
                vertical_left,
                vertical_right,
                vis_img,
                processed_img,
                result_images,
            )
            # Ensure vertical lines are drawn on all result images
            if vertical_left and vertical_right:
                self._draw_vertical_lines_on_all_result_images(
                    vertical_left, vertical_right, result_images
                )
        else:
            # For non-structured_packing modes, handle normally
            pass

        # Process intersection points and angles
        intersection_points = self._process_intersection_and_angles(
            y1_left,
            y1_right,
            processed_img,
            largest_contour,
            q,
            filename,
            save_files,
            result_images,
            init_data,
        )

        # Handle cases with insufficient intersection points
        if not intersection_points or len(intersection_points) < 2:
            angles = self._handle_insufficient_intersection_points(
                processed_img, largest_contour, cx, cy, result_images
            )
            return processed_img, [largest_contour], angles

        # Calculate contact angles and create final result
        # For structured_packing mode, get vertical lines from result_images
        final_vertical_left = vertical_left
        final_vertical_right = vertical_right
        if self.analysis_mode == "structured_packing":
            final_vertical_left = result_images.get("vertical_left", vertical_left)
            final_vertical_right = result_images.get("vertical_right", vertical_right)

        angles = self._calculate_final_contact_angles_and_result(
            intersection_points,
            largest_contour,
            filename,
            save_files,
            q,
            y1_left,
            y1_right,
            processed_img,
            result_images,
            final_vertical_left,
            final_vertical_right,
            init_data,
            result_lists,
        )

        return processed_img, [largest_contour], angles

    def _initialize_single_image_processing(self, filename, save_files, src):
        """Initialize variables for single image processing."""
        try:
            init_data = start_run([filename], 0, save_files, self._folder_path)
            if init_data:
                (
                    _,
                    _,
                    _,
                    _,
                    _,
                    _,
                    shifted_points,
                    shifted_x,
                    shifted_y,
                    cnt_y_neu,
                    cnt_x_neu,
                    cnt_x,
                    cnt_y,
                    _,
                    _,
                    _,
                    _,
                    src_new,
                    _,
                ) = init_data
                # If src_new is valid and src wasn't provided, use it
                if src is None and src_new is not None:
                    src = src_new
                return {
                    "shifted_points": shifted_points,
                    "shifted_x": shifted_x,
                    "shifted_y": shifted_y,
                    "cnt_x": cnt_x,
                    "cnt_y": cnt_y,
                    "cnt_x_neu": cnt_x_neu,
                    "cnt_y_neu": cnt_y_neu,
                }
        except Exception as e:
            logger.error(f"Error in _initialize_single_image_processing: {e}")

        # Return default values if initialization fails
        return {
            "shifted_points": [],
            "shifted_x": [],
            "shifted_y": [],
            "cnt_x": [],
            "cnt_y": [],
            "cnt_x_neu": [],
            "cnt_y_neu": [],
        }

    def _prepare_image(self, src, result_images):
        """Prepare the image by rotation and cropping."""
        processed_img = rotate_image(src, self.rotate_angle)
        processed_img = crop_image(
            processed_img, (self.x_img, self.w_img, self.y_img, self.h_img)
        )
        # Always store original for preview and as fallback
        result_images["original"] = processed_img.copy()
        result_images["fallback"] = processed_img.copy()
        return processed_img

    def _prepare_background(self, processed_img, background):
        """Ensure background image matches processed image dimensions."""
        src_h, src_w = processed_img.shape[:2]
        bg_h, bg_w = background.shape[:2]
        if bg_h != src_h or bg_w != src_w:
            background = cv2.resize(background, (src_w, src_h))
        return background

    def _create_baseline_visualization(
        self, processed_img, y1_left, y1_right, result_images
    ):
        """Create baseline visualization image."""
        baseline_img = processed_img.copy()

        if (
            y1_left is not None
            and y1_right is not None
            and not np.isnan(y1_left)
            and not np.isnan(y1_right)
        ):
            if self.analysis_mode == "channel":
                draw_dual_baselines(
                    baseline_img,
                    y1_left,
                    y1_right,
                    color1=(0, 255, 0),
                    color2=(0, 0, 255),
                    thickness=4,
                )
            else:
                draw_connection_line(
                    baseline_img,
                    (0, y1_left),
                    (baseline_img.shape[1], y1_right),
                    color=(0, 0, 255),
                    thickness=2,
                )

        # Store baseline image and update fallback
        result_images["baseline"] = baseline_img
        result_images["fallback"] = baseline_img.copy()

        # Store baseline coordinates and channel-specific information
        result_images["baseline_coords"] = (y1_left, y1_right)
        if (
            self.analysis_mode == "channel"
            and y1_left is not None
            and y1_right is not None
        ):
            result_images["axis_y"] = (y1_left + y1_right) / 2
            result_images["baseline_distance_px"] = abs(y1_right - y1_left)
            result_images["baseline_distance_mm"] = (
                abs(y1_right - y1_left) / self.pixel if self.pixel > 0 else 0
            )

    def _find_and_validate_contours(
        self,
        processed_img,
        background,
        result_images,
        y1_left=None,
        y1_right=None,
        vertical_left=None,
        vertical_right=None,
    ):
        """Find and validate contours in the image."""
        # Background subtraction and thresholding
        diff = cv2.absdiff(processed_img, background)
        gray = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (5, 5), 0)
        thresh = cv2.threshold(gray, self.threshold, 255, cv2.THRESH_BINARY)[1]
        result_images["thresh"] = thresh.copy()

        # Find contours
        contours, _ = cv2.findContours(
            thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        vis_img = processed_img.copy()

        try:

            # Only apply width filter for structured_packing mode
            if self.analysis_mode == "structured_packing":
                valid_contours = []
                for contour in contours:
                    x, y, w, h = cv2.boundingRect(contour)
                    width_mm = w / self.pixel if self.pixel > 0 else w
                    if 1.0 <= width_mm <= 7.0:
                        valid_contours.append(contour)
            else:
                valid_contours = contours  # accept all contours for other modes

            if not valid_contours:
                result_images["contour"] = vis_img.copy()
                result_images["fallback"] = vis_img.copy()
                return None, vis_img

            # Find largest valid contour and apply appropriate filtering
            largest_contour = max(valid_contours, key=cv2.contourArea)

            # Apply filtering based on analysis mode
            is_structured_packing = (
                self.analysis_mode == "structured_packing"
                and vertical_left is not None
                and vertical_right is not None
            )

            if is_structured_packing:
                # For structured_packing mode, filter by vertical lines
                largest_contour = filter_contour_by_vertical_lines(
                    contour=largest_contour,
                    vertical_left=vertical_left,
                    vertical_right=vertical_right,
                )
                # Draw filtered contour (trimmed at vertical lines)
                if len(largest_contour) > 0:
                    draw_filled_contour(
                        vis_img, largest_contour, color=(0, 255, 0), alpha=0.3
                    )
                    cv2.drawContours(vis_img, [largest_contour], -1, (0, 255, 0), 3)
            else:
                # For other modes (especially contact_angle), filter by baseline slope
                largest_contour = filter_contour_by_baseline_slope(
                    contour=largest_contour, y1_left=y1_left, y1_right=y1_right
                )
                # Draw normally filtered contour
                draw_filled_contour(
                    vis_img, largest_contour, color=(0, 255, 0), alpha=0.3
                )
                cv2.drawContours(vis_img, [largest_contour], -1, (0, 255, 0), 2)

            return largest_contour, vis_img

        except Exception as e:
            logger.error(f"Error in _find_and_validate_contours: {e}")
            result_images["contour"] = vis_img.copy()
            result_images["fallback"] = vis_img.copy()
            return None, vis_img

    def _handle_no_contour_case(
        self, processed_img, result_images, vertical_left, vertical_right
    ):
        """Handle preview/result when no contour is found.

        Returns tuple (processed_img, [None], None) consistent with callers.
        """
        # Edge case: structured_packing + preview mode + no valid contour
        # Show the original (middle) frame as result so something is displayed
        if self.analysis_mode == "structured_packing":
            # Use the image with vertical lines if available, otherwise use original
            if "original" in result_images and result_images["original"] is not None:
                result_images["result"] = result_images["original"].copy()
            else:
                result_images["result"] = processed_img.copy()

            # Ensure vertical lines are drawn on the result image
            if vertical_left and vertical_right:
                x1_l, y1_l, x2_l, y2_l = map(int, vertical_left)
                cv2.line(
                    result_images["result"], (x1_l, y1_l), (x2_l, y2_l), (0, 0, 255), 3
                )
                x1_r, y1_r, x2_r, y2_r = map(int, vertical_right)
                cv2.line(
                    result_images["result"], (x1_r, y1_r), (x2_r, y2_r), (0, 0, 255), 3
                )

        return processed_img, [None], None

    def _process_contour_measurements(
        self,
        largest_contour,
        vis_img,
        y1_left,
        y1_right,
        result_lists,
        result_images,
        q,
    ):
        """Process contour measurements and visualization."""
        # Calculate center using moments
        moment = cv2.moments(largest_contour)
        cx, cy = 0, 0

        if moment["m00"] != 0:
            cx = int(moment["m10"] / moment["m00"])
            cy = int(moment["m01"] / moment["m00"])

            # Enhanced visualization for free sedimentation mode
            if y1_left is None or y1_right is None:
                self._add_free_sedimentation_visualization(
                    vis_img, largest_contour, cx, cy
                )
            else:
                self._add_baseline_mode_visualization(
                    vis_img,
                    largest_contour,
                    cx,
                    cy,
                    y1_left,
                    y1_right,
                )

            # Calculate and store dimensions
            self._calculate_and_store_dimensions(largest_contour, result_lists, q)

            # Add area diameter to result_images for real-time display
            if (
                result_lists
                and "area_diameter_mm" in result_lists
                and q < len(result_lists["area_diameter_mm"])
            ):
                area_diameter_mm = result_lists["area_diameter_mm"][q]
                if not math.isnan(area_diameter_mm):
                    result_images["area_diameter_mm"] = area_diameter_mm
                    logger.debug(
                        f"Added area_diameter_mm to result_images: {area_diameter_mm}"
                    )

        # Store visualization images
        result_images["contour"] = vis_img.copy()
        result_images["fallback"] = vis_img.copy()

        return cx, cy

    def _add_free_sedimentation_visualization(self, vis_img, largest_contour, cx, cy):
        """Add visualization elements for free sedimentation mode."""
        # Add 30% transparent green fill for contour area
        draw_filled_contour(vis_img, largest_contour, color=(0, 255, 0), alpha=0.3)

        x, y, w, h = cv2.boundingRect(largest_contour)
        draw_rectangle(vis_img, x, y, w, h, color=(0, 0, 255), thickness=2)
        draw_center_point(
            vis_img, cx, cy, color=(0, 0, 255), crosshair_size=20, thickness=2
        )

    def _add_baseline_mode_visualization(
        self, vis_img, largest_contour, cx, cy, y1_left, y1_right
    ):
        """Add visualization elements for baseline modes."""
        # Add 30% transparent green fill for contour area
        draw_filled_contour(vis_img, largest_contour, color=(0, 255, 0), alpha=0.3)

        x, y, w, h = cv2.boundingRect(largest_contour)
        # Consistent red rectangle around contour (thickness=2)
        draw_rectangle(vis_img, x, y, w, h, color=(0, 0, 255), thickness=2)

        if self.analysis_mode == "channel":
            draw_dual_baselines(
                vis_img,
                y1_left,
                y1_right,
                color1=(0, 255, 0),
                color2=(0, 0, 255),
                thickness=3,
            )
            axis_y = (y1_left + y1_right) / 2
            draw_axis_line(vis_img, axis_y, color=(255, 255, 0), thickness=1)
            highlight_interaction_zone(
                vis_img, largest_contour, y1_left, zone=10, color=[0, 255, 255]
            )
            highlight_interaction_zone(
                vis_img, largest_contour, y1_right, zone=10, color=[255, 0, 255]
            )
        elif self.analysis_mode == "contact_angle":
            # For contact_angle mode, check if contour touches baseline
            # If it doesn't touch, baseline and angle lines will be drawn later
            # Always draw center point with consistent style
            pass

        # Always draw center point for baseline modes (consistent style)
        draw_center_point(
            vis_img, cx, cy, color=(0, 0, 255), crosshair_size=20, thickness=2
        )

    def _calculate_and_store_dimensions(self, largest_contour, result_lists, q):
        """Calculate and store contour dimensions, area, and diameter."""
        _, _, current_w_px, current_h_px = cv2.boundingRect(largest_contour)

        # Calculate contour area with fallback for open contours
        area_px = self._calculate_robust_area(largest_contour)

        # Calculate diameter using D = sqrt(4*A/pi)
        diameter_px = math.sqrt(4 * area_px / math.pi) if area_px > 0 else 0

        if current_w_px == 0 or current_h_px == 0:
            self._set_rect_nan(result_lists, q)
            self._set_area_diameter_nan(result_lists, q)
        else:
            self._set_rect_px(result_lists, q, current_w_px, current_h_px)
            self._set_rect_mm(result_lists, q, current_w_px, current_h_px)
            self._set_area_diameter_px(result_lists, q, area_px, diameter_px)
            self._set_area_diameter_mm(result_lists, q, area_px, diameter_px)

    def _calculate_robust_area(self, contour):
        """Calculate contour area with basic fallback for small areas.

        Args:
        ----
            contour: Input contour points

        Returns:
        -------
            Area in pixels (float)

        """
        if contour is None or len(contour) == 0:
            return 0.0

        try:
            # Calculate standard contour area
            area = cv2.contourArea(contour)

            # If area is very small, use bounding rectangle as fallback
            if area < 10.0:
                x, y, w, h = cv2.boundingRect(contour)
                # Use elliptical area estimation: A = π * (w/2) * (h/2)
                area = math.pi * w * h / 4
                logger.debug(f"Fallback elliptical area estimation: {area} px²")

            return float(area)

        except Exception as e:
            logger.warning(f"Error calculating contour area: {e}")
            return 0.0

    def _set_rect_nan(self, result_lists, q):
        """Set rectangle dimension lists to NaN at index q."""
        for key in [
            "rect_width_px",
            "rect_height_px",
            "rect_width_mm",
            "rect_height_mm",
            "area_px",
            "area_mm",
            "diameter_px",
            "diameter_mm",
        ]:
            if isinstance(result_lists.get(key), list):
                result_lists[key][q] = float("nan")

    def _set_rect_px(self, result_lists, q, w_px, h_px):
        """Set rectangle width and height in px at index q."""
        if isinstance(result_lists.get("rect_width_px"), list):
            result_lists["rect_width_px"][q] = w_px
        if isinstance(result_lists.get("rect_height_px"), list):
            result_lists["rect_height_px"][q] = h_px

    def _set_rect_mm(self, result_lists, q, w_px, h_px):
        """Set rectangle width and height in mm at index q."""
        if self.pixel is not None and self.pixel > 0:
            if isinstance(result_lists.get("rect_width_mm"), list):
                result_lists["rect_width_mm"][q] = w_px / self.pixel
            if isinstance(result_lists.get("rect_height_mm"), list):
                result_lists["rect_height_mm"][q] = h_px / self.pixel
        else:
            if isinstance(result_lists.get("rect_width_mm"), list):
                result_lists["rect_width_mm"][q] = float("nan")
            if isinstance(result_lists.get("rect_height_mm"), list):
                result_lists["rect_height_mm"][q] = float("nan")

    def _set_area_diameter_nan(self, result_lists, q):
        """Set area and diameter to NaN at index q."""
        for key in ["area_px", "area_mm", "diameter_px", "diameter_mm"]:
            if isinstance(result_lists.get(key), list):
                result_lists[key][q] = float("nan")
        # Also set area-based diameter to NaN
        for key in ["area_diameter_px", "area_diameter_mm"]:
            if key not in result_lists:
                result_lists[key] = []
            # Extend list if necessary
            while len(result_lists[key]) <= q:
                result_lists[key].append(float("nan"))
            result_lists[key][q] = float("nan")

    def _set_area_diameter_px(self, result_lists, q, area_px, diameter_px):
        """Set area and diameter in pixels at index q."""
        if isinstance(result_lists.get("area_px"), list):
            result_lists["area_px"][q] = area_px
        if isinstance(result_lists.get("diameter_px"), list):
            result_lists["diameter_px"][q] = diameter_px
        # Set area-based diameter (calculated from detected area)
        if "area_diameter_px" not in result_lists:
            result_lists["area_diameter_px"] = []
        # Extend list if necessary
        while len(result_lists["area_diameter_px"]) <= q:
            result_lists["area_diameter_px"].append(float("nan"))
        result_lists["area_diameter_px"][q] = diameter_px

    def _set_area_diameter_mm(self, result_lists, q, area_px, diameter_px):
        """Set area and diameter in mm at index q."""
        if self.pixel is not None and self.pixel > 0:
            # Area conversion: area_mm = area_px / (pixel^2)
            area_mm = area_px / (self.pixel * self.pixel)
            diameter_mm = diameter_px / self.pixel

            if isinstance(result_lists.get("area_mm"), list):
                result_lists["area_mm"][q] = area_mm
            if isinstance(result_lists.get("diameter_mm"), list):
                result_lists["diameter_mm"][q] = diameter_mm
            # Set area-based diameter (calculated from detected area)
            if "area_diameter_mm" not in result_lists:
                result_lists["area_diameter_mm"] = []
            # Extend list if necessary
            while len(result_lists["area_diameter_mm"]) <= q:
                result_lists["area_diameter_mm"].append(float("nan"))
            result_lists["area_diameter_mm"][q] = diameter_mm
        else:
            if isinstance(result_lists.get("area_mm"), list):
                result_lists["area_mm"][q] = float("nan")
            if isinstance(result_lists.get("diameter_mm"), list):
                result_lists["diameter_mm"][q] = float("nan")
            if "area_diameter_mm" not in result_lists:
                result_lists["area_diameter_mm"] = []
            # Extend list if necessary
            while len(result_lists["area_diameter_mm"]) <= q:
                result_lists["area_diameter_mm"].append(float("nan"))
            result_lists["area_diameter_mm"][q] = float("nan")

    def _handle_structured_packing_mode(
        self,
        largest_contour,
        vertical_left,
        vertical_right,
        vis_img,
        processed_img,
        result_images,
    ):
        """Handle visualization and processing for structured packing mode."""
        if (
            self.analysis_mode != "structured_packing"
            or not vertical_left
            or not vertical_right
        ):
            return

        # Create structured packing visualization - preserve existing contour/center
        # visualization
        structured_img = vis_img.copy()  # vis_img already has contour and center point
        baseline_with_vertical = (
            result_images["baseline"].copy()
            if "baseline" in result_images
            else processed_img.copy()
        )
        original_with_vertical = processed_img.copy()

        # Draw vertical lines ON TOP of existing visualization (contour + center point)
        self._draw_vertical_lines(
            vertical_left,
            vertical_right,
            structured_img,
            baseline_with_vertical,
            original_with_vertical,
        )

        # Store vertical lines in result_images
        result_images["vertical_left"] = vertical_left
        result_images["vertical_right"] = vertical_right

        # Perform contact detection
        left_contact, right_contact = detect_vertical_line_contact(
            largest_contour, vertical_left, vertical_right, contact_threshold=1
        )

        # Store contact detection results
        result_images["left_contact_detected"] = left_contact
        result_images["right_contact_detected"] = right_contact

        # Draw contact indicators if needed
        if left_contact or right_contact:
            structured_img = draw_contact_indicators(
                structured_img,
                vertical_left,
                vertical_right,
                left_contact,
                right_contact,
            )
            baseline_with_vertical = draw_contact_indicators(
                baseline_with_vertical,
                vertical_left,
                vertical_right,
                left_contact,
                right_contact,
            )

        # Update images with vertical lines and contact indicators
        result_images["contour"] = structured_img
        result_images["baseline"] = baseline_with_vertical
        result_images["original_with_vertical"] = original_with_vertical

    def _draw_vertical_lines(
        self,
        vertical_left,
        vertical_right,
        structured_img,
        baseline_with_vertical,
        original_with_vertical,
    ):
        """Draw vertical lines on multiple image types."""
        # Draw left vertical line (ensure integer coordinates)
        x1_l, y1_l, x2_l, y2_l = map(int, vertical_left)
        cv2.line(structured_img, (x1_l, y1_l), (x2_l, y2_l), (0, 0, 255), 3)
        cv2.line(baseline_with_vertical, (x1_l, y1_l), (x2_l, y2_l), (0, 0, 255), 3)
        cv2.line(original_with_vertical, (x1_l, y1_l), (x2_l, y2_l), (0, 0, 255), 3)

        # Draw right vertical line (ensure integer coordinates)
        x1_r, y1_r, x2_r, y2_r = map(int, vertical_right)
        cv2.line(structured_img, (x1_r, y1_r), (x2_r, y2_r), (0, 0, 255), 3)
        cv2.line(baseline_with_vertical, (x1_r, y1_r), (x2_r, y2_r), (0, 0, 255), 3)
        cv2.line(original_with_vertical, (x1_r, y1_r), (x2_r, y2_r), (0, 0, 255), 3)

    def _draw_vertical_lines_on_all_result_images(
        self, vertical_left, vertical_right, result_images
    ):
        """Draw vertical lines on ALL result images to ensure they're always visible."""
        if not vertical_left or not vertical_right:
            return

        # Draw on all available images in result_images,
        # including those created by contour detection
        for image_key in ["original", "baseline", "contour", "result", "thresh"]:
            if image_key in result_images and result_images[image_key] is not None:
                img = result_images[image_key]

                # Skip thresh image since it's binary
                if image_key == "thresh":
                    continue

                # Ensure we have a color image for line drawing
                if len(img.shape) == 2:  # Grayscale
                    img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
                    result_images[image_key] = img

                # Draw vertical lines (ensure integer coordinates)
                x1_l, y1_l, x2_l, y2_l = map(int, vertical_left)
                cv2.line(img, (x1_l, y1_l), (x2_l, y2_l), (0, 0, 255), 3)
                x1_r, y1_r, x2_r, y2_r = map(int, vertical_right)
                cv2.line(img, (x1_r, y1_r), (x2_r, y2_r), (0, 0, 255), 3)

    def _process_intersection_and_angles(
        self,
        y1_left,
        y1_right,
        processed_img,
        largest_contour,
        q,
        filename,
        save_files,
        result_images,
        init_data,
    ):
        """Process intersection points and calculate angles."""
        # Find intersection points
        (
            intersection_points,
            intersection_img,
            _cnt,
            shifted_points,
            shifted_x,
            shifted_y,
        ) = find_intersection_points(
            y1_left,
            y1_right,
            processed_img,
            self.threshold,
            q,
            contours=largest_contour,
            pixel=self.pixel,
        )

        if intersection_img is not None:
            # Draw intersection points
            for _, point in enumerate(intersection_points):
                if point is not None:
                    x, y = point
                    cv2.circle(
                        intersection_img, (int(x), int(y)), 10, (0, 255, 255), -1
                    )
                    cv2.circle(intersection_img, (int(x), int(y)), 12, (0, 0, 0), 2)

            # Draw bounding rectangle around the contour on intersection image
            if largest_contour is not None:
                x, y, w, h = cv2.boundingRect(largest_contour)
                draw_rectangle(
                    intersection_img, x, y, w, h, color=(0, 0, 255), thickness=2
                )

            result_images["intersection"] = intersection_img
            result_images["intersection_points"] = intersection_points

        return intersection_points

    def _handle_insufficient_intersection_points(
        self, processed_img, largest_contour, cx, cy, result_images
    ):
        """Handle cases with insufficient intersection points."""
        # Create a comprehensive result image
        result_image = processed_img.copy()

        # Draw filled contour area (30% transparent green)
        draw_filled_contour(result_image, largest_contour, color=(0, 255, 0), alpha=0.3)

        # Draw contour outline (consistent green, thickness=2)
        cv2.drawContours(result_image, [largest_contour], -1, (0, 255, 0), 2)

        if cx != 0 or cy != 0:
            # Draw bounding rectangle (consistent red, thickness=2)
            x, y, w, h = cv2.boundingRect(largest_contour)
            cv2.rectangle(result_image, (x, y), (x + w, y + h), (0, 0, 255), 2)

            # Draw center point (consistent style: red, size=20, thickness=2)
            draw_center_point(
                result_image, cx, cy, color=(0, 0, 255), crosshair_size=20, thickness=2
            )

        result_images["result"] = result_image
        result_images["fallback"] = result_image.copy()

        # Add vertical lines for structured_packing mode
        if self.analysis_mode == "structured_packing":
            vertical_left = result_images.get("vertical_left")
            vertical_right = result_images.get("vertical_right")
            if vertical_left and vertical_right:
                x1_l, y1_l, x2_l, y2_l = map(int, vertical_left)
                cv2.line(result_image, (x1_l, y1_l), (x2_l, y2_l), (0, 0, 255), 3)
                x1_r, y1_r, x2_r, y2_r = map(int, vertical_right)
                cv2.line(result_image, (x1_r, y1_r), (x2_r, y2_r), (0, 0, 255), 3)
                # Update both result images with vertical lines
                result_images["result"] = result_image
                result_images["fallback"] = result_image.copy()

        return {"left": float("NaN"), "right": float("NaN")}

    def _calculate_final_contact_angles_and_result(
        self,
        intersection_points,
        largest_contour,
        filename,
        save_files,
        q,
        y1_left,
        y1_right,
        processed_img,
        result_images,
        vertical_left,
        vertical_right,
        init_data,
        result_lists,
    ):
        """Calculate final contact angles and create comprehensive result image."""
        # Calculate drop area
        center_points_px, center_points_mm = calculate_drop_area(
            y1_left,
            y1_right,
            intersection_points,
            largest_contour,
            processed_img,
            [],
            [],
            q,
            result_images,
            {},
            self.pixel,
        )

        # Process contour to separate left and right sides
        x_mean, x_left_cnt, y_left_cnt, x_right_cnt, y_right_cnt = process_contour(
            largest_contour,
            init_data["cnt_x"],
            init_data["cnt_y"],
            [],
            [],
            [],
            [],
            y1_left,
            init_data["cnt_x_neu"],
            init_data["cnt_y_neu"],
        )

        # SUBSECTION: Polynomial cropping
        threshold_y = y1_left - 10  # Crop slightly above baseline
        x_left_crop, y_left_crop, x_right_crop, y_right_crop = crop_contour_points(
            x_left_cnt, y_left_cnt, x_right_cnt, y_right_cnt, threshold_y
        )

        # SUBSECTION: Contact angle fitting/calculation
        if (
            self.fitting_mode == "Polynom"
            and len(x_left_crop) > 0
            and len(x_right_crop) > 0
        ):
            try:
                # Rotate coordinates for polynomial fitting (was Koordinaten_drehen)
                x_left_90, y_left_90, x_right_90, y_right_90 = rotate_coordinates_90(
                    x_left_crop, y_left_crop, x_right_crop, y_right_crop
                )

                # Apply polynomial fitting (was Polynom_links and Polynom_rechts)
                left_contact_angle_polynom = fit_left_polynomial(
                    x_left_90,
                    y_left_90,
                    intersection_points,
                    self.polynom,
                )

                right_contact_angle_polynom = fit_right_polynomial(
                    x_right_90,
                    y_right_90,
                    x_mean,
                    self.polynom,
                )
            except Exception as e:
                logger.error(f"Error in polynomial fitting: {e}")
                left_contact_angle_polynom = [float("NaN")]
                right_contact_angle_polynom = [float("NaN")]

        elif (
            self.fitting_mode == "Ellipse"
            and len(x_left_crop) > 0
            and len(x_right_crop) > 0
        ):
            try:
                # Initial parameter guess for ellipse fitting
                _ = (
                    [intersection_points[0][0], intersection_points[0][1], 1, 1]
                    if intersection_points
                    else None
                )

                # Calculate contact angle using ellipse fitting (was Ellipse_CA)
                _ = calculate_ellipse_contact_angle(
                    x_left_crop,
                    y_left_crop,
                    x_right_crop,
                    y_right_crop,
                    intersection_points,
                )

                # Calculate contact angles for left and right sides
                left_contact_angle_ellipse = calculate_contact_angle_left(
                    x_left_crop,
                    y_left_crop,
                    intersection_points,
                )

                right_contact_angle_ellipse = calculate_contact_angle_right(
                    x_right_crop, y_right_crop
                )
            except Exception as e:
                logger.error(f"Error in ellipse fitting: {e}")
                left_contact_angle_ellipse = [float("NaN")]
                right_contact_angle_ellipse = [float("NaN")]
        elif (
            self.fitting_mode == "Tangent"
            and len(x_left_crop) > 0
            and len(x_right_crop) > 0
        ):
            # Use tangent method explicitly
            advancing_contact_angles, receding_contact_angles, _ = (
                calculate_tangent_contact_angles(
                    processed_img.shape[1],
                    init_data["shifted_points"],
                    init_data["shifted_x"],
                    init_data["shifted_y"],
                    intersection_points,
                    y1_left,
                    y1_right,
                    processed_img,
                    filename,
                    self.output_path,
                    [],
                    [],
                    q,
                    save_files,
                )
            )
        else:
            # Default to arc method or when selected fitting mode is arc
            advancing_contact_angles = []
            receding_contact_angles = []
            advancing_contact_angles, receding_contact_angles, _ = (
                calculate_contact_angles(
                    processed_img.shape[1],
                    [],
                    [],
                    [],
                    intersection_points,
                    y1_left,
                    y1_right,
                    processed_img,
                    filename,
                    self.output_path,
                    advancing_contact_angles,
                    receding_contact_angles,
                    q,
                    result_images,
                    save_files,
                    largest_contour,
                )
            )

        # Determine which angles to use based on fitting mode
        if (
            self.fitting_mode == "Polynom"
            and left_contact_angle_polynom
            and right_contact_angle_polynom
        ):
            left_angle = left_contact_angle_polynom[0]
            right_angle = right_contact_angle_polynom[0]
        elif (
            self.fitting_mode == "Ellipse"
            and left_contact_angle_ellipse
            and right_contact_angle_ellipse
        ):
            left_angle = left_contact_angle_ellipse[0]
            right_angle = right_contact_angle_ellipse[0]
        elif self.fitting_mode == "Tangent":
            left_angle = (
                advancing_contact_angles[-1]
                if advancing_contact_angles
                else float("NaN")
            )
            right_angle = (
                receding_contact_angles[-1] if receding_contact_angles else float("NaN")
            )
        else:
            # Use the angles calculated by the calculate_contact_angles function
            left_angle = (
                advancing_contact_angles[-1]
                if advancing_contact_angles
                else float("NaN")
            )
            right_angle = (
                receding_contact_angles[-1] if receding_contact_angles else float("NaN")
            )

        # Save the angles to the main result lists for all modes
        # result_lists is a parameter of this function, so it is always defined
        if (
            isinstance(result_lists, dict)
            and "advancing_contact_angles" in result_lists
            and "receding_contact_angles" in result_lists
            and isinstance(q, int)
        ):
            result_lists["advancing_contact_angles"][q] = left_angle
            result_lists["receding_contact_angles"][q] = right_angle

        angles = {"left": left_angle, "right": right_angle}

        # Create comprehensive result image
        self._create_comprehensive_result_image(
            result_images,
            angles,
            advancing_contact_angles,
            receding_contact_angles,
            largest_contour,
            vertical_left,
            vertical_right,
        )

        return angles

    def _create_comprehensive_result_image(
        self,
        result_images,
        angles,
        advancing_contact_angles,
        receding_contact_angles,
        largest_contour,
        vertical_left,
        vertical_right,
    ):
        """Create the final comprehensive result image with all visualizations."""
        result_image = result_images["original"].copy()

        # Draw baseline if available and not in structured packing mode
        if (
            "baseline_coords" in result_images
            and self.analysis_mode != "structured_packing"
        ):
            y1_left, y1_right = result_images["baseline_coords"]
            if (
                y1_left is not None
                and y1_right is not None
                and not np.isnan(y1_left)
                and not np.isnan(y1_right)
            ):
                cv2.line(
                    result_image,
                    (0, int(y1_left)),
                    (result_image.shape[1], int(y1_right)),
                    (0, 0, 255),
                    3,
                )

        # Draw vertical lines for structured packing mode (consistent thickness=3)
        if (
            self.analysis_mode == "structured_packing"
            and vertical_left
            and vertical_right
        ):
            x1_l, y1_l, x2_l, y2_l = map(int, vertical_left)
            cv2.line(result_image, (x1_l, y1_l), (x2_l, y2_l), (0, 0, 255), 3)
            x1_r, y1_r, x2_r, y2_r = map(int, vertical_right)
            cv2.line(result_image, (x1_r, y1_r), (x2_r, y2_r), (0, 0, 255), 3)

        # Draw intersection points and contact angle lines
        self._draw_intersection_points_and_angles(
            result_image,
            result_images,
            angles,
            advancing_contact_angles,
            receding_contact_angles,
        )

        # Draw filled contour area (30% transparent green)
        draw_filled_contour(result_image, largest_contour, color=(0, 255, 0), alpha=0.3)

        # Draw contour outline (consistent green color, thickness=2)
        cv2.drawContours(result_image, [largest_contour], -1, (0, 255, 0), 2)

        # Draw bounding rectangle around the contour (consistent red color, thickness=2)
        if largest_contour is not None:
            x, y, w, h = cv2.boundingRect(largest_contour)
            draw_rectangle(result_image, x, y, w, h, color=(0, 0, 255), thickness=2)

            # Draw center point for appropriate modes
            modes_with_center = [
                "structured_packing",
                "contact_angle",
                "free_sedimentation",
            ]
            if self.analysis_mode in modes_with_center:
                # Calculate center using moments
                moment = cv2.moments(largest_contour)
                if moment["m00"] != 0:
                    cx = int(moment["m10"] / moment["m00"])
                    cy = int(moment["m01"] / moment["m00"])
                    # Consistent center point style (red color, size=20, thickness=2)
                    draw_center_point(
                        result_image,
                        cx,
                        cy,
                        color=(0, 0, 255),
                        crosshair_size=20,
                        thickness=2,
                    )

        # Store the result image
        result_images["result"] = result_image
        result_images["fallback"] = result_image.copy()

        # Ensure fallback result exists
        if "result" not in result_images:
            self._create_fallback_result(result_images, largest_contour)

    def _draw_intersection_points_and_angles(
        self,
        result_image,
        result_images,
        angles,
        advancing_contact_angles,
        receding_contact_angles,
    ):
        """Draw intersection points and contact angle lines on result image."""
        if "intersection_points" not in result_images:
            return

        intersection_points = result_images["intersection_points"]
        if not intersection_points or not all(
            point is not None and not any(np.isnan(x) for x in point)
            for point in intersection_points[:2]
        ):
            return

        # Draw intersection points
        for point in intersection_points[:2]:
            cv2.circle(
                result_image, (int(point[0]), int(point[1])), 8, (0, 255, 255), -1
            )
            cv2.circle(result_image, (int(point[0]), int(point[1])), 10, (0, 0, 0), 2)

        # Draw contact angle lines
        latest_adv = (
            angles["left"]
            if not np.isnan(angles["left"])
            else (
                advancing_contact_angles[-1]
                if advancing_contact_angles
                else float("NaN")
            )
        )
        latest_rec = (
            angles["right"]
            if not np.isnan(angles["right"])
            else (
                receding_contact_angles[-1] if receding_contact_angles else float("NaN")
            )
        )

        if (
            not np.isnan(latest_adv)
            and not np.isnan(latest_rec)
            and len(intersection_points) >= 2
        ):
            # Draw left side (advancing) angle line
            if not np.isnan(latest_adv):
                x, y = intersection_points[0]
                angle_rad = np.radians(latest_adv)
                line_length = 80
                end_x = int(x + line_length * np.cos(angle_rad))
                end_y = int(y - line_length * np.sin(angle_rad))
                cv2.line(result_image, (int(x), int(y)), (end_x, end_y), (0, 255, 0), 2)

            # Draw right side (receding) angle line
            if not np.isnan(latest_rec):
                x, y = intersection_points[1]
                angle_rad = np.radians(180 - latest_rec)
                line_length = 80
                end_x = int(x + line_length * np.cos(angle_rad))
                end_y = int(y - line_length * np.sin(angle_rad))
                cv2.line(result_image, (int(x), int(y)), (end_x, end_y), (0, 255, 0), 2)

    def _create_fallback_result(self, result_images, largest_contour):
        """Create a basic fallback result image if none was created."""
        fallback_result = result_images.get("original").copy()
        if largest_contour is not None:
            # Draw filled contour area (30% transparent green)
            draw_filled_contour(
                fallback_result, largest_contour, color=(0, 255, 0), alpha=0.3
            )
            cv2.drawContours(fallback_result, [largest_contour], -1, (0, 255, 0), 2)
            moment = cv2.moments(largest_contour)
            if moment["m00"] != 0:
                cx = int(moment["m10"] / moment["m00"])
                cy = int(moment["m01"] / moment["m00"])
                cv2.circle(fallback_result, (cx, cy), 8, (0, 0, 255), -1)
        result_images["result"] = fallback_result
        result_images["fallback"] = fallback_result.copy()
