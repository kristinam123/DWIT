"""Centralized logging management for Droplet Wall Interaction Tool (DWIT).

This module provides a unified logging system that captures
Droplet Wall Interaction Tool (DWIT) application logs
and routes them to the log overlay with proper formatting and filtering.
"""

import logging
import sys
from datetime import datetime

from PySide6.QtCore import QObject, QSettings, Signal


class LogLevel:
    """Log level constants."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


class TerminalStyleFormatter(logging.Formatter):
    """Formatter that creates terminal-like log messages."""

    def format(self, record):
        """Format the log record in a terminal-like style."""
        # Format timestamp to be more readable (like a terminal)
        timestamp = datetime.fromtimestamp(record.created).strftime("%H:%M:%S")

        # Create terminal-style message: [LEVEL] HH:MM:SS message
        message = f"[{record.levelname}] {timestamp} {record.getMessage()}"

        # Add exception info if present
        if record.exc_info:
            message += "\n" + self.formatException(record.exc_info)

        return message


class StdCapture:
    """Capture stdout/stderr and route to logging."""

    def __init__(self, logger_name="stdout", level=logging.INFO):
        """Initialize the StdCapture with logger name and level."""
        self.logger = logging.getLogger(logger_name)
        self.level = level
        self.original_stream = None

    def write(self, text):
        """Write text to the original stream only.

        Avoid logging to prevent recursion.
        """
        if self.original_stream:
            self.original_stream.write(text)
            self.original_stream.flush()

    def flush(self):
        """Flush the stream."""
        if self.original_stream:
            self.original_stream.flush()


class ColoredLogHandler(logging.Handler):
    """Custom log handler that sends formatted messages to the log overlay."""

    def __init__(self, log_overlay=None, logging_manager=None):
        """Initialize the ColoredLogHandler with optional overlay and manager."""
        super().__init__()
        self.log_overlay = log_overlay
        self.logging_manager = logging_manager

    def emit(self, record):
        """Emit a log record to the overlay only if the log type is enabled."""
        if not self.log_overlay or not self.logging_manager:
            return
        # Check if the log type is enabled before emitting
        if not self.logging_manager.is_level_enabled(record.levelname):
            return
        try:
            message = self.format(record)
            self.log_overlay.append_log_message(message, record.levelname)
            # Update highest level tracking
            self.logging_manager.update_highest_level(record.levelname)
        except Exception:
            # Avoid recursive logging errors
            pass

    def set_log_overlay(self, log_overlay):
        """Set the log overlay reference."""
        self.log_overlay = log_overlay

    def set_logging_manager(self, logging_manager):
        """Set the logging manager reference."""
        self.logging_manager = logging_manager


class LoggingManager(QObject):
    """Centralized logging manager for the application."""

    # Signal emitted when a new log message is received
    log_level_updated = Signal(str)  # highest level since last reset

    _instance = None

    def __new__(cls):
        """Singleton pattern to ensure only one logging manager exists."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """Initialize the LoggingManager singleton instance."""
        if hasattr(self, "_initialized"):
            return

        super().__init__()
        self._initialized = True

        # Log filtering settings
        self.enabled_levels = {
            LogLevel.DEBUG: True,
            LogLevel.INFO: True,
            LogLevel.WARNING: True,
            LogLevel.ERROR: True,
        }

        # Track highest log level for status indicator
        self.highest_level = "info"
        self.level_priorities = {"debug": 0, "info": 1, "warning": 2, "error": 3}

        # Track counts of warnings and errors for status indicator
        self.warning_count = 0
        self.error_count = 0

        # Settings will be loaded after QApplication is properly initialized
        self._settings_loaded = False

        # Setup stdout/stderr capture
        self.setup_print_capture()

        # Setup the custom handler
        self.custom_handler = ColoredLogHandler()
        self.custom_handler.set_log_overlay(None)  # Will be set later
        self.custom_handler.set_logging_manager(self)  # Set reference to self

        # Configure the handler with terminal-style formatter
        formatter = TerminalStyleFormatter()
        self.custom_handler.setFormatter(formatter)
        self.custom_handler.setLevel(logging.DEBUG)

        # Setup root logger to capture all logs
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.DEBUG)

        # Remove existing handlers to avoid duplicates
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)

        # Add our custom handler first (highest priority)
        root_logger.addHandler(self.custom_handler)

        # Also add a console handler for terminal output with filtering
        class ConsoleLogHandler(logging.StreamHandler):
            def __init__(self, logging_manager, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.logging_manager = logging_manager

            def emit(self, record):
                # Suppress log types that are disabled
                if not self.logging_manager.is_level_enabled(record.levelname):
                    return
                super().emit(record)

        console_handler = ConsoleLogHandler(self, sys.__stdout__)
        console_handler.setFormatter(TerminalStyleFormatter())
        console_handler.setLevel(logging.DEBUG)  # Show debug and higher to terminal
        root_logger.addHandler(console_handler)

        # Also capture logging from third-party libraries by explicitly setting handlers
        # on commonly used library loggers
        for logger_name in [
            "PIL",
            "matplotlib",
            "numpy",
            "opencv",
            "cv2",
            "PySide6",
            "Qt",
        ]:
            lib_logger = logging.getLogger(logger_name)
            lib_logger.setLevel(
                logging.WARNING
            )  # Only warnings and errors from libraries
            lib_logger.addHandler(self.custom_handler)
            lib_logger.propagate = True  # Ensure they propagate to root logger

    def initialize_settings(self):
        """Initialize settings after QApplication is properly set up."""
        if not self._settings_loaded:
            self.load_filter_settings()
            self._settings_loaded = True

    def setup_print_capture(self):
        """Set up capture of print statements to route to logging."""
        # Create custom stdout/stderr captures
        self.stdout_capture = StdCapture("stdout", logging.INFO)
        self.stderr_capture = StdCapture("stderr", logging.ERROR)

        # Store original streams
        self.stdout_capture.original_stream = sys.__stdout__
        self.stderr_capture.original_stream = sys.__stderr__

        # Replace stdout/stderr
        sys.stdout = self.stdout_capture
        sys.stderr = self.stderr_capture

    def set_log_overlay(self, log_overlay):
        """Set the log overlay for message display."""
        self.custom_handler.set_log_overlay(log_overlay)

    def update_highest_level(self, level: str):
        """Update the highest log level and emit signal."""
        level_lower = level.lower()
        if level_lower in self.level_priorities:
            # Track if we need to emit signal
            should_emit_signal = False

            # Update counts for warnings and errors
            if level_lower == "warning":
                self.warning_count += 1
                should_emit_signal = True
            elif level_lower == "error":
                self.error_count += 1
                should_emit_signal = True

            current_priority = self.level_priorities.get(self.highest_level, 0)
            new_priority = self.level_priorities[level_lower]

            if new_priority > current_priority:
                self.highest_level = level_lower
                should_emit_signal = True

            # Emit signal if either the level changed or a count was updated
            if should_emit_signal:
                self.log_level_updated.emit(self.highest_level)

    def reset_highest_level(self):
        """Reset the highest level and counts (useful when user opens log overlay)."""
        self.highest_level = "info"
        self.warning_count = 0
        self.error_count = 0
        self.log_level_updated.emit(self.highest_level)

    def set_level_enabled(self, level: str, enabled: bool):
        """Enable or disable a specific log level."""
        if level in self.enabled_levels:
            self.enabled_levels[level] = enabled
            # Only save if settings have been loaded
            if self._settings_loaded:
                self.save_filter_settings()

    def is_level_enabled(self, level: str) -> bool:
        """Check if a log level is enabled."""
        return self.enabled_levels.get(level, True)

    def save_filter_settings(self):
        """Save filter settings to QSettings."""
        settings = QSettings()
        settings.beginGroup("LoggingFilters")
        for level, enabled in self.enabled_levels.items():
            settings.setValue(level, enabled)
        settings.endGroup()

    def load_filter_settings(self):
        """Load filter settings from QSettings."""
        settings = QSettings()
        settings.beginGroup("LoggingFilters")
        for level in self.enabled_levels:
            # Default all levels to True if not set
            self.enabled_levels[level] = settings.value(level, True, type=bool)
        settings.endGroup()

    def get_status_counts(self):
        """Get the current warning and error counts."""
        return {"warning_count": self.warning_count, "error_count": self.error_count}

    @staticmethod
    def get_logger(name: str) -> logging.Logger:
        """Get a logger instance with the specified name."""
        return logging.getLogger(name)

    @staticmethod
    def log_debug(logger_name: str, message: str):
        """Log a debug message."""
        logger = logging.getLogger(logger_name)
        logger.debug(message)

    @staticmethod
    def log_info(logger_name: str, message: str):
        """Log an info message."""
        logger = logging.getLogger(logger_name)
        logger.info(message)

    @staticmethod
    def log_warning(logger_name: str, message: str):
        """Log a warning message."""
        logger = logging.getLogger(logger_name)
        logger.warning(message)

    @staticmethod
    def log_error(logger_name: str, message: str):
        """Log an error message."""
        logger = logging.getLogger(logger_name)
        logger.error(message)


# Global instance
logging_manager = LoggingManager()


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance with the specified name."""
    return LoggingManager.get_logger(name)


def log_debug(logger_name: str, message: str):
    """Log a debug message using the specified logger."""
    LoggingManager.log_debug(logger_name, message)


def log_info(logger_name: str, message: str):
    """Log an info message using the specified logger."""
    LoggingManager.log_info(logger_name, message)


def log_warning(logger_name: str, message: str):
    """Log a warning message using the specified logger."""
    LoggingManager.log_warning(logger_name, message)


def log_error(logger_name: str, message: str):
    """Log an error message using the specified logger."""
    LoggingManager.log_error(logger_name, message)


# Initialize self-logging for the logging manager
_self_logger = logging.getLogger("logging_manager")
