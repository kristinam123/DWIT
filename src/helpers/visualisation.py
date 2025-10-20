"""Drawing and visualization utilities.

For experiment visualization in Droplet Wall Interaction Tool (DWIT).
This module contains visualization utilities extracted from core.py
to improve code organization and maintainability.
"""

import cv2
import numpy as np

from src.utilities.core_utils import get_logger

# Setup logger for this module
logger = get_logger(__name__)


def draw_intersection_points_and_angles(
    result_image,
    result_images,
    angles,
    advancing_contact_angles,
    receding_contact_angles,
):
    """Draw intersection points and contact angle lines on result image.

    Args:
    ----
        result_image: Image to draw on (modified in-place)
        result_images: Dictionary containing intersection_points
        angles: Dictionary with 'left' and 'right' angle values
        advancing_contact_angles: List of advancing angles
        receding_contact_angles: List of receding angles

    """
    if "intersection_points" not in result_images:
        return

    intersection_points = result_images["intersection_points"]
    if not intersection_points or not all(
        point is not None and not any(np.isnan(x) for x in point)
        for point in intersection_points[:2]
    ):
        return

    # Draw intersection points
    for point in intersection_points[:2]:
        cv2.circle(result_image, (int(point[0]), int(point[1])), 8, (0, 255, 255), -1)
        cv2.circle(result_image, (int(point[0]), int(point[1])), 10, (0, 0, 0), 2)

    # Draw contact angle lines
    latest_adv = (
        angles["left"]
        if not np.isnan(angles["left"])
        else (
            advancing_contact_angles[-1] if advancing_contact_angles else float("NaN")
        )
    )
    latest_rec = (
        angles["right"]
        if not np.isnan(angles["right"])
        else (receding_contact_angles[-1] if receding_contact_angles else float("NaN"))
    )

    if (
        not np.isnan(latest_adv)
        and not np.isnan(latest_rec)
        and len(intersection_points) >= 2
    ):
        # Draw left side (advancing) angle line
        if not np.isnan(latest_adv):
            x, y = intersection_points[0]
            angle_rad = np.radians(latest_adv)
            line_length = 80
            end_x = int(x + line_length * np.cos(angle_rad))
            end_y = int(y - line_length * np.sin(angle_rad))
            cv2.line(result_image, (int(x), int(y)), (end_x, end_y), (0, 255, 0), 2)

        # Draw right side (receding) angle line
        if not np.isnan(latest_rec):
            x, y = intersection_points[1]
            angle_rad = np.radians(180 - latest_rec)
            line_length = 80
            end_x = int(x + line_length * np.cos(angle_rad))
            end_y = int(y - line_length * np.sin(angle_rad))
            cv2.line(result_image, (int(x), int(y)), (end_x, end_y), (0, 255, 0), 2)


def create_fallback_result(result_images, largest_contour):
    """Create a basic fallback result image if none was created.

    Args:
    ----
        result_images: Dictionary to store result images
        largest_contour: The droplet contour to visualize

    """
    fallback_result = result_images.get("original").copy()
    if largest_contour is not None:
        # Draw filled contour area (30% transparent green)
        draw_filled_contour(
            fallback_result, largest_contour, color=(0, 255, 0), alpha=0.3
        )
        cv2.drawContours(fallback_result, [largest_contour], -1, (0, 255, 0), 2)
        moment = cv2.moments(largest_contour)
        if moment["m00"] != 0:
            cx = int(moment["m10"] / moment["m00"])
            cy = int(moment["m01"] / moment["m00"])
            cv2.circle(fallback_result, (cx, cy), 8, (0, 0, 255), -1)
    result_images["result"] = fallback_result
    result_images["fallback"] = fallback_result.copy()


def draw_filled_contour(img, contour, color=(0, 255, 0), alpha=0.3):
    """Draw a filled contour with transparency.

    Args:
    ----
        img: Input image
        contour: Contour points
        color: Fill color in BGR format (default: green)
        alpha: Transparency level (0.0 = transparent, 1.0 = opaque)

    Returns:
    -------
        Modified image with filled contour

    """
    if contour is None or len(contour) == 0:
        return img

    try:
        # Create a copy for overlay
        overlay = img.copy()

        # Fill the contour on the overlay as-is
        cv2.fillPoly(overlay, [contour], color)

        # Blend with original image
        cv2.addWeighted(overlay, alpha, img, 1 - alpha, 0, img)

        logger.debug(f"Drew filled contour with color {color} and alpha {alpha}")
        return img
    except Exception as e:
        logger.error(f"Error drawing filled contour: {e}")
        return img


