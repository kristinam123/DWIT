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
    parameters: dict | None = None,
    folder_name: str | None = None,
    file_names: str | None = None,
) -> None:
    """Save measurement results to Excel in the specified directory.

    Args:
    ----
        output_dir: Directory to save results
        (Excel is written directly into this directory as `results_raw.xlsx`)
        times: Time values per frame (seconds or index)
        result_lists: Dictionary containing measurement results
            (see documentation for expected keys)

        parameters: Optional dictionary of analysis parameters to save alongside
            the results (e.g., pixel, fps, threshold, rotate_angle, etc.).
        folder_name: Optional short folder name (not full path) where the
            image series resides. This will be saved in a `Folder` column.
        file_names: Optional file names (including extension) of the image
            series used for analysis. This will be saved in a `FileName` column.

    """
    # Extract and process data from result_lists
    extracted_data = _extract_data_from_results(result_lists, len(times))

    # Check for data availability
    availability = _check_data_availability(extracted_data)

    # Extract center coordinates
    coordinates = _extract_center_coordinates(
        extracted_data["centers"], extracted_data["centers_mm"]
    )

    # Create raw data dictionary
    raw_data = _create_raw_data_dict(times, extracted_data, coordinates, availability)

    # Prepare parameter rows (inline) and FileName column values using helpers
    meta_rows = _prepare_meta_rows(folder_name, parameters)
    file_col_values = _prepare_file_col_values(file_names, times)

    # Assemble final data dict with FileName and Time columns first
    data_with_files = _assemble_data_with_files(raw_data, times, file_col_values)

    # Save raw data with specific formatting. Write a file named
    # `results_raw.xlsx` directly into the provided `output_dir`.
    excel_filename = "results_raw.xlsx"
    # Ensure the output directory exists
    try:
        os.makedirs(output_dir, exist_ok=True)
    except Exception as e:
        logger.error(f"Failed to create output directory '{output_dir}': {e}")
        # Fall back to current directory
        output_dir = os.getcwd()
    _save_dataframe_to_excel(data_with_files, output_dir, excel_filename, meta_rows)


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
        "area_px": ensure_list(
            result_lists.get("area_px", [float("nan")] * num_times), num_times
        ),
        "area_mm": ensure_list(
            result_lists.get("area_mm", [float("nan")] * num_times), num_times
        ),
        "diameter_px": ensure_list(
            result_lists.get("diameter_px", [float("nan")] * num_times), num_times
        ),
        "diameter_mm": ensure_list(
            result_lists.get("diameter_mm", [float("nan")] * num_times), num_times
        ),
        "rect_width_px": ensure_list(result_lists["rect_width_px"], num_times),
        "rect_height_px": ensure_list(result_lists["rect_height_px"], num_times),
        "rect_width_mm": ensure_list(result_lists["rect_width_mm"], num_times),
        "rect_height_mm": ensure_list(result_lists["rect_height_mm"], num_times),
        "ellipse_diameter_px": ensure_list(
            result_lists.get("ellipse_diameter_px", [float("nan")] * num_times),
            num_times,
        ),
        "ellipse_diameter_mm": ensure_list(
            result_lists.get("ellipse_diameter_mm", [float("nan")] * num_times),
            num_times,
        ),
        "velocities": ensure_list(result_lists["velocity"], num_times),
        "area_diameter_px": ensure_list(
            result_lists.get("area_diameter_px", [float("nan")] * num_times), num_times
        ),
        "area_diameter_mm": ensure_list(
            result_lists.get("area_diameter_mm", [float("nan")] * num_times), num_times
        ),
        "centers": ensure_list(result_lists["center_points_px"], num_times),
        "centers_mm": ensure_list(result_lists["center_points_mm"], num_times),
        "contact_line_px": ensure_list(result_lists["contact_line_px"], num_times),
        "contact_line_mm": ensure_list(result_lists["contact_line_mm"], num_times),
    }

    # Process discontinuous velocities
    data["discontinuous_velocity_px_s"] = ensure_list(
        result_lists.get("discontinuous_velocity_px_s"), num_times
    )
    data["discontinuous_velocity_mm_s"] = ensure_list(
        result_lists.get("discontinuous_velocity_mm_s"), num_times
    )

    # Process additional structured packing metrics
    data["vertical_line_distance_px"] = ensure_list(
        result_lists.get("vertical_line_distance_px"), num_times
    )
    data["vertical_line_distance_mm"] = ensure_list(
        result_lists.get("vertical_line_distance_mm"), num_times
    )
    data["contact_time_frames"] = ensure_list(
        result_lists.get("contact_time_frames"), num_times
    )
    data["contact_time_seconds"] = ensure_list(
        result_lists.get("contact_time_seconds"), num_times
    )

    return data


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
            if (
                isinstance(point, (list, tuple))
                and len(point) >= 2
                and point[0] is not None
                and point[1] is not None
            ):
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
        "Area [px]": extracted_data["area_px"],
        "Area [mm]": extracted_data["area_mm"],
        "Diameter [px]": extracted_data["diameter_px"],
        "Diameter [mm]": extracted_data["diameter_mm"],
        "Contour width [px]": extracted_data["rect_width_px"],
        "Contour height [px]": extracted_data["rect_height_px"],
        "Contour width [mm]": extracted_data["rect_width_mm"],
        "Contour height [mm]": extracted_data["rect_height_mm"],
        "Ellipse diameter [px]": extracted_data["ellipse_diameter_px"],
        "Ellipse diameter [mm]": extracted_data["ellipse_diameter_mm"],
        "X of center [px]": coordinates["centers_x"],
        "Y of center [px]": coordinates["centers_y"],
        "X of center [mm]": coordinates["centers_x_mm"],
        "Y of center [mm]": coordinates["centers_y_mm"],
        "Velocity": extracted_data["velocities"],
        "Area diameter [px]": extracted_data["area_diameter_px"],
        "Area diameter [mm]": extracted_data["area_diameter_mm"],
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


