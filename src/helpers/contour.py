"""Contour analysis and filtering utilities for MesszelleApp."""

import cv2
import numpy as np

from src.utilities.logging_manager import get_logger

# Setup logger for this module
logger = get_logger(__name__)


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
    logger.debug(f"Params: y1_left={y1_left}, y1_right={y1_right}, intersection_points={intersection_points}, pixel={pixel}")

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
    logger.debug(f"Params: contour_len={len(contour) if hasattr(contour, '__len__') else 'unknown'}, line_y={line_y}")

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
        intersection, p1_above, p2_above = _calculate_intersection_point(
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
        x_left: X-coordinates of left contour
        y_left: Y-coordinates of left contour
        x_right: X-coordinates of right contour
        y_right: Y-coordinates of right contour
        threshold_y: Y threshold for cropping

    Returns:
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

    x_min, x_max, slope = baseline_params

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
