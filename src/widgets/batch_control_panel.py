"""Batch Control Panel widget for managing batch processing controls.

Part of Droplet Wall Interaction Tool (DWIT).
"""

from collections.abc import Callable

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMenu,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.helpers.batch import FolderItemDelegate
from src.utilities.core_utils import get_logger
from src.widgets.folder_manager import FolderDropZone

logger = get_logger(__name__)


class BatchControlPanel(QWidget):
    """Widget for batch processing controls and folder list management."""

    def __init__(
        self,
        parent: QWidget | None = None,
        on_add_folders: Callable[[], None] | None = None,
        on_folders_dropped: Callable[[list[str]], None] | None = None,
        on_show_help: Callable[[], None] | None = None,
        on_process_batch: Callable[[], None] | None = None,
        on_set_process_mode: Callable[[str], None] | None = None,
        on_pause_resume: Callable[[], None] | None = None,
        on_stop: Callable[[], None] | None = None,
        on_context_menu: Callable[[object], None] | None = None,
    ):
        """Initialize the BatchControlPanel widget.

        Parameters
        ----------
        parent : QWidget | None
            Parent widget
        on_add_folders : Callable | None
            Callback when Add Folders button is clicked
        on_folders_dropped : Callable[[list[str]], None] | None
            Callback when folders are dropped
        on_show_help : Callable | None
            Callback when help button is clicked
        on_process_batch : Callable | None
            Callback when process batch button is clicked
        on_set_process_mode : Callable[[str], None] | None
            Callback when process mode is changed
        on_pause_resume : Callable | None
            Callback when pause/resume button is clicked
        on_stop : Callable | None
            Callback when stop button is clicked
        on_context_menu : Callable[[object], None] | None
            Callback when context menu is requested

        """
        super().__init__(parent)

        # Store callbacks
        self.on_add_folders = on_add_folders
        self.on_folders_dropped = on_folders_dropped
        self.on_show_help = on_show_help
        self.on_process_batch = on_process_batch
        self.on_set_process_mode = on_set_process_mode
        self.on_pause_resume = on_pause_resume
        self.on_stop = on_stop
        self.on_context_menu = on_context_menu

        # Processing mode state
        self.processing_mode = "undone"

        # Initialize UI
        self._create_widgets()
        self._setup_layout()
        self._setup_connections()

    def _create_widgets(self) -> None:
        """Create all child widgets."""
        # Create folder list widget with custom delegate
        self.folder_list = QListWidget()
        self.folder_list.setSelectionMode(QListWidget.ExtendedSelection)
        self.folder_list.setMinimumHeight(100)
        self.folder_list.setUniformItemSizes(False)
        self.folder_delegate = FolderItemDelegate()
        self.folder_list.setItemDelegate(self.folder_delegate)
        self.folder_list.setContextMenuPolicy(Qt.CustomContextMenu)

        # Results scanner thread and worker (initialized later)
        self._results_scanner_thread = None
        self._results_scanner_worker = None

        # Batch progress bar
        self.batch_progress = QProgressBar()
        self.batch_progress.setRange(0, 100)
        self.batch_progress.setValue(0)
        self.batch_progress.setFixedHeight(3)
        self.batch_progress.setTextVisible(False)
        self.batch_progress.setStyleSheet(
            """
            QProgressBar {
                border: none;
                background-color: #e0e0e0;
                border-radius: 1px;
            }
            QProgressBar::chunk {
                background-color: #4CAF50;
                border-radius: 1px;
            }
        """
        )

        # Control buttons
        self.add_folders_btn = QPushButton("Add Folders")
        self.add_folders_btn.setFixedHeight(32)
        self.add_folders_btn.setMinimumWidth(100)
        self.add_folders_btn.setToolTip(
            "Add one or more folders to the batch processing queue. "
            "The application will automatically find subfolders containing data."
        )

        # Drag-and-drop zone
        self.drop_zone = FolderDropZone()
        try:
            self.drop_zone.setFixedWidth(130)
        except Exception:
            self.drop_zone.setMinimumWidth(90)

        # Help button
        self.help_btn = QPushButton("?")
        self.help_btn.setFixedSize(32, 32)
        self.help_btn.setToolTip("Click to learn about folder detection")
        self.help_btn.setStyleSheet(
            """
            QPushButton {
                background-color: #808080;
                color: white;
                border-radius: 16px;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #606060;
            }
            QPushButton:pressed {
                background-color: #404040;
            }
        """
        )

        # Split button for processing options
        self.split_button_widget = QWidget()
        split_button_layout = QHBoxLayout(self.split_button_widget)
        split_button_layout.setContentsMargins(0, 0, 0, 0)
        split_button_layout.setSpacing(0)

        self.process_batch_btn = QPushButton("Process Undone")
        self.process_batch_btn.setMinimumWidth(120)

        self.mode_dropdown_btn = QPushButton("▲")
        self.mode_dropdown_btn.setMaximumWidth(20)
        self.mode_dropdown_btn.setMinimumWidth(20)

        # Create dropdown menu
        self.process_menu = QMenu(self)
        process_undone_action = self.process_menu.addAction("Process Undone")
        process_undone_action.setToolTip(
            "Process only folders that don't have results_raw.xlsx file (default)"
        )
        process_undone_action.triggered.connect(lambda: self.set_process_mode("undone"))

        process_all_action = self.process_menu.addAction("Process All")
        process_all_action.setToolTip(
            "Process all folders independent from done-status"
        )
        process_all_action.triggered.connect(lambda: self.set_process_mode("all"))

        self.mode_dropdown_btn.setMenu(self.process_menu)

        split_button_layout.addWidget(self.process_batch_btn)
        split_button_layout.addWidget(self.mode_dropdown_btn)

        # Pause/Resume button
        self.pause_resume_btn = QPushButton()
        self.pause_resume_btn.setIcon(
            QIcon.fromTheme("media-playback-pause", QIcon(":/icons/pause.png"))
        )
        self.pause_resume_btn.setToolTip("Pause processing")
        self.pause_resume_btn.setFixedSize(30, 30)
        self.pause_resume_btn.setIconSize(QSize(20, 20))

        # Stop button
        self.stop_btn = QPushButton()
        self.stop_btn.setIcon(
            QIcon.fromTheme("media-playback-stop", QIcon(":/icons/stop.png"))
        )
        self.stop_btn.setToolTip("Stop processing")
        self.stop_btn.setFixedSize(30, 30)
        self.stop_btn.setIconSize(QSize(20, 20))

        # Hidden compatibility widgets
        self.folder_counter = QLabel("0/0")
        self.folder_counter.hide()

        self.overall_progress = QProgressBar()
        self.overall_progress.setRange(0, 100)
        self.overall_progress.setValue(0)
        self.overall_progress.hide()

    def _setup_layout(self) -> None:
        """Set up widget layout."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # Create combined controls layout
        controls_layout = QHBoxLayout()
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(5)

        controls_layout.addWidget(self.add_folders_btn)
        controls_layout.addWidget(self.drop_zone)
        controls_layout.addWidget(self.help_btn)
        controls_layout.addWidget(self.split_button_widget)
        controls_layout.addWidget(self.pause_resume_btn)
        controls_layout.addWidget(self.stop_btn)

        # Add controls at the top
        main_layout.addLayout(controls_layout)

        # Add folder list
        main_layout.addWidget(self.folder_list)

        # Add batch progress bar
        main_layout.addWidget(self.batch_progress)

    def _setup_connections(self) -> None:
        """Connect widget signals to callbacks."""
        if self.on_add_folders:
            self.add_folders_btn.clicked.connect(self.on_add_folders)

        if self.on_folders_dropped:
            self.drop_zone.folders_dropped.connect(self.on_folders_dropped)

        if self.on_show_help:
            self.help_btn.clicked.connect(self.on_show_help)

        if self.on_process_batch:
            self.process_batch_btn.clicked.connect(self.on_process_batch)

        if self.on_pause_resume:
            self.pause_resume_btn.clicked.connect(self.on_pause_resume)

        if self.on_stop:
            self.stop_btn.clicked.connect(self.on_stop)

        if self.on_context_menu:
            self.folder_list.customContextMenuRequested.connect(self.on_context_menu)

    def set_process_mode(self, mode: str) -> None:
        """Set the processing mode and update button text.

        Parameters
        ----------
        mode : str
            Processing mode: "undone" or "all"

        """
        self.processing_mode = mode

        if mode == "undone":
            self.process_batch_btn.setText("Process Undone")
            self.process_batch_btn.setToolTip(
                "Process only folders that don't have results_raw.xlsx file"
            )
        else:  # mode == "all"
            self.process_batch_btn.setText("Process All")
            self.process_batch_btn.setToolTip(
                "Process all folders independent from done-status"
            )

        self.mode_dropdown_btn.setToolTip(
            f"Current mode: {mode}. Click to change processing mode."
        )

        logger.info(f"Processing mode set to: {mode}")

        # Call the callback if provided
        if self.on_set_process_mode:
            self.on_set_process_mode(mode)

    def set_pause_resume_state(self, is_paused: bool) -> None:
        """Update pause/resume button state.

        Parameters
        ----------
        is_paused : bool
            True if paused, False if running

        """
        if is_paused:
            self.pause_resume_btn.setIcon(
                QIcon.fromTheme("media-playback-start", QIcon(":/icons/play.png"))
            )
            self.pause_resume_btn.setToolTip("Resume processing")
        else:
            self.pause_resume_btn.setIcon(
                QIcon.fromTheme("media-playback-pause", QIcon(":/icons/pause.png"))
            )
            self.pause_resume_btn.setToolTip("Pause processing")
