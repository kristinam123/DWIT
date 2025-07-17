"""Contact detection utilities for droplet analysis in MesszelleApp."""

from typing import Optional

import cv2

from src.utilities.logging_manager import get_logger

# Setup logger for this module
logger = get_logger(__name__)


def _check_single_line_contact(
    contour_points,
    vertical_line: tuple[int, int, int, int],
    contact_threshold: int,
) -> bool:
    """Check if contour makes contact with a single vertical line.

    Args:
    ----
        contour_points: Array of contour points
        vertical_line: Vertical line coordinates (x1, y1, x2, y2)
        contact_threshold: Distance threshold in pixels for contact detection
        line_name: Name of the line for logging purposes

    Returns:
    -------
        bool: True if contact is detected, False otherwise

    """
    x1, y1, x2, y2 = vertical_line
    line_x = int(x1)  # Convert numpy int to regular int if needed

    # Find contour points close to the line
    for point in contour_points:
        px, py = point
        # Check if point is within threshold distance of the vertical line
        if abs(px - line_x) <= contact_threshold and min(int(y1), int(y2)) <= py <= max(
            int(y1), int(y2)
        ):
            return True
    return False


def _prepare_contour_points(contour):
    """Extract and prepare contour points for processing.

    Args:
    ----
        contour: The contour to process

    Returns:
    -------
        Array of contour points or None if invalid

    """
    if contour is None or len(contour) == 0:
        logger.warning("No contour provided for contact detection")
        return None

    # Extract contour points
    contour_points = contour.reshape(-1, 2) if len(contour.shape) == 3 else contour
    return contour_points


def detect_vertical_line_contact(
    contour,
    vertical_left: tuple[int, int, int, int],
    vertical_right: tuple[int, int, int, int],
    contact_threshold: int = 3,
) -> tuple[bool, bool]:
    """Detect if a contour makes contact with vertical lines.

    Checks contact with left and right boundaries.

    Args:
    ----
        contour: The contour to check for contact
        vertical_left: Left vertical line coordinates (x1, y1, x2, y2)
        vertical_right: Right vertical line coordinates (x1, y1, x2, y2)
        contact_threshold: Distance threshold in pixels for contact detection

    Returns:
    -------
        tuple[bool, bool]: (left_contact, right_contact) indicating contact
        with each line

    """
    contour_points = _prepare_contour_points(contour)
    if contour_points is None:
        return False, False

    try:
        left_contact = False
        right_contact = False

        # Check contact with left vertical line
        if vertical_left is not None:
            left_contact = _check_single_line_contact(
                contour_points, vertical_left, contact_threshold
            )

        # Check contact with right vertical line
        if vertical_right is not None:
            right_contact = _check_single_line_contact(
                contour_points, vertical_right, contact_threshold
            )

        logger.info(
            f"Contact detection results: left={left_contact}, right={right_contact}"
        )
        return left_contact, right_contact

    except Exception as e:
        logger.error(f"Error during contact detection: {e}")
        return False, False


def get_contact_frame_status(
    left_contact_frame: Optional[int],
    right_contact_frame: Optional[int],
) -> str:
    """Get the contact status string for display purposes.

    Args:
    ----
        left_contact_frame: Frame number when left contact first occurred
            (None if not yet)
        right_contact_frame: Frame number when right contact first occurred
            (None if not yet)

    Returns:
    -------
        str: Status string describing current contact state

    """
    status_parts = []

    if left_contact_frame is not None:
        status_parts.append(f"Left: Frame {left_contact_frame}")
    else:
        status_parts.append("Left: No contact")

    if right_contact_frame is not None:
        status_parts.append(f"Right: Frame {right_contact_frame}")
    else:
        status_parts.append("Right: No contact")

    status_string = " | ".join(status_parts)
    return status_string


def draw_contact_indicators(
    image,
    vertical_left: tuple[int, int, int, int],
    vertical_right: tuple[int, int, int, int],
    left_contact: bool,
    right_contact: bool,
    left_contact_frame: Optional[int] = None,
    right_contact_frame: Optional[int] = None,
    current_frame: int = 0,
):
    """Draw visual indicators for contact detection on the image.

    Args:
    ----
        image: Image to draw on
        vertical_left: Left vertical line coordinates
        vertical_right: Right vertical line coordinates
        left_contact: Whether left contact is currently detected
        right_contact: Whether right contact is currently detected
        left_contact_frame: Frame number of first left contact (None if not yet)
        right_contact_frame: Frame number of first right contact (None if not yet)
        current_frame: Current frame number

    """
    if image is None:
        logger.warning("No image provided for drawing contact indicators")
        return

    try:
        # Colors for contact indicators
        contact_color = (0, 255, 0)  # Green for contact
        no_contact_color = (0, 0, 255)  # Red for no contact

        # Draw contact indicators on vertical lines
        if vertical_left is not None:
            x1_l, y1_l, x2_l, y2_l = vertical_left
            x1_l, y1_l, x2_l, y2_l = (
                int(x1_l),
                int(y1_l),
                int(x2_l),
                int(y2_l),
            )  # Convert numpy ints
            color = contact_color if left_contact else no_contact_color
            # Draw a small circle at the top of the left line
            cv2.circle(image, (x1_l, y1_l), 8, color, -1)

        if vertical_right is not None:
            x1_r, y1_r, x2_r, y2_r = vertical_right
            x1_r, y1_r, x2_r, y2_r = (
                int(x1_r),
                int(y1_r),
                int(x2_r),
                int(y2_r),
            )  # Convert numpy ints
            color = contact_color if right_contact else no_contact_color
            # Draw a small circle at the top of the right line
            cv2.circle(image, (x1_r, y1_r), 8, color, -1)

    except Exception as e:
        logger.error(f"Error drawing contact indicators: {e}")
