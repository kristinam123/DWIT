"""Intersection and geometry utilities for contour analysis in MesszelleApp."""

import cv2
import numpy as np

from src.utilities.logging_manager import get_logger

# Setup logger for this module
logger = get_logger(__name__)


def find_intersection_points(
    y1_left, y1_right, src, threshold=50, q=0, contours=None, pixel=1.0
):
    """Find intersection points between baseline and droplet.

    Uses the contours that have already been detected.

    Args:
    ----
        y1_left: Y-coordinate of the left baseline point.
        y1_right: Y-coordinate of the right baseline point.
        src: Source image for processing.
        threshold: Threshold value for processing (default: 50).
        q: Quality parameter (default: 0).
        contours: Pre-detected contours (default: None).
        pixel: Pixel scaling factor (default: 1.0).

    Returns:
    -------
        tuple of (intersection_points, img, cnt, xsp1, xsp2,
                 shifted_points, shifted_x, shifted_y)

    """
    logger.debug(f"Params: y1_left={y1_left}, y1_right={y1_right}, threshold={threshold}, pixel={pixel}, contours_provided={contours is not None}")

    # Validate input and setup visualization
    vis_img, baseline_y, dimensions = _setup_intersection_analysis(
        src, y1_left, y1_right
    )
    if vis_img is None:
        return [], None, None, [], [], []

    h, w = dimensions

    # Get or detect contours
    contours = _get_or_detect_contours(src, contours, threshold, pixel)
    if (
        contours is None
        or (hasattr(contours, "size") and contours.size == 0)
        or (hasattr(contours, "__len__") and len(contours) == 0)
    ):
        return [], vis_img, None, [], [], []

    # Find intersection points with the baseline
    left_x, right_x, largest_contour = _find_baseline_intersections(
        contours, baseline_y, vis_img
    )
    if left_x is None or right_x is None:
        return [], vis_img, None, [], [], []

    # Create final intersection points and visualization
    intersection_points = _create_intersection_points(
        left_x, right_x, baseline_y, vis_img
    )

    # Calculate shifted points for tangent lines
    shifted_points, shifted_x, shifted_y = _calculate_shifted_points(
        intersection_points, largest_contour, baseline_y, vis_img, w
    )

    # Return results
    cnt = None
    if contours is not None:
        if hasattr(contours, "size"):
            if contours.size > 0:
                cnt = contours[0]
        elif hasattr(contours, "__len__") and len(contours) > 0:
            cnt = contours[0]
    logger.debug(
        f"Intersection analysis complete: "
        f"{len(intersection_points)} intersection points, "
        f"{len(shifted_points)} shifted points"
    )
    return intersection_points, vis_img, cnt, shifted_points, shifted_x, shifted_y


def _setup_intersection_analysis(src, y1_left, y1_right):
    """Set up intersection analysis with input validation and baseline calculation."""
    # Create visualization image
    vis_img = src.copy() if src is not None else None

    # Handle invalid input
    if src is None or y1_left is None or y1_right is None:
        return None, None, None

    # Get image dimensions
    h, w = src.shape[:2]

    # Calculate baseline y position
    baseline_y = (
        int((y1_left + y1_right) / 2)
        if y1_left is not None and y1_right is not None
        else h // 2
    )

    # Draw baseline
    cv2.line(vis_img, (0, baseline_y), (w, baseline_y), (0, 0, 255), 2)

    return vis_img, baseline_y, (h, w)


def _get_or_detect_contours(src, contours, threshold, pixel):
    """Get existing contours or detect new ones from the image."""
    if contours is not None:
        return contours
    return _detect_contours_from_image(src, threshold, pixel)


def _detect_contours_from_image(src, threshold, pixel):
    """Detect and filter contours from the image."""
    # Process the image to find contours
    gray = cv2.cvtColor(src, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    _, thresh = cv2.threshold(blur, threshold, 255, cv2.THRESH_BINARY)

    # Add morphological operations to clean up the binary image
    kernel = np.ones((1, 1), np.uint8)
    component_mask = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)
    all_contours, _ = cv2.findContours(
        component_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )

    # Filter contours based on drop width constraints
    return _filter_contours_by_size(all_contours, pixel)


