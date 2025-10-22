"""Analysis workflow module for DWIT.

This module combines utilities for running the image analysis pipeline:
- Pipeline: manages the image processing workflow, initialization, velocity
    calculations, finalization, and saving of results.
- FileHandler: handles collection, validation, optional video extraction, and
    optional preloading of image files.
- ResultsAssembler: prepares and stores analysis outputs (areas, diameters,
    center points, velocities, contact-line and rectangle metrics) in a
    consistent structure for downstream saving and reporting.

Classes and functions in this module interact with helpers (initialisation,
saving), utilities (image I/O, measurement helpers, logging), and processors
to produce the final results used by the DWIT GUI and batch workflows.
"""

import glob
import math
import os
from collections.abc import Callable

from src.helpers.initialisation import initiate_run
from src.helpers.save_results import save_results
from src.utilities.core_utils import get_logger
from src.utilities.image_utils import convert_videos_to_images, safe_imread
from src.utilities.measurement_utils import calculate_velocities

logger = get_logger(__name__)


class Pipeline:
    """Manages the image processing pipeline and workflow."""

    def __init__(
        self,
        analysis_mode: str = "free_sedimentation",
        folder_path: str = "",
        fps: int = 100,
        pixel: float = 1.0,
    ):
        """Initialize the Pipeline.

        Args:
        ----
            analysis_mode: The analysis mode
            folder_path: Path to the folder containing images
            fps: Frames per second
            pixel: Pixels per millimeter

        """
        self.analysis_mode = analysis_mode
        self.folder_path = folder_path
        self.fps = fps
        self.pixel = pixel

    def setup_and_initialize(self, files: list[str], save_files: bool) -> tuple:
        """Set up and initialize the analysis run.

        Args:
        ----
            files: List of image files
            save_files: Whether to save output files

        Returns:
        -------
            tuple: (background, time, time_int, result_lists)

        """
        try:
            background, _, time, time_int, result_lists = initiate_run(
                files, save_files, self.folder_path, self.fps
            )
            return background, time, time_int, result_lists
        except Exception as e:
            logger.error(f"Error in setup_and_initialize: {e}")
            raise

    def calculate_discontinuous_velocity(
        self,
        result_lists: dict,
        vertical_left: tuple | None,
        vertical_right: tuple | None,
    ) -> None:
        """Calculate discontinuous velocity for structured packing mode.

        Args:
        ----
            result_lists: Dictionary of results
            vertical_left: Left vertical line coordinates
            vertical_right: Right vertical line coordinates

        """
        if self.analysis_mode != "structured_packing":
            return

        if not vertical_left or not vertical_right:
            logger.warning("Cannot calculate velocity: vertical lines not detected")
            return

        try:
            # Calculate and store line distances
            distance_px, distance_mm = self._calculate_line_distance(
                vertical_left, vertical_right
            )
            num_files = len(result_lists.get("filenames", []))
            self._store_line_distances(
                result_lists, distance_px, distance_mm, num_files
            )

            # Calculate and store velocity if both contacts detected
            self._process_contact_velocity(
                result_lists, distance_px, distance_mm, num_files
            )

        except Exception as e:
            logger.error(f"Error calculating discontinuous velocity: {e}")

    def _calculate_line_distance(
        self, vertical_left: tuple, vertical_right: tuple
    ) -> tuple[float, float]:
        """Calculate distance between vertical lines."""
        x1_l, _, _, _ = vertical_left
        x1_r, _, _, _ = vertical_right
        distance_px = abs(x1_r - x1_l)
        distance_mm = distance_px / self.pixel if self.pixel > 0 else 0
        return distance_px, distance_mm

    def _store_line_distances(
        self, result_lists: dict, distance_px: float, distance_mm: float, num_files: int
    ) -> None:
        """Store vertical line distances in result lists."""
        if "vertical_line_distance_px" in result_lists:
            result_lists["vertical_line_distance_px"] = [distance_px] * num_files
        if "vertical_line_distance_mm" in result_lists:
            result_lists["vertical_line_distance_mm"] = [distance_mm] * num_files

    def _process_contact_velocity(
        self, result_lists: dict, distance_px: float, distance_mm: float, num_files: int
    ) -> None:
        """Calculate velocity from contact frames and store results."""
        left_contact_frame = result_lists.get("left_contact_frame")
        right_contact_frame = result_lists.get("right_contact_frame")

        if not self._are_contact_frames_valid(left_contact_frame, right_contact_frame):
            logger.warning("Contact frames not properly detected for velocity calc")
            return

        # Calculate contact time and velocity
        contact_time_frames = right_contact_frame - left_contact_frame
        contact_time_seconds = contact_time_frames / self.fps
        velocity_px_s = distance_px / contact_time_seconds
        velocity_mm_s = distance_mm / contact_time_seconds

        # Store results
        self._store_velocity_results(
            result_lists,
            velocity_px_s,
            velocity_mm_s,
            contact_time_frames,
            contact_time_seconds,
            num_files,
        )

        logger.info(
            f"Discontinuous velocity: {velocity_mm_s:.2f} mm/s "
            f"(contact time: {contact_time_seconds:.3f} s)"
        )

    def _are_contact_frames_valid(
        self, left_frame: int | None, right_frame: int | None
    ) -> bool:
        """Check if both contact frames are valid."""
        return (
            left_frame is not None
            and right_frame is not None
            and right_frame > left_frame
        )

    def _store_velocity_results(
        self,
        result_lists: dict,
        velocity_px_s: float,
        velocity_mm_s: float,
        contact_time_frames: int,
        contact_time_seconds: float,
        num_files: int,
    ) -> None:
        """Store velocity and contact time results."""
        if "discontinuous_velocity_px_s" in result_lists:
            result_lists["discontinuous_velocity_px_s"] = [velocity_px_s] * num_files
        if "discontinuous_velocity_mm_s" in result_lists:
            result_lists["discontinuous_velocity_mm_s"] = [velocity_mm_s] * num_files
        if "contact_time_frames" in result_lists:
            result_lists["contact_time_frames"] = [contact_time_frames] * num_files
        if "contact_time_seconds" in result_lists:
            result_lists["contact_time_seconds"] = [contact_time_seconds] * num_files

    def finalize_results(
        self,
        result_lists: dict,
        vertical_left: tuple | None,
        vertical_right: tuple | None,
        save_files: bool,
        processing_stopped: bool,
        progress_callback: Callable | None,
        time: list,
        files: list[str],
    ) -> None:
        """Finalize results by calculating velocities and saving.

        Args:
        ----
            result_lists: Dictionary of results
            vertical_left: Left vertical line coordinates
            vertical_right: Right vertical line coordinates
            save_files: Whether to save output files
            processing_stopped: Whether processing was stopped early
            progress_callback: Progress callback function
            time: List of time values
            files: List of image files

        """
        # Calculate discontinuous velocity for structured packing
        if self.analysis_mode == "structured_packing":
            self.calculate_discontinuous_velocity(
                result_lists, vertical_left, vertical_right
            )

        # Handle final progress and save
        self._handle_final_progress_and_save(
            result_lists,
            save_files,
            processing_stopped,
            progress_callback,
            time,
            files,
        )

    def _handle_final_progress_and_save(
        self,
        result_lists: dict,
        save_files: bool,
        processing_stopped: bool,
        progress_callback: Callable | None,
        time: list,
        files: list[str],
    ) -> None:
        """Handle final progress reporting and save results.

        Args:
        ----
            result_lists: Dictionary of results
            save_files: Whether to save output files
            processing_stopped: Whether processing was stopped
            progress_callback: Progress callback function
            time: List of time values
            files: List of image files

        """
        try:
            # Calculate velocities if not in structured_packing mode
            if self.analysis_mode != "structured_packing":
                center_points_px = result_lists.get("center_points_px", [])
                # Ensure pixel and fps are floats
                pixel = self.pixel
                fps = self.fps
                try:
                    pixel = float(pixel) if not isinstance(pixel, float) else pixel
                except Exception:
                    pixel = 1.0
                try:
                    fps = float(fps) if not isinstance(fps, float) else fps
                except Exception:
                    fps = 1.0
                # Ensure time_values are flat list of floats
                time_values = []
                for t in time:
                    try:
                        time_values.append(float(t))
                    except Exception:
                        time_values.append(float("NaN"))
                if center_points_px and len(center_points_px) > 1:
                    velocities = calculate_velocities(
                        center_points_px,
                        pixel=pixel,
                        fps=fps,
                        time_values=time_values,
                    )
                    result_lists["velocity"] = velocities
                else:
                    num_files = len(files)
                    result_lists["velocity"] = [float("NaN")] * num_files

            # Report final progress
            if progress_callback and not processing_stopped:
                try:
                    progress_callback(
                        100,
                        "Complete",
                        result_lists.get("images", [{}])[-1],
                        len(files),
                    )
                except Exception as e:
                    logger.debug(f"Progress callback error: {e}")

            # Save results if requested
            if save_files and not processing_stopped:
                try:
                    save_results(
                        self.folder_path,
                        time,
                        result_lists,
                    )
                    logger.info("Results saved successfully")
                except Exception as e:
                    logger.error(f"Error saving results: {e}")

        except Exception as e:
            logger.error(f"Error in final progress and save: {e}")


