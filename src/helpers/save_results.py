"""Result saving utilities.

For exporting experiment data in Droplet Wall Interaction Tool.
"""

import os
import time
from typing import Union

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import xlsxwriter
from scipy.fft import fft, fftfreq
from scipy.optimize import curve_fit

from src.utilities.conversion import convert_to_float_list
from src.utilities.logging_manager import get_logger

# Configure matplotlib to use non-interactive backend
matplotlib.use("Agg")
plt.ioff()  # Turn off interactive mode


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

    ################################# DISABLED ########################################
    # # Process and filter data
    # filtered_data = _process_and_filter_data(raw_data, times, availability)

    # # Save filtered data
    # _save_dataframe_to_excel(filtered_data, output_dir, "results_filtered.xlsx")

    # # Generate plots
    # _generate_plots(raw_data, filtered_data, output_dir, availability)

    # # Analyze wobble
    # _analyze_wobble(output_dir=output_dir, times=times, result_lists=result_lists)
    ###################################################################################


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


def _process_and_filter_data(raw_data, times, availability):
    """Process and filter data including outlier removal.

    Args:
    ----
        raw_data: Dictionary with raw data
        times: Time values
        availability: Dictionary with data availability flags

    Returns:
    -------
        Dictionary containing filtered data

    """
    # Create filtered data by removing first and last 0.1s and shifting times by 0.05s
    filtered_times, filtered_data = _filter_time_series_data(times, raw_data)

    # Apply outlier removal specifically for contact angles if available
    if (
        availability["has_angle_data"]
        and "Advancing CA" in filtered_data
        and "Receding CA" in filtered_data
    ):
        adv_times, adv_angles = _remove_outliers(
            filtered_data["Advancing CA"], "Advancing Contact Angles", 1.0
        )
        rec_times, rec_angles = _remove_outliers(
            filtered_data["Receding CA"], "Receding Contact Angles", 1.0
        )

        # Create new angle data with values only at positions where both have valid data
        filtered_data["Advancing CA"] = [float("nan")] * len(filtered_times)
        filtered_data["Receding CA"] = [float("nan")] * len(filtered_times)

        # Map the filtered angles back to their corresponding time indices
        for i, t_idx in enumerate(adv_times):
            if t_idx < len(filtered_times):
                filtered_data["Advancing CA"][t_idx] = adv_angles[i]

        for i, t_idx in enumerate(rec_times):
            if t_idx < len(filtered_times):
                filtered_data["Receding CA"][t_idx] = rec_angles[i]

    return filtered_data


def _generate_plots(raw_data, filtered_data, output_dir, availability):
    """Generate all plots for the results.

    Args:
    ----
        raw_data: Dictionary with raw data
        filtered_data: Dictionary with filtered data
        output_dir: Output directory for plots
        availability: Dictionary with data availability flags

    """
    # Plot raw data for different measurements
    _plot_data(
        raw_data,
        output_dir,
        "contour.png",
        ["Contour width [mm]", "Contour height [mm]"],
        "Contour",
    )
    _plot_data(
        raw_data,
        output_dir,
        "center.png",
        ["X of center [mm]", "Y of center [mm]"],
        "Center",
    )
    _plot_data(raw_data, output_dir, "velocity.png", ["Velocity"], "Velocity")

    # Plot angles only if data is available
    if availability["has_angle_data"]:
        _plot_data(
            raw_data,
            output_dir,
            "angles.png",
            ["Advancing CA", "Receding CA"],
            "Angles",
        )
        _plot_data(
            filtered_data,
            output_dir,
            "angles_filtered.png",
            ["Advancing CA", "Receding CA"],
            "Angles",
        )

    # Plot contact line only if data is available
    if availability["has_contact_line_data"]:
        _plot_data(
            raw_data,
            output_dir,
            "contact_line.png",
            ["Contact line [mm]"],
            "Contact Line",
        )
        _plot_data(
            filtered_data,
            output_dir,
            "contact_line_filtered.png",
            ["Contact line [mm]"],
            "Contact Line",
        )

    # Plot filtered data for other measurements
    _plot_data(
        filtered_data,
        output_dir,
        "contour_filtered.png",
        ["Contour width [mm]", "Contour height [mm]"],
        "Contour",
    )
    _plot_data(
        filtered_data,
        output_dir,
        "center_filtered.png",
        ["X of center [mm]", "Y of center [mm]"],
        "Center",
    )
    _plot_data(
        filtered_data,
        output_dir,
        "velocity_filtered.png",
        ["Velocity"],
        "Velocity",
    )


