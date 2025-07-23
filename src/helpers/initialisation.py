"""Experiment and application initialization utilities.

For Droplet Wall Interaction Tool.
"""

import os
import re

import cv2
import numpy as np

from src.utilities.logging_manager import get_logger

# Setup logger for this module
logger = get_logger(__name__)


def start_run(img_names, q, save_files, folder_path):
    """Process a single image for analysis with improved error handling.

    Args:
    ----
        img_names: list of image filenames or paths
        q: Index of image to process
        save_files: Whether to save intermediate files
        folder_path: Path to folder containing images

    Returns:
    -------
        tuple of analysis results for the image or None if processing fails

    """
    logger.debug(f"Starting image processing run: index={q}, save_files={save_files}")

    # Validate inputs and resolve image path
    img_names, image_path, filename = _validate_and_resolve_image_path(
        img_names, q, folder_path
    )

    # Load the image directly from its full path
    src = cv2.imread(image_path, cv2.IMREAD_COLOR)
    if src is None:
        logger.error(f"OpenCV failed to load image: {image_path}")
        raise ValueError(f"Failed to load image: {image_path}")

    # Validate the loaded image
    if not isinstance(src, np.ndarray) or src.size == 0 or len(src.shape) < 2:
        logger.error(
            f"Invalid image data: "
            f"shape={src.shape if hasattr(src, 'shape') else 'N/A'}, "
            f"size={src.size if hasattr(src, 'size') else 'N/A'}"
        )
        raise ValueError(f"Invalid image data loaded from: {image_path}")

    # Initialize empty lists for image processing
    lists = [
        "y1_list",
        "y2_list",
        "x1_list",
        "x2_list",
        "y1_neu",
        "xsp",
        "shifted_points",
        "shifted_x",
        "shifted_y",
        "cnt_y_neu",
        "cnt_x_neu",
        "cnt_x",
        "cnt_y",
        "x_left_cnt",
        "y_left_cnt",
        "x_right_cnt",
        "y_right_cnt",
    ]
    initialized_lists = {name: [] for name in lists}

    logger.debug(f"Image processing run completed successfully for {filename}")
    return (*initialized_lists.values(), src, filename)


def _validate_and_resolve_image_path(img_names, q, folder_path):
    """Validate inputs and resolve the image path and filename."""
    # Validate img_names type
    if not isinstance(img_names, list) and not isinstance(img_names, str):
        logger.error(
            f"Invalid img_names type: expected list or string, got {type(img_names)}"
        )
        raise TypeError(f"Expected list or string for img_names, got {type(img_names)}")

    # Check if the list is empty
    if not img_names:
        logger.error("Empty image list provided")
        raise ValueError("Empty image list provided")

    # Validate index
    if q < 0 or q >= len(img_names):
        logger.error(f"Invalid index {q} for list of length {len(img_names)}")
        raise IndexError(f"Invalid index {q} for list of length {len(img_names)}")

    # Get the image path, handling different input formats
    if isinstance(img_names[q], str):
        if os.path.isabs(img_names[q]):
            image_path = img_names[q]
            filename = os.path.basename(image_path)

        else:
            filename = img_names[q]
            image_path = os.path.join(folder_path, filename)

    else:
        logger.error(
            f"Invalid path type at index {q}: expected string, got {type(img_names[q])}"
        )
        raise TypeError(f"Expected string path at index {q}, got {type(img_names[q])}")

    # Verify that the image path exists
    if not os.path.exists(image_path):
        logger.error(f"Image file not found: {image_path}")
        raise FileNotFoundError(f"Image file not found: {image_path}")

    return img_names, image_path, filename


def initiate_run(files, save_files, folder_path, fps):
    """Initialize the angle measurement program.

    Args:
    ----
        files (list): list of image files
        save_files (bool): Whether to save intermediate files
        folder_path (str): Path to image folder
        fps (float): Frames per second

    Returns:
    -------
        tuple: Initialized data structures

    """
    logger.info(
        f"Initiating run with {len(files) if files else 0} files, "
        f"save_files={save_files}, fps={fps}"
    )

    # Initialize result lists

    result_lists = {
        "advancing_contact_angles": [],
        "receding_contact_angles": [],
        "left_contact_angle_ellipse": [],
        "right_contact_angle_ellipse": [],
        "center_points_px": [],
        "center_points_mm": [],
        "rect_width_px": [],
        "rect_height_px": [],
        "rect_width_mm": [],
        "rect_height_mm": [],
        "velocity": [],
        "lines_list": [],
    }

    # assign float nan to all lists in result_lists

    for key in result_lists:
        result_lists[key] = [float("nan")] * len(files)

    # Process image files

    img_names = []
    time = []
    time_int = []

    if save_files:
        logger.info("Save files mode: processing all images")
        for file in files:
            img_names.append(os.path.basename(file))

        first_image_path = os.path.join(folder_path, img_names[0])

        background = cv2.imread(first_image_path, cv2.IMREAD_COLOR)

        if background is None:
            logger.error(f"Failed to load background image: {first_image_path}")

        time_int, time = _calculate_timestamps(img_names, fps)
        logger.info(f"Calculated timestamps for {len(time_int)} images")
    else:
        logger.info("Single image mode: processing middle image")
        img_name = os.path.basename(files[len(files) // 2])
        img_name_0 = os.path.basename(files[0])

        background_path = os.path.join(folder_path, img_name_0)

        background = cv2.imread(background_path, cv2.IMREAD_COLOR)

        if background is None:
            logger.error(f"Failed to load background image: {background_path}")

        img_names = [img_name]  # Ensure this is always a list

    logger.info("Run initialization completed successfully")
    return (background, img_names, time, time_int, result_lists)


def _calculate_timestamps(image_filenames, fps):
    """Calculate timestamps for image files based on their numerical suffixes.

    Args:
    ----
        image_filenames (list): list of image filenames
        fps (float): Frames per second

    Returns:
    -------
        tuple: Lists of integer and string timestamps

    """
    if not image_filenames:
        logger.warning("No image filenames provided for timestamp calculation")
        return [], []

    first_image = image_filenames[0]
    first_number = __extract_image_number(first_image)

    time_int = []
    time_str = []

    for i, filename in enumerate(image_filenames):
        current_number = __extract_image_number(filename)
        timestamp = (current_number - first_number) * (1 / fps)
        timestamp = round(timestamp, 4)
        time_int.append(timestamp)
        time_str.append(str(timestamp))

    logger.info(
        f"Timestamp calculation complete: {len(time_int)} timestamps "
        f"from {first_number} to {current_number}"
    )
    return time_int, time_str


def __extract_image_number(filename):
    """Extract the numerical part from an image filename with improved error handling.

    Args:
    ----
        filename (str): Image filename

    Returns:
    -------
        int: Extracted numerical value or 0 if extraction fails

    """
    if not filename:
        logger.warning("Empty filename provided for number extraction")
        return 0

    # Look for a 6-digit number near the end of the filename (timestamp format)
    zahl_str = re.search(r"(\d{6})\D*$", filename)
    if not zahl_str:
        # Try a more lenient pattern as fallback
        zahl_str = re.search(r"(\d+)\D*$", filename)
        if not zahl_str:
            logger.warning(f"No numerical pattern found in filename: {filename}")
            return 0

    extracted_number = int(zahl_str.group(1))
    return extracted_number
