"""Contact angle calculation utilities for Droplet Wall Interaction Tool."""

import cv2
import numpy as np
from scipy.optimize import curve_fit, leastsq

from src.utilities.logging_manager import get_logger

# Setup logger for this module
logger = get_logger(__name__)

# region Arc
RADIUS = 30


def _validate_calculation_inputs(
    img, intersection_points, contour, advancing_contact_angles, receding_contact_angles
):
    """Validate inputs for contact angle calculation.

    Args:
    ----
        img: Processed image
        intersection_points: Detected intersection points
        contour: The largest contour used for calculations
        advancing_contact_angles: List of advancing angles
        receding_contact_angles: List of receding angles

    Returns:
    -------
        tuple: (is_valid, advancing_angles, receding_angles)

    """
    if advancing_contact_angles is None:
        advancing_contact_angles = []
    if receding_contact_angles is None:
        receding_contact_angles = []

    # Ensure we have valid data
    if (
        img is None
        or intersection_points is None
        or len(intersection_points) < 2
        or contour is None
    ):
        logger.warning(
            f"Invalid data for contact angle calculation - img: {img is not None}, "
            + "intersections: "
            + f"{len(intersection_points) if intersection_points else 0}, "
            + f"contour: {contour is not None}"
        )
        advancing_contact_angles.append(float("NaN"))
        receding_contact_angles.append(float("NaN"))
        return False, advancing_contact_angles, receding_contact_angles

    return True, advancing_contact_angles, receding_contact_angles


def _prepare_visualization(img, cols, y1_left, y1_right, intersection_points):
    """Prepare the image for angle visualization.

    Args:
    ----
        img: Original image
        cols: Image width
        y1_left: Left baseline y-coordinate
        y1_right: Right baseline y-coordinate
        intersection_points: Detected intersection points

    Returns:
    -------
        tuple: (angle_img, baseline_y, baseline_slope)

    """
    # Create a copy of the image for angle visualization
    angle_img = img.copy()

    # Ensure baseline is drawn
    baseline_y = int((y1_left + y1_right) / 2)
    cv2.line(angle_img, (0, baseline_y), (cols - 1, baseline_y), (0, 0, 255), 2)

    # Calculate the baseline slope
    baseline_slope = 0
    if cols > 1:
        baseline_slope = (y1_right - y1_left) / (cols - 1)

    # Define constant arc radius

    # Draw intersection points
    for i, point in enumerate(intersection_points):
        cv2.circle(
            angle_img, point, 5, (255, 0, 0), -1
        )  # Blue circles at intersection points

    return angle_img, baseline_y, baseline_slope


def _find_contact_point_on_arc(intersection, contour_points, side_index, baseline_y):
    """Find the contact point where the arc intersects with the contour.

    Args:
    ----
        intersection: Intersection point coordinates
        contour_points: Array of contour points
        side_index: 0 for left side, 1 for right side
        baseline_y: Y-coordinate of baseline

    Returns:
    -------
        Contact point coordinates or None if not found

    """
    # Determine arc sweep direction based on which side we're on
    if side_index == 0:  # Left side
        start_angle = 90
        end_angle = 0
        angle_step = -1
    else:  # Right side
        start_angle = 90
        end_angle = 180
        angle_step = 1

    # Find the first point where the arc touches the contour
    contact_point = None

    # Generate points along the arc until we find one that intersects with the contour
    for angle_deg in range(start_angle, end_angle, angle_step):
        angle_rad = np.radians(angle_deg)
        # Calculate point on the arc
        arc_point = (
            int(intersection[0] + RADIUS * np.cos(angle_rad)),
            int(intersection[1] + RADIUS * np.sin(angle_rad)),
        )

        # Check if this arc point is close to any contour point
        for contour_point in contour_points:
            dist = np.sqrt(
                (arc_point[0] - contour_point[0]) ** 2
                + (arc_point[1] - contour_point[1]) ** 2
            )
            if dist < 2:  # Within 2 pixels is considered an intersection
                contact_point = contour_point
                break

        if contact_point is not None:
            break

    # If no contact point was found, try to find the closest contour point to the arc
    if contact_point is None:
        min_dist = float("inf")
        for contour_point in contour_points:
            # Only consider points above the baseline
            if contour_point[1] < baseline_y:
                # Check distance from intersection to this contour point
                dist = np.sqrt(
                    (intersection[0] - contour_point[0]) ** 2
                    + (intersection[1] - contour_point[1]) ** 2
                )
                if dist < min_dist and RADIUS * 0.7 < dist < RADIUS * 1.3:
                    min_dist = dist
                    contact_point = contour_point

    return contact_point