def _analyze_wobble(
    output_dir: str,
    times: list[float],
    result_lists: dict[str, list[float]],
) -> None:
    """Analyzes the wobble (oscillation) of drops based on contour dimensions.

    Args:
    ----
        output_dir: Directory to save results
        times: Time values for x-axis
        result_lists: Dictionary containing measurement results

    """
    rect_width_mm = result_lists["rect_width_mm"]
    rect_height_mm = result_lists["rect_height_mm"]
    os.makedirs(output_dir, exist_ok=True)

    # Step 1: Prepare and validate the input data
    data_dict = _prepare_wobble_data(times, rect_width_mm, rect_height_mm)
    if data_dict is None:
        return

    # Step 2: Filter data to include only valid points
    filtered_data = _filter_valid_data(data_dict)
    if filtered_data is None:
        return

    # Raw data for Excel output
    raw_data = {
        "Time (s)": filtered_data["times_array"],
        "Width (mm)": filtered_data["rect_w_mm"],
        "Height (mm)": filtered_data["rect_h_mm"],
    }

    # Step 3: Perform curve fitting
    fit_results = _perform_sine_fitting(filtered_data)

    # Step 4: Create and save the plot
    _create_wobble_plot(fit_results, output_dir)

    # Step 5: Save results to Excel
    _save_wobble_results_to_excel(fit_results, raw_data, output_dir)


def _prepare_wobble_data(times, rect_width_mm, rect_height_mm):
    """Prepare and validate data for wobble analysis.

    Args:
    ----
        times: Time values
        rect_width_mm: Rectangle width values in mm
        rect_height_mm: Rectangle height values in mm

    Returns:
    -------
        Dictionary with prepared data or None if preparation failed

    """
    try:
        # Convert all inputs to numpy arrays and ensure they're 1D arrays
        times_array = np.asarray(convert_to_float_list(times), dtype=float).ravel()
        rect_w_mm = np.asarray(
            convert_to_float_list(rect_width_mm), dtype=float
        ).ravel()
        rect_h_mm = np.asarray(
            convert_to_float_list(rect_height_mm), dtype=float
        ).ravel()
    except (ValueError, TypeError) as e:
        logger.error(f"Failed to convert to float list: {e}")
        return None

    # Ensure all arrays have the same length before masking
    min_length = min(len(times_array), len(rect_w_mm), len(rect_h_mm))
    if min_length == 0:
        return None

    times_array = times_array[:min_length]
    rect_w_mm = rect_w_mm[:min_length]
    rect_h_mm = rect_h_mm[:min_length]

    # Handle scalar inputs
    if times_array.ndim == 0:
        times_array = np.array([float(times_array)])
    if rect_w_mm.ndim == 0:
        rect_w_mm = np.array([float(rect_w_mm)])
    if rect_h_mm.ndim == 0:
        rect_h_mm = np.array([float(rect_h_mm)])

    return {"times_array": times_array, "rect_w_mm": rect_w_mm, "rect_h_mm": rect_h_mm}


def _filter_valid_data(data_dict):
    """Filter data to include only valid points with positive times.

    Args:
    ----
        data_dict: Dictionary with raw data arrays

    Returns:
    -------
        Dictionary with filtered data or None if filtering failed

    """
    times_array = data_dict["times_array"]
    rect_w_mm = data_dict["rect_w_mm"]
    rect_h_mm = data_dict["rect_h_mm"]

    # Create and validate the positive time mask
    try:
        positive_time_mask = times_array >= 0
        if not np.any(positive_time_mask):
            return None

        # Apply the mask using boolean indexing
        times_array = times_array[positive_time_mask]
        rect_w_mm = rect_w_mm[positive_time_mask]
        rect_h_mm = rect_h_mm[positive_time_mask]

        # Log removed points
        removed_count = np.sum(~positive_time_mask)
        if removed_count > 0:
            logger.info(f"Removed {removed_count} points with negative time")
    except Exception as e:
        logger.error(f"Failed to create positive time mask: {e}")
        return None

    # Create masks for valid values (not NaN)
    try:
        valid_w_mm = ~np.isnan(rect_w_mm)
        valid_h_mm = ~np.isnan(rect_h_mm)
        valid_times = ~np.isnan(times_array)

        # Combine all validity masks
        valid_mask = valid_times & valid_w_mm & valid_h_mm

        # Apply the combined mask
        times_valid = times_array[valid_mask]
        rect_w_mm_valid = rect_w_mm[valid_mask]
        rect_h_mm_valid = rect_h_mm[valid_mask]

        # Check if we have enough valid data
        if len(times_valid) < 5:
            return None
    except Exception as e:
        logger.error(f"Failed to create valid mask: {e}")
        return None

    return {
        "times_array": times_array,
        "rect_w_mm": rect_w_mm,
        "rect_h_mm": rect_h_mm,
        "times_valid": times_valid,
        "rect_w_mm_valid": rect_w_mm_valid,
        "rect_h_mm_valid": rect_h_mm_valid,
    }


