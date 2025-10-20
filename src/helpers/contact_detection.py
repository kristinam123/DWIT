"""Contact detection utilities for droplet analysis in Droplet Wall Interaction Tool."""

from src.utilities.core_utils import get_logger

# Setup logger for this module
logger = get_logger(__name__)


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


def get_contact_frame_status(
    left_contact_frame: int | None,
    right_contact_frame: int | None,
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
