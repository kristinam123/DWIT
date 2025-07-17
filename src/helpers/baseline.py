"""Baseline detection utilities for droplet and experiment analysis in MesszelleApp."""

import cv2
import numpy as np

from src.utilities.logging_manager import get_logger

# Setup logger for this module
logger = get_logger(__name__)


def find_single_baseline(image, baseline_offset=0, baseline_tf=False, manual_offset=0):
    """Enhanced function to detect the baseline where the droplet sits.

    Uses multiple detection strategies with automatic threshold determination.

    Args:
    ----
        image: Input image
        baseline_offset: Manual offset adjustment for baseline
        baseline_tf: If True, use manual offset only
        manual_offset: Manual offset value

    Returns:
    -------
        y1_left: Left side Y coordinate of baseline
        y1_right: Right side Y coordinate of baseline

    """
    img_h, img_w = image.shape[:2]

    if baseline_tf:
        y1_left = img_h - manual_offset
        y1_right = y1_left
        logger.info(
            f"Using manual baseline at y={y1_left} (manual_offset={manual_offset})"
        )
        return y1_left, y1_right
    else:
        logger.info("Using automatic baseline detection")
        # Make a copy of the image for processing
        working_img = image.copy()
        height, width = working_img.shape[:2]

        try:
            # Apply pre-processing to enhance the baseline visibility
            gray = cv2.cvtColor(working_img, cv2.COLOR_BGR2GRAY)
            blurred = cv2.GaussianBlur(gray, (5, 5), 0)

            # Strategy 1: Edge detection with Canny using adaptive thresholds
            # Automatically determine thresholds based on image statistics
            median = np.median(blurred)
            sigma = 0.5  # Standard deviation for Canny thresholds
            threshold_min = int(max(0, (1.0 - sigma) * median))
            threshold_max = int(min(255, (1.0 + sigma) * median))

            edges = cv2.Canny(blurred, threshold_min, threshold_max)

            # Strategy 2: Use Hough Line Transform to find horizontal lines
            lines = cv2.HoughLinesP(
                edges,
                1,
                np.pi / 180,
                threshold=50,
                minLineLength=width // 4,
                maxLineGap=20,
            )

            baseline_candidates = []

            # Process detected lines
            if lines is not None:
                for line in lines:
                    x1, y1, x2, y2 = line[0]
                    # Filter for mostly horizontal lines (small slope)
                    if abs(y2 - y1) < height * 0.1:  # Allowing slight tilt
                        # Calculate score based on length and position
                        line_length = np.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)
                        position_score = 1.0 - (
                            min(y1, y2) / height
                        )  # Favor lines in lower half
                        score = line_length * position_score
                        baseline_candidates.append((x1, y1, x2, y2, score))
            else:
                logger.warning("No lines detected with Hough transform")

            # Select the best line if candidates exist
            if baseline_candidates:
                # Sort by score descending
                baseline_candidates.sort(key=lambda x: x[4], reverse=True)

                # Get best candidate
                x1, y1, x2, y2, score = baseline_candidates[0]

                # Return baseline coordinates with offset
                y1_left = int(y1) - baseline_offset
                y1_right = int(y2) - baseline_offset
                logger.info(f"Detected baseline: left={y1_left}, right={y1_right}")

                return y1_left, y1_right
            else:
                logger.warning("No valid baseline candidates found, returning None")
                return None, None

        except Exception as e:
            logger.error(f"Error during baseline detection: {e}")
            return None, None


