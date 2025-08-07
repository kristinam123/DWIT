"""Result saving utilities.

For exporting experiment data in Droplet Wall Interaction Tool.
"""

import os
import time
from typing import Union

import numpy as np
import pandas as pd

from src.utilities.logging_manager import get_logger

# Setup logger for this module
logger = get_logger(__name__)


def save_results(
    output_dir: str,
    times: list[Union[float, str]],
    result_lists: dict[str, list[Union[float, str]]],
) -> None:
    """Save measurement results as plots and Excel in the specified directory.

    Args:
    ----
        output_dir: Directory to save results
        times: Time values for x-axis
        result_lists: Dictionary containing measurement results

    """
    logger.debug(
        f"save_results called with times: {len(times)}, "
        f"result_lists keys: {list(result_lists.keys())}"
    )

    # Prepare output directory
    if not _prepare_output_directory(output_dir):
        logger.error(f"Failed to create or access output directory: {output_dir}")
        return

    # Extract and process data from result_lists
    extracted_data = _extract_data_from_results(result_lists, len(times))
    logger.debug(f"Extracted data keys: {list(extracted_data.keys())}")

    # Check for data availability
    availability = _check_data_availability(extracted_data)
    logger.debug(f"Data availability: {availability}")

    # Extract center coordinates
    coordinates = _extract_center_coordinates(
        extracted_data["centers"], extracted_data["centers_mm"]
    )
    logger.debug(f"Extracted coordinates: {coordinates}")

    # Create raw data dictionary
    raw_data = _create_raw_data_dict(times, extracted_data, coordinates, availability)
    logger.debug(f"Raw data keys: {list(raw_data.keys())}")

    # Save raw data with specific formatting
    # Save Excel file in parent of Output, prefix with folder name
    parent_dir = os.path.dirname(output_dir.rstrip(os.sep))
    folder_name = os.path.basename(parent_dir)
    # Sanitize folder name for filename: remove invalid/special characters
    import re

    sanitized_folder_name = re.sub(r'[\\/:*?"<>|]', "_", folder_name)
    # Warn if non-ASCII characters are present
    if not all(ord(c) < 128 for c in sanitized_folder_name):
        logger.warning(
            f"Folder name '{folder_name}' contains non-ASCII characters. "
            f"This may cause issues on some systems."
        )
    excel_filename = f"{sanitized_folder_name}_results_raw.xlsx"
    _save_dataframe_to_excel(raw_data, parent_dir, excel_filename)


def _extract_data_from_results(result_lists, num_times):
    """Extract and process data from result lists.

    Args:
    ----
        result_lists: Dictionary containing measurement results
        num_times: Number of time points

    Returns:
    -------
        Dictionary containing extracted data

    """

    def ensure_list(val, n):
        if isinstance(val, list):
            return val
        return [val] * n

    data = {
        "advancing_angles": ensure_list(
            result_lists["advancing_contact_angles"], num_times
        ),
        "receding_angles": ensure_list(
            result_lists["receding_contact_angles"], num_times
        ),
        "rect_width_px": ensure_list(result_lists["rect_width_px"], num_times),
        "rect_height_px": ensure_list(result_lists["rect_height_px"], num_times),
        "rect_width_mm": ensure_list(result_lists["rect_width_mm"], num_times),
        "rect_height_mm": ensure_list(result_lists["rect_height_mm"], num_times),
        "velocities": ensure_list(result_lists["velocity"], num_times),
        "centers": ensure_list(result_lists["center_points_px"], num_times),
        "centers_mm": ensure_list(result_lists["center_points_mm"], num_times),
        "contact_line_px": ensure_list(result_lists["contact_line_px"], num_times),
        "contact_line_mm": ensure_list(result_lists["contact_line_mm"], num_times),
    }

    # Process discontinuous velocities
    dv_px_s_val = result_lists.get("discontinuous_velocity_px_s")
    dv_mm_s_val = result_lists.get("discontinuous_velocity_mm_s")

    if isinstance(dv_px_s_val, (float, int)):
        data["discontinuous_velocity_px_s"] = [dv_px_s_val] * num_times
    else:
        data["discontinuous_velocity_px_s"] = [float("nan")] * num_times

    if isinstance(dv_mm_s_val, (float, int)):
        data["discontinuous_velocity_mm_s"] = [dv_mm_s_val] * num_times
    else:
        data["discontinuous_velocity_mm_s"] = [float("nan")] * num_times

    return data


def _prepare_output_directory(output_dir):
    """Create output directory if it doesn't exist.

    Args:
    ----
        output_dir: Directory to create

    Returns:
    -------
        Boolean indicating if directory was created successfully

    """
    try:
        os.makedirs(output_dir, exist_ok=True)
        return True
    except (PermissionError, OSError) as e:
        logger.error(f"Failed to create output directory {output_dir}: {e}")
        return False


def _check_data_availability(data):
    """Check for availability of different data types.

    Args:
    ----
        data: Dictionary containing extracted data

    Returns:
    -------
        Dictionary with boolean flags for available data types

    """
    # Check if contact angle data is available
    has_angle_data = (
        data["advancing_angles"]
        and any(
            val
            for val in data["advancing_angles"]
            if val not in (None, "", float("nan"))
        )
    ) or (
        data["receding_angles"]
        and any(
            val
            for val in data["receding_angles"]
            if val not in (None, "", float("nan"))
        )
    )

    # Check if contact line data is available
    has_contact_line_data = data["contact_line_mm"] and any(
        val for val in data["contact_line_mm"] if val not in (None, "", float("nan"))
    )

    return {
        "has_angle_data": has_angle_data,
        "has_contact_line_data": has_contact_line_data,
    }


