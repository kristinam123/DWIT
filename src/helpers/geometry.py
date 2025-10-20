"""Contour analysis and filtering utilities for Droplet Wall Interaction Tool.

This module provides utilities for contour analysis, including intersection
and geometry calculations.
"""

import cv2
import numpy as np

from src.utilities.core_utils import get_logger

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
    logger.debug(
        f"Params: y1_left={y1_left}, "
        f"y1_right={y1_right}, "
        f"threshold={threshold}, "
        f"pixel={pixel}, "
        f"contours_provided={contours is not None}"
    )

    # Validate input and setup visualization
    vis_img, baseline_y, dimensions = _setup_intersection_analysis(
        src, y1_left, y1_right
    )
    if vis_img is None:
        return [], None, None, [], [], []

    _h, w = dimensions

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
        _x, _y, w, _h = cv2.boundingRect(contour)
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


def _calculate_center_point(cnt, h, w, line_y, pixel):
    """Calculate center point from contour.

    Args:
    ----
        cnt: Contour data
        h: Image height
        w: Image width
        line_y: Y-coordinate of the baseline
        pixel: Pixels per mm conversion factor

    Returns:
    -------
        tuple of (center_point_px, center_point_mm)

    """
    cx, cy = None, None

    # Use contour moments if we have a valid contour
    if cnt is not None and len(cnt) > 0:
        try:
            cnt_largest = cnt[0] if isinstance(cnt, list) and len(cnt) > 0 else cnt
            moment = cv2.moments(cnt_largest)
            if moment["m00"] != 0:
                cx = int(moment["m10"] / moment["m00"])
                cy = int(moment["m01"] / moment["m00"])
            else:
                logger.warning("Contour moments calculation failed: m00 is zero")
        except Exception as e:
            logger.error(f"Error calculating contour moments: {e}")

    # Return center points - ensure they are always numbers, not None
    center_point_px = [
        cx if cx is not None else float("nan"),
        cy if cy is not None else float("nan"),
    ]
    if cx is not None and cy is not None and pixel > 0:
        center_point_mm = [cx / pixel, cy / pixel]
        logger.debug(f"Center point: {center_point_px} px = {center_point_mm} mm")
    else:
        center_point_mm = [float("nan"), float("nan")]
        logger.warning("Could not calculate valid center point in mm")

    return center_point_px, center_point_mm


def _visualize_center_point(img, cx, cy, line_y, w):
    """Draw center point and baseline on image.

    Args:
    ----
        img: Image to draw on
        cx: Center point x-coordinate
        cy: Center point y-coordinate
        line_y: Y-coordinate of the baseline
        w: Image width

    Returns:
    -------
        Visualized image

    """
    if img is None or cx is None or cy is None:
        return img

    # Check for NaN values before converting to int
    if isinstance(cx, float) and np.isnan(cx):
        logger.warning("Center x-coordinate is NaN, skipping visualization")
        return img
    if isinstance(cy, float) and np.isnan(cy):
        logger.warning("Center y-coordinate is NaN, skipping visualization")
        return img

    img_copy = img.copy()
    cv2.circle(img_copy, (int(cx), int(cy)), 5, (0, 0, 255), -1)
    cv2.line(img_copy, (0, line_y), (w - 1, line_y), (0, 0, 255), 2)

    return img_copy


def _calculate_area_between_intersections(
    img_copy, cnt, intersection_points, line_y, width
):
    """Calculate and visualize area between intersection points.

    Args:
    ----
        img_copy: Image to draw on
        cnt: Contour data
        intersection_points: Detected intersection points
        line_y: Y-coordinate of the baseline
        width: Image width

    Returns:
    -------
        tuple of (visualized image, area lines drawn)

    """
    if intersection_points is None or len(intersection_points) < 2:
        return img_copy, 0

    # Find start and end columns for area calculation
    start_column = min(p[0] for p in intersection_points if p is not None)
    end_column = max(p[0] for p in intersection_points if p is not None)

    # Calculate area for columns between intersection points
    area_lines_drawn = 0
    for x in range(start_column, end_column + 1):
        if x > 5 and x < width - 5:
            points_in_column = [point[0] for point in cnt if point[0][0] == x]
            if not points_in_column:
                continue

            lowest_point = min(points_in_column, key=lambda point: point[1])
            cv2.line(
                img_copy,
                (lowest_point[0], lowest_point[1]),
                (lowest_point[0], line_y),
                (0, 255, 0),
                thickness=1,
            )
            area_lines_drawn += 1
    return img_copy, area_lines_drawn