def find_dual_baseline(
    middle_src, baseline_offset=0, baseline_tf=False, manual_offset=0
):
    """Find baselines in both upper and lower regions for channel mode.

    Args:
    ----
        middle_src: Source image to process
        baseline_offset: Manual offset adjustment for baseline
        baseline_tf: If True, use manual offset only
        manual_offset: Manual offset value

    Returns:
    -------
        upper_baseline: Y coordinate of baseline in upper region
            (relative to upper region)
        lower_baseline: Y coordinate of baseline in lower region
            (relative to lower region)
        axis_y: Y coordinate of the dividing axis in original image coordinates

    """
    logger.info("Finding dual baseline for channel mode")

    axis_y, upper_region, lower_region = _find_axisymmetric_axis_channel(middle_src)

    try:
        # Lower baseline (region 1): use find_single_baseline on lower_region
        y1_left_1, y1_right_1 = find_single_baseline(
            lower_region, baseline_offset, baseline_tf, manual_offset
        )

        # Upper baseline (region 2): use find_single_baseline on upper_region
        y1_left_2, y1_right_2 = find_single_baseline(
            upper_region, baseline_offset, baseline_tf, manual_offset
        )

        if y1_left_1 is not None and y1_left_2 is not None:
            logger.info(
                f"Dual baseline found - Lower: ({y1_left_1}, {y1_right_1}), "
                f"Upper: ({y1_left_2}, {y1_right_2})"
            )
        else:
            logger.warning("One or both baselines could not be detected")

        # Return both baselines and axis_y
        return y1_left_1, y1_right_1, y1_left_2, y1_right_2, axis_y

    except Exception as e:
        logger.error(f"Failed to find dual baseline: {e}")
        # Fallback: use region centers if detection fails
        lower_h = lower_region.shape[0]
        upper_h = upper_region.shape[0]
        y1_left_1 = y1_right_1 = lower_h // 2
        y1_left_2 = y1_right_2 = upper_h // 2
        logger.warning(
            f"Using fallback baseline positions - Lower center: {y1_left_1}, "
            f"Upper center: {y1_left_2}"
        )
        return y1_left_1, y1_right_1, y1_left_2, y1_right_2, axis_y


def _find_axisymmetric_axis_channel(image):
    """Find the axisymmetric axis for channel mode analysis.

    This function identifies the horizontal axis that divides the white area
    (channel) in a way that creates symmetric upper and lower halves.

    Args:
    ----
        image: Input image (BGR format)

    Returns:
    -------
        axis_y: Y-coordinate of the horizontal axisymmetric axis
        upper_region: Image region above the axis
        lower_region: Image region below the axis

    """
    height, width = image.shape[:2]

    try:
        # Convert to grayscale and apply thresholding to identify white areas
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

        # Use a high threshold to capture only the brightest (white) areas
        _, white_mask = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)

        # Apply morphological operations to clean up the mask
        kernel = np.ones((5, 5), np.uint8)
        white_mask = cv2.morphologyEx(white_mask, cv2.MORPH_OPEN, kernel)
        white_mask = cv2.morphologyEx(white_mask, cv2.MORPH_CLOSE, kernel)

        # Calculate horizontal projection of white pixels
        horizontal_projection = np.sum(white_mask, axis=1)
        total_white_pixels = np.sum(horizontal_projection)

        # Find the center of mass of the white area
        if total_white_pixels == 0:
            # Fallback to image center
            axis_y = height // 2
            logger.warning("No white pixels found, using image center as axis")
        else:
            # Calculate weighted center
            y_coords = np.arange(height)
            center_of_mass_y = (
                np.sum(y_coords * horizontal_projection) / total_white_pixels
            )
            axis_y = int(center_of_mass_y)

        # Ensure axis is within image bounds with some margin
        margin = 50  # Minimum distance from top/bottom edges
        axis_y = max(margin, min(height - margin, axis_y))

        # Split image into upper and lower regions
        upper_region = image[:axis_y, :]
        lower_region = image[axis_y:, :]

        logger.info(f"Axisymmetric axis found at y={axis_y}")

        return axis_y, upper_region, lower_region

    except Exception as e:
        logger.error(f"Failed to find axisymmetric axis: {e}")
        # Fallback to simple center split
        axis_y = height // 2
        upper_region = image[:axis_y, :]
        lower_region = image[axis_y:, :]
        logger.warning(f"Using fallback center split at y={axis_y}")
        return axis_y, upper_region, lower_region
