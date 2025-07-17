"""Core camera control and acquisition logic for MesszelleApp.

Includes threading and hardware integration.
"""

import ctypes
import os
import time
from typing import Any, Optional

import numpy as np
from PIL import Image
from PySide6.QtCore import Property, QObject, QSettings, Signal

import src.utilities.XsCamera as XsCamera
from src.threads.camera_threads import LiveFeedThread, RecordingThread
from src.utilities.logging_manager import get_logger
from src.utilities.roi import RoiVar
from src.utilities.XsCamera import (
    XS_LIVE,
    XS_PARAM,
    XS_PRE_PARAM,
    XS_REC_MODE,
    XS_STATUS,
    XS_SYNCIN_CFG,
)

# Setup logger for this module
logger = get_logger(__name__)

# Constants
DEFAULT_RECORD_SECONDS = 15
DEFAULT_SAVE_FOLDER = "data"
CAMERA_LIB_PATH = (
    "C:\\Users\\arifr\\Documents\\IDT\\CameraSDK 2.16.08\\Bin\\x64\\XStreamDrv"
)


class CameraCore(QObject):
    """Core camera functionality with improved error handling and type hints.

    Signals:
        image_updated: Emitted when a new image is available.
        recording_state_changed: Emitted when recording starts/stops.
        live_state_changed: Emitted when live feed starts/stops.
        exp_changed, fps_changed, period_changed: Emitted when camera parameters change.
        error_occurred: Emitted when an error occurs.
    """

    image_updated = Signal()
    recording_state_changed = Signal(bool)
    live_state_changed = Signal(bool)
    exp_changed = Signal(int)
    fps_changed = Signal(int)
    period_changed = Signal(int)
    error_occurred = Signal(str)
    status_changed = Signal(str)

    def __init__(self):
        """Initialize the CameraCore instance."""
        super().__init__()
        logger.info("Initializing CameraCore")

        # Camera parameter limits
        self.min_exp = 1000
        self.max_exp = 1000000
        self.min_period = 10000
        self.max_period = 1000000
        self.min_fps = 1
        self.max_fps = 100
        self.cam_max_width = 5120
        self.cam_max_height = 2880

        # Settings storage
        self.settings = QSettings("MeasurementCellApp", "Camera")

        # Camera parameters
        self._exp = self.settings.value("last_exp", 1000, int)
        self._fps = self.settings.value("last_fps", 30, int)
        self._period = self.settings.value("last_period", 33333, int)
        self._roi_x1 = self.settings.value("roi_x1", 0, int)
        self._roi_x2 = self.settings.value("roi_x2", 500, int)
        self._roi_y1 = self.settings.value("roi_y1", 0, int)
        self._roi_y2 = self.settings.value("roi_y2", 500, int)

        # Add ROI variables expected by ROIDialog
        self.x1_var = RoiVar(self._roi_x1)
        self.x2_var = RoiVar(self._roi_x2 or self.cam_max_width)
        self.y1_var = RoiVar(self._roi_y1)
        self.y2_var = RoiVar(self._roi_y2 or self.cam_max_height)

        # Recording parameters
        self.frames = int(self._fps * DEFAULT_RECORD_SECONDS)
        self.pixelDepth = 8  # Pixel depth in bits (8, 16, 24)

        # State variables
        self.current_image = None
        self.live_frame = None
        self.bufferSize = None
        self.roiWidth = None
        self.roiHeight = None
        self.save_as = None
        self.is_recording = False
        self.is_saving = False
        self.recording = False
        self.live_feed = False
        self.list_of_images = []

        # Camera objects
        self.cameras_found = None
        self.camera_handle = None
        self.live_thread = None
        self.record_thread = None

        # Initialize camera
        try:
            self.initialize_camera()
        except Exception as e:
            self.error_occurred.emit(f"Failed to initialize camera: {e!s}")

    # Properties with getters and setters
    def get_exp(self) -> int:
        """Get the current exposure time value."""
        return self._exp

    def set_exp(self, value: int) -> None:
        """Set the exposure time value."""
        if self._exp != value:
            self._exp = value
            self.settings.setValue("last_exp", value)
            self.exp_changed.emit(value)

    def get_fps(self) -> int:
        """Get the current frames per second value."""
        return self._fps

    def set_fps(self, value: int) -> None:
        """Set the frames per second value."""
        if self._fps != value:
            self._fps = value
            self.settings.setValue("last_fps", value)
            self.fps_changed.emit(value)
            self.frames = int(value * DEFAULT_RECORD_SECONDS)

    def get_period(self) -> int:
        """Get the current period value."""
        return self._period

    def set_period(self, value: int) -> None:
        """Set the period value."""
        if self._period != value:
            self._period = value
            self.settings.setValue("last_period", value)
            self.period_changed.emit(value)

    # Qt properties
    exp = Property(int, get_exp, set_exp, notify=exp_changed)
    fps = Property(int, get_fps, set_fps, notify=fps_changed)
    period = Property(int, get_period, set_period, notify=period_changed)

    def initialize_camera(self) -> None:
        """Initialize the camera and get handles."""
        logger.info("Initializing camera")
        try:
            XsCamera.LoadLibrary(CAMERA_LIB_PATH)
            self.cameras_found = list(
                XsCamera.XsEnumCameras(XsCamera.XS_ENUM_FLT.XS_EF_ALL)
            )

            if not self.cameras_found:
                logger.error("No camera found during enumeration")
                self.error_occurred.emit("No camera found")
                return

            camera_id = self.cameras_found[0].nCameraId
            logger.info(f"Using camera ID: {camera_id}")

            # Pre-configure camera
            XsCamera.XsPreConfigCamera(camera_id, XS_PRE_PARAM.XSPP_PCIX_DMASIZE, 4096)

            # Open camera
            self.camera_handle = XsCamera.XsOpenCamera(camera_id)
            logger.info("Camera opened successfully")

            # Get initial ROI dimensions
            self._update_roi_dimensions()
            logger.info("Camera initialization completed successfully")

        except Exception as e:
            error_msg = f"Camera initialization error: {e!s}"
            logger.error(error_msg)
            self.error_occurred.emit(error_msg)
            raise ConnectionError(f"Failed to initialize camera: {e!s}")

    def _update_roi_dimensions(self) -> None:
        """Update ROI dimensions from camera settings."""
        if not self.camera_handle:
            return

        try:
            cam_settings = XsCamera.XsReadCameraSettings(self.camera_handle)
            self.roiWidth = XsCamera.XsGetParameter(
                self.camera_handle, cam_settings, XS_PARAM.XSP_ROIWIDTH
            )
            self.roiHeight = XsCamera.XsGetParameter(
                self.camera_handle, cam_settings, XS_PARAM.XSP_ROIHEIGHT
            )
            self.bufferSize = int(
                self.roiWidth * self.roiHeight * (self.pixelDepth // 8)
            )

        except Exception as e:
            logger.error(f"Failed to update ROI dimensions: {e!s}")
            pass

    # Camera parameter methods
    def update_exp(self) -> None:
        """Update exposure time with current value."""
        self.update_camera_exp(self._exp)

    def update_camera_exp(self, exp: int) -> None:
        """Update camera exposure time.

        Args:
        ----
            exp: Exposure time in milliseconds

        """
        try:
            # Convert to nanoseconds and clamp to valid range
            exp = exp * 1000
            exp = max(min(exp, self.max_exp), self.min_exp)
            exp = min(exp, self._period)  # Exposure can't exceed period

            # Update property
            self.set_exp(int(exp / 1000))

            # Update camera
            if self.camera_handle:
                cam_settings = XsCamera.XsReadCameraSettings(self.camera_handle)
                XsCamera.XsSetParameter(
                    self.camera_handle, cam_settings, XS_PARAM.XSP_EXPOSURE, exp
                )
                XsCamera.XsRefreshCameraSettings(self.camera_handle, cam_settings)
        except Exception as e:
            logger.error(f"Failed to update exposure: {e!s}")
            pass

    def update_camera_period(self, period: int) -> None:
        """Update camera period (time between frames).

        Args:
        ----
            period: Period in nanoseconds

        """
        try:
            # Clamp to valid range
            period = max(min(period, self.max_period), self.min_period)

            # Update property
            self.set_period(period)

            # Update camera
            if self.camera_handle:
                cam_settings = XsCamera.XsReadCameraSettings(self.camera_handle)
                XsCamera.XsSetParameter(
                    self.camera_handle, cam_settings, XS_PARAM.XSP_PERIOD, period
                )
                XsCamera.XsRefreshCameraSettings(self.camera_handle, cam_settings)
        except Exception as e:
            logger.error(f"Failed to update frame period: {e!s}")
            pass

    def update_fps(self) -> None:
        """Update FPS with current value."""
        self.update_camera_fps(self._fps)

    def update_camera_fps(self, fps: int) -> None:
        """Update the camera FPS by setting the appropriate period.

        Args:
        ----
            fps: Frames per second

        """
        try:
            # Clamp to valid range
            fps = max(min(fps, self.max_fps), self.min_fps)

            # Calculate period in nanoseconds
            period_ns = int(1000000000 / fps + 0.5)

            # Update camera period and FPS property
            self.update_camera_period(period_ns)
            self.set_fps(fps)
        except Exception as e:
            logger.error(f"Failed to update FPS: {e!s}")
            pass

    def change_roi(self, width: int, height: int) -> None:
        """Change camera region of interest.

        Args:
        ----
            width: ROI width in pixels
            height: ROI height in pixels

        """
        try:
            # Validate dimensions
            width = max(16, min(width, self.cam_max_width))
            height = max(16, min(height, self.cam_max_height))

            # Sync properties
            self._roi_x1 = self.x1_var.get()
            self._roi_x2 = self.x2_var.get()
            self._roi_y1 = self.y1_var.get()
            self._roi_y2 = self.y2_var.get()

            # Save to settings
            self.settings.setValue("roi_x1", self._roi_x1)
            self.settings.setValue("roi_x2", self._roi_x2)
            self.settings.setValue("roi_y1", self._roi_y1)
            self.settings.setValue("roi_y2", self._roi_y2)

            # Update ROI dimensions
            self.roiWidth = width
            self.roiHeight = height

            # Update camera
            if self.camera_handle:
                cam_settings = XsCamera.XsReadCameraSettings(self.camera_handle)
                XsCamera.XsSetParameter(
                    self.camera_handle, cam_settings, XS_PARAM.XSP_ROIWIDTH, width
                )
                XsCamera.XsSetParameter(
                    self.camera_handle, cam_settings, XS_PARAM.XSP_ROIHEIGHT, height
                )
                XsCamera.XsRefreshCameraSettings(self.camera_handle, cam_settings)

                # Update buffer size
                self.bufferSize = int(width * height * (self.pixelDepth // 8))
        except Exception as e:
            logger.error(f"Failed to change ROI: {e!s}")
            pass

    # Image processing and saving
    def save_images(
        self,
        image_list: list[Image.Image],
        save_as: str,
        folder: str = DEFAULT_SAVE_FOLDER,
        quality: int = 90,
    ) -> None:
        """Save images to disk.

        Args:
        ----
            image_list: list of PIL Images to save
            save_as: Base name for saved files
            folder: Folder to save images in
            quality: Image quality for compression (0-100)

        """
        if not image_list:
            return

        try:
            # Create folder if it doesn't exist
            os.makedirs(folder, exist_ok=True)

            def save_image(img: Image.Image, idx: int) -> None:
                """Save an individual image to disk."""
                file_path = os.path.join(folder, f"{save_as}_{idx+1}.jpg")
                os.makedirs(os.path.dirname(file_path), exist_ok=True)
                img.save(file_path, format="JPEG", quality=quality)

            # Save each image
            for idx, img in enumerate(image_list):
                save_image(img, idx)

        except Exception as e:
            logger.error(f"Error saving images: {e!s}")
            pass

    def _process_image_data(
        self, image_data: np.ndarray, emit_signal: bool = True
    ) -> Optional[Image.Image]:
        """Process raw image data into a PIL Image.

        Args:
        ----
            image_data: Raw image data as numpy array
            emit_signal: Whether to emit image_updated signal

        Returns:
        -------
            PIL Image object or None if processing failed

        """
        try:
            # Process based on data size
            if len(image_data) == self.roiWidth * self.roiHeight:
                # Grayscale 8-bit
                image_data = image_data.reshape((self.roiHeight, self.roiWidth))
                image = Image.fromarray(image_data, "L")
            elif len(image_data) == self.roiWidth * self.roiHeight * 3:
                # RGB 24-bit
                image_data = image_data.reshape((self.roiHeight, self.roiWidth, 3))
                image = Image.fromarray(image_data, "RGB")
            elif len(image_data) == self.roiWidth * self.roiHeight * 2:
                # Grayscale 16-bit
                image_data = image_data.reshape((self.roiHeight, self.roiWidth))
                image = Image.fromarray(image_data, "I;16")
            else:
                return None

            # Update current image and emit signal
            self.current_image = image
            if emit_signal:
                self.image_updated.emit()

            return image
        except Exception:
            logger.error("Error processing image data")
            return None

    # Camera operation setup
    def setup_camera_for_capture(self, mode: str = "live") -> tuple[ctypes.c_char, Any]:
        """Configure camera for live view or recording.

        Args:
        ----
            mode: "live" or "record"

        Returns:
        -------
            tuple of (buffer, frame)

        """
        try:
            # Read camera settings
            cam_settings = XsCamera.XsReadCameraSettings(self.camera_handle)

            # Get ROI dimensions
            self.roiWidth = XsCamera.XsGetParameter(
                self.camera_handle, cam_settings, XS_PARAM.XSP_ROIWIDTH
            )
            self.roiHeight = XsCamera.XsGetParameter(
                self.camera_handle, cam_settings, XS_PARAM.XSP_ROIHEIGHT
            )

            # Calculate buffer size
            self.bufferSize = int(
                self.roiWidth * self.roiHeight * (self.pixelDepth // 8)
            )

            # Mode-specific setup
            if mode == "record":
                # Set exposure and period
                self.update_camera_exp(self._exp)
                self.update_camera_period(self._period)
                XsCamera.XsSetParameter(
                    self.camera_handle,
                    cam_settings,
                    XS_PARAM.XSP_REC_MODE,
                    XS_REC_MODE.XS_RM_NORMAL,
                )

            # Common settings
            XsCamera.XsSetParameter(
                self.camera_handle,
                cam_settings,
                XS_PARAM.XSP_PIX_DEPTH,
                self.pixelDepth,
            )
            XsCamera.XsSetParameter(
                self.camera_handle, cam_settings, XS_PARAM.XSP_FRAMES, self.frames
            )
            XsCamera.XsSetParameter(
                self.camera_handle, cam_settings, XS_PARAM.XSP_PRE_TRIG, 0
            )
            XsCamera.XsSetParameter(
                self.camera_handle,
                cam_settings,
                XS_PARAM.XSP_SYNCIN_CFG,
                XS_SYNCIN_CFG.XS_SIC_INTERNAL,
            )

            # Apply settings
            XsCamera.XsRefreshCameraSettings(self.camera_handle, cam_settings)

            # Create buffer and frame
            buffer = ctypes.create_string_buffer(self.bufferSize)
            frame = XsCamera.XS_FRAME()

            return buffer, frame
        except Exception as e:
            self.error_occurred.emit(f"Failed to configure camera: {e!s}")
            raise ConnectionError(f"Failed to configure camera: {e!s}")

    # Camera operation loops
    def live_feed_loop(self, stopper=None):
        """Live feed generator function.

        Args:
        ----
            stopper: Thread stopper object

        Yields:
        ------
            PIL Image objects from live feed

        """
        try:
            # Set up camera for live feed
            live_buf, self.live_frame = self.setup_camera_for_capture("live")

            # Start live feed
            self.live_feed = True
            XsCamera.XsLive(self.camera_handle, XS_LIVE.XS_LIVE_START)

            # Loop for frames
            loop_idx = 0
            while loop_idx < self.frames:
                # Check for stop request
                if stopper and stopper.is_stop_requested():
                    break

                # Get frame
                XsCamera.XsMemoryPreview(self.camera_handle, self.live_frame)

                # Process frame
                image_data = np.frombuffer(live_buf, dtype=np.uint8)
                image = self._process_image_data(image_data)

                if image:
                    yield image

                loop_idx += 1
        except Exception as e:
            self.error_occurred.emit(f"Live feed error: {e!s}")
        finally:
            # Ensure live feed is stopped
            XsCamera.XsLive(self.camera_handle, XS_LIVE.XS_LIVE_STOP)
            self.live_feed = False

    def record_feed_loop(self, stopper=None):
        """Record the camera feed in a separate thread.

        Args:
        ----
            stopper: Thread stopper object

        Returns:
        -------
            list of recorded images

        """
        try:
            # Set up camera for recording
            rec_buf, self.live_frame = self.setup_camera_for_capture("record")

            # Set recording state
            self.is_recording = True
            self.recording = True

            # Start recording
            XsCamera.XsMemoryStartGrab(
                self.camera_handle, 0, 0, self.frames, 0, 0, 0, 0
            )
            time.sleep(0.1)

            # Wait for recording to complete
            t_start = time.time()
            t_elapsed = 0
            _, status, _, _ = XsCamera.XsGetCameraStatus(self.camera_handle)

            while (
                status == XS_STATUS.XSST_REC_PRETRG
                or status == XS_STATUS.XSST_REC_POSTRG
            ) and t_elapsed < 10:
                time.sleep(0.1)
                _, status, _, _ = XsCamera.XsGetCameraStatus(self.camera_handle)
                t_elapsed = time.time() - t_start

            # Recording complete, start saving
            self.is_recording = False
            self.list_of_images = []
            self.is_saving = True

            # Process each frame
            for loop_idx in range(self.frames):
                # Check for stop request
                if stopper and stopper.is_stop_requested():
                    break

                # Read frame
                XsCamera.XsMemoryReadFrame(self.camera_handle, 0, 0, loop_idx, rec_buf)

                # Process frame
                dtype = (
                    np.uint8
                    if self.pixelDepth == 8
                    else np.uint16 if self.pixelDepth == 16 else np.uint32
                )
                image_data = np.frombuffer(rec_buf, dtype=dtype)
                image = self._process_image_data(image_data, emit_signal=False)

                if image:
                    self.list_of_images.append(image)

            return self.list_of_images
        except Exception as e:
            self.error_occurred.emit(f"Recording error: {e!s}")
            return []
        finally:
            # Save images
            if self.save_as is None:
                self.save_as = "frame"

            self.save_images(self.list_of_images, self.save_as, DEFAULT_SAVE_FOLDER)
            self.is_saving = False
            self.recording = False

    # Thread management
    def start_live(self):
        """Start the live feed in a separate thread."""
        # Stop existing thread if any
        if self.live_thread:
            self.stop_live()

        # Create and start new thread
        self.live_thread = LiveFeedThread(self)
        self.live_thread.stopper.clear_stop()
        self.live_thread.start()

        # Update state
        self.live_state_changed.emit(True)

    def stop_live(self):
        """Stop the live feed thread."""
        if self.live_thread:
            # Request stop
            self.live_thread.stopper.stop()

            # Wait for thread to complete
            self._join_thread(self.live_thread, "Live feed")
            self.live_thread = None

        # Update state
        self.live_feed = False
        self.live_state_changed.emit(False)

    def start_record(self):
        """Start recording in a separate thread."""
        # Stop existing thread if any
        if self.record_thread:
            self.stop_record()

        # Create and start new thread
        self.record_thread = RecordingThread(self)
        self.record_thread.stopper.clear_stop()
        self.record_thread.start()

        # Update state
        self.recording_state_changed.emit(True)

    def stop_record(self) -> None:
        """Stop the recording thread safely.

        Stops the recording thread and updates the recording state.
        """
        if self.record_thread:
            self.record_thread.stopper.stop()
            self._join_thread(self.record_thread, "Recording")
            self.record_thread = None

        self.recording = False
        self.recording_state_changed.emit(False)

    def _join_thread(self, thread: Any, thread_name: str) -> bool:
        """Join a thread with timeout.

        Args:
        ----
            thread: Thread to join
            thread_name: Name of the thread

        Returns:
        -------
            bool: True if thread joined successfully, False if timed out

        """
        if thread:
            success = thread.wait(2000)  # 2000ms = 2 seconds
            if not success:
                self.error_occurred.emit(
                    f"{thread_name} thread failed to stop properly"
                )
                return False
            else:
                return True
        return True

    def close(self) -> None:
        """Close the camera connection and release resources.

        Should be called when application is closing to ensure proper cleanup.
        """
        try:
            # Stop any active threads first
            if hasattr(self, "live_thread") and self.live_thread:
                self.stop_live()

            if hasattr(self, "record_thread") and self.record_thread:
                self.stop_record()

            # Close camera connection
            if hasattr(self, "camera_handle") and self.camera_handle:
                XsCamera.XsCloseCamera(self.camera_handle)
                self.camera_handle = None

        except Exception as e:
            self.error_occurred.emit(f"Error closing camera: {e!s}")