def _calculate_left_extension_area(img_copy, cnt, intersection_points, line_y, width):
    """Calculate and visualize left extension area.

    Args:
    ----
        img_copy: Image to draw on
        cnt: Contour data
        intersection_points: Detected intersection points
        line_y: Y-coordinate of the baseline
        width: Image width

    Returns:
    -------
        tuple of (visualized image, extension lines drawn)

    """
    if intersection_points is None or len(intersection_points) < 2:
        return img_copy, 0

    # Find start column for left extension
    start_column = min(p[0] for p in intersection_points if p is not None)
    start_column_contour = max(0, start_column - 50)

    # Calculate area for left extension
    left_extension_lines = 0
    for x in range(start_column_contour, start_column + 1):
        if x > 5 and x < width - 5:
            points_in_column_over_base_line = [
                point[0] for point in cnt if point[0][0] == x and point[0][1] < line_y
            ]
            if not points_in_column_over_base_line:
                continue

            lowest_point_contour = min(
                points_in_column_over_base_line, key=lambda point: point[1]
            )
            highest_point_contour = max(
                points_in_column_over_base_line, key=lambda point: point[1]
            )
            cv2.line(
                img_copy,
                (lowest_point_contour[0], lowest_point_contour[1]),
                (highest_point_contour[0], highest_point_contour[1]),
                (0, 255, 0),
                thickness=1,
            )
            left_extension_lines += 1
    return img_copy, left_extension_lines


def _calculate_right_extension_area(img_copy, cnt, intersection_points, line_y, width):
    """Calculate and visualize right extension area.

    Args:
    ----
        img_copy: Image to draw on
        cnt: Contour data
        intersection_points: Detected intersection points
        line_y: Y-coordinate of the baseline
        width: Image width

    Returns:
    -------
        tuple of (visualized image, extension lines drawn)

    """
    if intersection_points is None or len(intersection_points) < 2:
        return img_copy, 0

    # Find end column for right extension
    end_column = max(p[0] for p in intersection_points if p is not None)
    end_column_contour = min(width, end_column + 50)

    # Calculate area for right extension
    right_extension_lines = 0
    for x in range(end_column, end_column_contour + 1):
        if x > 5 and x < width - 5:
            points_in_column_over_base_line = [
                point[0] for point in cnt if point[0][0] == x and point[0][1] < line_y
            ]
            if not points_in_column_over_base_line:
                continue

            lowest_point_contour = min(
                points_in_column_over_base_line, key=lambda point: point[1]
            )
            highest_point_contour = max(
                points_in_column_over_base_line, key=lambda point: point[1]
            )
            cv2.line(
                img_copy,
                (lowest_point_contour[0], lowest_point_contour[1]),
                (highest_point_contour[0], highest_point_contour[1]),
                (0, 255, 0),
                thickness=1,
            )
            right_extension_lines += 1
    return img_copy, right_extension_lines


