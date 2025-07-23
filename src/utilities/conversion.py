"""Unit conversion utilities.

For experiment data in Droplet Wall Interaction Tool (DWIT).
"""

from typing import Any

from src.utilities.logging_manager import get_logger

# Setup logger for this module
logger = get_logger(__name__)


def convert_to_float_list(values: list[Any]) -> list[float]:
    """Convert a list of mixed types to floats, handling non-numeric values properly.

    Args:
    ----
        values: list of values to convert

    Returns:
    -------
        list of float values with non-numerics converted to NaN

    """
    try:
        result = []
        non_numeric_count = 0

        for i, v in enumerate(values):
            try:
                if isinstance(v, list):
                    logger.warning(f"Found nested list at index {i}, converting to NaN")
                    result.append(float("nan"))
                    non_numeric_count += 1
                else:
                    converted_value = float(v)
                    result.append(converted_value)
            except (ValueError, TypeError) as e:
                logger.warning(
                    f"Failed to convert value at index {i}: {v} -> NaN (Error: {e})"
                )
                result.append(float("nan"))
                non_numeric_count += 1

        if non_numeric_count > 0:
            logger.debug(
                f"Conversion completed: {len(values) - non_numeric_count}/"
                f"{len(values)} values converted successfully, "
                f"{non_numeric_count} converted to NaN"
            )
        else:
            logger.debug(
                f"Conversion completed successfully: all {len(values)} values "
                f"converted to floats"
            )

        return result

    except Exception as e:
        logger.error(f"Unexpected error during conversion: {e}")
        # Return list of NaN values as fallback
        fallback_result = [float("nan")] * len(values)
        return fallback_result
