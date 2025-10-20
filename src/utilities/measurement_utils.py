"""Measurement utilities for Droplet Wall Interaction Tool (DWIT).

Consolidated module providing:
- Baseline detection utilities
- Structured packing edge detection
- Velocity calculations from center points
- Backwards-compatible re-exports for contact-angle helpers

This module centralises common measurement helpers used by the analysis
pipeline and GUI, and provides a stable, single-location API for legacy
imports that previously referenced separate baseline, packing, velocity,
or contact-angle helper modules.
"""

import cv2
import numpy as np

from src.analysis.contact_angle.arc_method import calculate_contact_angles
from src.analysis.contact_angle.ellipse_method import (
    calculate_contact_angle_left,
    calculate_contact_angle_right,
    calculate_ellipse_contact_angle,
)
from src.analysis.contact_angle.polynomial_method import (
    fit_left_polynomial,
    fit_right_polynomial,
    rotate_coordinates_90,
)
from src.analysis.contact_angle.tangent_method import calculate_tangent_contact_angles
from src.utilities.core_utils import get_logger

# Setup logger for this module
logger = get_logger(__name__)

__all__ = [
    "calculate_contact_angle_left",
    "calculate_contact_angle_right",
    "calculate_contact_angles",
    "calculate_ellipse_contact_angle",
    "calculate_tangent_contact_angles",
    "fit_left_polynomial",
    "fit_right_polynomial",
    "rotate_coordinates_90",
]

__all__ = ["calculate_velocities"]

__all__ = ["find_vertical_lines"]

__all__ = ["find_single_baseline"]


def find_single_baseline(image, baseline_offset=0, baseline_tf=False, manual_offset=0):
    """Enhanced function to detect the baseline where the droplet sits.

    Uses multiple detection strategies with automatic threshold determination.

    Args:
    ----
        image: Input image
        baseline_offset: Manual offset adjustment for baseline
        baseline_tf: If True, use manual offset only
        manual_offset: Manual offset value

    Returns:
    -------
        y1_left: Left side Y coordinate of baseline
        y1_right: Right side Y coordinate of baseline

    """
    img_h, _img_w = image.shape[:2]

    if baseline_tf:
        y1_left = img_h - manual_offset
        y1_right = y1_left
        logger.debug(
            f"Using manual baseline at y={y1_left} (manual_offset={manual_offset})"
        )
        return y1_left, y1_right
    else:
        logger.debug("Using automatic baseline detection")
        # Make a copy of the image for processing
        working_img = image.copy()
        height, width = working_img.shape[:2]

        try:
            # Apply pre-processing to enhance the baseline visibility
            gray = cv2.cvtColor(working_img, cv2.COLOR_BGR2GRAY)
            blurred = cv2.GaussianBlur(gray, (5, 5), 0)

            # Strategy 1: Edge detection with Canny using adaptive thresholds
            # Automatically determine thresholds based on image statistics
            median = np.median(blurred)
            sigma = 0.5  # Standard deviation for Canny thresholds
            threshold_min = int(max(0, (1.0 - sigma) * median))
            threshold_max = int(min(255, (1.0 + sigma) * median))

            edges = cv2.Canny(blurred, threshold_min, threshold_max)

            # Strategy 2: Use Hough Line Transform to find horizontal lines
            lines = cv2.HoughLinesP(
                edges,
                1,
                np.pi / 180,
                threshold=50,
                minLineLength=width // 4,
                maxLineGap=20,
            )

            baseline_candidates = []

            # Process detected lines
            if lines is not None:
                for line in lines:
                    x1, y1, x2, y2 = line[0]
                    # Filter for mostly horizontal lines (small slope)
                    if abs(y2 - y1) < height * 0.1:  # Allowing slight tilt
                        # Calculate score based on length and position
                        line_length = np.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)
                        position_score = 1.0 - (
                            min(y1, y2) / height
                        )  # Favor lines in lower half
                        score = line_length * position_score
                        baseline_candidates.append((x1, y1, x2, y2, score))
            else:
                logger.warning("No lines detected with Hough transform")

            # Select the best line if candidates exist
            if baseline_candidates:
                # Sort by score descending
                baseline_candidates.sort(key=lambda x: x[4], reverse=True)

                # Get best candidate
                x1, y1, x2, y2, score = baseline_candidates[0]

                # Return baseline coordinates with offset
                y1_left = int(y1) - baseline_offset
                y1_right = int(y2) - baseline_offset
                logger.debug(f"Detected baseline: left={y1_left}, right={y1_right}")

                return y1_left, y1_right
            else:
                logger.warning("No valid baseline candidates found, returning None")
                return None, None

        except Exception as e:
            logger.error(f"Error during baseline detection: {e}")
            return None, None