def calculate_drop_area(
    y1_left,
    y1_right,
    intersection_points,
    cnt,
    img,
    center_points_px,
    center_points_mm,
    q,
    result_images,
    result_lists,
    pixel,
):
    """Process drop area and find center point.

    Args:
    ----
        y1_left: Left baseline y-coordinate
        y1_right: Right baseline y-coordinate
        intersection_points: Detected intersection points
        cnt: Contour data
        img: Processed image
        center_points_px: list of center points (in pixels)
        center_points_mm: list of center points (in mm)
        q: Current image index
        result_images: Dictionary to store result images
        result_lists: Dictionary to store analysis results
        pixel: Pixels per mm conversion factor

    Returns:
    -------
        Center point in pixels and mm

    """
    logger.debug(
        f"Params: y1_left={y1_left}, y1_right={y1_right}, "
        f"intersection_points={intersection_points}, pixel={pixel}"
    )

    # Create a copy of the image for visualization
    img_copy = img.copy() if img is not None else None

    # Get image dimensions
    h, w = img.shape[:2] if img is not None else (100, 100)

    # Calculate baseline center line
    line_y = (
        round((y1_left + y1_right) / 2)
        if y1_left is not None and y1_right is not None
        else h // 2
    )

    # Calculate center point
    center_point_px, center_point_mm = _calculate_center_point(cnt, h, w, line_y, pixel)

    # Store in result_lists
    if result_lists is not None and isinstance(result_lists, dict):
        result_lists["center_point"] = center_point_px

    # Visualize center point
    if (
        img_copy is not None
        and center_point_px[0] is not None
        and center_point_px[1] is not None
    ):
        img_copy = _visualize_center_point(
            img_copy, center_point_px[0], center_point_px[1], line_y, w
        )
        result_images["drop_area"] = img_copy

    # Calculate area if we have valid intersection points and contour
    if (
        intersection_points is not None
        and len(intersection_points) >= 2
        and cnt is not None
        and len(cnt) > 0
        and img_copy is not None
    ):
        logger.info("Calculating drop area between intersection points")

        # Calculate area between intersection points
        img_copy, area_lines = _calculate_area_between_intersections(
            img_copy, cnt, intersection_points, line_y, w
        )

        # Calculate left extension area
        img_copy, left_lines = _calculate_left_extension_area(
            img_copy, cnt, intersection_points, line_y, w
        )

        # Calculate right extension area
        img_copy, right_lines = _calculate_right_extension_area(
            img_copy, cnt, intersection_points, line_y, w
        )

        logger.info(
            f"Area visualization complete: "
            f"{area_lines + left_lines + right_lines} total lines"
        )

        # Update result images
        result_images["drop_area"] = img_copy

    # Return center points
    logger.info(f"Drop area calculation complete: center={center_point_px} px")
    return [center_point_px], [center_point_mm]


def process_contour(
    contour,
    cnt_x,
    cnt_y,
    x_left_cnt,
    y_left_cnt,
    x_right_cnt,
    y_right_cnt,
    line_y,
    cnt_x_neu,
    cnt_y_neu,
    q=0,
):
    """Process contour to find mean X value and left/right contour points.

    Args:
    ----
        contour: Contour array
        cnt_x: list to store contour x-coordinates
        cnt_y: list to store contour y-coordinates
        x_left_cnt: list to store left contour x-coordinates
        y_left_cnt: list to store left contour y-coordinates
        x_right_cnt: list to store right contour x-coordinates
        y_right_cnt: list to store right contour y-coordinates
        line_y: Y-coordinate of the baseline
        cnt_x_neu: list to store processed contour x-coordinates
        cnt_y_neu: list to store processed contour y-coordinates
        q: Current image index (default: 0)

    Returns:
    -------
        tuple of (x_mean, x_left_cnt, y_left_cnt, x_right_cnt, y_right_cnt)

    """
    logger.debug(
        f"Params: contour_len="
        f"{len(contour) if hasattr(contour, '__len__') else 'unknown'}, "
        f"line_y={line_y}"
    )

    # Handle missing contour
    if contour is None or len(contour) == 0:
        logger.warning("No contour provided for processing")
        return 0, x_left_cnt, y_left_cnt, x_right_cnt, y_right_cnt

    try:
        # Extract contour points
        if hasattr(contour, "shape") and len(contour.shape) > 1:
            contour_points = contour.reshape(-1, 2)
        else:
            # Handle case where contour is already flat or in different format
            contour_points = np.array(contour)
            if len(contour_points.shape) == 3 and contour_points.shape[1] == 1:
                contour_points = contour_points.reshape(-1, 2)

        # Process contour coordinates
        xs = contour_points[:, 0]
        ys = contour_points[:, 1]

        # Add to tracking lists
        cnt_x.extend(xs)
        cnt_y.extend(ys)

        # Calculate mean x position
        x_mean = np.mean(xs) if len(xs) > 0 else 0

        # Separate left and right points
        for x, y in zip(xs, ys):
            if x < x_mean:
                x_left_cnt.append(x)
                y_left_cnt.append(y)
            else:
                x_right_cnt.append(x)
                y_right_cnt.append(y)

        # Add points near baseline to special lists
        if line_y is not None:
            for x, y in zip(xs, ys):
                if abs(y - line_y) < 10:  # Points within 10px of baseline
                    cnt_x_neu.append(x)
                    cnt_y_neu.append(y)

        return x_mean, x_left_cnt, y_left_cnt, x_right_cnt, y_right_cnt

    except Exception as e:
        logger.error(f"Error processing contour: {e}")
        return 0, x_left_cnt, y_left_cnt, x_right_cnt, y_right_cnt


