"""Dosage threading utilities for automated injection and refill in MesszelleApp."""

from PySide6.QtCore import QThread, Signal

from src.utilities.logging_manager import get_logger

# Setup logger for this module
logger = get_logger(__name__)


class DosageButtonThread(QThread):
    """Thread for handling dosage button actions in the GUI."""

    finished = Signal()
    steps_left_update = Signal(str)

    def __init__(self, controller, button_type, steps_value=None, time_value=None):
        """Initialize the DosageButtonThread with controller and button parameters."""
        super().__init__()
        logger.debug(f"Initializing DosageButtonThread for button type: {button_type}")

        self.controller = controller
        self.button_type = button_type
        self.steps_value = steps_value
        self.time_value = time_value

        # Connect thread finished signal for cleanup logging
        self.finished.connect(
            lambda: logger.debug(f"DosageButtonThread for {button_type} completed")
        )

        # Initialize current_steps_left for tracking injection progress
        self.current_steps_left = "0"

    def run(self):
        """Execute the dosage operation based on button type."""
        try:
            logger.debug(f"Starting dosage operation: {self.button_type}")

            if self.button_type == "Init.":
                self.controller.initialise()
                self.controller.resolution(address="a", full="1")
                self.steps_left_update.emit("0")
                logger.debug("Dosage system initialization completed")

            elif self.button_type == "Refill":
                result = self.controller.refill(address="a", steps="2085")
                if result != 0:
                    logger.debug("Refill operation completed successfully")
                    self.steps_left_update.emit("2085")
                else:
                    logger.warning("Refill operation returned zero steps")
                    self.steps_left_update.emit("0")

            elif self.button_type == "Inject":
                try:
                    steps_left = int(self.current_steps_left)
                    steps = self.steps_value

                    if steps_left >= steps:
                        inject = self.controller.stroke(
                            address="a",
                            steps=str(steps),
                            valve_pos="O",
                            direction="D",
                            time_stroke=str(self.time_value),
                        )

                        if inject != 0:
                            new_steps_left = str(steps_left - steps)
                            logger.debug(
                                f"Injection completed. Steps left: {new_steps_left}"
                            )
                            self.steps_left_update.emit(new_steps_left)
                        else:
                            logger.warning("Injection operation returned zero")
                            self.steps_left_update.emit(str(steps_left))
                    else:
                        logger.warning(
                            f"Not enough steps left for injection: {steps_left}/{steps}"
                        )

                except (ValueError, TypeError) as e:
                    logger.error(f"Error in injection calculation: {e}")
                    self.steps_left_update.emit(self.current_steps_left)

            else:
                logger.warning(f"Unknown button type: {self.button_type}")

        except Exception as e:
            logger.error(f"Error in dosage operation '{self.button_type}': {e}")
            raise

        finally:
            self.finished.emit()
