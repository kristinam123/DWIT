"""Improved overlay widgets that properly follow their parent windows."""

import re

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
)

from src.utilities.logging_manager import get_logger

# Setup logger for this module
logger = get_logger(__name__)


class SmoothOverlay(QFrame):
    """Base class for smooth animated overlays that follow their parent."""

    def __init__(self, parent=None):
        """Initialize the overlay as a child widget."""
        super().__init__(parent)
        self.parent_widget = parent
        self._hide_connection_active = False  # Track connection state

        logger.info(f"Initializing {self.__class__.__name__} overlay")

        # Use the centralized logger instead of creating a separate one
        self.logger = logger

        self._setup_overlay()
        self._setup_animation()

    def _setup_overlay(self):
        """Set up the overlay as a child widget."""
        # Make it a child widget, not a separate window
        self.setParent(self.parent_widget)

        # Style the overlay with consistent design
        self.setStyleSheet(
            """
            QFrame {
                background-color: rgba(0, 0, 0, 240);
                border: 1px solid rgba(128, 128, 128, 180);
                border-radius: 8px;
            }
        """
        )

        self.setAttribute(Qt.WA_StyledBackground, True)
        # Ensure the overlay receives proper mouse events
        self.setAttribute(Qt.WA_OpaquePaintEvent, False)
        self.setFocusPolicy(Qt.StrongFocus)
        self.hide()

    def _setup_animation(self):
        """Set up smooth show/hide animations."""
        self.opacity_effect = QGraphicsOpacityEffect()
        self.setGraphicsEffect(self.opacity_effect)

        # Consistent animation settings
        self.animation_duration = 250
        self.fade_animation = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.fade_animation.setDuration(self.animation_duration)
        self.fade_animation.setEasingCurve(QEasingCurve.Type.OutCubic)

    def show_overlay(self):
        """Show overlay with smooth animation."""
        try:
            # Ensure clean state before starting new animation
            self._ensure_clean_animation_state()

            # Force a clean visibility state
            self.setVisible(True)
            self._update_geometry()
            self.raise_()

            # Animate fade in
            self.fade_animation.setStartValue(0.0)
            self.fade_animation.setEndValue(1.0)
            self.fade_animation.start()

        except Exception as e:
            logger.error(f"Error showing overlay: {e}")
            # Fallback: show without animation
            self.setVisible(True)
            self.raise_()

    def hide_overlay(self):
        """Hide overlay with smooth animation."""
        try:
            # Ensure clean state before starting new animation
            self._ensure_clean_animation_state()

            # Animate fade out
            self.fade_animation.setStartValue(1.0)
            self.fade_animation.setEndValue(0.0)

            # Only connect if not already connected
            if not self._hide_connection_active:
                self.fade_animation.finished.connect(self._on_hide_finished)
                self._hide_connection_active = True

            self.fade_animation.start()

        except Exception as e:
            logger.error(f"Error hiding overlay: {e}")
            # Fallback: hide immediately
            self.setVisible(False)

    def _ensure_clean_animation_state(self):
        """Ensure animation is in clean state before starting new animation."""
        # Stop any running animation first
        if self.fade_animation.state() != self.fade_animation.State.Stopped:
            self.fade_animation.stop()

        # Disconnect all connections if any exist (only if we have an active connection)
        if self._hide_connection_active:
            try:
                self.fade_animation.finished.disconnect()
                self._hide_connection_active = False
            except (RuntimeError, TypeError):
                # Connection was already disconnected or never existed
                self._hide_connection_active = False

    def _on_hide_finished(self):
        """Handle hide animation completion."""
        self.setVisible(False)
        # Disconnect the signal and update our tracking state
        try:
            self.fade_animation.finished.disconnect(self._on_hide_finished)
        except (RuntimeError, TypeError):
            # Connection was already disconnected
            pass
        finally:
            self._hide_connection_active = False

    def toggle_overlay(self):
        """Toggle overlay visibility."""
        try:
            # Stop any running animation first to ensure clean state
            if self.fade_animation.state() != self.fade_animation.State.Stopped:
                self.fade_animation.stop()
                # Reset opacity to a known state
                self.opacity_effect.setOpacity(1.0 if self.isVisible() else 0.0)

            if self.isVisible():
                self.hide_overlay()
            else:
                self.show_overlay()

        except Exception as e:
            logger.error(f"Error toggling overlay: {e}")
            # Fallback to simple visibility toggle
            if self.isVisible():
                self.setVisible(False)
            else:
                self.setVisible(True)
                self.raise_()

    def _update_geometry(self):
        """Update overlay geometry - to be implemented by subclasses."""
        pass

    def resize_event(self, event):
        """Handle resize events."""
        super().resize_event(event)
        if self.isVisible():
            self._update_geometry()

    def show_event(self, event):
        """Handle show events."""
        super().show_event(event)
        self._update_geometry()

    def mousePressEvent(self, event):  # noqa: N802
        """Handle mouse press events to close overlay when clicking on empty areas."""
        # Check if the click is on an interactive widget
        widget_at_pos = self.childAt(event.pos())

        # If clicked on an interactive widget, let it handle the event
        if widget_at_pos and widget_at_pos.isEnabled():
            super().mousePressEvent(event)
            return

        # If clicked on empty space, close the overlay
        self.hide_overlay()