def _prepare_contour_points(contour):
    """Convert contour to a manageable format.

    Args:
    ----
        contour: The input contour in various possible formats

    Returns:
    -------
        tuple of (contour_points, original_shape)

    """
    if contour is None or len(contour) == 0:
        return None, None

    # Convert contour to a manageable format
    if hasattr(contour, "shape") and len(contour.shape) > 1:
        if len(contour.shape) == 3:  # OpenCV's findContours default format [n, 1, 2]
            contour_points = contour.reshape(-1, 2)
            original_shape = contour.shape
        else:
            contour_points = contour
            original_shape = None
    else:
        # Handle case where contour is already in different format
        contour_points = np.array(contour)
        if len(contour_points.shape) == 3 and contour_points.shape[1] == 1:
            contour_points = contour_points.reshape(-1, 2)
            original_shape = contour_points.shape
        else:
            original_shape = None

    return contour_points, original_shape


def _calculate_baseline_slope(contour_points, y1_left, y1_right):
    """Calculate baseline slope and related parameters.

    Args:
    ----
        contour_points: Contour points in 2D array format
        y1_left: Y-coordinate at the leftmost point of the baseline
        y1_right: Y-coordinate at the rightmost point of the baseline

    Returns:
    -------
        tuple of (x_min, x_max, slope) or None if calculation isn't possible

    """
    # Get the min and max x coordinates
    x_min = np.min(contour_points[:, 0])
    x_max = np.max(contour_points[:, 0])

    # If x_min and x_max are the same, we can't define a slope
    if x_min == x_max:
        return None

    # Calculate the slope of the baseline
    slope = (y1_right - y1_left) / (x_max - x_min)

    return x_min, x_max, slope


def _calculate_baseline_y(x, x_min, slope, y1_left):
    """Calculate the y-coordinate on the baseline for a given x-coordinate.

    Args:
    ----
        x: X-coordinate
        x_min: Minimum x-coordinate of the contour
        slope: Slope of the baseline
        y1_left: Y-coordinate at the leftmost point of the baseline

    Returns:
    -------
        Y-coordinate on the baseline

    """
    return slope * (x - x_min) + y1_left


def _calculate_intersection_point(p1, p2, x_min, slope, y1_left):
    """Calculate intersection point between a line segment and the baseline.

    Args:
    ----
        p1: First point of the segment (x1, y1)
        p2: Second point of the segment (x2, y2)
        x_min: Minimum x-coordinate of the contour
        slope: Slope of the baseline
        y1_left: Y-coordinate at the leftmost point of the baseline

    Returns:
    -------
        Intersection point or None if no intersection exists

    """
    x1, y1 = p1
    x2, y2 = p2

    # Calculate baseline y at these x-coordinates
    y1_base = _calculate_baseline_y(x1, x_min, slope, y1_left)
    y2_base = _calculate_baseline_y(x2, x_min, slope, y1_left)

    # Check if points are above the baseline
    p1_above = y1 < y1_base
    p2_above = y2 < y2_base

    # Only calculate intersection if the segment crosses the baseline
    if p1_above == p2_above:
        return None, p1_above, p2_above  # No intersection

    # Handle vertical segments separately
    if x2 == x1:
        y_intersect = _calculate_baseline_y(x1, x_min, slope, y1_left)
        if min(y1, y2) <= y_intersect <= max(y1, y2):
            return (x1, y_intersect), p1_above, p2_above
        return None, p1_above, p2_above

    # Calculate segment parameters
    a = (y2 - y1) / (x2 - x1)  # Segment slope
    b = y1 - a * x1  # Segment y-intercept

    # Avoid division by zero or near-zero
    if abs(a - slope) <= 1e-9:
        return None, p1_above, p2_above

    # Calculate intersection x-coordinate
    x_intersect = (b - y1_left + slope * x_min) / (slope - a)

    # Check if intersection is within segment bounds
    if min(x1, x2) <= x_intersect <= max(x1, x2):
        y_intersect = a * x_intersect + b
        return (x_intersect, y_intersect), p1_above, p2_above

    return None, p1_above, p2_above