def find_vertical_lines(image):
    """Find two vertical lines representing the edges of a structured packing.

    The packing is expected to be a dark object in the middle with white background.
    Lines are placed exactly at the leftmost and rightmost points of the detected object
    plus 1 pixel offset (outside the object).

    Args:
    ----
        image: Input image
        threshold: Threshold value for binary conversion

    Returns:
    -------
        tuple: ((x1_left, y1_left),
                (x1_right, y1_right))
                coordinates of the left and right vertical lines

    """
    logger.debug(f"Input image shape: {image.shape}")
    # Convert to grayscale if it's color
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image

    # Apply Gaussian blur to reduce noise
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)

    # Apply threshold to highlight the dark packing against white background
    _, binary = cv2.threshold(blurred, 50, 255, cv2.THRESH_BINARY_INV)

    # Find contours of the dark packing
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    # If no contours found, return None
    if not contours:
        logger.warning("No contours found in image")
        return None, None

    # Find the largest contour (should be the structured packing)
    try:
        largest_contour = max(contours, key=cv2.contourArea)
        logger.debug(f"Largest contour has {len(largest_contour)} points")

        # Use OpenCV's built-in function to find extreme points
        leftmost = tuple(largest_contour[largest_contour[:, :, 0].argmin()][0])
        rightmost = tuple(largest_contour[largest_contour[:, :, 0].argmax()][0])

        # Extract x-coordinates
        leftmost_x = leftmost[0]
        rightmost_x = rightmost[0]

        # Add offset - SUBTRACT 1 pixel from left edge (move outside)
        # and ADD 1 pixel to right edge, but keep within image bounds
        left_edge_x = max(0, leftmost_x - 1)  # Ensure >= 0
        right_edge_x = min(image.shape[1] - 1, rightmost_x + 1)  # Ensure < width

        # The vertical lines go from top to bottom of the image
        # Convert to regular Python integers to avoid numpy type issues
        left_line = (int(left_edge_x), 0, int(left_edge_x), image.shape[0])
        right_line = (int(right_edge_x), 0, int(right_edge_x), image.shape[0])

        logger.debug(
            f"Successfully found vertical lines: left={left_line}, right={right_line}"
        )
        return left_line, right_line

    except Exception as e:
        logger.error(f"Failed to find vertical lines: {e}")
        return None, None


def _validate_inputs(center_points_px, pixel, fps, time_values, velocities):
    """Validate and prepare input parameters.

    Args:
    ----
        center_points_px: List of center points
        pixel: Pixels per mm conversion factor
        fps: Frames per second
        time_values: Optional list of timestamps
        velocities: Optional existing velocity list

    Returns:
    -------
        Tuple of validated (pixel, fps, time_values, velocities)

    """
    # Initialize velocities if needed
    if velocities is None:
        velocities = [0.0]  # First velocity is always 0
    elif len(velocities) == 0:
        velocities.append(0.0)

    # Ensure pixel value is valid to avoid division by zero
    if pixel is None or pixel <= 0:
        logger.warning(f"Invalid pixel value ({pixel}), using default 1.0")
        pixel = 1.0

    # If no time values provided, generate them based on fps
    if time_values is None or len(time_values) < len(center_points_px):
        # Ensure fps is valid
        if fps is None or fps <= 0:
            logger.warning(f"Invalid fps value ({fps}), using default 1.0")
            fps = 1.0
        time_values = [i / fps for i in range(len(center_points_px))]

    return pixel, fps, time_values, velocities


def _normalize_points(center_points_px):
    """Normalize center points to ensure they're all valid coordinate pairs.

    Args:
    ----
        center_points_px: List of center points in various formats

    Returns:
    -------
        List of normalized center points

    """
    normalized_points = []
    nan_count = 0

    for i, point in enumerate(center_points_px):
        # Handle None values
        if point is None:
            normalized_points.append([float("NaN"), float("NaN")])
            nan_count += 1
        # Handle correct list/tuple format
        elif isinstance(point, list | tuple) and len(point) >= 2:
            # Check if the values in the list are valid numbers
            if all(
                isinstance(v, int | float)
                and not (isinstance(v, float) and np.isnan(v))
                for v in point[:2]
            ):
                normalized_points.append(point)
            else:
                normalized_points.append([float("NaN"), float("NaN")])
                nan_count += 1
        # Handle scalar nan values (catches both float nan and np.nan)
        elif (
            (isinstance(point, float) and np.isnan(point))
            or (np.isscalar(point) and np.isnan(point))
            or np.isscalar(point)
        ):
            normalized_points.append([float("NaN"), float("NaN")])
            nan_count += 1
        else:
            # Any other unexpected format
            normalized_points.append([float("NaN"), float("NaN")])
            nan_count += 1
    if nan_count > 0:
        logger.warning(
            f"Found {nan_count} invalid/NaN points out of "
            f"{len(center_points_px)} total points"
        )

    return normalized_points


