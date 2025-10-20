"""Ellipse-based contact angle calculation methods."""

import numpy as np
from scipy.optimize import curve_fit, leastsq

from src.utilities.core_utils import get_logger

# Setup logger for this module
logger = get_logger(__name__)


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