def _extract_center_coordinates(centers, centers_mm):
    """Extract x and y coordinates from center points.

    Args:
    ----
        centers: List of center points in pixels
        centers_mm: List of center points in mm

    Returns:
    -------
        Dictionary containing extracted coordinates

    """
    # Extract x and y coordinates from centers
    centers_x = []
    centers_y = []
    for point in centers:
        if (
            isinstance(point, (list, tuple))
            and len(point) >= 2
            and point[0] is not None
            and point[1] is not None
        ):
            centers_x.append(float(point[0]))
            centers_y.append(float(point[1]))
        else:
            centers_x.append(float("nan"))
            centers_y.append(float("nan"))

    # Extract x and y coordinates from centers_mm if it contains coordinate pairs
    centers_x_mm = []
    centers_y_mm = []
    if (
        centers_mm
        and isinstance(centers_mm[0], (list, tuple))
        and len(centers_mm[0]) >= 2
    ):
        for point in centers_mm:
            if isinstance(point, (list, tuple)) and len(point) >= 2:
                centers_x_mm.append(float(point[0]))
                centers_y_mm.append(float(point[1]))
            else:
                centers_x_mm.append(float("nan"))
                centers_y_mm.append(float("nan"))
    else:
        # If centers_mm is just a list of x-coordinates
        centers_x_mm = centers_mm
        centers_y_mm = [float("nan")] * len(centers_mm)

    return {
        "centers_x": centers_x,
        "centers_y": centers_y,
        "centers_x_mm": centers_x_mm,
        "centers_y_mm": centers_y_mm,
    }


def _create_raw_data_dict(times, extracted_data, coordinates, availability):
    """Create raw data dictionary for export and plotting.

    Args:
    ----
        times: Time values
        extracted_data: Dictionary with extracted data
        coordinates: Dictionary with center coordinates
        availability: Dictionary with data availability flags

    Returns:
    -------
        Dictionary containing organized raw data

    """
    raw_data = {
        "Time": times,
        "Contour width [px]": extracted_data["rect_width_px"],
        "Contour height [px]": extracted_data["rect_height_px"],
        "Contour width [mm]": extracted_data["rect_width_mm"],
        "Contour height [mm]": extracted_data["rect_height_mm"],
        "X of center [px]": coordinates["centers_x"],
        "Y of center [px]": coordinates["centers_y"],
        "X of center [mm]": coordinates["centers_x_mm"],
        "Y of center [mm]": coordinates["centers_y_mm"],
        "Velocity": extracted_data["velocities"],
        "Discontinuous Velocity [px/s]": extracted_data["discontinuous_velocity_px_s"],
        "Discontinuous Velocity [mm/s]": extracted_data["discontinuous_velocity_mm_s"],
    }

    # Only add angle data if available
    if availability["has_angle_data"]:
        raw_data["Advancing CA"] = extracted_data["advancing_angles"]
        raw_data["Receding CA"] = extracted_data["receding_angles"]

    # Only add contact line data if available
    if availability["has_contact_line_data"]:
        raw_data["Contact line [px]"] = extracted_data["contact_line_px"]
        raw_data["Contact line [mm]"] = extracted_data["contact_line_mm"]

    return raw_data


def _save_dataframe_to_excel(data_dict, output_dir, filename):
    """Save a data dictionary to Excel with consistent formatting and error handling.

    Args:
    ----
        data_dict: Dictionary where keys are column names and values are lists of data
        output_dir: Directory to save the Excel file
        filename: Excel filename
        description: Description

    """
    excel_path = os.path.join(output_dir, filename)

    # Determine number of rows
    num_rows = max(len(values) for values in data_dict.values()) if data_dict else 0

    # Convert dictionary to DataFrame
    df_data = {}
    for key, values in data_dict.items():
        # Create a series of the right length, filling with NaN if needed
        if len(values) < num_rows:
            padded_values = values + [np.nan] * (num_rows - len(values))
        else:
            padded_values = values
        df_data[key] = padded_values

    # Create DataFrame
    df = pd.DataFrame(df_data)

    try:
        # Save DataFrame to Excel file with NaN/INF handling
        df.to_excel(excel_path, index=False, na_rep="", float_format="%.6f")
        logger.info(f"Successfully saved Excel file: {excel_path}")
        return True
    except (PermissionError, OSError) as e:
        logger.error(f"Failed to save Excel file: {e}")
        # Try with a different filename
        if "raw" in filename:  # Only try alternative name for raw data
            alternative_path = os.path.join(
                output_dir, f"{os.path.splitext(filename)[0]}_{int(time.time())}.xlsx"
            )
            logger.warning(f"Trying alternative filename: {alternative_path}")
            try:
                df.to_excel(
                    alternative_path, index=False, na_rep="", float_format="%.6f"
                )
                logger.info(
                    f"Successfully saved Excel file with alternative name: "
                    f"{alternative_path}"
                )
                return True
            except (PermissionError, OSError) as e:
                logger.error(f"Failed to save Excel file with alternative name: {e}")
        return False