class FileHandler:
    """Handles file operations including image collection and validation."""

    def __init__(self, folder_path: str = ""):
        """Initialize FileHandler with a folder path.

        Args:
        ----
            folder_path: Path to the folder containing images/videos

        """
        self.folder_path = folder_path
        self.image_extensions = [
            "*.jpg",
            "*.jpeg",
            "*.png",
            "*.bmp",
            "*.gif",
            "*.tiff",
        ]
        self.video_extensions = ["*.mp4", "*.avi", "*.mov", "*.mkv", "*.wmv", "*.flv"]

    def has_media_files(self) -> bool:
        """Check if the folder contains any media files (images or videos).

        Returns
        -------
            bool: True if media files are found, False otherwise

        """
        has_media = False

        # Check for images
        for ext in self.image_extensions:
            found = glob.glob(os.path.join(self.folder_path, ext))
            if found:
                has_media = True
                break

        # Check for common video extensions if no images found
        if not has_media:
            for vext in self.video_extensions:
                found = glob.glob(os.path.join(self.folder_path, vext))
                if found:
                    has_media = True
                    logger.info(f"Found video file(s) with extension {vext}")
                    break

        if not has_media:
            logger.error(f"No image or video files found in {self.folder_path}")

        return has_media

    def collect_image_files(self, progress_callback=None) -> list[str] | None:
        """Collect all image files from the folder, including extracted from videos.

        Args:
        ----
            progress_callback: Callback for progress updates during video extraction

        Returns:
        -------
            list[str] | None: List of image file paths or None if no files found

        """
        # Check for at least one image or video file in the folder before proceeding
        if not self.has_media_files():
            return None

        # First check for video files and convert them to images if found
        extracted_images = convert_videos_to_images(self.folder_path, progress_callback)
        if extracted_images:
            logger.info(
                f"Extracted {len(extracted_images)} images from video files "
                f"for detection."
            )

        # Find image files in the folder with fully qualified paths
        image_files = []
        for ext in self.image_extensions:
            files_found = glob.glob(os.path.join(self.folder_path, ext))
            image_files.extend(files_found)

        # Add extracted images if any were found
        if extracted_images:
            image_files.extend(extracted_images)

        if not image_files:
            logger.error(
                f"No image or video files found in the selected folder "
                f"after extraction. Path: {self.folder_path}"
            )
            return None

        # Sort files by name
        image_files.sort()
        return image_files

    def select_files_for_processing(
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

    def preload_images_if_reasonable(self, files: list[str]) -> dict[int, any] | None:
        """Preload images into memory if the dataset is reasonably sized.

        Args:
        ----
            files: List of file paths to potentially preload

        Returns:
        -------
            dict[int, any] | None: Dictionary mapping indices to images, or None

        """
        # Only preload if we have a reasonable number of files (< 100)
        if len(files) > 100:
            logger.debug(
                f"Skipping image preload: {len(files)} files exceeds threshold"
            )
            return {}

        preloaded_images = {}
        for q, file_path in enumerate(files):
            img = safe_imread(file_path)
            if img is not None:
                preloaded_images[q] = img
            else:
                logger.warning(f"Failed to preload image {q}: {file_path}")

        logger.info(f"Preloaded {len(preloaded_images)} images into memory")
        return preloaded_images


class ResultsAssembler:
    """Assembles and manages analysis results storage."""

    def __init__(self, analysis_mode: str = "free_sedimentation", pixel: float = 1.0):
        """Initialize the ResultsAssembler.

        Args:
        ----
            analysis_mode: The analysis mode
            pixel: Pixels per millimeter for unit conversion

        """
        self.analysis_mode = analysis_mode
        self.pixel = pixel

    def initialize_result_lists(self, result_lists: dict, num_files: int) -> None:
        """Initialize all result lists with proper structure and default values.

        Args:
        ----
            result_lists: Dictionary to store results
            num_files: Number of files to process

        """
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
            "area_mm2",
            "diameter_px",
            "diameter_mm",
            "rect_width_px",
            "rect_width_mm",
            "rect_height_px",
            "rect_height_mm",
            "ellipse_diameter_px",
            "ellipse_diameter_mm",
            "velocity",
            "contact_line_px",
            "contact_line_mm",
        ]

        for key in scalar_lists:
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
                    isinstance(item, list | tuple) and len(item) == 2
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

    def store_center_point(
        self, result_lists: dict, center_point: tuple, index: int
    ) -> None:
        """Store center point coordinates.

        Args:
        ----
            result_lists: Dictionary of results
            center_point: (x, y) coordinates
            index: Frame index

        """
        if center_point is None or not isinstance(center_point, tuple | list):
            self._set_center_point_nan(result_lists, index)
            return

        cx, cy = center_point
        if not isinstance(cx, int | float) or not isinstance(cy, int | float):
            self._set_center_point_nan(result_lists, index)
            return

        if math.isnan(cx) or math.isnan(cy):
            self._set_center_point_nan(result_lists, index)
            return

        # Store in pixels
        self._ensure_center_point_lists(result_lists, index)
        result_lists["center_points_px"][index] = [float(cx), float(cy)]

        # Convert to mm
        if self.pixel > 0:
            result_lists["center_points_mm"][index] = [
                float(cx / self.pixel),
                float(cy / self.pixel),
            ]
        else:
            result_lists["center_points_mm"][index] = [float("NaN"), float("NaN")]

    def _set_center_point_nan(self, result_lists: dict, index: int) -> None:
        """Set center point to NaN for given index."""
        self._ensure_center_point_lists(result_lists, index)
        result_lists["center_points_px"][index] = [float("NaN"), float("NaN")]
        result_lists["center_points_mm"][index] = [float("NaN"), float("NaN")]

    def _ensure_center_point_lists(self, result_lists: dict, index: int) -> None:
        """Ensure center point lists exist and are correctly sized."""
        for key in ["center_points_px", "center_points_mm"]:
            if key not in result_lists:
                result_lists[key] = []
            while len(result_lists[key]) <= index:
                result_lists[key].append([float("NaN"), float("NaN")])

    def ensure_rect_lists(self, result_lists: dict, index: int) -> None:
        """Ensure rectangle dimension lists exist.

        Args:
        ----
            result_lists: Dictionary of results
            index: Frame index

        """
        rect_keys = [
            "rect_width_px",
            "rect_width_mm",
            "rect_height_px",
            "rect_height_mm",
        ]
        for key in rect_keys:
            if key not in result_lists:
                result_lists[key] = []
            while len(result_lists[key]) <= index:
                result_lists[key].append(float("NaN"))

    def store_rect_dimensions(
        self, result_lists: dict, rect_w: float, rect_h: float, index: int
    ) -> None:
        """Store rectangle dimensions.

        Args:
        ----
            result_lists: Dictionary of results
            rect_w: Rectangle width in pixels
            rect_h: Rectangle height in pixels
            index: Frame index

        """
        self.ensure_rect_lists(result_lists, index)

        if rect_w == 0 or rect_h == 0 or math.isnan(rect_w) or math.isnan(rect_h):
            self.set_rect_nan(result_lists, index)
            return

        # Store pixels
        result_lists["rect_width_px"][index] = float(rect_w)
        result_lists["rect_height_px"][index] = float(rect_h)

        # Convert to mm
        if self.pixel > 0:
            result_lists["rect_width_mm"][index] = float(rect_w / self.pixel)
            result_lists["rect_height_mm"][index] = float(rect_h / self.pixel)

            # Calculate ellipse diameter (sqrt(width_mm * height_mm))
            width_mm = result_lists["rect_width_mm"][index]
            height_mm = result_lists["rect_height_mm"][index]
            if width_mm > 0 and height_mm > 0:
                ellipse_diameter_mm = math.sqrt(width_mm * height_mm)
            else:
                ellipse_diameter_mm = float("nan")
            # Store ellipse diameter
            if "ellipse_diameter_mm" not in result_lists:
                result_lists["ellipse_diameter_mm"] = []
            while len(result_lists["ellipse_diameter_mm"]) <= index:
                result_lists["ellipse_diameter_mm"].append(float("nan"))
            result_lists["ellipse_diameter_mm"][index] = ellipse_diameter_mm
        else:
            result_lists["rect_width_mm"][index] = float("NaN")
            result_lists["rect_height_mm"][index] = float("NaN")

            # Store NaN for ellipse diameter
            if "ellipse_diameter_mm" not in result_lists:
                result_lists["ellipse_diameter_mm"] = []
            while len(result_lists["ellipse_diameter_mm"]) <= index:
                result_lists["ellipse_diameter_mm"].append(float("nan"))
            result_lists["ellipse_diameter_mm"][index] = float("nan")

    def set_rect_nan(self, result_lists: dict, index: int) -> None:
        """Set rectangle dimensions to NaN.

        Args:
        ----
            result_lists: Dictionary of results
            index: Frame index

        """
        self.ensure_rect_lists(result_lists, index)
        result_lists["rect_width_px"][index] = float("NaN")
        result_lists["rect_height_px"][index] = float("NaN")
        result_lists["rect_width_mm"][index] = float("NaN")
        result_lists["rect_height_mm"][index] = float("NaN")

    def store_area_diameter_values(
        self, result_lists: dict, area_px: float, diameter_px: float, index: int
    ) -> None:
        """Store area and diameter values.

        Args:
        ----
            result_lists: Dictionary of results
            area_px: Area in pixels
            diameter_px: Diameter in pixels
            index: Frame index

        """
        # Ensure lists exist
        for key in ["area_px", "area_mm", "area_mm2", "diameter_px", "diameter_mm"]:
            if key not in result_lists:
                result_lists[key] = []
            while len(result_lists[key]) <= index:
                result_lists[key].append(float("NaN"))

        # Store pixels
        result_lists["area_px"][index] = float(area_px)
        result_lists["diameter_px"][index] = float(diameter_px)

        # Convert to mm
        if self.pixel > 0:
            area_mm = area_px / (self.pixel**2)
            diameter_mm = diameter_px / self.pixel
            result_lists["area_mm"][index] = float(area_mm)
            result_lists["area_mm2"][index] = float(
                area_mm
            )  # Store area_mm2 same as area_mm
            result_lists["diameter_mm"][index] = float(diameter_mm)

            # Calculate area diameter (sqrt(4*A/pi))
            if area_mm > 0:
                area_diameter_mm = math.sqrt(4 * area_mm / math.pi)
            else:
                area_diameter_mm = float("nan")
            # Store area diameter
            if "area_diameter_mm" not in result_lists:
                result_lists["area_diameter_mm"] = []
            while len(result_lists["area_diameter_mm"]) <= index:
                result_lists["area_diameter_mm"].append(float("nan"))
            result_lists["area_diameter_mm"][index] = area_diameter_mm
        else:
            result_lists["area_mm"][index] = float("NaN")
            result_lists["area_mm2"][index] = float("NaN")
            result_lists["diameter_mm"][index] = float("NaN")

            # Store NaN for area diameter
            if "area_diameter_mm" not in result_lists:
                result_lists["area_diameter_mm"] = []
            while len(result_lists["area_diameter_mm"]) <= index:
                result_lists["area_diameter_mm"].append(float("nan"))
            result_lists["area_diameter_mm"][index] = float("nan")

    def store_contact_line_data(
        self, result_lists: dict, result_images: dict, index: int
    ) -> None:
        """Store contact line data from result images.

        Args:
        ----
            result_lists: Dictionary of results
            result_images: Dictionary of result images
            index: Frame index

        """
        # Skip for free_sedimentation and structured_packing modes
        if self.analysis_mode in ["free_sedimentation", "structured_packing"]:
            # Ensure lists exist but store NaN
            for key in ["contact_line_px", "contact_line_mm"]:
                if key not in result_lists:
                    result_lists[key] = []
                while len(result_lists[key]) <= index:
                    result_lists[key].append(float("NaN"))
                result_lists[key][index] = float("NaN")
            return

        # Ensure lists exist
        for key in ["contact_line_px", "contact_line_mm"]:
            if key not in result_lists:
                result_lists[key] = []
            while len(result_lists[key]) <= index:
                result_lists[key].append(float("NaN"))

        # Get contact line values from result_images
        contact_line_px = result_images.get("contact_line_px", float("NaN"))
        contact_line_mm = result_images.get("contact_line_mm", float("NaN"))

        # Only store if not a list or tuple
        if isinstance(contact_line_px, list | tuple):
            contact_line_px = float("NaN")
        if isinstance(contact_line_mm, list | tuple):
            contact_line_mm = float("NaN")

        result_lists["contact_line_px"][index] = float(contact_line_px)
        result_lists["contact_line_mm"][index] = float(contact_line_mm)