def _find_contour_baseline_intersections(contour_points, x_min, slope, y1_left):
    """Find intersections between contour and baseline.

    Args:
    ----
        contour_points: Contour points in 2D array format
        x_min: Minimum x-coordinate of the contour
        slope: Slope of the baseline
        y1_left: Y-coordinate at the leftmost point of the baseline

    Returns:
    -------
        tuple of (intersections, above_baseline_segments)

    """
    # Find intersections of contour with baseline
    intersections = []
    above_baseline_segments = []
    current_segment = []

    # Process points and identify segments above the baseline
    for i in range(len(contour_points)):
        p1 = contour_points[i]
        p2 = contour_points[(i + 1) % len(contour_points)]

        # Calculate intersection with baseline
        intersection, p1_above, _p2_above = _calculate_intersection_point(
            p1, p2, x_min, slope, y1_left
        )

        # Add point to current segment if it's above baseline
        if p1_above:
            current_segment.append(p1)

        # Process intersection if one exists
        if intersection is not None:
            intersections.append(intersection)

            # Add intersection to current segment
            current_segment.append(intersection)

            # Save current segment and start a new one
            if current_segment:
                above_baseline_segments.append(current_segment)
                current_segment = []

        # If we're at the end and have a non-empty segment, save it
        if i == len(contour_points) - 1 and current_segment:
            above_baseline_segments.append(current_segment)

    return intersections, above_baseline_segments


def _create_filtered_contour(
    intersections,
    above_baseline_segments,
    contour_points,
    x_min,
    slope,
    y1_left,
    original_shape,
):
    """Create filtered contour combining segments above baseline.

    Args:
    ----
        intersections: list of intersection points between contour and baseline
        above_baseline_segments: list of point segments above the baseline
        contour_points: Original contour points
        x_min: Minimum x-coordinate of the contour
        slope: Slope of the baseline
        y1_left: Y-coordinate at the leftmost point of the baseline
        original_shape: Original shape of the contour array

    Returns:
    -------
        Filtered contour in original format

    """
    # Combine all segments and baseline into a new contour
    filtered_points = []

    # Add all points from segments above the baseline
    if above_baseline_segments:
        # Sort segments by x-coordinate of first point
        above_baseline_segments.sort(key=lambda segment: segment[0][0])

        # Add points from all segments
        for segment in above_baseline_segments:
            filtered_points.extend(segment)

    # If we have at least two intersections, add baseline points between them
    if len(intersections) >= 2:
        # Get leftmost and rightmost intersections
        leftmost = min(intersections, key=lambda p: p[0])
        rightmost = max(intersections, key=lambda p: p[0])

        # Add the leftmost intersection if not already in filtered_points
        if not any(np.array_equal(leftmost, p) for p in filtered_points):
            filtered_points.append(leftmost)

        # Add baseline points at adaptive intervals based on contour density
        x_start = leftmost[0]
        x_end = rightmost[0]

        # Calculate average density of original contour points
        x_coords = contour_points[:, 0]
        x_diffs = np.diff(np.sort(x_coords))
        if len(x_diffs) > 0:
            median_spacing = np.median(x_diffs[x_diffs > 0])
            # Use a step size that's similar to the original contour density
            step = max(1, int(median_spacing))
        else:
            step = max(1, int((x_end - x_start) / 20))  # Default to 20 points

        # Add points along the baseline
        for x in np.arange(x_start + step, x_end, step):
            y = slope * (x - x_min) + y1_left
            filtered_points.append((x, y))

        # Add the rightmost intersection if not already in filtered_points
        if not any(np.array_equal(rightmost, p) for p in filtered_points):
            filtered_points.append(rightmost)

    # Convert to array
    filtered_points = np.array(filtered_points)

    # If we don't have enough points, return the original contour
    if len(filtered_points) < 3:
        return None

    # Use convex hull to get a properly ordered contour
    # This works well for droplet shapes which are generally convex
    hull = cv2.convexHull(filtered_points.astype(np.float32))

    # Convert back to the original contour format
    if original_shape is not None and len(original_shape) == 3:
        filtered_contour = hull.astype(np.int32)
    else:
        filtered_contour = hull.reshape(-1, 2).astype(np.int32)

    return filtered_contour


def crop_contour_points(
    x_left: list[float],
    y_left: list[float],
    x_right: list[float],
    y_right: list[float],
    threshold_y: float,
) -> tuple[list[float], list[float], list[float], list[float]]:
    """Crop contour points above a certain y threshold.

    Args:
    ----
        x_left: X-coordinates of left contour
        y_left: Y-coordinates of left contour
        x_right: X-coordinates of right contour
        y_right: Y-coordinates of right contour
        threshold_y: Y threshold for cropping

    Returns:
    -------
        tuple of cropped coordinates (x_left, y_left, x_right, y_right)

    """
    x_left_cropped = []
    y_left_cropped = []
    x_right_cropped = []
    y_right_cropped = []

    # Filter left contour points
    for i in range(len(y_left)):
        if y_left[i] > threshold_y:
            x_left_cropped.append(x_left[i])
            y_left_cropped.append(y_left[i])

    # Filter right contour points
    for i in range(len(y_right)):
        if y_right[i] > threshold_y:
            x_right_cropped.append(x_right[i])
            y_right_cropped.append(y_right[i])

    return x_left_cropped, y_left_cropped, x_right_cropped, y_right_cropped