def _filter_contours_by_size(all_contours, pixel):
    """Filter contours based on drop width constraints (1-7mm)."""
    valid_contours = []
    for i, contour in enumerate(all_contours):
        x, y, w, h = cv2.boundingRect(contour)
        width_mm = w / pixel if pixel > 0 else w

        # Filter contours based on width constraints - drops should be 1-7mm wide
        if 1.0 <= width_mm <= 7.0:
            valid_contours.append(contour)

    if valid_contours:
        logger.info(f"Using {len(valid_contours)} valid contours")
        return valid_contours
    else:
        logger.warning("No valid contours found after filtering")
        return []


def _find_baseline_intersections(contours, baseline_y, vis_img):
    """Find intersection points between the largest contour and baseline."""
    if (
        contours is None
        or (hasattr(contours, "size") and contours.size == 0)
        or (hasattr(contours, "__len__") and len(contours) == 0)
    ):
        logger.warning("No contours available for intersection analysis")
        return None, None, None

    # Get the largest contour
    largest_contour = (
        max(contours, key=cv2.contourArea) if isinstance(contours, list) else contours
    )

    # Draw the contour for visualization
    cv2.drawContours(vis_img, [largest_contour], 0, (0, 255, 0), 2)

    # Convert contour to manageable format and find intersections
    contour_points = largest_contour.reshape(-1, 2)
    left_x, right_x = _find_intersection_coordinates(contour_points, baseline_y)

    return left_x, right_x, largest_contour


def _find_intersection_coordinates(contour_points, baseline_y):
    """Find the left and right intersection coordinates with the baseline."""
    epsilon = 2  # Tolerance in pixels for proximity to baseline

    # Find points that are close to the baseline
    near_baseline_points = [
        pt for pt in contour_points if abs(pt[1] - baseline_y) < epsilon
    ]

    if near_baseline_points is not None and len(near_baseline_points) > 0:
        near_baseline_points.sort(key=lambda pt: pt[0])
        return _process_baseline_proximity_points(
            near_baseline_points, contour_points, baseline_y
        )

    # Fallback method if no points found near baseline
    return _fallback_intersection_method(contour_points, baseline_y)


def _process_baseline_proximity_points(
    near_baseline_points, contour_points, baseline_y
):
    """Process points found near the baseline to determine intersections."""
    if len(near_baseline_points) >= 2:
        left_x = near_baseline_points[0][0]
        right_x = near_baseline_points[-1][0]
        return left_x, right_x
    elif len(near_baseline_points) == 1:
        left_x = near_baseline_points[0][0]
        right_x = _find_baseline_crossings(contour_points, baseline_y, left_x)
        return left_x, right_x

    return None, None


def _find_baseline_crossings(contour_points, baseline_y, left_x):
    """Find baseline crossings when only one proximity point exists."""
    crossings = []
    for i in range(len(contour_points) - 1):
        pt1 = contour_points[i]
        pt2 = contour_points[i + 1]

        # Check if the line segment crosses the baseline
        if (
            (pt1[1] <= baseline_y and pt2[1] >= baseline_y)
            or (pt1[1] >= baseline_y and pt2[1] <= baseline_y)
        ) and (
            pt2[1] != pt1[1]
        ):  # Avoid division by zero
            # Calculate x at intersection using line equation
            t = (baseline_y - pt1[1]) / (pt2[1] - pt1[1])
            x_intersect = pt1[0] + t * (pt2[0] - pt1[0])
            crossings.append(x_intersect)

    if crossings and len(crossings) > 1:
        crossings.sort()
        # Find the crossing that's furthest from left_x
        distances = [abs(x - left_x) for x in crossings]
        furthest_idx = distances.index(max(distances))
        right_x = crossings[furthest_idx]
        return right_x

    return None