def _calculate_tangent_slope(contact_point, contour_points, intersection):
    """Calculate the tangent slope at the contact point.

    Args:
    ----
        contact_point: Contact point coordinates
        contour_points: Array of contour points
        intersection: Intersection point coordinates

    Returns:
    -------
        Calculated tangent slope

    """
    # Calculate local tangent at contact point using nearby contour points
    neighbors = []
    for contour_point in contour_points:
        dist = np.sqrt(
            (contact_point[0] - contour_point[0]) ** 2
            + (contact_point[1] - contour_point[1]) ** 2
        )
        if 0 < dist < 10:  # Consider points within 10 pixels
            neighbors.append(contour_point)

    # Sort neighbors by x-coordinate
    neighbors.sort(key=lambda p: p[0])

    # Calculate tangent slope using local linear regression if enough neighbors
    tangent_slope = 0
    if len(neighbors) >= 3:
        x_values = [p[0] for p in neighbors]
        y_values = [p[1] for p in neighbors]

        try:
            # Calculate linear regression using numpy
            a = np.vstack([x_values, np.ones(len(x_values))]).T
            tangent_slope, _ = np.linalg.lstsq(a, y_values, rcond=None)[0]
        except Exception as e:
            logger.warning(f"Linear regression failed: {e}, using fallback method")
            # Fallback to simple vector calculation
            if contact_point[0] != intersection[0]:
                tangent_slope = (contact_point[1] - intersection[1]) / (
                    contact_point[0] - intersection[0]
                )
    else:
        # Fallback: use the vector from intersection to contact point
        if contact_point[0] != intersection[0]:
            tangent_slope = (contact_point[1] - intersection[1]) / (
                contact_point[0] - intersection[0]
            )

    return tangent_slope


def _calculate_angle_from_slopes(tangent_slope, baseline_slope, side_index):
    """Calculate contact angle from tangent and baseline slopes.

    Args:
    ----
        tangent_slope: Slope of the tangent line
        baseline_slope: Slope of the baseline
        side_index: 0 for left side, 1 for right side

    Returns:
    -------
        Contact angle in degrees

    """
    # Calculate contact angle based on local tangent and baseline
    contact_angle_deg = np.degrees(
        np.arctan(
            np.abs(
                (tangent_slope - baseline_slope) / (1 + tangent_slope * baseline_slope)
            )
        )
    )

    # Adjust angle based on which side we're on and the slope directions
    if side_index == 0:  # Left side (advancing)
        if tangent_slope > 0:  # Positive slope (/)
            contact_angle_deg = 180 - contact_angle_deg
    else:  # Right side (receding)
        if tangent_slope < 0:  # Negative slope (\)
            contact_angle_deg = 180 - contact_angle_deg

    return contact_angle_deg


def _draw_angle_visualization(
    angle_img, contact_point, intersection, tangent_slope, start_angle, end_angle
):
    """Draw visualization elements for the calculated angle.

    Args:
    ----
        angle_img: Image to draw on
        contact_point: Contact point coordinates
        intersection: Intersection point coordinates
        tangent_slope: Slope of the tangent line
        start_angle: Start angle for arc visualization
        end_angle: End angle for arc visualization

    """
    # Draw the contact point
    cv2.circle(
        angle_img, contact_point, 4, (0, 255, 255), -1
    )  # Yellow circle for contact point

    # Draw line from intersection to contact point
    cv2.line(angle_img, intersection, contact_point, (0, 255, 0), 2)

    # Draw tangent line
    tangent_dx = RADIUS * 2  # Extend tangent line by 2*RADIUS
    tangent_dy = tangent_slope * tangent_dx

    tangent_start = (
        int(contact_point[0] - tangent_dx),
        int(contact_point[1] - tangent_dy),
    )
    tangent_end = (
        int(contact_point[0] + tangent_dx),
        int(contact_point[1] + tangent_dy),
    )

    # Draw the tangent line
    cv2.line(angle_img, tangent_start, tangent_end, (0, 255, 255), 1)

    # Draw the arc used to find the contact point
    cv2.ellipse(
        angle_img,
        intersection,
        (RADIUS, RADIUS),
        0,
        min(start_angle, end_angle),
        max(start_angle, end_angle),
        (255, 0, 255),
        1,
    )