def filter_contour_by_baseline_slope(contour, y1_left, y1_right):
    """Filter contour to remove points below baseline slope.

    Integrates the baseline slope as part of the contour boundary.

    Args:
    ----
        contour: The input contour to filter
        y1_left: Y-coordinate at the leftmost point of the baseline
        y1_right: Y-coordinate at the rightmost point of the baseline

    Returns:
    -------
        The filtered contour with baseline slope integrated

    """
    # Handle edge cases
    if contour is None or len(contour) == 0:
        return contour

    # Handle free sedimentation mode where baseline coordinates are None
    if y1_left is None or y1_right is None:
        # In free sedimentation mode, return the contour unfiltered
        return contour

    # Step 1: Prepare contour points
    contour_points, original_shape = _prepare_contour_points(contour)

    # Step 2: Calculate baseline slope
    baseline_params = _calculate_baseline_slope(contour_points, y1_left, y1_right)
    if baseline_params is None:
        return contour

    x_min, _x_max, slope = baseline_params

    # Step 3: Find intersections and segments above baseline
    intersections, above_baseline_segments = _find_contour_baseline_intersections(
        contour_points, x_min, slope, y1_left
    )

    # If no intersections, return original contour
    if not intersections:
        return contour

    # Step 4: Create filtered contour
    filtered_contour = _create_filtered_contour(
        intersections,
        above_baseline_segments,
        contour_points,
        x_min,
        slope,
        y1_left,
        original_shape,
    )

    # If filtered contour creation failed, return original
    if filtered_contour is None:
        return contour

    return filtered_contour


def filter_contour_by_vertical_lines(contour, vertical_left, vertical_right):
    """Remove contour portions between vertical lines, keep portions outside.

    Removes contour points that lie between the vertical line boundaries,
    keeping only the portions of the contour outside the vertical lines.

    Args:
    ----
        contour: The input contour to filter
        vertical_left: Left vertical line coordinates (x1, y1, x2, y2)
        vertical_right: Right vertical line coordinates (x1, y1, x2, y2)

    Returns:
    -------
        Contour with points only outside the vertical lines

    """
    # Handle edge cases
    if contour is None or len(contour) == 0:
        return contour

    # Handle cases where vertical lines are not defined
    if vertical_left is None or vertical_right is None:
        return contour

    # Extract x-coordinates from vertical lines
    x_left = vertical_left[0]  # x1 from (x1, y1, x2, y2)
    x_right = vertical_right[0]  # x1 from (x1, y1, x2, y2)

    # Ensure left is actually to the left of right
    if x_left > x_right:
        x_left, x_right = x_right, x_left

    # Step 1: Prepare contour points
    contour_points, original_shape = _prepare_contour_points(contour)
    if contour_points is None:
        return contour

    # Step 2: Filter points to keep only those OUTSIDE vertical lines
    x_coords = contour_points[:, 0]
    y_coords = contour_points[:, 1]

    # Find points OUTSIDE the vertical lines (left of left line OR right of right line)
    outside_lines = (x_coords < x_left) | (x_coords > x_right)

    # If no points are outside the lines, return empty contour
    if not np.any(outside_lines):
        if original_shape is not None and len(original_shape) == 3:
            return np.array([], dtype=np.int32).reshape(0, 1, 2)
        else:
            return np.array([], dtype=np.int32).reshape(0, 2)

    # Keep only the points outside the lines
    filtered_x = x_coords[outside_lines]
    filtered_y = y_coords[outside_lines]
    filtered_points = np.column_stack((filtered_x, filtered_y))

    # Convert back to original OpenCV contour format
    if original_shape is not None and len(original_shape) == 3:
        # Reshape to [n, 1, 2] format
        filtered_contour = filtered_points.reshape(-1, 1, 2).astype(np.int32)
    else:
        filtered_contour = filtered_points.astype(np.int32)

    return filtered_contour