def _perform_sine_fitting(data_dict):
    """Perform linear regression and sine fitting on valid data.

    Args:
    ----
        data_dict: Dictionary with filtered valid data

    Returns:
    -------
        Dictionary with fitting results

    """
    times_valid = data_dict["times_valid"]
    rect_w_mm_valid = data_dict["rect_w_mm_valid"]
    rect_h_mm_valid = data_dict["rect_h_mm_valid"]

    # Calculate means (averages) for the complete dataset
    mean_w_mm = np.mean(rect_w_mm_valid)
    mean_h_mm = np.mean(rect_h_mm_valid)

    # Initialize variables that will be used for plotting and analysis
    settling_idx = 0
    times_stable = times_valid
    mean_w_mm_stable = mean_w_mm
    mean_h_mm_stable = mean_h_mm

    # Define fitting functions
    def _linear_func(x, a, b):
        return a * x + b

    def _damped_sine_func(x, amp, freq, phase, offset, decay):
        """Model a damped oscillation with exponential decay."""
        return amp * np.exp(-decay * x) * np.sin(2 * np.pi * freq * x + phase) + offset

    # Fit width and height data - Linear regression
    popt_w_lin, _ = curve_fit(_linear_func, times_valid, rect_w_mm_valid)
    popt_h_lin, _ = curve_fit(_linear_func, times_valid, rect_h_mm_valid)

    # Generate linear trend values
    w_lin_trend = _linear_func(times_valid, *popt_w_lin)
    h_lin_trend = _linear_func(times_valid, *popt_h_lin)

    # Detrend data (remove linear trend)
    w_detrended = rect_w_mm_valid - w_lin_trend
    h_detrended = rect_h_mm_valid - h_lin_trend

    # Default sine parameters for cases with insufficient data
    w_sine_params = {
        "amplitude": 0,
        "frequency": 0,
        "phase": 0,
        "offset": mean_w_mm,
        "decay": 0,
    }
    h_sine_params = {
        "amplitude": 0,
        "frequency": 0,
        "phase": 0,
        "offset": mean_h_mm,
        "decay": 0,
    }
    w_sine_fit = np.ones_like(times_valid) * mean_w_mm
    h_sine_fit = np.ones_like(times_valid) * mean_h_mm

    # Perform sine fitting if we have enough data
    if len(times_valid) >= 10:
        # Define settling period (first 30% of the data or at least 8 points)
        settling_percentage = 0.3
        settling_idx = max(8, int(len(times_valid) * settling_percentage))

        # Use data AFTER settling period for ALL analysis
        times_stable = times_valid[settling_idx:]
        w_stable = rect_w_mm_valid[settling_idx:]
        h_stable = rect_h_mm_valid[settling_idx:]

        # Calculate means using ONLY stable data (after settling)
        mean_w_px_stable = np.mean(w_stable)
        mean_h_px_stable = np.mean(h_stable)
        mean_w_mm_stable = np.mean(rect_w_mm_valid[settling_idx:])
        mean_h_mm_stable = np.mean(rect_h_mm_valid[settling_idx:])

        # Try to perform sine fitting
        w_sine_params, w_sine_fit = _fit_damped_sine(
            times_stable, w_detrended[settling_idx:], mean_w_mm_stable
        )
        h_sine_params, h_sine_fit = _fit_damped_sine(
            times_stable, h_detrended[settling_idx:], mean_h_mm_stable
        )
    else:
        # Default values for insufficient data
        mean_w_px_stable = mean_w_mm
        mean_h_px_stable = mean_h_mm
        mean_w_mm_stable = mean_w_mm
        mean_h_mm_stable = mean_h_mm

    return {
        "times_valid": times_valid,
        "rect_w_mm_valid": rect_w_mm_valid,
        "rect_h_mm_valid": rect_h_mm_valid,
        "settling_idx": settling_idx,
        "times_stable": times_stable,
        "mean_w_px_stable": mean_w_px_stable,
        "mean_h_px_stable": mean_h_px_stable,
        "mean_w_mm_stable": mean_w_mm_stable,
        "mean_h_mm_stable": mean_h_mm_stable,
        "w_sine_params": w_sine_params,
        "h_sine_params": h_sine_params,
        "w_sine_fit": w_sine_fit,
        "h_sine_fit": h_sine_fit,
    }