def _calculate_point_velocity(prev_point, curr_point, pixel, time_diff):
    """Calculate velocity between two points.

    Args:
    ----
        prev_point: Previous center point coordinates
        curr_point: Current center point coordinates
        pixel: Pixels per mm conversion factor
        time_diff: Time difference between frames

    Returns:
    -------
        Calculated velocity or NaN if calculation not possible

    """
    # Ensure points are valid and have numeric coordinates
    if (
        prev_point is None
        or curr_point is None
        or len(prev_point) < 2
        or len(curr_point) < 2
        or prev_point[0] is None
        or prev_point[1] is None
        or curr_point[0] is None
        or curr_point[1] is None
        or np.isnan(prev_point[0])
        or np.isnan(prev_point[1])
        or np.isnan(curr_point[0])
        or np.isnan(curr_point[1])
    ):
        return float("NaN")

    # Calculate displacement
    dx_pixels = curr_point[0] - prev_point[0]
    dy_pixels = curr_point[1] - prev_point[1]

    # Calculate total displacement (2D)
    displacement = np.sqrt(dx_pixels**2 + dy_pixels**2)

    # Convert to mm/s (using safe division)
    velocity = (displacement / max(1.0, pixel)) / time_diff
    velocity = round(velocity, 2)

    return velocity


def _ensure_complete_velocity_list(velocities, target_length):
    """Ensure velocity list matches the required length.

    Args:
    ----
        velocities: Current list of velocities
        target_length: Required length for the velocity list

    Returns:
    -------
        Complete velocity list with added NaN values if needed

    """
    if len(velocities) < target_length:
        # Fill any missing values with NaN
        missing_count = target_length - len(velocities)
        logger.warning(f"Missing {missing_count} velocity values, filling with NaN")
        velocities.extend([float("NaN")] * missing_count)

    return velocities


def calculate_velocities(
    center_points_px, pixel=None, fps=None, time_values=None, velocities=None
):
    """Calculate velocities from center points.

    Args:
    ----
        center_points_px: list of center points in pixels
        pixel: Pixels per mm conversion factor
        fps: Frames per second (used when time_values not provided)
        time_values: Optional list of timestamps for each frame
        velocities: Optional pre-existing velocity list to append to

    Returns:
    -------
        list of velocities in mm/s

    """
    logger.info(
        f"Starting velocity calculation with "
        f"{len(center_points_px) if center_points_px else 0} points, "
        f"pixel={pixel}, fps={fps}"
    )

    # Ensure we have valid input data
    if not center_points_px or len(center_points_px) < 2:
        logger.warning(
            f"Insufficient center points for velocity calculation: "
            f"{len(center_points_px) if center_points_px else 0} points"
        )
        result = [float("NaN")] * (len(center_points_px) if center_points_px else 1)
        return result

    # Validate and prepare inputs
    pixel, fps, time_values, velocities = _validate_inputs(
        center_points_px, pixel, fps, time_values, velocities
    )

    # Normalize the center_points_px to ensure they're all coordinate pairs
    center_points_px = _normalize_points(center_points_px)

    # Calculate velocities
    for i in range(1, len(center_points_px)):
        # Get centers from current and previous frames
        prev_point = center_points_px[i - 1]
        curr_point = center_points_px[i]

        # Calculate time difference
        time_diff = (
            time_values[i] - time_values[i - 1] if i < len(time_values) else 1.0 / fps
        )

        # Avoid division by zero
        if abs(time_diff) < 1e-10:
            logger.warning(
                f"Frame {i}: Time difference too small ({time_diff}), "
                f"setting velocity to NaN"
            )
            velocities.append(float("NaN"))
            continue

        try:
            velocity = _calculate_point_velocity(
                prev_point, curr_point, pixel, time_diff
            )
            velocities.append(velocity)
        except (TypeError, IndexError) as e:
            # Handle any unexpected errors during calculation
            logger.error(f"Frame {i}: Error calculating velocity: {e}")
            velocities.append(float("NaN"))

    # Make sure we have the right number of velocities
    velocities = _ensure_complete_velocity_list(velocities, len(center_points_px))

    logger.info(
        f"Velocity calculation complete: {len(velocities)} velocities calculated"
    )

    return velocities
