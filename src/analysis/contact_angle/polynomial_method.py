"""Polynomial-based contact angle calculation methods."""

import numpy as np

from src.utilities.core_utils import get_logger

# Setup logger for this module
logger = get_logger(__name__)


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
