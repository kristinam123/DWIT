"""Drawing utilities for experiment visualization in MesszelleApp."""

import cv2
import numpy as np

from src.utilities.logging_manager import get_logger

# Setup logger for this module
logger = get_logger(__name__)


def draw_dual_baselines(
    img,
    y1_left,
    y1_right,
    color1=(0, 255, 0),
    color2=(0, 0, 255),
    thickness=4,
):
    """Draw two horizontal baselines with optional outlines on an image."""
    img_width = img.shape[1]

    try:
        # Upper baseline
        cv2.line(img, (0, int(y1_left)), (img_width, int(y1_left)), color1, thickness)
        cv2.line(img, (0, int(y1_right)), (img_width, int(y1_right)), color2, thickness)
    except Exception as e:
        logger.error(f"Error drawing dual baselines: {e}")


def draw_axis_line(img, y, color=(255, 255, 0), thickness=1):
    """Draw a horizontal axis line at y."""
    img_width = img.shape[1]

    try:
        cv2.line(img, (0, int(y)), (img_width, int(y)), color, thickness)
    except Exception as e:
        logger.error(f"Error drawing axis line: {e}")


def draw_intersection_points(img, points, y1_left, y1_right, mode="channel"):
    """Draw intersection points.

    Colored by proximity to y1_left/y1_right for channel mode, else yellow/black.
    """
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

    logger.info(
        f"Drew {points_drawn} intersection points "
        f"({len(upper_points)} upper, {len(lower_points)} lower)"
    )
    return upper_points, lower_points


def draw_connection_line(img, p1, p2, color=(0, 255, 0), thickness=2):
    """Draw a line between two points."""
    try:
        cv2.line(
            img, (int(p1[0]), int(p1[1])), (int(p2[0]), int(p2[1])), color, thickness
        )
    except Exception as e:
        logger.error(f"Error drawing connection line: {e}")


def draw_rectangle(img, x, y, w, h, color=(0, 0, 255), thickness=2):
    """Draw a rectangle on the image."""
    try:
        cv2.rectangle(img, (x, y), (x + w, y + h), color, thickness)
    except Exception as e:
        logger.error(f"Error drawing rectangle: {e}")


def draw_center_point(img, cx, cy, color=(0, 0, 255), crosshair_size=20, thickness=2):
    """Draw a center point with crosshairs on the image."""
    try:
        cv2.circle(img, (cx, cy), 8, color, -1)
        cv2.line(
            img, (cx - crosshair_size, cy), (cx + crosshair_size, cy), color, thickness
        )
        cv2.line(
            img, (cx, cy - crosshair_size), (cx, cy + crosshair_size), color, thickness
        )
    except Exception as e:
        logger.error(f"Error drawing center point: {e}")


def highlight_interaction_zone(img, contour, y, zone=10, color=[0, 255, 255]):
    """Highlight the interaction zone around a given y-coordinate on the image."""
    try:
        img_width = img.shape[1]
        mask = np.zeros(img.shape[:2], dtype=np.uint8)
        cv2.rectangle(mask, (0, int(y) - zone), (img_width, int(y) + zone), 255, -1)
        contour_mask = np.zeros(img.shape[:2], dtype=np.uint8)
        cv2.drawContours(contour_mask, [contour], -1, 255, -1)
        intersection = cv2.bitwise_and(mask, contour_mask)

        highlighted_pixels = np.sum(intersection > 0)
        if highlighted_pixels > 0:
            img[intersection > 0] = color
    except Exception as e:
        logger.error(f"Error highlighting interaction zone: {e}")