def _fit_damped_sine(times, values, mean_value):
    """Fit a damped sine wave to the data.

    Args:
    ----
        times: Time values
        values: Data values
        mean_value: Mean of values

    Returns:
    -------
        Tuple of (sine_params, sine_fit)

    """

    # Damped sine function
    def _damped_sine_func(x, amp, freq, phase, offset, decay):
        """Model a damped oscillation with exponential decay."""
        return amp * np.exp(-decay * x) * np.sin(2 * np.pi * freq * x + phase) + offset

    # Estimate frequency using FFT
    data_fft = np.abs(fft(values - np.mean(values)))
    sample_spacing = (times[-1] - times[0]) / (len(times) - 1)
    freqs = fftfreq(len(times), sample_spacing)

    # Find dominant frequency
    pos_mask = freqs > 0
    dom_freq_idx = np.argmax(data_fft[pos_mask]) if np.any(pos_mask) else 0
    freq_guess = abs(freqs[pos_mask][dom_freq_idx]) if dom_freq_idx > 0 else 0.5

    # Parameter guesses
    amp_guess = max(0.1, min(np.std(values), np.ptp(values)))
    decay_guess = 0.1

    # Ensure frequency guess is reasonable
    freq_guess = min(max(0.1, freq_guess), 5.0) if freq_guess > 0 else 0.5

    # Bounds for curve fitting
    amp_max = np.ptp(values) * 2
    bounds = (
        [0, 0.01, -2 * np.pi, mean_value * 0.5, 0],  # Lower bounds
        [amp_max, 10, 2 * np.pi, mean_value * 1.5, 5],  # Upper bounds
    )

    try:
        # Perform damped sine fit
        popt, _ = curve_fit(
            _damped_sine_func,
            times,
            values,
            p0=[amp_guess, freq_guess, 0, mean_value, decay_guess],
            bounds=bounds,
            maxfev=10000,
        )
        sine_fit = _damped_sine_func(times, *popt)
        sine_params = {
            "amplitude": popt[0],
            "frequency": popt[1],
            "phase": popt[2],
            "offset": popt[3],
            "decay": popt[4],
        }
    except (RuntimeError, ValueError) as e:
        logger.error(f"Failed to fit sine data: {e}")
        sine_params = {
            "amplitude": 0,
            "frequency": 0,
            "phase": 0,
            "offset": mean_value,
            "decay": 0,
        }
        sine_fit = np.ones_like(times) * mean_value

    return sine_params, sine_fit


def _create_wobble_plot(fit_results, output_dir):
    """Create and save the wobble analysis plot.

    Args:
    ----
        fit_results: Dictionary with fitting results
        output_dir: Directory to save the plot

    Returns:
    -------
        Boolean indicating success or failure

    """
    try:
        # Extract data from results
        times_valid = fit_results["times_valid"]
        rect_w_mm_valid = fit_results["rect_w_mm_valid"]
        rect_h_mm_valid = fit_results["rect_h_mm_valid"]
        settling_idx = fit_results["settling_idx"]
        w_sine_fit = fit_results["w_sine_fit"]
        h_sine_fit = fit_results["h_sine_fit"]
        mean_w_mm_stable = fit_results["mean_w_mm_stable"]
        mean_h_mm_stable = fit_results["mean_h_mm_stable"]
        w_sine_params = fit_results["w_sine_params"]
        h_sine_params = fit_results["h_sine_params"]

        # Create plot
        plt.figure(figsize=(12, 8))

        # Plot width data with different styling for settling vs. stable periods
        plt.plot(
            times_valid[:settling_idx],
            rect_w_mm_valid[:settling_idx],
            "bo",
            alpha=0.3,
            markersize=3,
        )
        plt.plot(
            times_valid[settling_idx:],
            rect_w_mm_valid[settling_idx:],
            "bo",
            alpha=0.7,
            markersize=4,
            label="Width",
        )

        # Plot height data with different styling for settling vs. stable periods
        plt.plot(
            times_valid[:settling_idx],
            rect_h_mm_valid[:settling_idx],
            "ro",
            alpha=0.3,
            markersize=3,
        )
        plt.plot(
            times_valid[settling_idx:],
            rect_h_mm_valid[settling_idx:],
            "ro",
            alpha=0.7,
            markersize=4,
            label="Height",
        )

        # Add vertical line showing where settling period ends
        plt.axvline(
            x=times_valid[settling_idx],
            color="k",
            linestyle="--",
            alpha=0.5,
            label="End of settling period",
        )

        # Plot average lines (using ONLY stable data)
        plt.plot(
            times_valid[settling_idx:],
            np.ones_like(times_valid[settling_idx:]) * mean_w_mm_stable,
            "b--",
            label=f"Avg Width: {mean_w_mm_stable:.2f} mm",
            linewidth=1,
        )
        plt.plot(
            times_valid[settling_idx:],
            np.ones_like(times_valid[settling_idx:]) * mean_h_mm_stable,
            "r--",
            label=f"Avg Height: {mean_h_mm_stable:.2f} mm",
            linewidth=1,
        )

        # Plot the fits only for the stable period
        plt.plot(
            times_valid[settling_idx:],
            w_sine_fit,
            "b-",
            label=f'Width Fit: Amp={w_sine_params["amplitude"]:.2f} mm, '
            f'Freq={w_sine_params["frequency"]:.2f} Hz',
            linewidth=1.5,
        )
        plt.plot(
            times_valid[settling_idx:],
            h_sine_fit,
            "r-",
            label=f'Height Fit: Amp={h_sine_params["amplitude"]:.2f} mm, '
            f'Freq={h_sine_params["frequency"]:.2f} Hz',
            linewidth=1.5,
        )

        # Add plot details
        plt.title("Drop Wobble Analysis - Contour Dimensions Over Time")
        plt.xlabel("Time (s)")
        plt.ylabel("Dimension (mm)")
        plt.grid(True, linestyle="--", alpha=0.7)
        plt.legend()

        # Save plot with robust error handling
        plt.tight_layout()

        return _save_wobble_plot(plt, output_dir)

    except Exception as e:
        logger.error(f"Failed to create wobble plot: {e}")
        plt.close()
        return False