def _process_single_intersection(
    intersection,
    side_index,
    contour_points,
    baseline_y,
    baseline_slope,
    angle_img,
    advancing_contact_angles,
    receding_contact_angles,
):
    """Process a single intersection point to calculate contact angle.

    Args:
    ----
        intersection: Intersection point coordinates
        side_index: 0 for left side, 1 for right side
        contour_points: Array of contour points
        baseline_y: Y-coordinate of baseline
        baseline_slope: Slope of baseline
        angle_img: Image for visualization
        advancing_contact_angles: List of advancing angles
        receding_contact_angles: List of receding angles

    Returns:
    -------
        Updated angle lists

    """
    side_name = "left (advancing)" if side_index == 0 else "right (receding)"

    # Skip if contour is empty or malformed
    if len(contour_points) < 3:
        logger.warning(
            f"Insufficient contour points ({len(contour_points)}) for {side_name} angle"
        )
        if side_index == 0:
            advancing_contact_angles.append(float("NaN"))
        else:
            receding_contact_angles.append(float("NaN"))
        return advancing_contact_angles, receding_contact_angles

    # Find contact point on arc
    contact_point = _find_contact_point_on_arc(
        intersection, contour_points, side_index, baseline_y
    )

    # If no contact point found, skip this side
    if contact_point is None:
        logger.warning(f"No suitable contact point found for {side_name}")
        if side_index == 0:
            advancing_contact_angles.append(float("NaN"))
        else:
            receding_contact_angles.append(float("NaN"))
        return advancing_contact_angles, receding_contact_angles

    # Convert contact point to tuple of integers
    contact_point = tuple(map(int, contact_point))

    # Calculate tangent slope
    tangent_slope = _calculate_tangent_slope(
        contact_point, contour_points, intersection
    )

    try:
        # Calculate contact angle
        contact_angle_deg = _calculate_angle_from_slopes(
            tangent_slope, baseline_slope, side_index
        )

        # Store the calculated angle
        if side_index == 0:  # Left side (advancing)
            advancing_contact_angles.append(contact_angle_deg)
            logger.info(f"Advancing contact angle: {contact_angle_deg:.2f}°")
        else:  # Right side (receding)
            receding_contact_angles.append(contact_angle_deg)
            logger.info(f"Receding contact angle: {contact_angle_deg:.2f}°")

    except Exception as e:
        logger.error(f"Error calculating contact angle for {side_name}: {e}")
        if side_index == 0:
            advancing_contact_angles.append(float("NaN"))
        else:
            receding_contact_angles.append(float("NaN"))
        return advancing_contact_angles, receding_contact_angles

    # Draw visualization elements
    start_angle = 90
    end_angle = 0 if side_index == 0 else 180
    _draw_angle_visualization(
        angle_img, contact_point, intersection, tangent_slope, start_angle, end_angle
    )

    return advancing_contact_angles, receding_contact_angles