def _fallback_intersection_method(contour_points, baseline_y):
    """Fallback method: project contour points onto baseline."""
    x_values = contour_points[:, 0]
    y_values = contour_points[:, 1]

    # Find contour points below baseline
    below_baseline = y_values >= baseline_y
    if np.any(below_baseline):
        x_below = x_values[below_baseline]
        if len(x_below) > 0:
            left_x = np.min(x_below)
            right_x = np.max(x_below)

            # Check if points are too close together
            if abs(right_x - left_x) >= 10:
                return left_x, right_x

    return None, None


def _create_intersection_points(left_x, right_x, baseline_y, vis_img):
    """Create and visualize the final intersection points."""
    logger.info(
        f"Successfully found intersection points: "
        f"left_x={int(left_x)}, right_x={int(right_x)}"
    )

    # Mark intersection points
    intersection_points = [(int(left_x), baseline_y), (int(right_x), baseline_y)]
    for i, point in enumerate(intersection_points):
        cv2.circle(vis_img, point, 5, (255, 0, 0), -1)

    return intersection_points


def _calculate_shifted_points(intersection_points, cnt, baseline_y, vis_img, w):
    """Calculate shifted points for tangent lines."""
    shifted_points = []
    shifted_x, shifted_y = [], []

    if cnt is None:
        return shifted_points, shifted_x, shifted_y

    contour_points = cnt.reshape(-1, 2)

    for i, point in enumerate(intersection_points):
        x, y = point
        shift_y = _calculate_shift_distance(cnt, baseline_y, i)
        y_shifted = y - shift_y

        best_x = _find_best_shifted_x(contour_points, x, y_shifted, i, w)

        # Draw the shifted point
        cv2.circle(vis_img, (int(best_x), y_shifted), 3, (0, 255, 255), -1)

        shifted_points.append((int(best_x), y_shifted))
        shifted_x.append(int(best_x))
        shifted_y.append(y_shifted)

    return shifted_points, shifted_x, shifted_y


def _calculate_shift_distance(cnt, baseline_y, point_index):
    """Calculate the shift distance based on contour size."""
    # Handle different contour formats (2D or 3D array)
    y_min = np.min(cnt[:, 0, 1]) if len(cnt.shape) == 3 else np.min(cnt[:, 1])

    contour_height = baseline_y - y_min if y_min < baseline_y else 0

    # Adaptive shift based on contour dimensions
    shift_y = max(5, min(20, int(contour_height * 0.2)))
    return shift_y


def _find_best_shifted_x(contour_points, x, y_shifted, point_index, w):
    """Find the best x coordinate for the shifted point."""
    best_x = x
    min_dist = float("inf")

    # Search through contour points to find the best match
    for cx, cy in contour_points:
        if abs(cy - y_shifted) < 3:  # Close to our target height
            dist = abs(cx - x)
            if dist < min_dist:
                min_dist = dist
                best_x = cx

    # If we couldn't find a good point, try interpolation
    if min_dist == float("inf"):
        best_x = _interpolate_shifted_x(contour_points, x, y_shifted, point_index)

    # Add slight adjustment based on which side we're on
    return max(0, best_x - 1) if point_index == 0 else min(w - 1, best_x + 1)


def _interpolate_shifted_x(contour_points, x, y_shifted, point_index):
    """Interpolate x coordinate when no close contour point is found."""
    # Find points above and below our target y
    points_above = [(cx, cy) for cx, cy in contour_points if cy < y_shifted]
    points_below = [(cx, cy) for cx, cy in contour_points if cy > y_shifted]

    # Sort by distance to target y
    points_above.sort(key=lambda p: abs(p[1] - y_shifted))
    points_below.sort(key=lambda p: abs(p[1] - y_shifted))

    # If we have points both above and below, interpolate
    if points_above and points_below:
        p_above = points_above[0]
        p_below = points_below[0]

        # Linear interpolation
        if p_below[1] != p_above[1]:  # Avoid division by zero
            t = (y_shifted - p_above[1]) / (p_below[1] - p_above[1])
            best_x = p_above[0] + t * (p_below[0] - p_above[0])
            return best_x

    return x  # Return original x if interpolation fails