def _save_wobble_plot(plt, output_dir):
    """Save the wobble plot to file with error handling.

    Args:
    ----
        plt: Matplotlib pyplot object
        output_dir: Directory to save the plot

    Returns:
    -------
        Boolean indicating success or failure

    """
    plot_path = os.path.join(output_dir, "drop_wobble_analysis.jpg")
    try:
        # Ensure output directory exists
        os.makedirs(output_dir, exist_ok=True)

        # Save with explicit path formatting
        plt.savefig(plot_path, dpi=300, format="jpg", bbox_inches="tight")
        plt.close()
        return True
    except Exception as e:
        logger.error(f"Failed to save plot: {e}")
        # Try alternative location as fallback
        try:
            alt_path = os.path.join(
                os.path.dirname(output_dir), "drop_wobble_analysis.jpg"
            )
            plt.savefig(alt_path, dpi=300, format="jpg", bbox_inches="tight")
            plt.close()
            return True
        except Exception as e:
            logger.error(f"Failed to save plot to alternative location: {e}")
            plt.close()
            return False


def _save_wobble_results_to_excel(fit_results, raw_data, output_dir):
    """Save wobble analysis results to Excel file.

    Args:
    ----
        fit_results: Dictionary with fitting results
        raw_data: Dictionary with raw data
        output_dir: Directory to save the Excel file

    Returns:
    -------
        Boolean indicating success or failure

    """
    try:
        # Extract needed data
        w_sine_params = fit_results["w_sine_params"]
        h_sine_params = fit_results["h_sine_params"]
        mean_w_px_stable = fit_results["mean_w_px_stable"]
        mean_h_px_stable = fit_results["mean_h_px_stable"]
        mean_w_mm_stable = fit_results["mean_w_mm_stable"]
        mean_h_mm_stable = fit_results["mean_h_mm_stable"]
        times_stable = fit_results["times_stable"]
        times_valid = fit_results["times_valid"]
        settling_idx = fit_results["settling_idx"]

        # Create analysis data dictionary
        analysis_data = {
            "Parameter": [
                "Width Average (mm) - Stable",
                "Height Average (mm) - Stable",
                "Width Amplitude (mm)",
                "Width Frequency (Hz)",
                "Width Phase",
                "Width Offset",
                "Width Decay",
                "Height Amplitude (mm)",
                "Height Frequency (Hz)",
                "Height Phase",
                "Height Offset",
                "Height Decay",
                "Settling Period (s)",
                "Stable Data Points",
                "Width Function",
                "Height Function",
            ],
            "Value": [
                mean_w_px_stable,
                mean_w_mm_stable,
                mean_h_px_stable,
                mean_h_mm_stable,
                w_sine_params["amplitude"],
                w_sine_params["frequency"],
                w_sine_params["phase"],
                w_sine_params["offset"],
                w_sine_params["decay"],
                h_sine_params["amplitude"],
                h_sine_params["frequency"],
                h_sine_params["phase"],
                h_sine_params["offset"],
                h_sine_params["decay"],
                (
                    float(times_valid[int(settling_idx)])
                    if settling_idx > 0 and int(settling_idx) < len(times_valid)
                    else 0.0
                ),
                len(times_stable),
                (
                    f"{w_sine_params['amplitude']:.2f} * "
                    f"exp(-{w_sine_params['decay']:.4f}*t) * "
                    f"sin(2*pi * {w_sine_params['frequency']:.2f} * t + "
                    f"{w_sine_params['phase']:.2f}) + "
                    f"{w_sine_params['offset']:.2f}"
                ),
                (
                    f"{h_sine_params['amplitude']:.2f} * "
                    f"exp(-{h_sine_params['decay']:.4f}*t) * "
                    f"sin(2*pi * {h_sine_params['frequency']:.2f} * t + "
                    f"{h_sine_params['phase']:.2f}) + "
                    f"{h_sine_params['offset']:.2f}"
                ),
            ],
        }

        return _write_wobble_excel(analysis_data, raw_data, output_dir)

    except Exception as e:
        logger.error(f"Failed to prepare wobble results data: {e}")
        return False


