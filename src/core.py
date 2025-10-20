"""Analysis core functionality.

For droplet and experiment analysis in Droplet Wall Interaction Tool.
"""

import copy
import math
import os
from collections.abc import Callable
from typing import Any

import cv2
import numpy as np
from PySide6.QtCore import Property, QObject, QSettings, Signal

from src.analysis.processors import (
    ContactAngleProcessor,
    ImageProcessor,
    VisualizationProcessor,
)
from src.analysis.settings_manager import SettingsManager
from src.analysis.workflow import FileHandler, Pipeline, ResultsAssembler
from src.helpers.contact_detection import (
    get_contact_frame_status,
)
from src.helpers.geometry import (
    calculate_drop_area,
    crop_contour_points,
    find_intersection_points,
    process_contour,
)
from src.helpers.initialisation import start_run
from src.helpers.visualisation import (
    draw_center_point,
    draw_filled_contour,
    draw_rectangle,
)
from src.utilities.core_utils import get_logger
from src.utilities.image_utils import (
    crop_image,
    rotate_image,
    safe_imread,
)
from src.utilities.measurement_utils import (
    calculate_contact_angle_left,
    calculate_contact_angle_right,
    calculate_contact_angles,
    calculate_ellipse_contact_angle,
    calculate_tangent_contact_angles,
    find_single_baseline,
    find_vertical_lines,
    fit_left_polynomial,
    fit_right_polynomial,
    rotate_coordinates_90,
)
from src.utilities.threading import create_background_threaded

# Setup logger for this module
logger = get_logger(__name__)


