"""DWIT utilities: centralized logging management and path identifier helpers.

This module provides a unified logging system that captures Droplet Wall
Interaction Tool (DWIT) application logs and routes them to the GUI log
overlay with proper formatting and filtering. It includes a singleton
LoggingManager, custom handlers and formatters, and helpers to capture
stdout/stderr and control which levels are shown in the overlay.

It also provides deterministic, reversible, filesystem-safe identifiers for
arbitrary Windows paths by encoding UTF-8 bytes using URL-safe base64
(stripping '=' padding) and prefixing tokens with 'b64_'. Unicode is
normalized to NFC before encoding and tokens that would match Windows
reserved device names are prefixed with '_' to avoid collisions.

Design notes:
- Tokens are deterministic and reversible; callers must still be aware of
    filesystem/path length limits.
- Uses urlsafe base64 and strips padding to keep tokens filename-safe; padding
    is restored on decode.
- No sidecar files are used; mapping is purely algorithmic.
"""

from __future__ import annotations

import base64
import binascii
import logging
import sys
import unicodedata
from datetime import datetime
from typing import Final

from PySide6.QtCore import QObject, QSettings, Signal

# Windows reserved device names (case-insensitive)
_RESERVED: Final[set[str]] = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    "COM1",
    "COM2",
    "COM3",
    "COM4",
    "COM5",
    "COM6",
    "COM7",
    "COM8",
    "COM9",
    "LPT1",
    "LPT2",
    "LPT3",
    "LPT4",
    "LPT5",
    "LPT6",
    "LPT7",
    "LPT8",
    "LPT9",
}


def _normalize(s: str) -> str:
    """Normalize Unicode to NFC for deterministic behavior."""
    return unicodedata.normalize("NFC", s)


def encode_path(path: str) -> str:
    r"""Encode an arbitrary path into a filesystem-safe token.

    The token is deterministic and reversible. It is safe for use as a
    filename or database key on Windows (uses only A-Za-z0-9_- and an ASCII
    prefix). Caller must be aware of overall length limits (Windows MAX_PATH).

    Example: encode_path(r"C:\\Users\\ä\\file.txt") -> 'b64_<...>'
    """
    if not isinstance(path, str):
        raise TypeError("path must be a str")

    normalized = _normalize(path)
    data = normalized.encode("utf-8")
    b64 = base64.urlsafe_b64encode(data).decode("ascii")
    # strip padding to make tokens shorter and still reversible (we re-pad on decode)
    b64 = b64.rstrip("=")
    token = "b64_" + b64
    # Guard against accidental reserved device names (case-insensitive)
    if token.upper() in _RESERVED:
        token = "_" + token
    return token


def decode_path(token: str) -> str:
    """Decode a token previously produced by encode_path back to the original path.

    Raises ValueError if the token format is not recognized or decoding fails.
    """
    if not isinstance(token, str):
        raise TypeError("token must be a str")

    # handle the optional leading '_' used when token matched a reserved name
    if token.startswith("_"):
        token = token[1:]

    if not token.startswith("b64_"):
        raise ValueError("unsupported token format")

    b64 = token[4:]
    # restore padding
    pad_len = (-len(b64)) % 4
    b64_padded = b64 + ("=" * pad_len)
    try:
        data = base64.urlsafe_b64decode(b64_padded.encode("ascii"))
    except (ValueError, binascii.Error) as exc:  # pragma: no cover - defensive
        raise ValueError("invalid base64 token") from exc

    return data.decode("utf-8")


__all__ = ["decode_path", "encode_path"]


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

        # Log filtering settings — default to showing only warnings and errors
        # (DEBUG and INFO are disabled by default to reduce noise).
        self.enabled_levels = {
            LogLevel.DEBUG: False,
            LogLevel.INFO: False,
            LogLevel.WARNING: True,
            LogLevel.ERROR: True,
        }

        # Track highest log level for status indicator
        # Default to 'warning' since debug/info are disabled by default
        self.highest_level = "warning"
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
        # Set to DEBUG so all messages reach handlers (filtering done in handlers)
        root_logger.setLevel(logging.DEBUG)

        # Remove existing handlers to avoid duplicates
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)

        # Add our custom handler first (highest priority)
        root_logger.addHandler(self.custom_handler)

        # Also add a console handler for terminal output with filtering
        class ConsoleLogHandler(logging.StreamHandler):
            """Custom console log handler respecting level filtering."""

            def __init__(self, logging_manager, *args, **kwargs):
                """Initialize console handler with reference to logging manager."""
                super().__init__(*args, **kwargs)
                self.logging_manager = logging_manager

            def emit(self, record):
                """Emit a log record only if its level is enabled."""
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