def _write_wobble_excel(analysis_data, raw_data, output_dir):
    """Write wobble analysis data to Excel file.

    Args:
    ----
        analysis_data: Dictionary with analysis results
        raw_data: Dictionary with raw data
        output_dir: Directory to save the Excel file

    Returns:
    -------
        Boolean indicating success or failure

    """
    try:
        # Prepare output file
        excel_path = os.path.join(output_dir, "results_wobble.xlsx")

        # Create a workbook and add a worksheet
        workbook = xlsxwriter.Workbook(excel_path, {"nan_inf_to_errors": True})
        worksheet = workbook.add_worksheet()

        # Create formats for header (bold)
        header_format = workbook.add_format({"bold": True})

        # Write header row
        header = ["Parameter", "Value", ""]  # Analysis data + separator
        header.extend(raw_data.keys())  # Raw data headers
        for col_num, value in enumerate(header):
            worksheet.write(0, col_num, value, header_format)

        # Determine the maximum number of rows needed
        max_rows = max(len(analysis_data["Parameter"]), len(raw_data["Time (s)"]))

        # Write data rows
        for i in range(max_rows):
            row_idx = i + 1  # Excel rows are 0-indexed, but we already wrote the header

            # Add analysis data or empty values
            if i < len(analysis_data["Parameter"]):
                worksheet.write(row_idx, 0, analysis_data["Parameter"][i])
                worksheet.write(row_idx, 1, analysis_data["Value"][i])
            else:
                worksheet.write(row_idx, 0, "")
                worksheet.write(row_idx, 1, "")

            # Add separator
            worksheet.write(row_idx, 2, "")

            # Add raw data or empty values
            col_idx = 3
            for key in raw_data:
                if i < len(raw_data[key]):
                    value = raw_data[key][i]
                    # Handle NaN/INF values that might cause Excel errors
                    if isinstance(value, (float, np.floating)) and (
                        np.isnan(value) or np.isinf(value)
                    ):
                        value = ""
                    worksheet.write(row_idx, col_idx, value)
                else:
                    worksheet.write(row_idx, col_idx, "")
                col_idx += 1

        # Auto-adjust column widths for better readability
        for col_num, key in enumerate(header):
            width = len(str(key)) + 2  # Add some padding
            worksheet.set_column(col_num, col_num, width)

        workbook.close()
        return True

    except Exception as e:
        logger.error(f"Failed to save Excel file: {e}")
        return False


def _remove_outliers(values, label="Data", z_threshold=2.0):
    """Remove outliers from data using z-score method.

    Args:
    ----
        values: list of values to filter
        label: Label
        z_threshold: Z-score threshold for outlier detection

    Returns:
    -------
        tuple of (time_indices, filtered_values)

    """
    # Convert values to numpy array for processing using our helper function
    values_array = np.array(convert_to_float_list(values))

    # Create corresponding time indices
    time_indices = np.arange(len(values_array))

    # Remove NaN values
    mask_valid = ~np.isnan(values_array)
    valid_values = values_array[mask_valid]
    valid_times = time_indices[mask_valid]

    # Check if we have enough valid data
    if len(valid_values) < 3:
        return valid_times, valid_values

    # Calculate statistics
    mean = np.mean(valid_values)
    std = np.std(valid_values)

    # Check if all values are identical (std=0) or very close
    if std < 1e-6:
        return valid_times, valid_values

    # Calculate z-scores with protection against division by zero
    z_scores = np.abs((valid_values - mean) / max(std, 1e-10))

    # Filter based on z-scores, but ensure we keep at least 50% of data points
    mask_filtered = z_scores < z_threshold

    # If we would remove too many points, adjust the threshold
    if np.sum(mask_filtered) < len(valid_values) * 0.5:
        # Sort z-scores and keep at least 50% of points
        min_keep = max(3, int(len(valid_values) * 0.5))  # Keep at least 3 points or 50%
        threshold_idx = min(min_keep, len(valid_values) - 1)
        new_threshold = np.sort(z_scores)[threshold_idx]
        mask_filtered = z_scores < new_threshold

    filtered_values = valid_values[mask_filtered]
    filtered_times = valid_times[mask_filtered]

    excluded = len(valid_values) - len(filtered_values)
    if excluded > 0:
        pass

    # If we still have too few points, return all valid data
    if len(filtered_values) < 3:
        return valid_times, valid_values

    return filtered_times, filtered_values


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