def _save_dataframe_to_excel(data_dict, output_dir, filename, meta_rows=None):
    """Save a data dictionary to Excel with consistent formatting and error handling.

    Args:
    ----
        data_dict: Dictionary where keys are column names and values are lists of data
        output_dir: Directory to save the Excel file
        filename: Excel filename
        description: Description
        meta_rows: Optional list of (key, value) tuples to write above the table

    """
    excel_path = os.path.join(output_dir, filename)

    # Build DataFrame from provided data dictionary
    df = _build_dataframe_from_dict(data_dict)

    # Insert meta rows (if any) into the DataFrame
    _insert_meta_rows_into_df(df, meta_rows)

    try:
        # Save DataFrame to Excel
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


def _build_dataframe_from_dict(data_dict):
    """Build a pandas DataFrame from a dict of column->list, padding shorter lists.

    Keeps behavior identical to the previous inline implementation.
    """
    # Determine number of rows
    num_rows = max(len(values) for values in data_dict.values()) if data_dict else 0

    # Convert dictionary to padded dict for DataFrame
    df_data = {}
    for key, values in data_dict.items():
        if len(values) < num_rows:
            padded_values = values + [np.nan] * (num_rows - len(values))
        else:
            padded_values = values
        df_data[key] = padded_values

    return pd.DataFrame(df_data)


def _insert_meta_rows_into_df(df: pd.DataFrame, meta_rows: list | None):
    """Insert meta rows (list of (label, val)) into the first rows of `df`.

    This helper isolates the parameter insertion logic and handles its own
    error logging so the caller remains simple and testable.
    """
    if not meta_rows:
        return

    try:
        if "Parameter" not in df.columns:
            df["Parameter"] = np.nan
        if "Value" not in df.columns:
            df["Value"] = np.nan

        # Ensure object dtype so string assignment doesn't trigger dtype warnings
        try:
            df["Parameter"] = df["Parameter"].astype("object")
            df["Value"] = df["Value"].astype("object")
        except Exception:
            # Best-effort: if astype fails, continue and rely on pandas coercion
            pass

        for i, (label, val) in enumerate(meta_rows):
            if i >= len(df):
                break
            df.at[i, "Parameter"] = label
            df.at[i, "Value"] = val
    except Exception as e:
        logger.warning("Failed to write inline parameters into first rows: %s", e)


def _prepare_meta_rows(folder_name, parameters):
    """Prepare metadata rows (Folder and parameters) for Excel export.

    Returns a list of (key, value) tuples.
    """
    meta_rows: list[tuple[str, str]] = []
    # Prefer full path for folder entry
    if folder_name is not None:
        meta_rows.append(("Folder", str(folder_name)))
    else:
        meta_rows.append(("Folder", ""))

    params = parameters or {}
    caption_map = {
        "fps": "FPS [1/s]",
        "pixel": "Pixel [px/mm]",
        "threshold": "Threshold",
        "rotate_angle": "Rotate Angle [Deg]",
        "baseline": "Baseline Offset [px]",
        "fitting_mode": "Fitting Mode",
        "polynom": "Polynom",
        "baseline_tf": "Manual Baseline On",
        "manual_baseline": "Manual Baseline Height [px]",
        "x_img": "ROI X [px]",
        "y_img": "ROI Y [px]",
        "w_img": "ROI W [px]",
        "h_img": "ROI H [px]",
    }

    ordered_keys = [
        "fps",
        "pixel",
        "threshold",
        "rotate_angle",
        "baseline",
        "baseline_tf",
        "manual_baseline",
        "fitting_mode",
        "polynom",
        "x_img",
        "y_img",
        "w_img",
        "h_img",
    ]
    used = set()
    # First, add known keys in desired order if present
    for key in ordered_keys:
        if key in params:
            val = params[key]
            caption = caption_map.get(key, str(key))
            meta_rows.append((caption, "" if val is None else str(val)))
            used.add(key)
    # Then, add any remaining keys in original insertion order
    for key, val in params.items():
        if key in used:
            continue
        caption = caption_map.get(key, str(key))
        meta_rows.append((caption, "" if val is None else str(val)))

    return meta_rows


def _prepare_file_col_values(file_names, times):
    """Prepare `FileName` column values matching the length of `times`.

    Handles single string, semicolon-separated strings, lists, and errors.
    """
    if file_names:
        try:
            if isinstance(file_names, str) and ";" in file_names:
                parts = [p for p in file_names.split(";") if p]
            elif isinstance(file_names, str):
                parts = [file_names]
            else:
                parts = list(file_names)
            basenames = [os.path.basename(p) for p in parts]
            if len(basenames) == len(times):
                return basenames
            if len(basenames) > 0:
                return [basenames[0]] * len(times)
            return [""] * len(times)
        except Exception:
            return [str(file_names)] * len(times)
    return [""] * len(times)


def _assemble_data_with_files(raw_data, times, file_col_values):
    """Ensure 'Time' exists and assemble final data dict with FileName first.

    Returns a new dict suitable for DataFrame construction.
    """
    if "Time" not in raw_data:
        raw_data["Time"] = times

    data_with_files = {"FileName": file_col_values}
    data_with_files["Time"] = raw_data.pop("Time")
    for key, val in raw_data.items():
        data_with_files[key] = val
    return data_with_files
