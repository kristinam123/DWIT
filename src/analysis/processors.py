"""Image processing, contact-angle processing, and visualization utilities for DWIT.

This module provides processors and helpers used across the DWIT application,
including contact angle calculations, intersection point detection, contour
measurements, and creation of annotated result images (baselines,
intersection points, filled contours, center points, and other overlays).

Provided processors:
- ContactAngleProcessor: contact-angle calculations and intersection handling.
- VisualizationProcessor: drawing and assembling annotated result visuals.
- ImageProcessor: image preparation (rotate/crop), baseline detection,
    contour finding/validation, and robust area calculation.

Designed to support all analysis modes (free_sedimentation, contact_angle,
channel, structured_packing) and to integrate with helpers and utilities
under src/helpers and src/utilities.
"""

import math
import os

import cv2
import numpy as np

from src.helpers.geometry import (
    filter_contour_by_baseline_slope,
    filter_contour_by_vertical_lines,
    find_intersection_points,
)
from src.helpers.visualisation import (
    create_fallback_result,
    draw_axis_line,
    draw_center_point,
    draw_connection_line,
    draw_dual_baselines,
    draw_filled_contour,
    draw_intersection_points,
    draw_intersection_points_and_angles,
    draw_rectangle,
)
from src.utilities.core_utils import get_logger
from src.utilities.image_utils import (
    crop_image,
    rotate_image,
    safe_imread,
)
from src.utilities.measurement_utils import find_single_baseline, find_vertical_lines

logger = get_logger(__name__)