def calculate_contact_angles(
    cols,
    shifted_points,
    shifted_x,
    shifted_y,
    intersection_points,
    y1_left,
    y1_right,
    img,
    filename,
    output_path,
    advancing_contact_angles=None,
    receding_contact_angles=None,
    q=0,
    result_images=None,
    save_files=False,
    contour=None,
):
    """Calculate contact angles using arc method.

    Args:
    ----
        cols: Image width
        shifted_points: Contour data points (not used in arc method)
        shifted_x: Contour x-coordinates (not used in arc method)
        shifted_y: Contour y-coordinates (not used in arc method)
        intersection_points: Detected intersection points
        y1_left: Left baseline y-coordinate
        y1_right: Right baseline y-coordinate
        img: Processed image
        filename: Current image filename
        output_path: Output directory (folder where results/files are saved)
        advancing_contact_angles: list of advancing angles (optional)
        receding_contact_angles: list of receding angles (optional)
        q: Current image index (default: 0)
        result_images: Dictionary to store result images (optional)
        save_files: Whether to save output files (default: False)
        contour: The largest contour used for arc method calculations

    Returns:
    -------
        Updated advancing_contact_angles and receding_contact_angles lists
        and angle image

    """
    logger.info(f"Calculating contact angles for image {q}: {filename}")

    # Check for missing baseline
    if y1_left is None or y1_right is None:
        logger.warning(
            f"Baseline not found (y1_left={y1_left}, y1_right={y1_right}) "
            f"for image {filename}. Skipping contact angle calculation."
        )
        if advancing_contact_angles is None:
            advancing_contact_angles = []
        if receding_contact_angles is None:
            receding_contact_angles = []
        advancing_contact_angles.append(float("NaN"))
        receding_contact_angles.append(float("NaN"))
        return advancing_contact_angles, receding_contact_angles, img

    # Validate inputs
    is_valid, advancing_contact_angles, receding_contact_angles = (
        _validate_calculation_inputs(
            img,
            intersection_points,
            contour,
            advancing_contact_angles,
            receding_contact_angles,
        )
    )

    if not is_valid:
        return advancing_contact_angles, receding_contact_angles, img

    # Prepare visualization
    angle_img, baseline_y, baseline_slope = _prepare_visualization(
        img, cols, y1_left, y1_right, intersection_points
    )

    # Convert contour to a more usable format
    contour_points = contour.squeeze()

    # Process each intersection point (left and right)
    for i, intersection in enumerate(intersection_points):
        advancing_contact_angles, receding_contact_angles = (
            _process_single_intersection(
                intersection,
                i,
                contour_points,
                baseline_y,
                baseline_slope,
                angle_img,
                advancing_contact_angles,
                receding_contact_angles,
            )
        )

    logger.info(f"Contact angle calculation completed for {filename}")
    return advancing_contact_angles, receding_contact_angles, angle_img


# endregion Arc


# region Tangent
def calculate_tangent_contact_angles(
    cols,
    shifted_points,
    shifted_x,
    shifted_y,
    intersection_points,
    y1_left,
    y1_right,
    img,
    filename,
    output_path,
    advancing_contact_angles=None,
    receding_contact_angles=None,
    q=0,
    result_images=None,
    save_files=False,
):
    """Calculate contact angles using tangent method.

    Args:
    ----
        cols: Image width.
        shifted_points: List of shifted contour points for tangent calculation.
        shifted_x: X-coordinates of shifted contour points.
        shifted_y: Y-coordinates of shifted contour points.
        intersection_points: Detected intersection points.
        y1_left: Average y-coordinate of the left baseline.
        y1_right: Average y-coordinate of the right baseline.
        img: Processed image.
        filename: Current image filename.
        output_path: Output directory (folder where results/files are saved).
        advancing_contact_angles: List of advancing angles (optional).
        receding_contact_angles: List of receding angles (optional).
        q: Current image index (default: 0).
        result_images: Dictionary to store result images (optional).
        save_files: Whether to save output files (default: False).

    Returns:
    -------
        Updated advancing_contact_angles and receding_contact_angles lists and image.

    """
    if advancing_contact_angles is None:
        advancing_contact_angles = []
    if receding_contact_angles is None:
        receding_contact_angles = []

    if img is None or intersection_points is None or len(intersection_points) < 2:
        logger.warning(f"Invalid data for contact angle calculation in image {q}")
        advancing_contact_angles.append(float("NaN"))
        receding_contact_angles.append(float("NaN"))
        return advancing_contact_angles, receding_contact_angles, img

    angle_img = img.copy()
    baseline_y = int((y1_left + y1_right) / 2)
    cv2.line(angle_img, (0, baseline_y), (cols - 1, baseline_y), (0, 0, 255), 2)

    for point in intersection_points:
        cv2.circle(angle_img, point, 5, (255, 0, 0), -1)

    baseline_slope = 0
    if cols > 1:
        baseline_slope = (y1_right - y1_left) / (cols - 1)

    left_point = intersection_points[0]
    right_point = intersection_points[1]

    if not shifted_points or len(shifted_points) < 2:
        shift_y = 15
        shifted_points = [
            (left_point[0], left_point[1] - shift_y),
            (right_point[0], right_point[1] - shift_y),
        ]

    for i, intersection in enumerate(intersection_points):
        if i >= len(shifted_points):
            logger.warning(f"Missing shifted point for intersection {i} in image {q}")
            continue
        tangent_point = shifted_points[i]
        if intersection[0] != tangent_point[0]:
            _process_tangent_side(
                i,
                intersection,
                tangent_point,
                baseline_slope,
                angle_img,
                advancing_contact_angles,
                receding_contact_angles,
                q,
            )
        else:
            _process_vertical_tangent(
                i,
                intersection,
                angle_img,
                advancing_contact_angles,
                receding_contact_angles,
                q,
            )

    return advancing_contact_angles, receding_contact_angles, angle_img