def draw_dual_baselines(
    img,
    y1_left,
    y1_right,
    color1=(0, 0, 255),
    color2=(0, 0, 255),
    thickness=3,
):
    """Draw two horizontal baselines with optional outlines on an image."""
    img_width = img.shape[1]
    logger.debug(
        f"Drawing dual baselines at y1_left={y1_left}, y1_right={y1_right}, "
        f"color1={color1}, color2={color2}, thickness={thickness}"
    )
    try:
        # Upper baseline
        cv2.line(img, (0, int(y1_left)), (img_width, int(y1_left)), color1, thickness)
        cv2.line(img, (0, int(y1_right)), (img_width, int(y1_right)), color2, thickness)
    except Exception as e:
        logger.error(f"Error drawing dual baselines: {e}")


def draw_axis_line(img, y, color=(0, 0, 255), thickness=3):
    """Draw a horizontal axis line at y."""
    img_width = img.shape[1]
    logger.debug(f"Drawing axis line at y={y}, color={color}, thickness={thickness}")
    try:
        cv2.line(img, (0, int(y)), (img_width, int(y)), color, thickness)
    except Exception as e:
        logger.error(f"Error drawing axis line: {e}")


def draw_intersection_points(img, points, y1_left, y1_right, mode="channel"):
    """Draw intersection points.

    Colored by proximity to y1_left/y1_right for channel mode, else yellow/black.
    """
    logger.debug(
        f"Drawing {len(points)} intersection points with "
        f"y1_left={y1_left}, y1_right={y1_right}, mode={mode}"
    )
    upper_points, lower_points = [], []
    points_drawn = 0

    for i, point in enumerate(points):
        if point is not None:
            x, y = point

            try:
                if mode == "channel":
                    if abs(y - y1_left) < abs(y - y1_right):
                        upper_points.append(point)
                        cv2.circle(img, (int(x), int(y)), 12, (0, 255, 0), -1)
                    else:
                        lower_points.append(point)
                        cv2.circle(img, (int(x), int(y)), 12, (0, 0, 255), -1)
                else:
                    cv2.circle(img, (int(x), int(y)), 10, (0, 255, 255), -1)
                    cv2.circle(img, (int(x), int(y)), 12, (0, 0, 0), 2)

                points_drawn += 1

            except Exception as e:
                logger.error(f"Error drawing intersection point {i}: {e}")

    logger.debug(
        f"Drew {points_drawn} intersection points "
        f"({len(upper_points)} upper, {len(lower_points)} lower)"
    )
    return upper_points, lower_points


def draw_connection_line(img, p1, p2, color=(0, 255, 0), thickness=2):
    """Draw a line between two points."""
    logger.debug(
        f"Drawing connection line from {p1} to {p2}, "
        f"color={color}, thickness={thickness}"
    )
    try:
        cv2.line(
            img, (int(p1[0]), int(p1[1])), (int(p2[0]), int(p2[1])), color, thickness
        )
    except Exception as e:
        logger.error(f"Error drawing connection line: {e}")


def draw_rectangle(img, x, y, w, h, color=(0, 0, 255), thickness=2):
    """Draw a rectangle on the image."""
    logger.debug(
        f"Drawing rectangle at x={x}, y={y}, w={w}, h={h}, "
        f"color={color}, thickness={thickness}"
    )
    try:
        cv2.rectangle(img, (int(x), int(y)), (int(x + w), int(y + h)), color, thickness)
    except Exception as e:
        logger.error(f"Error drawing rectangle: {e}")


def draw_center_point(img, cx, cy, color=(0, 0, 255), crosshair_size=20, thickness=2):
    """Draw a center point with crosshairs on the image."""
    logger.debug(
        f"Drawing center point at ({cx}, {cy}), "
        f"color={color}, crosshair_size={crosshair_size}, thickness={thickness}"
    )
    try:
        cv2.drawMarker(
            img,
            (int(cx), int(cy)),
            color,
            markerType=cv2.MARKER_CROSS,
            markerSize=crosshair_size,
            thickness=thickness,
        )
    except Exception as e:
        logger.error(f"Error drawing center point: {e}")