class ContactAngleProcessor:
    """Processes contact angle measurements for droplet analysis."""

    def __init__(
        self,
        analysis_mode: str,
        pixel: float = 1.0,
        polynom: int = 2,
        fitting_mode: str = "polynomial",
    ):
        """Initialize ContactAngleProcessor.

        Args:
        ----
            analysis_mode: Analysis mode (e.g., "contact_angle", "free_sedimentation")
            pixel: Pixels per millimeter conversion factor
            polynom: Polynomial degree for curve fitting
            fitting_mode: Mode for contact angle fitting

        """
        self.analysis_mode = analysis_mode
        self.pixel = pixel
        self.polynom = polynom
        self.fitting_mode = fitting_mode

    def handle_free_sedimentation_angles(self, angles_from_single: dict) -> dict:
        """Handle contact angle processing for free sedimentation mode.

        Args:
        ----
            angles_from_single: Dictionary with 'left' and 'right' angles

        Returns:
        -------
            Dictionary with processed angles

        """
        if angles_from_single:
            return {
                "left": angles_from_single.get("left", float("nan")),
                "right": angles_from_single.get("right", float("nan")),
            }
        return {"left": float("nan"), "right": float("nan")}

    def extract_contour_measurements(
        self, contours: list, result_lists: dict, calculate_robust_area_func=None
    ) -> tuple:
        """Extract measurements from the largest contour.

        Args:
        ----
            contours: List of detected contours
            result_lists: Dictionary of results
            calculate_robust_area_func: Optional function to calculate robust area

        Returns:
        -------
            Tuple of (center_point, rect_width, rect_height, area_px, diameter_px)

        """
        # Initialize with safe defaults
        center_point = [float("nan"), float("nan")]
        rect_width = float("nan")
        rect_height = float("nan")
        area_px = float("nan")
        diameter_px = float("nan")

        if not contours or contours[0] is None:
            # No contour detected, return defaults
            return center_point, rect_width, rect_height, area_px, diameter_px

        # Process any detected contours to extract measurements
        largest_contour = contours[0]

        # Calculate contour area with robust handling for open contours
        if calculate_robust_area_func is not None:
            area_px = calculate_robust_area_func(largest_contour)
        else:
            # Fallback to basic area calculation
            area_px = cv2.contourArea(largest_contour)

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
        elif not (isinstance(center_point, list | tuple) and len(center_point) == 2):
            center_point = [float("nan"), float("nan")]

        _x, _y, w, h = cv2.boundingRect(largest_contour)
        rect_width = w
        rect_height = h

        return center_point, rect_width, rect_height, area_px, diameter_px

    def process_intersection_points(
        self,
        y1_left,
        y1_right,
        processed_img,
        contours,
        threshold,
        q,
        result_images,
    ) -> tuple[float, float]:
        """Process intersection points and contact line calculations.

        Args:
        ----
            y1_left: Left baseline Y coordinate
            y1_right: Right baseline Y coordinate
            processed_img: Processed image array
            contours: List of detected contours
            threshold: Threshold value for processing
            q: Queue parameter for find_intersection_points
            result_images: Dictionary to store result images

        Returns:
        -------
            Tuple of (contact_line_px, contact_line_mm)

        """
        contact_line_px = float("nan")
        contact_line_mm = float("nan")

        # Skip for free_sedimentation and structured_packing modes
        if (
            self.analysis_mode in ["free_sedimentation", "structured_packing"]
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
            threshold,
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


class VisualizationProcessor:
    """Handles visualization and drawing operations for analysis results."""

    def __init__(
        self,
        analysis_mode: str,
        pixel: float,
        threshold: int,
        baseline: list[int],
    ):
        """Initialize the VisualizationProcessor.

        Parameters
        ----------
        analysis_mode : str
            The current analysis mode (e.g., 'free_sedimentation', 'channel').
        pixel : float
            Pixels per mm conversion factor.
        threshold : int
            Threshold value for image processing.
        baseline : list[int]
            Baseline coordinates [y1_left, y1_right].

        """
        self.analysis_mode = analysis_mode
        self.pixel = pixel
        self.threshold = threshold
        self.baseline = baseline

    def create_baseline_visualization(
        self,
        processed_img: np.ndarray,
        y1_left: int | None,
        y1_right: int | None,
        result_images: dict,
    ) -> None:
        """Create baseline visualization image.

        Parameters
        ----------
        processed_img : np.ndarray
            The processed image.
        y1_left : int | None
            Left baseline y-coordinate.
        y1_right : int | None
            Right baseline y-coordinate.
        result_images : dict
            Dictionary to store result images.

        """
        if self.analysis_mode in ["free_sedimentation"]:
            # No baseline for free sedimentation
            result_images["baseline"] = processed_img.copy()
        else:
            # Draw baseline for other modes
            result_images["baseline"] = self._draw_baseline_on_image(
                processed_img, y1_left, y1_right
            )

    def _draw_baseline_on_image(
        self, img: np.ndarray, y1_left: int | None, y1_right: int | None
    ) -> np.ndarray:
        """Draw baseline on image.

        Parameters
        ----------
        img : np.ndarray
            Input image.
        y1_left : int | None
            Left baseline y-coordinate.
        y1_right : int | None
            Right baseline y-coordinate.

        Returns
        -------
        np.ndarray
            Image with baseline drawn.

        """
        baseline_img = img.copy()
        if y1_left is not None and y1_right is not None:
            # Draw line from left to right edge
            cv2.line(
                baseline_img,
                (0, int(y1_left)),
                (img.shape[1], int(y1_right)),
                (0, 255, 0),
                2,
            )
        return baseline_img

    def add_free_sedimentation_visualization(
        self, vis_img: np.ndarray, largest_contour: np.ndarray, cx: float, cy: float
    ) -> None:
        """Add visualization elements for free sedimentation mode.

        Parameters
        ----------
        vis_img : np.ndarray
            Visualization image to draw on.
        largest_contour : np.ndarray
            The largest detected contour.
        cx : float
            Center x-coordinate.
        cy : float
            Center y-coordinate.

        """
        # Add 30% transparent green fill for contour area
        draw_filled_contour(vis_img, largest_contour, color=(0, 255, 0), alpha=0.3)

        x, y, w, h = cv2.boundingRect(largest_contour)
        draw_rectangle(vis_img, x, y, w, h, color=(0, 0, 255), thickness=2)
        draw_center_point(
            vis_img, cx, cy, color=(0, 0, 255), crosshair_size=20, thickness=2
        )

    def add_baseline_mode_visualization(
        self,
        vis_img: np.ndarray,
        largest_contour: np.ndarray,
        y1_left: int | None,
        y1_right: int | None,
        cx: float,
        cy: float,
        result_images: dict,
    ) -> None:
        """Add visualization elements for baseline modes.

        Parameters
        ----------
        vis_img : np.ndarray
            Visualization image to draw on.
        largest_contour : np.ndarray
            The largest detected contour.
        y1_left : int | None
            Left baseline y-coordinate.
        y1_right : int | None
            Right baseline y-coordinate.
        cx : float
            Center x-coordinate.
        cy : float
            Center y-coordinate.
        result_images : dict
            Dictionary of result images.

        """
        # Add 30% transparent green fill for contour area
        draw_filled_contour(vis_img, largest_contour, color=(0, 255, 0), alpha=0.3)

        x, y, w, h = cv2.boundingRect(largest_contour)
        # Consistent red rectangle around contour (thickness=2)
        draw_rectangle(vis_img, x, y, w, h, color=(0, 0, 255), thickness=2)

        if self.analysis_mode == "channel":
            # Draw dual baselines (consistent red color, thickness=3)
            draw_dual_baselines(
                vis_img,
                y1_left,
                y1_right,
                color1=(0, 0, 255),
                color2=(0, 0, 255),
                thickness=3,
            )
        elif self.analysis_mode == "contact_angle" and y1_left is not None:
            # Single baseline at y1_left (consistent red color, thickness=3)
            cv2.line(
                vis_img,
                (0, int(y1_left)),
                (vis_img.shape[1], int(y1_left)),
                (0, 0, 255),
                3,
            )

        # Always draw center point for baseline modes (consistent style)
        draw_center_point(
            vis_img, cx, cy, color=(0, 0, 255), crosshair_size=20, thickness=2
        )

    def draw_vertical_lines(
        self,
        img: np.ndarray,
        vertical_left: tuple | None,
        vertical_right: tuple | None,
        color: tuple = (255, 0, 255),
        thickness: int = 2,
    ) -> np.ndarray:
        """Draw vertical lines on image.

        Parameters
        ----------
        img : np.ndarray
            Image to draw on.
        vertical_left : tuple | None
            Left vertical line parameters (x1, y1, x2, y2).
        vertical_right : tuple | None
            Right vertical line parameters (x1, y1, x2, y2).
        color : tuple, default=(255, 0, 255)
            Line color (B, G, R).
        thickness : int, default=2
            Line thickness.

        Returns
        -------
        np.ndarray
            Image with vertical lines drawn.

        """
        result = img.copy()
        if vertical_left:
            x1, y1, x2, y2 = vertical_left
            cv2.line(result, (int(x1), int(y1)), (int(x2), int(y2)), color, thickness)
        if vertical_right:
            x1, y1, x2, y2 = vertical_right
            cv2.line(result, (int(x1), int(y1)), (int(x2), int(y2)), color, thickness)
        return result

    def create_comprehensive_result_image(
        self,
        result_images: dict,
        angles: dict,
        advancing_contact_angles: list,
        receding_contact_angles: list,
        largest_contour: np.ndarray,
        vertical_left: tuple | None = None,
        vertical_right: tuple | None = None,
    ) -> None:
        """Create comprehensive result image with all annotations.

        Parameters
        ----------
        result_images : dict
            Dictionary containing intermediate result images (modified in-place).
        angles : dict
            Dictionary with 'left' and 'right' contact angle values.
        advancing_contact_angles : list
            List of advancing contact angles.
        receding_contact_angles : list
            List of receding contact angles.
        largest_contour : np.ndarray
            The largest detected contour.
        vertical_left : tuple | None, default=None
            Left vertical line parameters for structured packing mode.
        vertical_right : tuple | None, default=None
            Right vertical line parameters for structured packing mode.

        """
        result_image = result_images["original"].copy()

        # Draw baseline and intersection/contact lines only if not structured_packing
        if self.analysis_mode != "structured_packing":
            if "baseline_coords" in result_images:
                y1_left, y1_right = result_images["baseline_coords"]
                if self.analysis_mode == "channel" and y1_left and y1_right:
                    draw_dual_baselines(
                        result_image,
                        y1_left,
                        y1_right,
                        color1=(0, 0, 255),
                        color2=(0, 0, 255),
                        thickness=3,
                    )
                elif self.analysis_mode == "contact_angle" and y1_left:
                    cv2.line(
                        result_image,
                        (0, int(y1_left)),
                        (result_image.shape[1], int(y1_left)),
                        (0, 0, 255),
                        3,
                    )
            # Draw intersection points and contact angle lines
            draw_intersection_points_and_angles(
                result_image,
                result_images,
                angles,
                advancing_contact_angles,
                receding_contact_angles,
            )
        # Draw vertical lines for structured packing mode (consistent thickness=3)
        if (
            self.analysis_mode == "structured_packing"
            and vertical_left
            and vertical_right
        ):
            result_image = self.draw_vertical_lines(
                result_image,
                vertical_left,
                vertical_right,
                color=(0, 0, 255),
                thickness=3,
            )

        # Draw filled contour area (30% transparent green)
        draw_filled_contour(result_image, largest_contour, color=(0, 255, 0), alpha=0.3)

        # Draw contour outline (consistent green color, thickness=2)
        cv2.drawContours(result_image, [largest_contour], -1, (0, 255, 0), 2)

        # ALWAYS draw bounding rectangle and center point when contour exists
        if largest_contour is not None and len(largest_contour) > 0:
            x, y, w, h = cv2.boundingRect(largest_contour)

            # Check for valid dimensions
            if w > 0 and h > 0:
                # Always draw rectangle (consistent red, thickness=2)
                draw_rectangle(result_image, x, y, w, h, color=(0, 0, 255), thickness=2)

                # Always calculate and draw center point
                # (consistent red, crosshair_size=20, thickness=2)
                moment = cv2.moments(largest_contour)
                if moment["m00"] != 0:
                    cx = int(moment["m10"] / moment["m00"])
                    cy = int(moment["m01"] / moment["m00"])
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
            create_fallback_result(result_images, largest_contour)

    def create_fallback_result(
        self, result_images: dict, largest_contour: np.ndarray
    ) -> np.ndarray:
        """Create fallback result image when full result cannot be generated.

        Parameters
        ----------
        result_images : dict
            Dictionary of intermediate result images.
        largest_contour : np.ndarray
            The largest detected contour.

        Returns
        -------
        np.ndarray
            Fallback result image.

        """
        # Try to use contour image if available
        if "contour" in result_images:
            return result_images["contour"].copy()

        # Otherwise create a basic image with contour
        if "original" in result_images:
            fallback_result = result_images["original"].copy()
            if len(fallback_result.shape) == 2:
                fallback_result = cv2.cvtColor(fallback_result, cv2.COLOR_GRAY2BGR)
            cv2.drawContours(fallback_result, [largest_contour], 0, (0, 255, 0), 2)
            return fallback_result

        # Last resort: create blank image
        return np.zeros((480, 640, 3), dtype=np.uint8)


class ImageProcessor:
    """Handles image processing operations for droplet analysis."""

    def __init__(
        self,
        analysis_mode: str = "free_sedimentation",
        threshold: int = 60,
        pixel: float = 1.0,
        rotate_angle: float = 0.0,
        x_img: int = 0,
        y_img: int = 0,
        w_img: int = 0,
        h_img: int = 0,
        polynom: int = 2,
        fitting_mode: str = "polynomial",
        baseline: int = 0,
        baseline_tf: bool = False,
        manual_baseline: int = 0,
    ):
        """Initialize ImageProcessor with analysis parameters.

        Args:
        ----
            analysis_mode: Analysis mode (e.g., "free_sedimentation", "contact_angle")
            threshold: Threshold value for image binarization
            pixel: Pixels per millimeter conversion factor
            rotate_angle: Angle to rotate images
            x_img: X coordinate for image cropping
            y_img: Y coordinate for image cropping
            w_img: Width for image cropping
            h_img: Height for image cropping
            polynom: Polynomial degree for curve fitting
            fitting_mode: Mode for contact angle fitting
            baseline: Baseline offset value
            baseline_tf: Baseline toggle flag
            manual_baseline: Manual baseline offset value

        """
        self.analysis_mode = analysis_mode
        self.threshold = threshold
        self.pixel = pixel
        self.rotate_angle = rotate_angle
        self.x_img = x_img
        self.y_img = y_img
        self.w_img = w_img
        self.h_img = h_img
        self.polynom = polynom
        self.fitting_mode = fitting_mode
        self.baseline = baseline
        self.baseline_tf = baseline_tf
        self.manual_baseline = manual_baseline

        # Temporary storage for structured packing mode
        self._vertical_left = None
        self._vertical_right = None

    def detect_baselines(
        self, files: list[str]
    ) -> tuple[float | None, float | None, tuple | None, tuple | None] | None:
        """Detect baselines for different analysis modes.

        Args:
        ----
            files: List of image files

        Returns:
        -------
            tuple: (y1_left, y1_right, vertical_left, vertical_right) or None

        """
        middle_index = len(files) // 2
        middle_file = files[middle_index]

        middle_src = safe_imread(middle_file)
        if middle_src is None:
            logger.error(
                f"Detection: Failed to load middle image file: "
                f"{os.path.basename(middle_file)}"
            )
            return None

        # Process middle image
        middle_src = self._process_middle_image_for_baseline(middle_src)
        if middle_src is None:
            return None

        # Detect baselines based on mode
        return self._detect_baselines_by_mode(middle_src)

    def _process_middle_image_for_baseline(self, middle_src):
        """Process middle image for baseline detection."""
        if middle_src is None:
            logger.error("Middle source image is None")
            return None

        # Apply rotation and cropping
        middle_src = rotate_image(middle_src, self.rotate_angle)
        middle_src = crop_image(
            middle_src, (self.x_img, self.w_img, self.y_img, self.h_img)
        )

        if middle_src is None or middle_src.size == 0:
            logger.error("Middle image became invalid after rotation/cropping")
            return None

        return middle_src

    def _detect_baselines_by_mode(self, middle_src):
        """Detect baselines based on analysis mode."""
        if self.analysis_mode == "structured_packing":
            return self._detect_structured_packing_lines(middle_src)
        elif self.analysis_mode == "free_sedimentation":
            return (None, None, None, None)
        else:
            return self._detect_single_baseline(middle_src)

    def _detect_structured_packing_lines(self, middle_src):
        """Detect vertical lines for structured packing mode."""
        vertical_left, vertical_right = find_vertical_lines(middle_src)
        if vertical_left is None or vertical_right is None:
            logger.error("Failed to detect vertical lines in structured_packing mode")
            return None
        # Store for later use
        self._vertical_left = vertical_left
        self._vertical_right = vertical_right
        return (0, 0, vertical_left, vertical_right)

    def _detect_single_baseline(self, middle_src):
        """Detect single baseline for standard modes."""
        try:
            # Crop to center 20% of image for better baseline detection
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
                return None

            y1_left, y1_right = find_single_baseline(
                middle_src_for_baseline,
                self.baseline,
                self.baseline_tf,
                self.manual_baseline,
            )

            if y1_left is None or y1_right is None:
                logger.error("Failed to detect baseline in middle image")
                return None

            if np.isnan(y1_left) or np.isnan(y1_right):
                logger.error("Detected baseline contains NaN values")
                return None

            logger.info(f"Detected baseline: y1_left={y1_left}, y1_right={y1_right}")
            return (y1_left, y1_right, None, None)
        except Exception as e:
            logger.error(f"Error finding baseline: {e}")
            return None

    def prepare_image(self, src, result_images: dict):
        """Prepare the image by rotation and cropping.

        Args:
        ----
            src: Source image array
            result_images: Dictionary to store processed images

        Returns:
        -------
            Processed image array

        """
        processed_img = rotate_image(src, self.rotate_angle)
        processed_img = crop_image(
            processed_img, (self.x_img, self.w_img, self.y_img, self.h_img)
        )
        # Always store original for preview and as fallback
        result_images["original"] = processed_img.copy()
        result_images["fallback"] = processed_img.copy()
        return processed_img

    def prepare_background(self, processed_img, background):
        """Ensure background image matches processed image dimensions.

        Args:
        ----
            processed_img: Processed image array
            background: Background image array

        Returns:
        -------
            Resized background image

        """
        src_h, src_w = processed_img.shape[:2]
        bg_h, bg_w = background.shape[:2]
        if bg_h != src_h or bg_w != src_w:
            background = cv2.resize(background, (src_w, src_h))
        return background

    def create_baseline_visualization(
        self, processed_img, y1_left, y1_right, result_images: dict
    ):
        """Create baseline visualization image.

        Args:
        ----
            processed_img: Processed image array
            y1_left: Left baseline y-coordinate
            y1_right: Right baseline y-coordinate
            result_images: Dictionary to store result images

        """
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

    def find_and_validate_contours(
        self,
        processed_img,
        background,
        result_images: dict,
        y1_left=None,
        y1_right=None,
        vertical_left=None,
        vertical_right=None,
    ):
        """Find and validate contours in the image.

        Args:
        ----
            processed_img: Processed image array
            background: Background image array
            result_images: Dictionary to store result images
            y1_left: Left baseline y-coordinate
            y1_right: Right baseline y-coordinate
            vertical_left: Left vertical line coordinates
            vertical_right: Right vertical line coordinates

        Returns:
        -------
            tuple: (largest_contour, vis_img)

        """
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
                    _x, _y, w, _h = cv2.boundingRect(contour)
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
            logger.error(f"Error in find_and_validate_contours: {e}")
            result_images["contour"] = vis_img.copy()
            result_images["fallback"] = vis_img.copy()
            return None, vis_img

    def calculate_robust_area(self, contour):
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

            # If area is very small or zero, use bounding box as fallback
            if area < 1.0:
                _, _, w, h = cv2.boundingRect(contour)
                area = float(w * h)
                logger.debug(f"Using bounding box area fallback: {area}")

            return area

        except Exception as e:
            logger.error(f"Error calculating contour area: {e}")
            return 0.0