def _process_tangent_side(
    i,
    intersection,
    tangent_point,
    baseline_slope,
    angle_img,
    advancing_contact_angles,
    receding_contact_angles,
    q,
):
    """Process a non-vertical tangent side."""
    tangent_slope = (intersection[1] - tangent_point[1]) / (
        intersection[0] - tangent_point[0]
    )
    angle_help = intersection[0] - tangent_point[0]
    angle_radians = np.arctan(
        np.abs((tangent_slope - baseline_slope) / (1 + tangent_slope * baseline_slope))
    )
    angle_degrees = np.degrees(angle_radians)

    if i == 0:
        correct_angle = 180 - angle_degrees if angle_help < 0 else angle_degrees
        angle_degrees = 180 - correct_angle
        advancing_contact_angles.append(angle_degrees)
        logger.debug(f"Image {q}: Left (advancing) contact angle: {angle_degrees:.2f}°")
    else:
        correct_angle = 180 - angle_degrees if angle_help > 0 else angle_degrees
        angle_degrees = 180 - correct_angle
        receding_contact_angles.append(angle_degrees)
        logger.debug(
            f"Image {q}: Right (receding) contact angle: " f"{angle_degrees:.2f}°"
        )

    dx = intersection[0] - tangent_point[0]
    dy = intersection[1] - tangent_point[1]
    length = np.sqrt(dx * dx + dy * dy)
    if length > 0:
        nx = dx / length
        ny = dy / length
        if ny > 0:
            nx = -nx
            ny = -ny
        scale_factor = 70.0
        extended_point = (
            int(intersection[0] + nx * scale_factor),
            int(intersection[1] + ny * scale_factor),
        )
        cv2.line(angle_img, intersection, extended_point, (0, 0, 255), 2)
        radius = 30
        tangent_angle = np.degrees(np.arctan2(ny, nx))
        if tangent_angle < 0:
            tangent_angle += 360
        baseline_angle = 0 if i == 0 else 180
        if i == 0:
            start_angle = tangent_angle
            end_angle = baseline_angle
            if start_angle > end_angle:
                if start_angle - end_angle > 180:
                    start_angle -= 360
            else:
                if end_angle - start_angle > 180:
                    end_angle -= 360
            cv2.ellipse(
                angle_img,
                intersection,
                (radius, radius),
                0,
                start_angle,
                end_angle,
                (0, 255, 0),
                2,
            )
        else:
            start_angle = baseline_angle
            end_angle = tangent_angle
            if end_angle < start_angle:
                end_angle += 360
            cv2.ellipse(
                angle_img,
                intersection,
                (radius, radius),
                0,
                start_angle,
                end_angle,
                (0, 255, 0),
                2,
            )


def _process_vertical_tangent(
    i, intersection, angle_img, advancing_contact_angles, receding_contact_angles, q
):
    """Process a vertical tangent side for tangent contact angle calculation."""
    angle_degrees = 90.0
    if i == 0:
        advancing_contact_angles.append(angle_degrees)
        logger.debug(
            f"Image {q}: Left (advancing) contact angle (vertical): "
            f"{angle_degrees:.2f}°"
        )
    else:
        receding_contact_angles.append(angle_degrees)
        logger.debug(
            f"Image {q}: Right (receding) contact angle (vertical): "
            f"{angle_degrees:.2f}°"
        )
    extended_point = (
        intersection[0],
        intersection[1] - 70,
    )
    cv2.line(angle_img, intersection, extended_point, (0, 0, 255), 2)
    radius = 30
    if i == 0:
        cv2.ellipse(angle_img, intersection, (radius, radius), 0, 90, 0, (0, 255, 0), 2)
    else:
        cv2.ellipse(
            angle_img,
            intersection,
            (radius, radius),
            0,
            180,
            90,
            (0, 255, 0),
            2,
        )


# endregion Tangent