class AnalysisCore(QObject):
    """Core functionality for analysis with improved structure.

    Provides properties, signals, and processing methods for analysis.
    Manages settings persistence and image processing operations.
    """

    def __init__(
        self,
        folder_path: str | None = None,
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

            # Initialize settings with a fixed application name. The
            # analysis-mode is handled via beginGroup()/endGroup so we
            # avoid accidentally nesting the same group twice by passing
            # the mode name as the application name to QSettings.
            # This also allows consistent reads/writes via beginGroup.
            self.settings = QSettings("CellSettings", "DWIT")

            # Initialize helper classes first (before loading settings)
            self.settings_manager = SettingsManager(self.analysis_mode)

            # Load settings from persistent storage
            self.load_settings()

            # Initialize remaining helper classes
            folder = self._folder_path if hasattr(self, "_folder_path") else ""
            self.file_handler = FileHandler(folder)
            self.image_processor = ImageProcessor(
                analysis_mode=self.analysis_mode,
                threshold=self.threshold if hasattr(self, "threshold") else 60,
                pixel=self.pixel if hasattr(self, "pixel") else 1.0,
                rotate_angle=(
                    self.rotate_angle if hasattr(self, "rotate_angle") else 0.0
                ),
                x_img=self.x_img if hasattr(self, "x_img") else 0,
                y_img=self.y_img if hasattr(self, "y_img") else 0,
                w_img=self.w_img if hasattr(self, "w_img") else 0,
                h_img=self.h_img if hasattr(self, "h_img") else 0,
                polynom=self.polynom if hasattr(self, "polynom") else 2,
                fitting_mode=(
                    self.fitting_mode if hasattr(self, "fitting_mode") else "polynomial"
                ),
                baseline=self.baseline if hasattr(self, "baseline") else 0,
                baseline_tf=self.baseline_tf if hasattr(self, "baseline_tf") else False,
                manual_baseline=(
                    self.manual_baseline if hasattr(self, "manual_baseline") else 0
                ),
            )
            self.results_assembler = ResultsAssembler(
                self.analysis_mode,
                self.pixel if hasattr(self, "pixel") else 1.0,
            )
            self.pipeline = Pipeline(
                analysis_mode=self.analysis_mode,
                folder_path=folder,
                fps=self.fps if hasattr(self, "fps") else 30,
                pixel=self.pixel if hasattr(self, "pixel") else 1.0,
            )
            self.contact_angle_processor = ContactAngleProcessor(
                analysis_mode=self.analysis_mode,
                pixel=self.pixel if hasattr(self, "pixel") else 1.0,
                polynom=self.polynom if hasattr(self, "polynom") else 2,
                fitting_mode=(
                    self.fitting_mode if hasattr(self, "fitting_mode") else "polynomial"
                ),
            )
            self.visualization_processor = VisualizationProcessor(
                analysis_mode=self.analysis_mode,
                pixel=self.pixel if hasattr(self, "pixel") else 1.0,
                threshold=self.threshold if hasattr(self, "threshold") else 100,
                baseline=(
                    [self.baseline, self.baseline]
                    if hasattr(self, "baseline")
                    else [0, 0]
                ),
            )

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
        self.settings_manager.save_setting(key, value)

    def add_folder_path(self, folder_path: str) -> None:
        """Add a folder path to the list if it's not already there."""
        if not folder_path:
            return

        # Normalize to absolute, platform-correct path to keep storage consistent
        norm_path = os.path.normpath(os.path.abspath(folder_path))
        if norm_path not in self._folder_paths:
            self._folder_paths.append(norm_path)
            logger.info(f"Added new folder path: {norm_path}")
            # Persist normalized paths
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
        if not folder_path:
            logger.warning(f"Attempted to remove invalid folder path: {folder_path}")
            return

        # Normalize incoming path for consistent comparison
        norm_path = os.path.normpath(os.path.abspath(folder_path))

        if norm_path in self._folder_paths:
            self._folder_paths.remove(norm_path)
            logger.info(f"Removed folder path: {folder_path}")
            # If removing the main folder, clear it
            if norm_path == self._main_folder_path:
                logger.warning(f"Removing main folder path: {norm_path}")
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

        # Normalize path
        norm_value = os.path.normpath(os.path.abspath(value))
        if self._folder_path != norm_value:
            logger.info(
                "Folder path changed from '%s' to '%s'",
                self._folder_path,
                norm_value,
            )
            self._folder_path = norm_value

            # Reset vertical lines when folder changes (for structured_packing mode)
            if self.analysis_mode == "structured_packing":
                self._vertical_left = None
                self._vertical_right = None
                logger.debug(
                    "Reset vertical lines for new folder in structured_packing mode"
                )

            # Save to settings
            self.save_setting("folderPath", self._folder_path)
            # Update output path (no 'Output' subfolder)
            self.output_path = value if value else ""
            self.folder_path_changed.emit(value)

            # Sync with file handler
            if hasattr(self, "file_handler"):
                self.file_handler.folder_path = norm_value

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
            # Sync with image processor
            if hasattr(self, "image_processor"):
                self.image_processor.y_img = value

    def set_h_img(self, value: int) -> None:
        """Set the height for image cropping."""
        if self._h_img != value:
            self._h_img = value
            self.save_setting("hImg", value)
            self.h_img_changed.emit(value)
            # Sync with image processor
            if hasattr(self, "image_processor"):
                self.image_processor.h_img = value

    def set_x_img(self, value: int) -> None:
        """Set the X coordinate for image cropping."""
        if self._x_img != value:
            self._x_img = value
            self.save_setting("xImg", value)
            self.x_img_changed.emit(value)
            # Sync with image processor
            if hasattr(self, "image_processor"):
                self.image_processor.x_img = value

    def set_w_img(self, value: int) -> None:
        """Set the width for image cropping."""
        if self._w_img != value:
            self._w_img = value
            self.save_setting("wImg", value)
            self.w_img_changed.emit(value)
            # Sync with image processor
            if hasattr(self, "image_processor"):
                self.image_processor.w_img = value

    def _sync_helper_params(self) -> None:
        """Synchronize parameters with helper class instances."""
        if hasattr(self, "image_processor"):
            self.image_processor.threshold = self.threshold
            self.image_processor.pixel = self.pixel
            self.image_processor.rotate_angle = self.rotate_angle
            self.image_processor.x_img = self.x_img
            self.image_processor.y_img = self.y_img
            self.image_processor.w_img = self.w_img
            self.image_processor.h_img = self.h_img
            self.image_processor.polynom = self.polynom
            self.image_processor.fitting_mode = self.fitting_mode
            self.image_processor.baseline = self.baseline
            self.image_processor.baseline_tf = self.baseline_tf
            self.image_processor.manual_baseline = self.manual_baseline

        if hasattr(self, "results_assembler"):
            self.results_assembler.pixel = self.pixel

        if hasattr(self, "pipeline"):
            self.pipeline.folder_path = self._folder_path
            self.pipeline.fps = self.fps
            self.pipeline.pixel = self.pixel

        if hasattr(self, "contact_angle_processor"):
            self.contact_angle_processor.pixel = self.pixel
            self.contact_angle_processor.polynom = self.polynom
            self.contact_angle_processor.fitting_mode = self.fitting_mode

        if hasattr(self, "visualization_processor"):
            self.visualization_processor.pixel = self.pixel
            self.visualization_processor.threshold = self.threshold
            self.visualization_processor.baseline = [self.baseline, self.baseline]
            self.visualization_processor.analysis_mode = self.analysis_mode

    def set_threshold(self, value: int) -> None:
        """Set the threshold value for image analysis."""
        if self._threshold != value:
            self._threshold = value
            self.save_setting("threshold", value)
            self.threshold_changed.emit(value)
            # Sync with image processor
            if hasattr(self, "image_processor"):
                self.image_processor.threshold = value

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
            # Sync with image processor
            if hasattr(self, "image_processor"):
                self.image_processor.polynom = value

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
        # Normalize incoming list to absolute normalized paths
        normalized = []
        try:
            for p in value or []:
                if p:
                    normalized.append(os.path.normpath(os.path.abspath(p)))
        except Exception:
            normalized = []

        if self._folder_paths != normalized:
            self._folder_paths = normalized
            self.save_setting("folderPaths", self._folder_paths)
            self.folder_paths_changed.emit(self._folder_paths)

    def set_main_folder_path(self, value: str) -> None:
        """Set the main folder path for analysis."""
        if not value or not isinstance(value, str):
            # Allow clearing main folder
            if value == "":
                self._main_folder_path = ""
                self.save_setting("mainFolderPath", "")
                self.main_folder_path_changed.emit("")
            return

        norm_value = os.path.normpath(os.path.abspath(value))
        if self._main_folder_path != norm_value:
            self._main_folder_path = norm_value
            self.save_setting("mainFolderPath", self._main_folder_path)
            self.main_folder_path_changed.emit(self._main_folder_path)

    # endregion SETTERS

    # region GETTERS
    def load_settings(self) -> None:
        """Load settings from persistent storage for the current analysis mode."""
        logger.info(f"Loading settings for analysis mode: {self.analysis_mode}")

        try:
            # Delegate to SettingsManager to load all settings
            settings_dict = self.settings_manager.load_settings()

            # Apply loaded settings to internal state
            self._pixel = settings_dict.get("pixel", 55.00)
            self._fps = settings_dict.get("fps", 100)
            self._manual_baseline = settings_dict.get("manual_baseline", 0)
            self._rotate_angle = settings_dict.get("rotate_angle", 0.0)
            self._baseline = settings_dict.get("baseline", 0)
            self._fitting_mode = settings_dict.get("fitting_mode", "Arc")
            self._polynom = settings_dict.get("polynom", 3)
            self._y_img = settings_dict.get("y_img", 0)
            self._h_img = settings_dict.get("h_img", 0)
            self._x_img = settings_dict.get("x_img", 0)
            self._w_img = settings_dict.get("w_img", 0)
            self._folder_path = settings_dict.get("folder_path", "")
            self._folder_paths = settings_dict.get("folder_paths", [])
            self._main_folder_path = settings_dict.get("main_folder_path", "")
            self._baseline_tf = settings_dict.get("baseline_tf", False)
            self._threshold = settings_dict.get("threshold", 50)

            # Initialize vertical lines for structured packing
            self._vertical_left = None
            self._vertical_right = None

            # Emit signals for folder paths
            try:
                self.folder_paths_changed.emit(self._folder_paths)
                self.main_folder_path_changed.emit(self._main_folder_path or "")
            except Exception:
                pass

        except Exception as e:
            logger.error(f"Failed to load settings for {self.analysis_mode}: {e}")
            raise

    def reset_to_defaults(self) -> None:
        """Reset selected parameters to their mode-specific defaults."""
        logger.info(f"Resetting parameters to defaults for mode: {self.analysis_mode}")
        try:
            # Delegate to SettingsManager to reset and reload
            self.settings_manager.reset_to_defaults()
            self.load_settings()
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

        # Normalize Unicode to NFC for deterministic behavior and accept
        # non-ASCII folder paths on Windows. Previously we rejected paths
        # containing non-ASCII characters which prevents normal usage on
        # systems where users have local-language folder names. Log a
        # non-blocking warning to aid debugging but continue.
        try:
            import unicodedata

            self._folder_path = unicodedata.normalize("NFC", self._folder_path)
        except Exception:
            # If normalization fails, continue with the original path
            pass

        # If path exists and is a directory we've already returned earlier.
        # Here we simply proceed — File operations will use the real path.
        try:
            # Try a roundtrip encode/decode to detect if any immediate
            # low-level issues are present, but do not block on encoding.
            # Use encode_path only for diagnostics if available.
            from src.utilities.core_utils import encode_path  # optional

            try:
                _ = encode_path(self._folder_path)
            except Exception:
                logger.debug("Could not encode folder path for diagnostic purposes")
        except Exception:
            # If path_identifier is not available, ignore and proceed
            pass

        # Accept path regardless of character set — OS-level calls will fail
        # later if the path is actually inaccessible.
        return True

    def _collect_image_files(self, progress_callback) -> list[str] | None:
        """Collect all image files from the folder, including extracted from videos.

        Args:
        ----
            progress_callback: Callback for progress updates during video extraction

        Returns:
        -------
            list[str] | None: List of image file paths or None if no files found

        """
        # Update file handler folder path
        self.file_handler.folder_path = self._folder_path

        # Use FileHandler to collect image files
        image_files = self.file_handler.collect_image_files(progress_callback)

        if image_files is None:
            self.error_occurred.emit(
                "No image or video files found in the selected folder"
            )

        return image_files

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
        # Use FileHandler to select files for processing
        return self.file_handler.select_files_for_processing(
            image_files, preview_middle
        )

    def _main(
        self,
        xlsx_file_path: str,
        files: list[str],
        save_files: bool,
        progress_callback: Callable | None = None,
        use_first_as_background: bool = False,
        background_files: list[str] | None = None,
    ) -> tuple[list, list, list, list, list, list, list, list, list]:
        """Run the main analysis pipeline with clean, consistent image processing."""
        # Setup and initialization
        background, time, time_int, result_lists = self._setup_and_initialize(
            files, save_files
        )

        # Initialize result lists with proper structure and default values
        num_files = len(files)
        self._initialize_result_lists(result_lists, num_files)

        # Background image preparation - START IN THREAD
        # This allows baseline detection to run concurrently
        # Use background_files for preview mode to sample all images (not just middle)
        bg_files = background_files if background_files is not None else files
        logger.info(
            f"Starting background creation in separate thread "
            f"with {len(bg_files)} images"
        )
        try:
            bg_future = create_background_threaded(
                image_paths=bg_files,
                use_first_as_background=use_first_as_background,
                num_images=10,
                rotate_angle=self.rotate_angle,
                crop_params=(self.x_img, self.w_img, self.y_img, self.h_img),
            )
        except Exception as e:
            logger.error(f"Failed to start background thread: {e}", exc_info=True)
            self.error_occurred.emit("Failed to start background creation")
            return None

        # Baseline detection - RUNS IMMEDIATELY (doesn't wait for background)
        logger.info("Starting baseline detection while background computes")
        baseline_data = self._detect_baselines(files)
        if baseline_data is None:
            return None

        # Get background result - waits if not ready yet
        logger.info("Retrieving background image from thread")
        try:
            background = bg_future.result(timeout=30)
        except TimeoutError:
            logger.error("Background creation timed out after 30 seconds")
            self.error_occurred.emit("Background creation timed out")
            return None
        except Exception as e:
            logger.error(f"Error getting background from thread: {e}", exc_info=True)
            self.error_occurred.emit("Failed to create background image")
            return None

        if background is None:
            logger.error("Background creation returned None")
            self.error_occurred.emit("Failed to create background image")
            return None

        logger.info(f"Background image ready: {background.shape}")

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
        return self.pipeline.setup_and_initialize(files, save_files)

    def _initialize_result_lists(self, result_lists, num_files):
        """Initialize all result lists with proper structure and default values."""
        # Delegate to ResultsAssembler
        self.results_assembler.initialize_result_lists(result_lists, num_files)

    def _detect_baselines(self, files):
        """Detect baselines for different analysis modes."""
        # Update image processor parameters
        self._sync_helper_params()

        # Use ImageProcessor to detect baselines
        baseline_data = self.image_processor.detect_baselines(files)

        if baseline_data is None:
            self.error_occurred.emit("Failed to detect baselines")
            return None

        # Store vertical lines if in structured_packing mode
        _, _, vertical_left, vertical_right = baseline_data
        if self.analysis_mode == "structured_packing":
            self._vertical_left = vertical_left
            self._vertical_right = vertical_right

        return baseline_data

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
        # Use FileHandler to preload images
        preloaded_images = self.file_handler.preload_images_if_reasonable(files)
        if preloaded_images:
            return preloaded_images

        # Fallback to empty dict if not preloading
        num_files = len(files)

        if num_files < 100:  # Only preload for reasonable sized datasets
            for file_path in files:
                img = safe_imread(file_path)
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
            q = int(q) if isinstance(q, int | float) else q

            if not isinstance(q, int):
                logger.error(f"q is not an integer: {type(q)}, value: {q}")
                q = int(q) if isinstance(q, int | float) else 0

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
            return safe_imread(files[q])

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
        q = int(q) if isinstance(q, int | float) else q

        # Store angle results (skip for free_sedimentation and structured_packing)
        if (
            angles
            and isinstance(angles, dict)
            and "left" in angles
            and self.analysis_mode not in ["free_sedimentation", "structured_packing"]
        ):
            result_lists["advancing_contact_angles"][q] = angles["left"]
            result_lists["receding_contact_angles"][q] = angles["right"]
        elif self.analysis_mode in ["free_sedimentation", "structured_packing"]:
            # Ensure NaN values for these modes
            result_lists["advancing_contact_angles"][q] = float("NaN")
            result_lists["receding_contact_angles"][q] = float("NaN")

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
        q = int(q) if isinstance(q, int | float) else 0
        self._store_center_point(result_lists, center_point, q)
        self._ensure_rect_lists(result_lists, q)
        self._store_rect_dimensions(result_lists, rect_w, rect_h, q)

    def _normalize_center_point(self, center_point):
        """Ensure center_point is a list/tuple of length 2."""
        if isinstance(center_point, float):
            return [center_point, float("nan")]
        if not (isinstance(center_point, list | tuple) and len(center_point) == 2):
            return [float("nan"), float("nan")]
        return center_point

    def _store_center_point(self, result_lists, center_point, q):
        """Store center point in px and mm."""
        self.results_assembler.store_center_point(result_lists, center_point, q)

    def _ensure_rect_lists(self, result_lists, q):
        """Ensure rectangle dimension lists exist and are long enough."""
        self.results_assembler.ensure_rect_lists(result_lists, q)

    def _store_rect_dimensions(self, result_lists, rect_w, rect_h, q):
        """Store rectangle dimensions in px and mm, and calculate area/diameter."""
        # Store rect dimensions
        self.results_assembler.store_rect_dimensions(result_lists, rect_w, rect_h, q)

        # Calculate area and diameter from current contour only
        area_px = float("nan")
        diameter_px = float("nan")

        # Only calculate area if we have a valid contour from the current frame
        if hasattr(self, "_current_contour") and self._current_contour is not None:
            area_px = self._calculate_robust_area(self._current_contour)
            diameter_px = math.sqrt(4 * area_px / math.pi) if area_px > 0 else 0

        # Store area and diameter values
        self._store_area_diameter_values(result_lists, area_px, diameter_px, q)

    def _store_area_diameter_values(self, result_lists, area_px, diameter_px, q):
        """Store area and diameter values in px and mm."""
        self.results_assembler.store_area_diameter_values(
            result_lists, area_px, diameter_px, q
        )

    def _store_contact_line_data(self, result_lists, result_images, q):
        """Store contact line data from result images."""
        self.results_assembler.store_contact_line_data(result_lists, result_images, q)

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
            self._update_result_images_for_progress(
                q, result_lists, result_images, rect_w, rect_h
            )
            continue_processing = progress_callback(
                (q + 1) / len(files),
                result_lists["advancing_contact_angles"][: q + 1],
                result_lists["receding_contact_angles"][: q + 1],
                result_lists["center_points_px"][: q + 1],
                result_images,
                result_lists,
            )
            # Emit deep copy to prevent image reference issues across signal queue
            self.image_processed.emit(q, copy.deepcopy(result_images))

            if continue_processing is False:
                if progress_callback:
                    progress_callback(
                        1.0,
                        result_lists["advancing_contact_angles"][: q + 1],
                        result_lists["receding_contact_angles"][: q + 1],
                        result_lists["center_points_px"][: q + 1],
                        result_images,
                    )
                return True
        return False

    def _update_result_images_for_progress(
        self, q, result_lists, result_images, rect_w, rect_h
    ):
        """Update result_images for progress callback."""
        if (
            rect_w is not None
            and not np.isnan(rect_w)
            and rect_h is not None
            and not np.isnan(rect_h)
        ):
            rect_width_mm = rect_w / self.pixel if self.pixel > 0 else 0
            rect_height_mm = rect_h / self.pixel if self.pixel > 0 else 0
            result_images["rect_width_mm"] = rect_width_mm
            result_images["rect_height_mm"] = rect_height_mm

            self._add_result_image_value(
                q,
                result_lists,
                result_images,
                "area_diameter_mm",
                logger_key="area_diameter_mm",
            )
            self._add_result_image_value(
                q,
                result_lists,
                result_images,
                "ellipse_diameter_mm",
                logger_key="ellipse_diameter_mm",
            )
            self._add_result_image_value(q, result_lists, result_images, "area_mm2")

            # Ensure velocity is in result_images (may be set by _calculate_velocity)
            if "velocity" not in result_images:
                self._add_result_image_value(q, result_lists, result_images, "velocity")

    def _add_result_image_value(
        self, q, result_lists, result_images, key, logger_key=None
    ):
        """Add a value from result_lists to result_images if valid."""
        value_list = result_lists.get(key, [])
        if q < len(value_list):
            value = value_list[q]
            if not math.isnan(value):
                result_images[key] = value
                if logger_key:
                    logger.debug(f"Added {logger_key} to result_images: {value}")

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
        # Delegate to Pipeline to finalize results
        self.pipeline.finalize_results(
            result_lists,
            vertical_left,
            vertical_right,
            save_files,
            processing_stopped,
            progress_callback,
            time,
            files,
        )

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
            _area_px,
            _diameter_px,
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
        return self.contact_angle_processor.handle_free_sedimentation_angles(
            angles_from_single
        )

    def _extract_contour_measurements(self, contours, result_lists):
        """Extract measurements from the largest contour."""
        # Clear or store the current contour
        if not contours or contours[0] is None:
            if hasattr(self, "_current_contour"):
                self._current_contour = None
        else:
            if hasattr(self, "_current_contour"):
                self._current_contour = contours[0]

        # Call the contact_angle_processor method with robust area calculation
        return self.contact_angle_processor.extract_contour_measurements(
            contours, result_lists, self._calculate_robust_area
        )

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
        return self.contact_angle_processor.process_intersection_points(
            y1_left,
            y1_right,
            processed_img,
            contours,
            self.threshold,
            q,
            result_images,
        )

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
            self.analysis_mode in ["free_sedimentation", "structured_packing"]
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
                isinstance(center_point, list | tuple) and len(center_point) == 2
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
        if result_images is None:
            result_images = {}
        if result_lists is None:
            result_lists = {}

        init_data = self._initialize_single_image_processing(filename, save_files, src)
        processed_img = self._prepare_image(src, result_images)
        background = self._prepare_background(processed_img, background)

        # Structured packing mode: set vertical lines
        if self.analysis_mode == "structured_packing":
            vertical_left, vertical_right = self._vertical_left, self._vertical_right
            result_images["vertical_left"] = vertical_left
            result_images["vertical_right"] = vertical_right

        self._create_baseline_visualization(
            processed_img, y1_left, y1_right, result_images
        )

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
            return self._single_image_no_contour(
                processed_img, result_images, vertical_left, vertical_right
            )

        cx, cy = self._process_contour_measurements(
            largest_contour,
            vis_img,
            y1_left,
            y1_right,
            result_lists,
            result_images,
            q,
        )

        # Handle visualization and result image for special modes
        if self.analysis_mode in ["free_sedimentation", "structured_packing"]:
            return self._single_image_special_mode_result(
                processed_img, largest_contour, cx, cy, result_images
            )

        # Intersection and angle processing
        return self._single_image_intersection_and_angles(
            y1_left,
            y1_right,
            processed_img,
            largest_contour,
            q,
            filename,
            save_files,
            result_images,
            init_data,
            vertical_left,
            vertical_right,
            result_lists,
        )

    def _single_image_no_contour(
        self, processed_img, result_images, vertical_left, vertical_right
    ):
        """Handle preview/result when no contour is found."""
        return self._handle_no_contour_case(
            processed_img, result_images, vertical_left, vertical_right
        )

    def _single_image_special_mode_result(
        self, processed_img, largest_contour, cx, cy, result_images
    ):
        """Create result image for free_sedimentation and structured_packing modes."""
        result_image = processed_img.copy()
        draw_filled_contour(result_image, largest_contour, color=(0, 255, 0), alpha=0.3)
        cv2.drawContours(result_image, [largest_contour], -1, (0, 255, 0), 2)
        if cx != 0 or cy != 0:
            x, y, w, h = cv2.boundingRect(largest_contour)
            cv2.rectangle(result_image, (x, y), (x + w, y + h), (0, 0, 255), 2)
            draw_center_point(
                result_image, cx, cy, color=(0, 0, 255), crosshair_size=20, thickness=2
            )
        if self.analysis_mode == "structured_packing":
            vertical_left = result_images.get("vertical_left")
            vertical_right = result_images.get("vertical_right")
            if vertical_left and vertical_right:
                x1_l, y1_l, x2_l, y2_l = map(int, vertical_left)
                cv2.line(result_image, (x1_l, y1_l), (x2_l, y2_l), (0, 0, 255), 3)
                x1_r, y1_r, x2_r, y2_r = map(int, vertical_right)
                cv2.line(result_image, (x1_r, y1_r), (x2_r, y2_r), (0, 0, 255), 3)
        result_images["result"] = result_image
        result_images["fallback"] = result_image.copy()
        return (
            processed_img,
            [largest_contour],
            {"left": float("NaN"), "right": float("NaN")},
        )

    def _single_image_intersection_and_angles(
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
        vertical_left,
        vertical_right,
        result_lists,
    ):
        """Process intersection points and angles for a single image."""
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
        if not intersection_points or len(intersection_points) < 2:
            angles = self._handle_insufficient_intersection_points(
                processed_img,
                largest_contour,
                cx=None,
                cy=None,
                result_images=result_images,
            )
            return processed_img, [largest_contour], angles

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
        # Sync image processor parameters and use it to prepare image
        self._sync_helper_params()
        return self.image_processor.prepare_image(src, result_images)

    def _prepare_background(self, processed_img, background):
        """Ensure background image matches processed image dimensions."""
        # Use ImageProcessor to prepare background
        return self.image_processor.prepare_background(processed_img, background)

    def _create_baseline_visualization(
        self, processed_img, y1_left, y1_right, result_images
    ):
        """Create baseline visualization image."""
        # Use ImageProcessor to create baseline visualization
        # This method updates result_images directly
        self.image_processor.create_baseline_visualization(
            processed_img, y1_left, y1_right, result_images
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
        # Sync image processor parameters and use it to find contours
        self._sync_helper_params()
        return self.image_processor.find_and_validate_contours(
            processed_img,
            background,
            result_images,
            y1_left,
            y1_right,
            vertical_left,
            vertical_right,
        )

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
        # Delegate to VisualizationProcessor
        self.visualization_processor.add_free_sedimentation_visualization(
            vis_img, largest_contour, cx, cy
        )

    def _add_baseline_mode_visualization(
        self, vis_img, largest_contour, cx, cy, y1_left, y1_right
    ):
        """Add visualization elements for baseline modes."""
        # Delegate to VisualizationProcessor
        result_images = {}  # Temporary dict for visualization processor
        self.visualization_processor.add_baseline_mode_visualization(
            vis_img, largest_contour, y1_left, y1_right, cx, cy, result_images
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
        # Use ImageProcessor to calculate robust area
        return self.image_processor.calculate_robust_area(contour)

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

    def _set_area_diameter_px(self, result_lists, q, area_px, diameter_px):
        """Set area and diameter in pixels at index q."""
        if isinstance(result_lists.get("area_px"), list):
            result_lists["area_px"][q] = area_px
        if isinstance(result_lists.get("diameter_px"), list):
            result_lists["diameter_px"][q] = diameter_px
        # Set area-based diameter (calculated from detected area)

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
            _shifted_points,
            _shifted_x,
            _shifted_y,
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

        # Calculate cx and cy from contour if not provided
        if cx is None or cy is None:
            moment = cv2.moments(largest_contour)
            if moment["m00"] != 0:
                cx = int(moment["m10"] / moment["m00"])
                cy = int(moment["m01"] / moment["m00"])

        # Always draw bounding rectangle and center point when possible
        if cx is not None and cy is not None:
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
        # center_points_px, center_points_mm = calculate_drop_area(
        #     y1_left,
        #     y1_right,
        #     intersection_points,
        #     largest_contour,
        #     processed_img,
        #     [],
        #     [],
        #     q,
        #     result_images,
        #     {},
        #     self.pixel,
        # )

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
                # Rotate coordinates for polynomial fitting
                x_left_90, y_left_90, x_right_90, y_right_90 = rotate_coordinates_90(
                    x_left_crop, y_left_crop, x_right_crop, y_right_crop
                )

                # Apply polynomial fitting
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
        # Delegate to VisualizationProcessor
        self.visualization_processor.create_comprehensive_result_image(
            result_images,
            angles,
            advancing_contact_angles,
            receding_contact_angles,
            largest_contour,
            vertical_left,
            vertical_right,
        )
