"""Arc-based contact angle calculation methods."""

import cv2
import numpy as np

from src.utilities.core_utils import get_logger

# Setup logger for this module
logger = get_logger(__name__)

# Define constant arc radius
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
        (0, 255, 0),
        2,
    )


def _process_single_intersection(
    intersection,
    i,
    contour_points,
    baseline_y,
    baseline_slope,
    angle_img,
    advancing_contact_angles,
    receding_contact_angles,
):
    """Process a single intersection point for contact angle calculation.

    Args:
    ----
        intersection: Intersection point coordinates
        i: Index of intersection (0 for left, 1 for right)
        contour_points: Array of contour points
        baseline_y: Y-coordinate of baseline
        baseline_slope: Slope of baseline
        angle_img: Image for visualization
        advancing_contact_angles: list of advancing angles
        receding_contact_angles: list of receding angles

    Returns:
    -------
        Updated lists of advancing and receding contact angles

    """
    # Find contact point where arc intersects with contour
    contact_point = _find_contact_point_on_arc(
        intersection, contour_points, i, baseline_y
    )

    if contact_point is None:
        logger.warning(f"Could not find contact point for intersection {i}")
        if i == 0:
            advancing_contact_angles.append(float("NaN"))
        else:
            receding_contact_angles.append(float("NaN"))
        return advancing_contact_angles, receding_contact_angles

    # Calculate tangent slope at contact point
    tangent_slope = _calculate_tangent_slope(
        contact_point, contour_points, intersection
    )

    # Calculate contact angle
    contact_angle_deg = _calculate_angle_from_slopes(tangent_slope, baseline_slope, i)

    # Store angle in appropriate list
    if i == 0:  # Left side (advancing)
        advancing_contact_angles.append(contact_angle_deg)
        logger.debug(f"Left (advancing) contact angle: {contact_angle_deg:.2f}°")
    else:  # Right side (receding)
        receding_contact_angles.append(contact_angle_deg)
        logger.debug(f"Right (receding) contact angle: {contact_angle_deg:.2f}°")

    # Draw visualization
    if i == 0:
        start_angle = 90
        end_angle = 0
    else:
        start_angle = 90
        end_angle = 180

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