# region Ellipse
def calculate_contact_angle_left(x_points, y_points, angles_list, intersection_points):
    """Calculate contact angle for the left side of the droplet.

    Args:
    ----
        x_points (array): X coordinates of contour points
        y_points (array): Y coordinates of contour points
        angles_list (list): list to append the calculated angle
        intersection_points (list): Intersection points with baseline

    Returns:
    -------
        list: Updated angles list

    """
    angles_list = []
    xc, yc, a, b, angle = _fit_ellipse(x_points, y_points)

    # Contact point coordinates
    x_contact = intersection_points[0][0]
    y_contact = intersection_points[0][1]

    # Calculate angle at contact point
    theta_point = np.arctan2(y_contact - yc, x_contact - xc)
    slope = _ellipse_slope(a, b, angle, theta_point)
    contact_angle = _calculate_contact_angle(slope)
    angles_list.append(contact_angle)

    return angles_list


def calculate_contact_angle_right(x_points, y_points, angles_list):
    """Calculate contact angle for the right side of the droplet.

    Args:
    ----
        x_points (array): X coordinates of contour points
        y_points (array): Y coordinates of contour points
        angles_list (list): list to append the calculated angle

    Returns:
    -------
        list: Updated angles list

    """
    angles_list = []
    _, _, a, b, angle = _fit_ellipse(x_points, y_points)

    # Calculate angle at theta_point = 0
    theta_point = 0
    slope = _ellipse_slope(a, b, angle, theta_point)
    contact_angle = _calculate_contact_angle(slope)
    angles_list.append(contact_angle)

    return angles_list


def calculate_ellipse_contact_angle(
    x_left,  # X coordinates of left contour points
    y_left,  # Y coordinates of left contour points
    x_right,  # X coordinates of right contour points
    y_right,  # Y coordinates of right contour points
    intersection_points,  # Intersection points with baseline
):
    """Calculate contact angle using ellipse fitting for both sides.

    Args:
    ----
        x_left (array): X coordinates of left contour points
        y_left (array): Y coordinates of left contour points
        x_right (array): X coordinates of right contour points
        y_right (array): Y coordinates of right contour points
        intersection_points (list): Intersection points with baseline

    Returns:
    -------
        float: Combined contact angle

    """
    contour_left = np.array([x_left, y_left])
    contour_right = np.array([x_right, y_right])
    intersection_point_left = np.array(intersection_points[0])
    intersection_point_right = np.array(intersection_points[1])

    params_left, _ = curve_fit(
        _ellipse,
        contour_left[0, :],
        contour_left[1, :],
        p0=[intersection_point_left[0], intersection_point_left[1], 1, 1],
    )
    params_right, _ = curve_fit(
        _ellipse,
        contour_right[0, :],
        contour_right[1, :],
        p0=[intersection_point_right[0], intersection_point_right[1], 1, 1],
    )

    left_slope = _tangent_slope(intersection_point_left[0], params_left)
    right_slope = _tangent_slope(intersection_point_right[0], params_right)

    contact_angle = (
        np.arctan((right_slope - left_slope) / (1 + left_slope * right_slope))
        * 180
        / np.pi
    )
    return contact_angle


def _tangent_slope(x, params):
    """Calculate tangent slope at a given x-coordinate on an ellipse.

    Args:
    ----
        x (float): X coordinate
        params (array): Ellipse parameters [xc, yc, a, b]

    Returns:
    -------
        float: Slope of tangent

    """
    xc, _, a, b = params
    return (
        -((b**2) / (a**2))
        * (x - xc)
        / (np.sqrt(b**2 - ((x - xc) ** 2) * (b**2) / (a**2)))
    )


def _ellipse(x, xc, yc, a, b):
    """Ellipse function for curve fitting.

    Args:
    ----
        x (array): X coordinates
        xc (float): X center of ellipse
        yc (float): Y center of ellipse
        a (float): Semi-major axis
        b (float): Semi-minor axis

    Returns:
    -------
        array: Y coordinates of ellipse

    """
    return yc + b * np.sqrt(1 - ((x - xc) ** 2) / a**2)


def _fit_ellipse(x, y):
    """Fit an ellipse to a set of points.

    Args:
    ----
        x (array): X coordinates of contour points
        y (array): Y coordinates of contour points

    Returns:
    -------
        array: Optimized ellipse parameters [xc, yc, a, b, angle]

    """
    if x is None or y is None:
        return None

    if len(x) <= 1 or len(y) <= 1:
        return None

    initial_guess = [np.mean(x), np.mean(y), np.std(x), np.std(y), 0]
    params_opt, _ = leastsq(__ellipse_residuals, initial_guess, args=(x, y))
    return params_opt


