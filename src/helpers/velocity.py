"""Velocity calculation utilities.

For experiment analysis in Droplet Wall Interaction Tool.
"""

import numpy as np

from src.utilities.logging_manager import get_logger

# Setup logger for this module
logger = get_logger(__name__)


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
        elif isinstance(point, (list, tuple)) and len(point) >= 2:
            # Check if the values in the list are valid numbers
            if all(
                isinstance(v, (int, float))
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