def _filter_time_series_data(times, data_dict):
    """Filter time series data by removing the first and last 0.05 seconds.

    Also shifts time by 0.05 seconds.

    Args:
    ----
        times: list of time values
        data_dict: Dictionary of data series

    Returns:
    -------
        tuple of (filtered_times, filtered_data_dict)

    """
    # Convert times to float for comparison
    float_times = [
        float(t) if isinstance(t, (int, float, str)) and t != "" else float("nan")
        for t in times
    ]

    # Find indices to keep (remove first and last 0.1s)
    if len(float_times) < 2:
        return times, data_dict  # Not enough data to filter

    min_time = min(t for t in float_times if not np.isnan(t))
    max_time = max(t for t in float_times if not np.isnan(t))

    # Calculate cutoff times
    lower_cutoff = min_time + 0.05
    upper_cutoff = max_time - 0.05

    # Find indices to keep
    indices_to_keep = [
        i
        for i, t in enumerate(float_times)
        if not np.isnan(t) and lower_cutoff <= t <= upper_cutoff
    ]

    if not indices_to_keep:
        return times, data_dict  # No data left after filtering

    # Create filtered times with 0.1s shift
    filtered_times = [float_times[i] - 0.05 for i in indices_to_keep]

    # Create filtered data dict
    filtered_data = {}
    for key, values in data_dict.items():
        if key == "Time":
            filtered_data[key] = filtered_times
            continue

        # Filter data series using the same indices
        filtered_values = []
        for i in indices_to_keep:
            if i < len(values):
                filtered_values.append(values[i])
            else:
                filtered_values.append(float("nan"))

        filtered_data[key] = filtered_values

    return filtered_times, filtered_data


def _prepare_plot_data(raw_data, columns_to_plot):
    """Prepare data for plotting by extracting and converting relevant columns.

    Args:
    ----
        raw_data: Dictionary containing all measurement data
        columns_to_plot: List of column names to plot

    Returns:
    -------
        pandas DataFrame with prepared data

    """
    # Extract only the necessary columns for the plot
    data = {"Time": raw_data["Time"]}
    for column in columns_to_plot:
        if column in raw_data:
            data[column] = raw_data[column]
        else:
            logger.warning(f"Column '{column}' not found in raw data")

    # Convert time values to float
    time_values = data.get("Time", [])
    float_times = []
    invalid_times = 0
    for t in time_values:
        try:
            float_times.append(float(t))
        except (ValueError, TypeError):
            float_times.append(float("nan"))
            invalid_times += 1

    if invalid_times > 0:
        logger.warning(f"Found {invalid_times} invalid time values")

    # Create a pandas DataFrame for easier handling
    df_data = {"Time": float_times}
    for key, values in data.items():
        if key != "Time":
            df_data[key] = convert_to_float_list(values)

    df = pd.DataFrame(df_data)

    # Drop rows with NaN time values
    df = df.dropna(subset=["Time"])

    return df


def _setup_plot(title):
    """Set up the plot figure and get color palette.

    Args:
    ----
        title: Title for the plot

    Returns:
    -------
        Tuple of (figure, colors)

    """
    # Create plot
    plt.figure(figsize=(4, 4))

    # Set of colors for different lines
    colors = [
        (0 / 255, 0 / 255, 0 / 255),  # Black
        (0 / 255, 84 / 255, 159 / 255),  # Blue
        (0 / 255, 97 / 255, 101 / 255),  # Petrol
        (0 / 255, 152 / 255, 161 / 255),  # Turquoise
    ]

    return plt.gcf(), colors


def _add_regression_lines(df, columns_to_plot):
    """Add regression lines for center position columns.

    Args:
    ----
        df: DataFrame containing the data
        columns_to_plot: List of column names to check for regression

    """
    for column in columns_to_plot:
        # Add linear regression for X center position
        # Need at least 2 points for regression
        if "X of center" in column and column in df.columns:
            # Get clean data for regression
            valid_data = df.dropna(subset=[column])

            if len(valid_data) >= 2:
                x_data = valid_data["Time"].values
                y_data = valid_data[column].values

                # Calculate linear regression
                slope, intercept = np.polyfit(x_data, y_data, 1)

                # Plot regression line
                reg_x = np.array([min(x_data), max(x_data)])
                reg_y = slope * reg_x + intercept

                plt.plot(
                    reg_x,
                    reg_y,
                    "--",
                    color="red",
                    linewidth=1,
                    alpha=0.8,
                    label=f"dx/dt = {slope:.3f} mm/s",
                )


def _determine_y_axis_label(columns_to_plot, title):
    """Determine appropriate y-axis label based on plot content.

    Args:
    ----
        columns_to_plot: List of column names being plotted
        title: Default title to use if no specific label is determined

    Returns:
    -------
        Appropriate y-axis label

    """
    if "Advancing CA" in columns_to_plot or "Receding CA" in columns_to_plot:
        return "CA (θ)"
    elif any("contour" in col.lower() for col in columns_to_plot):
        return "Contour (mm)"
    elif any("velocity" in col.lower() for col in columns_to_plot):
        return "Velocity (mm/s)"
    elif any("center" in col.lower() for col in columns_to_plot):
        return "Position (mm)"
    elif any("contact line" in col.lower() for col in columns_to_plot):
        return "Contact Line (mm)"
    else:
        return title


