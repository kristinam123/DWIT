"""Baseline detection utilities.

For droplet and experiment analysis in Droplet Wall Interaction Tool.
"""

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
        logger.debug(
            f"Using manual baseline at y={y1_left} (manual_offset={manual_offset})"
        )
        return y1_left, y1_right
    else:
        logger.debug("Using automatic baseline detection")
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
                logger.debug(f"Detected baseline: left={y1_left}, right={y1_right}")

                return y1_left, y1_right
            else:
                logger.warning("No valid baseline candidates found, returning None")
                return None, None

        except Exception as e:
            logger.error(f"Error during baseline detection: {e}")
            return None, None