class LogOverlay(SmoothOverlay):
    """Improved log overlay with filtering and color coding."""

    def __init__(self, parent=None):
        """Initialize the LogOverlay."""
        super().__init__(parent)
        self.logging_manager = None  # Will be set later
        self.color_formats = self._setup_color_formats()

        # Store all log messages for re-filtering
        self.all_messages = []  # list of (message, level) tuples

        # Buffer for incoming log messages
        self._buffered_messages = []  # list of (message, level)

        # Timer for flushing the buffer
        self._flush_timer = QTimer(self)
        self._flush_timer.setInterval(100)  # ms, adjust as needed
        self._flush_timer.timeout.connect(self._flush_buffered_messages)
        self._flush_timer.start()

        self._create_widgets()

    def _setup_color_formats(self):
        """Set up text formats for different log levels."""
        formats = {}

        # [DEBUG] - Cyan
        debug_format = QTextCharFormat()
        debug_format.setForeground(QColor("#00FFFF"))
        debug_format.setFontWeight(QFont.Weight.Bold)
        formats["DEBUG"] = debug_format

        # [INFO] - Green
        info_format = QTextCharFormat()
        info_format.setForeground(QColor("#00FF00"))
        info_format.setFontWeight(QFont.Weight.Bold)
        formats["INFO"] = info_format

        # [WARNING] - Orange
        warning_format = QTextCharFormat()
        warning_format.setForeground(QColor("#FFA500"))
        warning_format.setFontWeight(QFont.Weight.Bold)
        formats["WARNING"] = warning_format

        # [ERROR] - Red
        error_format = QTextCharFormat()
        error_format.setForeground(QColor("#FF0000"))
        error_format.setFontWeight(QFont.Weight.Bold)
        formats["ERROR"] = error_format

        # Message text (always white, normal weight)
        message_format = QTextCharFormat()
        message_format.setForeground(QColor("#FFFFFF"))
        message_format.setFontWeight(QFont.Weight.Normal)
        formats["MESSAGE"] = message_format

        # Timestamp format (gray)
        timestamp_format = QTextCharFormat()
        timestamp_format.setForeground(QColor("#888888"))
        timestamp_format.setFontWeight(QFont.Weight.Normal)
        formats["TIMESTAMP"] = timestamp_format

        return formats

    def _create_widgets(self):
        """Create the log overlay widgets."""
        layout = QVBoxLayout(self)

        # Filter controls with close button integrated
        filter_frame = QFrame()
        filter_frame.setStyleSheet(
            """
            QFrame {
                background-color: rgba(40, 40, 40, 200);
                border: 1px solid rgba(128, 128, 128, 100);
                border-radius: 4px;
                margin: 2px;
            }
        """
        )
        filter_layout = QHBoxLayout(filter_frame)
        filter_layout.setContentsMargins(8, 4, 8, 4)

        # Close button (moved to left of checkboxes)
        self.toggle_btn = QToolButton()
        self.toggle_btn.setText("▼ Log")
        self.toggle_btn.setToolTip("Hide log")
        self.toggle_btn.clicked.connect(self.hide_overlay)
        self.toggle_btn.setStyleSheet(
            """
            QToolButton {
                color: white;
                border: none;
                font-weight: bold;
                background-color: transparent;
                font-size: 12px;
            }
            QToolButton:hover {
                background-color: rgba(255, 255, 255, 20);
                border-radius: 4px;
            }
        """
        )
        filter_layout.addWidget(self.toggle_btn)

        # Create checkboxes for each log level
        self.level_checkboxes = {}
        levels = [
            ("DEBUG", "#00FFFF", "Show debug messages"),
            ("INFO", "#00FF00", "Show info messages"),
            ("WARNING", "#FFA500", "Show warning messages"),
            ("ERROR", "#FF0000", "Show error messages"),
        ]

        for level, color, tooltip in levels:
            checkbox = QCheckBox(level)
            checkbox.setChecked(True)  # Default to all enabled
            checkbox.setToolTip(tooltip)
            checkbox.setStyleSheet(
                f"""
                QCheckBox {{
                    color: {color};
                    font-size: 11px;
                    font-weight: bold;
                }}
                QCheckBox::indicator {{
                    width: 14px;
                    height: 14px;
                }}
                QCheckBox::indicator:unchecked {{
                    background-color: rgba(60, 60, 60, 200);
                    border: 1px solid rgba(120, 120, 120, 200);
                    border-radius: 2px;
                }}
                QCheckBox::indicator:checked {{
                    background-color: {color};
                    border: 1px solid {color};
                    border-radius: 2px;
                }}
            """
            )
            checkbox.stateChanged.connect(
                lambda state, lvl=level: self._on_filter_changed(lvl, state == 2)
            )
            self.level_checkboxes[level] = checkbox
            filter_layout.addWidget(checkbox)

        # Clear button
        clear_btn = QToolButton()
        clear_btn.setText("Clear")
        clear_btn.setToolTip("Clear all log messages")
        clear_btn.clicked.connect(self.clear_log)
        clear_btn.setStyleSheet(
            """
            QToolButton {
                color: white;
                border: 1px solid rgba(128, 128, 128, 100);
                border-radius: 3px;
                padding: 2px 8px;
                font-size: 11px;
                background-color: rgba(60, 60, 60, 150);
            }
            QToolButton:hover {
                background-color: rgba(80, 80, 80, 200);
            }
            QToolButton:pressed {
                background-color: rgba(100, 100, 100, 200);
            }
        """
        )
        filter_layout.addStretch(1)
        filter_layout.addWidget(clear_btn)

        layout.addWidget(filter_frame)

        # Log text area with terminal-like styling
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Consolas", 10))
        self.log_text.setStyleSheet(
            """
            QTextEdit {
                background-color: rgba(12, 12, 12, 240);
                color: white;
                border: 1px solid rgba(128, 128, 128, 100);
                border-radius: 6px;
                padding: 8px;
                selection-background-color: rgba(70, 130, 180, 100);
            }
            QScrollBar:vertical {
                background-color: rgba(40, 40, 40, 180);
                width: 12px;
                border-radius: 6px;
                border: none;
            }
            QScrollBar::handle:vertical {
                background-color: rgba(100, 100, 100, 200);
                border-radius: 6px;
                min-height: 20px;
                margin: 2px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: rgba(130, 130, 130, 220);
            }
            QScrollBar::handle:vertical:pressed {
                background-color: rgba(160, 160, 160, 240);
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: none;
            }
        """
        )
        self.log_text.setMinimumHeight(200)
        self.log_text.setMaximumHeight(350)
        layout.addWidget(self.log_text)

    def set_logging_manager(self, logging_manager):
        """Set the logging manager reference and sync filter states."""
        self.logging_manager = logging_manager

        # Ensure logging manager settings are initialized
        if self.logging_manager:
            self.logging_manager.initialize_settings()

        # Sync checkbox states with saved settings
        if self.logging_manager:
            for level, checkbox in self.level_checkboxes.items():
                enabled = self.logging_manager.is_level_enabled(level)
                checkbox.setChecked(enabled)

            # Refresh display to show only enabled levels
            self._refresh_display()

    def _on_filter_changed(self, level: str, enabled: bool):
        """Handle filter checkbox changes."""
        if self.logging_manager:
            self.logging_manager.set_level_enabled(level, enabled)
            # Re-display all messages with new filter settings
            self._refresh_display()

    def append_log_message(self, message: str, level: str):
        """Append a formatted log message to storage and display if enabled."""
        # Always store the message regardless of filter state
        self.all_messages.append((message, level))

        # Limit stored messages to prevent memory issues
        if len(self.all_messages) > 2000:
            # Remove oldest 500 messages
            self.all_messages = self.all_messages[500:]

        # Buffer the message for periodic flush
        self._buffered_messages.append((message, level))

        # Optionally, flush immediately if buffer is too large
        if len(self._buffered_messages) > 100:
            self._flush_buffered_messages()

    def _flush_buffered_messages(self):
        """Flush buffered log messages to the display if their level is enabled."""
        if not self._buffered_messages:
            return
        for message, level in self._buffered_messages:
            if self.logging_manager and self.logging_manager.is_level_enabled(level):
                self._display_single_message(message, level)
        self._buffered_messages.clear()

    def _display_single_message(self, message: str, level: str):
        """Display a single log message with formatting."""
        cursor = self.log_text.textCursor()
        cursor.movePosition(QTextCursor.End)

        # Parse the message to separate components
        # Expected format: [LEVEL] HH:MM:SS message
        match = re.match(r"(\[(\w+)\])\s+(\d{2}:\d{2}:\d{2})\s+(.*)", message)
        if match:
            level_bracket = match.group(1)  # [LEVEL]
            level_name = match.group(2)  # LEVEL
            timestamp = match.group(3)  # HH:MM:SS
            rest_message = match.group(4)  # message content

            # Insert level bracket with appropriate color
            level_format = self.color_formats.get(
                level_name, self.color_formats["MESSAGE"]
            )
            cursor.insertText(level_bracket, level_format)

            # Insert timestamp in gray
            cursor.insertText(f" {timestamp} ", self.color_formats["TIMESTAMP"])

            # Insert rest of message in white
            cursor.insertText(rest_message, self.color_formats["MESSAGE"])
        else:
            # Fallback: try to parse older format [LEVEL] timestamp - logger - message
            match_old = re.match(r"(\[(\w+)\])(.*)", message)
            if match_old:
                level_bracket = match_old.group(1)  # [LEVEL]
                level_name = match_old.group(2)  # LEVEL
                rest_message = match_old.group(3)  # Everything after [LEVEL]

                # Insert level bracket with appropriate color
                level_format = self.color_formats.get(
                    level_name, self.color_formats["MESSAGE"]
                )
                cursor.insertText(level_bracket, level_format)

                # Insert rest of message in white
                cursor.insertText(rest_message, self.color_formats["MESSAGE"])
            else:
                # Ultimate fallback: use message format for entire message
                cursor.insertText(message, self.color_formats["MESSAGE"])

        # Add newline
        cursor.insertText("\n", self.color_formats["MESSAGE"])

        # Auto-scroll to bottom
        self.log_text.ensureCursorVisible()

    def _refresh_display(self):
        """Refresh the display to show all messages."""
        # Clear current display
        self.log_text.clear()

        # Re-display all messages that match current filter settings
        for message, level in self.all_messages:
            if self.logging_manager and self.logging_manager.is_level_enabled(level):
                self._display_single_message(message, level)

        # Auto-scroll to bottom after refresh
        self.log_text.ensureCursorVisible()

    def clear_log(self):
        """Clear all log messages and buffer."""
        self.log_text.clear()
        self.all_messages.clear()  # Also clear stored messages
        self._buffered_messages.clear()

    def _update_geometry(self):
        """Update overlay geometry to stick to bottom of parent."""
        if not self.parent_widget:
            return

        parent_rect = self.parent_widget.rect()
        height = 350  # Reduced height since header is removed

        # Position at bottom of parent with consistent margin
        self.setGeometry(0, parent_rect.height() - height, parent_rect.width(), height)