def _adjust_aspect_ratio(ax):
    """Adjust aspect ratio of the plot to make it square.

    Args:
    ----
        ax: Matplotlib axis object

    """
    # Get current limits
    x_min, x_max = ax.get_xlim()
    y_min, y_max = ax.get_ylim()

    # Find the range of each axis
    x_range = x_max - x_min
    y_range = y_max - y_min

    # Ensure no division by zero
    if x_range == 0:
        x_range = 1
    if y_range == 0:
        y_range = 1

    # Calculate the ratio to make the aspect ratio 1:1
    ratio = x_range / y_range

    # Adjust the aspect ratio to make the plot square
    ax.set_aspect(ratio)


def _save_plot_to_file(output_dir, filename):
    """Save the current plot to a file.

    Args:
    ----
        output_dir: Directory to save the plot
        filename: Filename for the plot

    Returns:
    -------
        Boolean indicating if the plot was saved successfully

    """
    try:
        output_path = os.path.join(output_dir, filename)
        plt.tight_layout()
        plt.savefig(output_path, dpi=600, format="png")
        logger.info(f"Successfully saved plot: {output_path}")

        # Close the plot to free memory
        plt.close()
        return True
    except Exception as e:
        logger.error(f"Error saving plot {filename}: {e}")
        # Ensure plot is closed even if there's an error
        plt.close()
        return False


def _style_and_save_plot(output_dir, filename, columns_to_plot, valid_columns, title):
    """Apply styling to the plot and save it to file.

    Args:
    ----
        output_dir: Directory to save the plot
        filename: Filename for the plot
        columns_to_plot: List of column names being plotted
        valid_columns: List of valid column names (those with data)
        title: Title for the plot

    Returns:
    -------
        Boolean indicating if the plot was saved successfully

    """
    try:
        # Set plot properties
        plt.xlabel("Time (s)", fontsize=12)

        # Determine and set y-axis label
        y_label = _determine_y_axis_label(columns_to_plot, title)
        plt.ylabel(y_label, fontsize=12)

        plt.xticks(fontsize=10)
        plt.yticks(fontsize=10)

        # Add legend only if there are labeled artists
        try:
            # Check if there are any labeled artists
            ax = plt.gca()
            handles, labels = ax.get_legend_handles_labels()

            if len(handles) > 0:  # Only add legend if we have labeled artists
                if len(valid_columns) > 1:
                    # Multiple series - try to position in the corner with least data
                    plt.legend(fontsize=8, loc="best", framealpha=0.7)
                elif len(valid_columns) == 1:
                    # Single series - position in upper right
                    plt.legend(fontsize=8, loc="upper right", framealpha=0.7)
            else:
                logger.debug("No labeled artists found, skipping legend")
        except Exception as e:
            logger.warning(f"Error creating legend: {e}")

        # Get axis and adjust aspect ratio
        ax = plt.gca()
        _adjust_aspect_ratio(ax)

        # Add tick settings
        ax.xaxis.set_major_locator(plt.MaxNLocator(4))
        ax.tick_params(axis="both", which="both", direction="in", top=True, right=True)

        # Save the plot
        return _save_plot_to_file(output_dir, filename)

    except Exception as e:
        logger.error(f"Error styling plot {filename}: {e}")
        # Ensure plot is closed even if there's an error
        plt.close()
        return False


def _plot_data(raw_data, output_dir, filename, columns_to_plot, title):
    """Plot data and save to output directory.

    Args:
    ----
        raw_data: Dictionary containing all measurement data
        output_dir: Directory to save the plot
        filename: Filename for the plot
        columns_to_plot: list of column names to plot
        title: Title for the plot

    """
    try:
        # Create output directory if it doesn't exist
        os.makedirs(output_dir, exist_ok=True)

        # Ensure filename uses .png extension
        if filename.lower().endswith(".jpg"):
            filename = filename[:-4] + ".png"

        # Prepare data for plotting
        df = _prepare_plot_data(raw_data, columns_to_plot)

        # Get valid columns to plot (those with data)
        valid_columns = [
            col
            for col in columns_to_plot
            if col in df.columns and not df[col].isna().all()
        ]

        # If there are no valid columns with data, skip saving the plot
        if len(valid_columns) == 0:
            logger.warning(
                "No valid columns with data found, skipping plot for %s", title
            )
            return

        # Setup the plot
        _, colors = _setup_plot(title)

        # Plot the actual data series
        for i, column in enumerate(valid_columns):
            if column in df.columns:
                # Use different colors for different series
                color = colors[i % len(colors)]
                plt.plot(
                    df["Time"],
                    df[column],
                    color=color,
                    linewidth=1.5,
                    label=column,
                    marker="o",
                    markersize=3,
                )

        # Add regression lines for center position data
        _add_regression_lines(df, columns_to_plot)

        # Style and save the plot
        _style_and_save_plot(
            output_dir, filename, columns_to_plot, valid_columns, title
        )

    except Exception as e:
        logger.error(f"Error creating plot {filename}: {e}")
        # Ensure plot is closed even if there's an error
        plt.close()