def _ellipse_slope(a, b, angle, theta):
    """Calculate the slope of an ellipse at a specific angle.

    Args:
    ----
        a (float): Semi-major axis of ellipse
        b (float): Semi-minor axis of ellipse
        angle (float): Rotation angle of ellipse
        theta (float): Parametric angle where slope is calculated

    Returns:
    -------
        float: Slope at the specified angle

    """
    dx_dtheta = -a * np.sin(theta)
    dy_dtheta = b * np.cos(theta)
    slope = dy_dtheta / dx_dtheta
    cos_angle = np.cos(angle)
    sin_angle = np.sin(angle)
    slope_rotated = (slope * cos_angle - sin_angle) / (cos_angle + slope * sin_angle)
    return slope_rotated


def _calculate_contact_angle(slope):
    """Calculate contact angle from a slope.

    Args:
    ----
        slope (float): Slope value

    Returns:
    -------
        float: Contact angle in degrees

    """
    contact_angle = np.arctan(-slope) * 180 / np.pi
    return contact_angle


def __ellipse_residuals(params, x, y):
    """Calculate residuals for ellipse fitting.

    Args:
    ----
        params (array): Ellipse parameters [xc, yc, a, b, angle]
        x (array): X coordinates of contour points
        y (array): Y coordinates of contour points

    Returns:
    -------
        array: Residuals for optimization

    """
    xc, yc, a, b, angle = params
    cos_angle = np.cos(angle)
    sin_angle = np.sin(angle)
    x_rot = (x - xc) * cos_angle + (y - yc) * sin_angle
    y_rot = -(x - xc) * sin_angle + (y - yc) * cos_angle
    residuals = (x_rot / a) ** 2 + (y_rot / b) ** 2 - 1
    return residuals


# endregion Ellipse


# region Polygon
def fit_left_polynomial(
    x_left_90: list[float],
    y_left_90: list[float],
    intersection_points: list[list[float]],
    ca_left_values: list[float],
    degree: int = 2,
) -> list[float]:
    """Fit polynomial to left contact angle region and calculate contact angle.

    Args:
    ----
        x_left_90: X-coordinates of rotated left contour
        y_left_90: Y-coordinates of rotated left contour
        intersection_points: list of intersection points
        ca_left_values: list to store calculated contact angle values
        degree: Degree of polynomial fit

    Returns:
    -------
        Updated list of left contact angle values

    """
    ca_left_values = []
    # Fit polynomial to points
    coeffs = np.polyfit(x_left_90, y_left_90, degree)
    poly = np.poly1d(coeffs)

    # Calculate derivative for tangent
    dpoly = np.polyder(poly)

    # Get contact point and slope
    x_contact = intersection_points[0][0]
    slope = dpoly(x_contact)

    # Calculate contact angle
    contact_angle = np.arctan(slope) * (180 / np.pi)
    ca_left_values.append(contact_angle)

    return ca_left_values


def fit_right_polynomial(
    x_right_90: list[float],
    y_right_90: list[float],
    x_mean: float,
    ca_right_values: list[float],
    degree: int = 2,
) -> list[float]:
    """Fit polynomial to right contact angle region and calculate contact angle.

    Args:
    ----
        x_right_90: X-coordinates of rotated right contour
        y_right_90: Y-coordinates of rotated right contour
        x_mean: Mean x-coordinate for contact point
        ca_right_values: list to store calculated contact angle values
        degree: Degree of polynomial fit

    Returns:
    -------
        Updated list of right contact angle values

    """
    ca_right_values = []
    # Fit polynomial to points
    coeffs = np.polyfit(x_right_90, y_right_90, degree)
    poly = np.poly1d(coeffs)

    # Calculate derivative for tangent
    dpoly = np.polyder(poly)

    # Calculate contact angle
    slope = dpoly(x_mean)
    contact_angle = np.arctan(slope) * (180 / np.pi)
    ca_right_values.append(contact_angle)

    return ca_right_values


def rotate_coordinates_90(
    x_left: list[float], y_left: list[float], x_right: list[float], y_right: list[float]
) -> tuple[list[float], list[float], list[float], list[float]]:
    """Rotate coordinates 90 degrees by swapping x and y.

    Args:
    ----
        x_left: X-coordinates of left contour
        y_left: Y-coordinates of left contour
        x_right: X-coordinates of right contour
        y_right: Y-coordinates of right contour

    Returns:
    -------
        tuple of rotated coordinates (x_left_90, y_left_90, x_right_90, y_right_90)

    """
    return y_left, x_left, y_right, x_right


# endregion Polygon