class NavigationOverlay(SmoothOverlay):
    """Improved navigation overlay that follows its parent smoothly."""

    def __init__(self, parent=None):
        """Initialize the NavigationOverlay."""
        super().__init__(parent)
        self.last_analysis_mode = 1  # Default to Free Sedimentation
        self._create_widgets()
        self._update_analysis_button_text()  # Initialize button text

    def _create_widgets(self):
        """Create navigation widgets."""
        layout = QVBoxLayout(self)

        # Header with consistent styling
        header_layout = QHBoxLayout()
        self.toggle_btn = QToolButton()
        self.toggle_btn.setText("Page Selection ▼")
        self.toggle_btn.clicked.connect(self.hide_overlay)
        self.toggle_btn.setStyleSheet(
            """
            QToolButton {
                color: white;
                border: none;
                font-weight: bold;
                background-color: transparent;
            }
            QToolButton:hover {
                background-color: rgba(255, 255, 255, 20);
                border-radius: 4px;
            }
        """
        )
        header_layout.addStretch(1)
        header_layout.addWidget(self.toggle_btn)
        layout.addLayout(header_layout)

        # Navigation buttons with consistent styling
        nav_frame = QFrame()
        nav_frame.setStyleSheet(
            """
            QFrame {
                background-color: rgba(20, 20, 20, 100);
                border: 1px solid rgba(128, 128, 128, 100);
                border-radius: 4px;
            }
        """
        )
        nav_layout = QVBoxLayout(nav_frame)

        main_pages = [
            (0, "Controllers"),
            (5, "Experiment Table"),
        ]

        for idx, text in main_pages:
            btn = QToolButton()
            btn.setText(text)
            btn.setStyleSheet(
                """
                QToolButton {
                    color: white;
                    text-align: center;
                    border: none;
                    font-size: 12px;
                    background-color: transparent;
                    min-width: 180px;
                }
                QToolButton:hover {
                    background-color: rgba(255, 255, 255, 25);
                    color: #ffffff;
                }
                QToolButton:pressed {
                    background-color: rgba(255, 255, 255, 40);
                }
            """
            )
            btn.clicked.connect(lambda checked, i=idx: self._navigate_to(i))
            nav_layout.addWidget(btn)

        # Add Analysis button (opens last selected analysis mode)
        self.analysis_btn = QToolButton()
        self.analysis_btn.setText("Analysis")
        self.analysis_btn.setStyleSheet(
            """
            QToolButton {
                color: white;
                text-align: center;
                border: none;
                font-size: 12px;
                background-color: transparent;
                min-width: 180px;
            }
            QToolButton:hover {
                background-color: rgba(255, 255, 255, 25);
                color: #ffffff;
            }
            QToolButton:pressed {
                background-color: rgba(255, 255, 255, 40);
            }
        """
        )
        self.analysis_btn.clicked.connect(self._open_analysis)
        nav_layout.addWidget(self.analysis_btn)

        # Add separator
        separator = QFrame()
        separator.setFrameStyle(QFrame.HLine | QFrame.Sunken)
        separator.setStyleSheet("color: rgba(128, 128, 128, 100);")
        nav_layout.addWidget(separator)

        # Add analysis mode buttons (indented)
        analysis_modes = [
            (1, "Free Sedimentation"),
            (2, "Contact Angle"),
            (3, "Channel"),
            (4, "Structured Packing"),
        ]

        for idx, text in analysis_modes:
            btn = QToolButton()
            btn.setText(f"  {text}")  # Indent with spaces
            btn.setStyleSheet(
                """
                QToolButton {
                    color: rgba(220, 220, 220, 200);
                    text-align: left;
                    border: none;
                    font-size: 11px;
                    background-color: transparent;
                    min-width: 180px;
                }
                QToolButton:hover {
                    background-color: rgba(255, 255, 255, 15);
                    color: #ffffff;
                }
                QToolButton:pressed {
                    background-color: rgba(255, 255, 255, 30);
                }
            """
            )
            btn.clicked.connect(lambda checked, i=idx: self._navigate_to_analysis(i))
            nav_layout.addWidget(btn)

        nav_layout.addStretch()
        layout.addWidget(nav_frame)

    def _update_geometry(self):
        """Update overlay geometry to stick to bottom-right of parent."""
        if not self.parent_widget:
            return

        parent_rect = self.parent_widget.rect()
        width = 220  # Reduced width for compact design
        height = 250  # Reduced height for compact design

        # Position at bottom-right of parent
        self.setGeometry(
            parent_rect.width() - width, parent_rect.height() - height, width, height
        )

    def _navigate_to(self, page_index):
        """Navigate to selected page."""
        if self.parent_widget and hasattr(
            self.parent_widget, "_apply_selected_navigation"
        ):
            self.parent_widget._apply_selected_navigation(page_index)
        self.hide_overlay()

    def _navigate_to_analysis(self, analysis_mode):
        """Navigate to specific analysis mode and remember it."""
        self.last_analysis_mode = analysis_mode
        self._update_analysis_button_text()
        if self.parent_widget and hasattr(
            self.parent_widget, "_apply_selected_navigation"
        ):
            self.parent_widget._apply_selected_navigation(analysis_mode)
        self.hide_overlay()

    def _open_analysis(self):
        """Open the last selected analysis mode."""
        if self.parent_widget and hasattr(
            self.parent_widget, "_apply_selected_navigation"
        ):
            self.parent_widget._apply_selected_navigation(self.last_analysis_mode)
        self.hide_overlay()

    def _update_analysis_button_text(self):
        """Update the analysis button text to show current mode."""
        mode_names = {
            1: "Free Sedimentation",
            2: "Contact Angle",
            3: "Channel",
            4: "Structured Packing",
        }
        current_mode = mode_names.get(self.last_analysis_mode, "Free Sedimentation")
        self.analysis_btn.setText(f"Analysis ({current_mode})")
