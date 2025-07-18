"""Packing utilities for droplet and experiment analysis in MesszelleApp."""

import cv2

from src.utilities.logging_manager import get_logger

# Setup logger for this module
logger = get_logger(__name__)


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
        # and ADD 1 pixel to right edge
        left_edge_x = leftmost_x - 1  # 1 pixel to the left of the leftmost point
        right_edge_x = rightmost_x + 1  # 1 pixel to the right of the rightmost point

        # The vertical lines go from top to bottom of the image
        left_line = (left_edge_x, 0, left_edge_x, image.shape[0])
        right_line = (right_edge_x, 0, right_edge_x, image.shape[0])

        logger.debug(
            f"Successfully found vertical lines: left={left_line}, right={right_line}"
        )
        return left_line, right_line

    except Exception as e:
        logger.error(f"Failed to find vertical lines: {e}")
        return None, None
