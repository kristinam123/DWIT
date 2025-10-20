"""Tangent-based contact angle calculation methods."""

import cv2
import numpy as np

from src.utilities.core_utils import get_logger

# Setup logger for this module
logger = get_logger(__name__)


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
        logger.debug(f"Image {q}: Right (receding) contact angle: {angle_degrees:.2f}°")

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
