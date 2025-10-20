"""Image processing and ROI selection utilities.

For droplet and experiment analysis in Droplet Wall Interaction Tool (DWIT).
"""

import glob
import os
from collections import Counter

import cv2
import numpy as np
from PySide6.QtCore import QRect, Qt, Signal
from PySide6.QtGui import QColor, QCursor, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QDialog, QLabel, QVBoxLayout

from src.utilities.core_utils import get_logger

# Setup logger for this module
logger = get_logger(__name__)


def safe_imread(path: str, flags=cv2.IMREAD_COLOR):
    """Robust image loader that handles Unicode paths on Windows.

    Tries cv2.imread first. If that returns None (which can happen when
    the underlying OpenCV build has trouble with Unicode paths on Windows),
    falls back to reading the file bytes and decoding with cv2.imdecode.
    """
    try:
        img = cv2.imread(path, flags)
        if img is not None:
            return img
    except Exception:
        # Continue to fallback
        logger.debug("cv2.imread raised exception for path: %s", path)

    # Fallback: read raw bytes and decode
    try:
        with open(path, "rb") as f:
            data = f.read()
        arr = np.frombuffer(data, dtype=np.uint8)
        img = cv2.imdecode(arr, flags)
        return img
    except Exception as e:
        logger.debug("safe_imread fallback failed for %s: %s", path, e)

        # Add extra diagnostics to help debug Unicode/path issues on Windows
        try:
            exists = os.path.exists(path)
            isfile = os.path.isfile(path)
            logger.debug(
                "safe_imread diagnostics: exists=%s, isfile=%s", exists, isfile
            )
            parent = os.path.dirname(path) or "."
            if os.path.isdir(parent):
                try:
                    entries = os.listdir(parent)
                    # Log first 20 entries with repr to show encoding differences
                    entries_sample = [repr(e) for e in entries[:20]]
                    logger.debug(
                        "Directory listing for %s (first %d): %s",
                        parent,
                        min(20, len(entries)),
                        entries_sample,
                    )
                except Exception as le:
                    logger.debug("Failed to list parent directory %s: %s", parent, le)
        except Exception:
            # Best-effort diagnostics only
            pass

        return None


def create_background_image(
    image_paths,
    use_first_as_background=False,
    num_images=10,
    rotate_angle=0,
    crop_params=(None, None, None, None),
):
    """Create a robust background image using multiple methods.

    Args:
    ----
        image_paths: list of paths to all images
        use_first_as_background: Whether to use first image as background
        num_images: Number of images to use for background calculation
        rotate_angle: Rotation angle to apply to images
        crop_params: tuple of (x, w, y, h) crop parameters

    Returns:
    -------
        Background image

    """
    logger.debug(
        f"Params: num_images={num_images}, "
        f"rotate_angle={rotate_angle}, "
        f"crop_params={crop_params}, "
        f"use_first_as_background={use_first_as_background}"
    )

    try:
        # Validate input
        if not image_paths or len(image_paths) == 0:
            logger.error("No image paths provided for background creation")
            return None

    except Exception as e:
        logger.error(f"Error in background image creation setup: {e}")
        return None

    # Simple approach: use first image directly
    if use_first_as_background:
        return _create_simple_background(image_paths[0], rotate_angle, crop_params)

    # Advanced approach: use multiple images
    logger.debug("Using advanced approach with multiple images for background creation")

    # Select sample indices
    sample_indices = _select_sample_indices(len(image_paths), num_images)

    # Load and preprocess sample images
    try:
        sample_images = _load_and_preprocess_samples(
            image_paths, sample_indices, rotate_angle, crop_params
        )
    except Exception as e:
        logger.error(f"Exception during sample image loading: {e}")
        return None

    # Create background from samples
    try:
        return _create_background_from_samples(sample_images)
    except Exception as e:
        logger.error(f"Exception during background creation from samples: {e}")
        return None


def _create_simple_background(image_path, rotate_angle, crop_params):
    """Create background image using the first image in the sequence.

    Args:
    ----
        image_path: Path to the image
        rotate_angle: Rotation angle to apply
        crop_params: Crop parameters (x, w, y, h)

    Returns:
    -------
        Background image or None if creation fails

    """
    x_img, w_img, y_img, h_img = crop_params
    logger.debug("Using first image as background (simple approach)")

    try:
        bg_img = safe_imread(image_path)
        if bg_img is None:
            logger.error(f"Failed to load first image: {image_path}")
            return None

        # Apply rotation and cropping to match analysis
        bg_img = rotate_image(bg_img, rotate_angle)
        bg_img = crop_image(bg_img, (x_img, w_img, y_img, h_img))

        logger.info("Background image created successfully using first image")
        return bg_img

    except Exception as e:
        logger.error(f"Error creating background from first image: {e}")
        return None


def _select_sample_indices(total_images, num_images):
    """Select indices of images to use for background creation.

    Args:
    ----
        total_images: Total number of images available
        num_images: Number of images to select

    Returns:
    -------
        List of selected indices

    """
    # If we have few images, use all of them up to num_images
    if total_images <= num_images:
        sample_indices = list(range(total_images))
    else:
        # Take evenly spaced samples to cover the whole sequence
        step = max(1, total_images // num_images)
        sample_indices = list(range(0, total_images, step))[:num_images]

    return sample_indices


def _load_and_preprocess_samples(
    image_paths, sample_indices, rotate_angle, crop_params
):
    """Load and preprocess sample images for background creation.

    Args:
    ----
        image_paths: List of image paths
        sample_indices: Indices of images to load
        rotate_angle: Rotation angle to apply
        crop_params: Crop parameters (x, w, y, h)

    Returns:
    -------
        List of preprocessed images

    """
    x_img, w_img, y_img, h_img = crop_params
    sample_images = []

    for idx in sample_indices:
        try:
            img = safe_imread(image_paths[idx])
            if img is None:
                logger.warning(
                    f"Failed to load image at index {idx}: {image_paths[idx]}"
                )
                continue

            # Apply rotation and cropping
            img = rotate_image(img, rotate_angle)
            img = crop_image(img, (x_img, w_img, y_img, h_img))

            sample_images.append(img)

        except Exception as e:
            logger.error(f"Error processing image at index {idx}: {e}")

    return sample_images


def _create_background_from_samples(sample_images):
    """Create background image from preprocessed sample images.

    Args:
    ----
        sample_images: List of preprocessed images

    Returns:
    -------
        Background image or None if creation fails

    """
    if not sample_images:
        logger.error("No images available for background creation")
        return None

    # Step 1: Find common dimensions
    common_height, common_width = _find_common_dimensions(sample_images)
    if not common_height or not common_width:
        return None

    # Step 2: Resize images to uniform size
    uniform_images = _resize_images_to_uniform(
        sample_images, common_height, common_width
    )
    if not uniform_images:
        return None

    # Step 3: Stack and compute median
    return _stack_and_median_images(uniform_images)


def _find_common_dimensions(sample_images):
    """Find the most common height and width among sample images."""
    heights = [img.shape[0] for img in sample_images if img is not None]
    widths = [img.shape[1] for img in sample_images if img is not None]
    if not heights or not widths:
        logger.error("No valid images (with shape) for background creation")
        return None, None
    common_height = Counter(heights).most_common(1)[0][0]
    common_width = Counter(widths).most_common(1)[0][0]
    return common_height, common_width


def _resize_images_to_uniform(sample_images, common_height, common_width):
    """Resize all images to the common dimensions."""
    uniform_images = []
    resized_count = 0
    for img in sample_images:
        if img is None:
            logger.warning("Skipping None image in background creation")
            continue
        if img.shape[0] != common_height or img.shape[1] != common_width:
            try:
                img = cv2.resize(img, (common_width, common_height))
                resized_count += 1
            except Exception as e:
                logger.error(f"Error resizing image: {e}")
                continue
        uniform_images.append(img)
    if not uniform_images:
        logger.error("No valid uniform images for stacking in background creation")
    if resized_count > 0:
        logger.info(f"Resized {resized_count} images to common dimensions")
    return uniform_images


def _stack_and_median_images(uniform_images):
    """Stack images and compute the median background image."""
    try:
        image_stack = np.stack(uniform_images, axis=0)
    except Exception as e:
        logger.error(f"Error creating image stack: {e}")
        return None
    try:
        background = np.median(image_stack, axis=0).astype(np.uint8)
        logger.info(
            f"Background image created successfully with shape: {background.shape}"
        )
        return background
    except Exception as e:
        logger.error(f"Error creating background image: {e}")
        return None


def rotate_image(image, angle):
    """Rotate an image starting from +90 degrees baseline.

    Args:
    ----
        image: Input image
        angle: User-selected rotation angle in degrees (0-360)

    Returns:
    -------
        Rotated image with expanded canvas to avoid clipping corners

    """
    # Defensive: check for None input
    if image is None:
        logger.error("rotate_image called with None image")
        return None

    # dont rotate if angle is 0
    effective_angle = 90 if angle == 0 else 180 - angle

    height, width = image.shape[:2]
    image_center = (width / 2, height / 2)

    try:
        rotation_mat = cv2.getRotationMatrix2D(image_center, effective_angle, 1.0)

        # Calculate new bounds using absolute values of cos/sin
        abs_cos = abs(rotation_mat[0, 0])
        abs_sin = abs(rotation_mat[0, 1])

        # Find the new width and height bounds
        bound_w = int(height * abs_sin + width * abs_cos)
        bound_h = int(height * abs_cos + width * abs_sin)

        # Adjust rotation matrix for new bounds
        rotation_mat[0, 2] += bound_w / 2 - image_center[0]
        rotation_mat[1, 2] += bound_h / 2 - image_center[1]

        # Rotate image with new bounds
        rotated_mat = cv2.warpAffine(image, rotation_mat, (bound_w, bound_h))

        return rotated_mat

    except Exception as e:
        logger.error(f"Error during image rotation: {e}")
        return image


def crop_image(image, crop_params):
    """Crop the image using the dimensions specified by the user.

    Dimensions as displayed on screen.

    Args:
    ----
        image: Input image to crop (already rotated)
        crop_params: tuple of (x, w, y, h) crop parameters

    Returns:
    -------
        Cropped image, respecting image boundaries

    """
    x_img, w_img, y_img, h_img = crop_params
    if image is None:
        logger.warning("Cannot crop: input image is None")
        return None

    # Get dimensions of the rotated image
    img_h, img_w = image.shape[:2]

    # Apply crop parameters directly as user sees them
    # Left, Right, Top, Bottom as displayed in the UI
    x_start = max(0, min(x_img, img_w - 1))  # Left
    x_end = min(img_w, max(x_start + 1, w_img))  # Right
    y_start = max(0, min(y_img, img_h - 1))  # Top
    y_end = min(img_h, max(y_start + 1, h_img))  # Bottom

    # Check if crop coordinates are valid
    if x_start >= x_end or y_start >= y_end:
        logger.warning("Invalid crop coordinates, returning original image")
        return image

    try:
        # Apply crop
        cropped = image[y_start:y_end, x_start:x_end]
        return cropped
    except Exception as e:
        logger.error(f"Error during image cropping: {e}")
        return image


def convert_videos_to_images(
    folder_path: str, progress_callback=None, use_simple_method=False
):
    """Convert video files in the given folder to image sequences.

    Args:
    ----
        folder_path: Path to folder containing video files
        progress_callback: Optional function to report progress
        use_simple_method: If True, uses a simpler direct conversion method

    Returns:
    -------
        list of paths to the extracted image files

    """
    logger.debug(f"Params: use_simple_method={use_simple_method}")

    # Check if folder exists
    if not os.path.exists(folder_path):
        logger.error(f"Folder does not exist: {folder_path}")
        return []

    # Find all video files in the folder
    video_extensions = ["*.avi", "*.mp4", "*.mov", "*.mkv"]
    video_files = []
    for ext in video_extensions:
        video_files.extend(glob.glob(os.path.join(folder_path, ext)))

    if not video_files:
        logger.debug(f"No video files found in folder: {folder_path}")
        return []

    logger.info(f"Found {len(video_files)} video files to convert")

    # Simple direct method as preferred by user
    if use_simple_method:
        logger.info("Using simple conversion method")
        return _convert_videos_simple_method(video_files, progress_callback)

    # More sophisticated method with additional features (original implementation)
    logger.info("Using advanced conversion method")
    return _convert_videos_advanced_method(video_files, folder_path, progress_callback)


def _convert_videos_simple_method(video_files, progress_callback=None):
    """Convert videos to images using the simple direct method preferred by the user.

    Args:
    ----
        video_files: list of video file paths
        progress_callback: Optional function to report progress

    Returns:
    -------
        list of paths to the extracted image files

    """
    logger.info("Starting simple video to image conversion")
    extracted_images = []
    total_videos = len(video_files)

    for video_idx, video_path in enumerate(video_files):
        video_name = os.path.splitext(os.path.basename(video_path))[0]

        # Create output directory in same folder as video
        output_dir = os.path.join(os.path.dirname(video_path), f"{video_name}_frames")
        os.makedirs(output_dir, exist_ok=True)

        try:
            vidcap = cv2.VideoCapture(video_path)
            if not vidcap.isOpened():
                logger.error(f"Failed to open video file: {video_path}")
                continue

            success, image = vidcap.read()
            count = 0

            while success:
                frame_path = os.path.join(output_dir, f"frame{count}.jpg")
                success_write = cv2.imwrite(frame_path, image)

                if success_write:
                    extracted_images.append(frame_path)
                else:
                    logger.warning(f"Failed to write frame {count} to {frame_path}")

                success, image = vidcap.read()
                count += 1

                # Update progress every 10 frames
                if progress_callback and count % 10 == 0:
                    progress_percent = ((video_idx + 0.5) / total_videos) * 100
                    progress_callback(min(progress_percent, 99))

            vidcap.release()
            logger.info(f"Successfully extracted {count} frames from {video_name}")

        except Exception as e:
            logger.error(f"Failed to convert video {video_path}: {e}")

    logger.info(
        f"Video conversion completed. Total extracted images: {len(extracted_images)}"
    )
    return extracted_images


def _convert_videos_advanced_method(video_files, folder_path, progress_callback=None):
    """Convert videos to images with more features.

    This is the original implementation that serves as a fallback.

    Args:
    ----
        video_files: list of video file paths
        folder_path: Path to folder containing video files
        progress_callback: Optional function to report progress

    Returns:
    -------
        list of paths to the extracted image files

    """
    logger.info("Starting advanced video to image conversion")
    extracted_images = []
    total_videos = len(video_files)

    for video_idx, video_path in enumerate(video_files):
        video_name = os.path.splitext(os.path.basename(video_path))[0]

        frames_dir = os.path.join(folder_path, f"{video_name}_frames")
        os.makedirs(frames_dir, exist_ok=True)

        try:
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                logger.error(f"Failed to open video file: {video_path}")
                continue

            frame_count = 0
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            fps = cap.get(cv2.CAP_PROP_FPS)

            # Determine frame interval - extract 5 frames per second
            target_fps = 5
            frame_interval = max(1, int(fps / target_fps))

            extracted_from_video = 0

            while True:
                ret, frame = cap.read()
                if not ret:
                    break

                # Extract only every nth frame based on the interval
                if frame_count % frame_interval == 0:
                    frame_path = os.path.join(
                        frames_dir, f"{video_name}_frame_{frame_count:06d}.jpg"
                    )
                    success_write = cv2.imwrite(
                        frame_path, frame, [int(cv2.IMWRITE_JPEG_QUALITY), 95]
                    )

                    if success_write:
                        extracted_images.append(frame_path)
                        extracted_from_video += 1
                    else:
                        logger.warning(
                            f"Failed to write frame {frame_count} to {frame_path}"
                        )

                frame_count += 1

                # Update progress
                if progress_callback and total_frames > 0:
                    progress_percent = (
                        (video_idx + frame_count / total_frames) / total_videos
                    ) * 100
                    progress_callback(min(progress_percent, 99))  # Cap at 99%

            cap.release()
            logger.info(
                f"Successfully extracted {extracted_from_video} frames "
                f"from {video_name} (processed {frame_count} total frames)"
            )

        except Exception as e:
            logger.error(f"Failed to convert video {video_path}: {e}")
            if "cap" in locals():
                cap.release()

    logger.info(
        f"Advanced video conversion completed. "
        f"Total extracted images: {len(extracted_images)}"
    )
    return extracted_images


class ROISelector(QDialog):
    """Dialog for selecting a region of interest on an image."""

    # Signal to emit when selection is confirmed with the coordinates
    roi_selected = Signal(int, int, int, int)  # Left, Top, Right, Bottom

    def __init__(self, parent=None, image_path=None, rotation_angle=0.0):
        """Initialize the ROISelector dialog."""
        super().__init__(parent)

        # Set up window properties like PreviewDialog
        self.setWindowTitle("Select Region of Interest")
        self.setWindowFlags(
            Qt.Tool  # Makes it a tool window (minimal decoration)
            | Qt.FramelessWindowHint  # Remove window frame
            | Qt.WindowStaysOnTopHint  # Keep on top
        )

        # Make the dialog opaque and fully interactive (not click-through)
        self.setWindowOpacity(1.0)

        # Store parameters
        self.image_path = image_path
        self.rotation_angle = rotation_angle
        self.original_image = None
        self.rotated_image = None

        # Initialize selection rectangle
        self.current_selection = None

        # Setup minimal UI like PreviewDialog
        self.setup_ui()

        # Load and process image
        if image_path:
            logger.info(f"Loading and rotating image for ROI selection: {image_path}")
            self.load_and_rotate_image()
        else:
            logger.warning(
                "No image path provided, ROISelector initialized without image"
            )

    def _install_label_mouse_events(self):
        """Install mouse event handlers for drag-and-drop ROI selection."""
        self._drag_start = None
        self._drag_current = None
        # Assign handlers via setattr to avoid static analyzers
        setattr(self.image_label, "mousePressEvent", self._label_mouse_press_event)
        setattr(self.image_label, "mouseMoveEvent", self._label_mouse_move_event)
        setattr(self.image_label, "mouseReleaseEvent", self._label_mouse_release_event)
        press = self.image_label.mousePressEvent
        move = self.image_label.mouseMoveEvent
        release = self.image_label.mouseReleaseEvent
        del press, move, release

    def _label_mouse_press_event(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_start = event.pos()
            self._drag_current = event.pos()
            self._dragging = True
        event.accept()

    def _label_mouse_move_event(self, event):
        if hasattr(self, "_dragging") and self._dragging and self._drag_start:
            self._drag_current = event.pos()
            # Update current_selection as QRect
            x1, y1 = self._drag_start.x(), self._drag_start.y()
            x2, y2 = self._drag_current.x(), self._drag_current.y()
            left, right = sorted([x1, x2])
            top, bottom = sorted([y1, y2])
            self.current_selection = QRect(left, top, right - left, bottom - top)
            self.update_display()
        event.accept()

    def _label_mouse_release_event(self, event):
        if hasattr(self, "_dragging") and self._dragging and self._drag_start:
            self._drag_current = event.pos()
            x1, y1 = self._drag_start.x(), self._drag_start.y()
            x2, y2 = self._drag_current.x(), self._drag_current.y()
            left, right = sorted([x1, x2])
            top, bottom = sorted([y1, y2])
            self.current_selection = QRect(left, top, right - left, bottom - top)
            self.update_display()
            self._dragging = False
        event.accept()

    def eventFilter(self, obj, event):  # noqa: N802
        """Intercept mouse events on the image label to handle button clicks."""
        from PySide6.QtCore import QEvent

        if obj == self.image_label and event.type() == QEvent.MouseButtonRelease:
            pos = event.pos()
            label_size = self.image_label.size()
            button_y = label_size.height() - 50
            button_spacing = 20
            total_button_width = 100 + 140 + button_spacing
            start_x = (label_size.width() - total_button_width) // 2
            cancel_rect = QRect(start_x, button_y, 100, 30)
            confirm_rect = QRect(start_x + 100 + button_spacing, button_y, 140, 30)
            if cancel_rect.contains(pos):
                self.reject()  # Close dialog as cancel
                return True
            if confirm_rect.contains(pos):
                # If no ROI selected, emit full image or default
                if self.current_selection:
                    # Convert display coordinates back to image coordinates
                    left, top, width, height = self.current_selection.getRect()
                    # Reverse the scaling and centering math
                    display_width = self.image_label.width() - 4
                    display_height = self.image_label.height() - 4
                    img_h, img_w = self.rotated_image.shape[:2]
                    scale_x = display_width / img_w
                    scale_y = display_height / img_h
                    scale = min(scale_x, scale_y)
                    scaled_width = int(img_w * scale)
                    scaled_height = int(img_h * scale)
                    center_x = (display_width - scaled_width) // 2 + 2
                    center_y = (display_height - scaled_height) // 2 + 2
                    img_left = int((left - center_x) / scale)
                    img_top = int((top - center_y) / scale)
                    img_right = int((left + width - center_x) / scale)
                    img_bottom = int((top + height - center_y) / scale)
                else:
                    # No selection, use full image
                    img_left, img_top = 0, 0
                    img_right = self.rotated_image.shape[1]
                    img_bottom = self.rotated_image.shape[0]
                self.roi_selected.emit(img_left, img_top, img_right, img_bottom)
                self.accept()
                return True
            # If not clicking a button, do not consume the event
            return False
        return super().eventFilter(obj, event)

    def set_roi(self, left, top, right, bottom):
        """Set the ROI selection rectangle in image coordinates and update display."""
        if self.rotated_image is None:
            logger.warning("Cannot set ROI: no rotated image available")
            return

        try:
            # Get image dimensions
            height, width = self.rotated_image.shape[:2]

            # Calculate scale factor used for display
            display_width = self.image_label.width() - 4  # Account for 2px border
            display_height = self.image_label.height() - 4

            # Calculate scaling to fit image in label while maintaining aspect ratio
            scale_x = display_width / width
            scale_y = display_height / height
            scale = min(scale_x, scale_y)

            # Calculate actual display size
            scaled_width = int(width * scale)
            scaled_height = int(height * scale)

            # Calculate centering offsets
            center_x = (display_width - scaled_width) // 2 + 2  # +2 for border
            center_y = (display_height - scaled_height) // 2 + 2

            # Convert from image coordinates to display coordinates
            display_left = int(left * scale) + center_x
            display_top = int(top * scale) + center_y
            display_right = int(right * scale) + center_x
            display_bottom = int(bottom * scale) + center_y

            # Create selection rectangle in display coordinates
            self.current_selection = QRect(
                display_left,
                display_top,
                display_right - display_left,
                display_bottom - display_top,
            )

            logger.info(
                f"ROI set successfully in display coordinates: "
                f"x={display_left}, y={display_top}, "
                f"w={display_right - display_left}, h={display_bottom - display_top}"
            )
            self.update_display()

        except Exception as e:
            logger.error(f"Error setting ROI: {e}")
            self.current_selection = None

    def setup_ui(self):
        """Set up the minimal user interface like PreviewDialog."""
        # Create layout with minimal margins (2-pixel frame)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)  # 2-pixel frame
        layout.setSpacing(0)

        # Image display label with 2-pixel border
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setStyleSheet(
            """
            QLabel {
                border: 2px solid #666666;
                background-color: transparent;
            }
        """
        )
        self.image_label.setScaledContents(False)  # We'll handle scaling manually
        self.image_label.setMouseTracking(True)
        self.image_label.setCursor(QCursor(Qt.CrossCursor))
        self.image_label.installEventFilter(self)

        self._install_label_mouse_events()

        layout.addWidget(self.image_label)

        # Set initial size - will be updated when image loads
        self.setFixedSize(100, 100)

    def load_and_rotate_image(self):
        """Load the image, apply rotation, and auto-size the dialog."""
        try:
            # Load the original image
            self.original_image = safe_imread(self.image_path)
            if self.original_image is None:
                logger.error(f"Failed to load image from path: {self.image_path}")
                return

            # Apply rotation using the same logic as PreviewDialog
            self.rotated_image = rotate_image(self.original_image, self.rotation_angle)

            # Get rotated image dimensions
            rot_height, rot_width = self.rotated_image.shape[:2]
            logger.info(
                f"Image rotated by {self.rotation_angle}°: {rot_width}x{rot_height}"
            )

            # Auto-size the dialog to fit the image
            self.auto_size_dialog()

            # Update the display
            self.update_display()

        except Exception as e:
            logger.error(f"Error loading and rotating image: {e}")

    def auto_size_dialog(self):
        """Auto-size dialog with responsive layout based on monitor dimensions.

        Scales image to 90% of the monitor's corresponding side.
        """
        if self.rotated_image is None:
            return
        try:
            height, width = self.rotated_image.shape[:2]

            # Get screen geometry
            if hasattr(self, "parent") and self.parent():
                screen = (
                    self.parent().screen() if hasattr(self.parent(), "screen") else None
                )
            else:
                screen = QApplication.primaryScreen()

            if screen:
                screen_geometry = screen.availableGeometry()
                screen_width = screen_geometry.width()
                screen_height = screen_geometry.height()
            else:
                screen_width, screen_height = 1920, 1080  # Fallback

            # Calculate scale so that the image side most likely to touch
            # the monitor covers 90% of the corresponding monitor side
            scale_w = screen_width * 0.9 / width
            scale_h = screen_height * 0.9 / height
            scale_factor = min(scale_w, scale_h)

            # Calculate display dimensions maintaining aspect ratio
            display_width = int(width * scale_factor)
            display_height = int(height * scale_factor)

            # Add padding for the 2-pixel border and margins
            # (2px border + 2px margin each side = 8px total)
            dialog_width = display_width + 8
            dialog_height = display_height + 8

            # Set the dialog size
            self.setFixedSize(dialog_width, dialog_height)

            # Set the label size to match the image
            self.image_label.setFixedSize(display_width, display_height)

            # Position the dialog for perfect centering
            self.position_dialog_centered()
        except Exception as e:
            logger.error(f"Error auto-sizing dialog: {e}")

    def position_dialog_centered(self):
        """Center the dialog on the screen both horizontally and vertically."""
        try:
            # Get the screen that contains the parent window
            if self.parent():
                if hasattr(self.parent(), "screen"):
                    screen = self.parent().screen()
                else:
                    # Find which screen contains the parent window
                    parent_geometry = self.parent().geometry()
                    parent_center = parent_geometry.center()

                    screen = None
                    for available_screen in QApplication.screens():
                        if available_screen.geometry().contains(parent_center):
                            screen = available_screen
                            break

                    # Fallback to primary screen if not found
                    if screen is None:
                        screen = QApplication.primaryScreen()
            else:
                screen = QApplication.primaryScreen()

            if screen:
                screen_geometry = screen.availableGeometry()

                # Calculate perfect center position
                x = screen_geometry.center().x() - self.width() // 2
                y = screen_geometry.center().y() - self.height() // 2

                # Ensure dialog stays within screen bounds
                # (should not be needed with our sizing logic)
                x = max(
                    screen_geometry.left(),
                    min(x, screen_geometry.right() - self.width()),
                )
                y = max(
                    screen_geometry.top(),
                    min(y, screen_geometry.bottom() - self.height()),
                )

                self.move(x, y)

        except Exception as e:
            logger.error(f"Error positioning dialog: {e}")

    def mouse_press_event(self, event):
        """Handle mouse press events on the dialog itself."""
        # Allow interactions with the preview dialog itself
        # This overrides the click-through behavior for the dialog area
        super().mouse_press_event(event)

    def close_event(self, event):
        """Handle dialog close event."""
        # Stop the timer when closing
        self.auto_close_timer.stop()
        super().close_event(event)

    def __del__(self):
        """Destructor to ensure cleanup."""
        try:
            if hasattr(self, "auto_close_timer") and self.auto_close_timer:
                self.auto_close_timer.stop()
        except Exception as e:
            logger.error(f"Error in ROISelector destructor: {e}")
            pass  # Ignore cleanup errors

    def update_display(self):
        """Update the image display with ROI overlay and buttons."""
        if self.rotated_image is None:
            return

        try:
            # Convert OpenCV image to Qt format
            height, width = self.rotated_image.shape[:2]
            rotated_rgb = cv2.cvtColor(self.rotated_image, cv2.COLOR_BGR2RGB)
            bytes_per_line = 3 * width
            q_image = QImage(
                rotated_rgb.data, width, height, bytes_per_line, QImage.Format_RGB888
            )

            # Scale image to fit in the label while maintaining aspect ratio
            label_size = self.image_label.size()
            scaled_pixmap = QPixmap.fromImage(
                q_image.scaled(
                    label_size.width() - 4,  # Account for 2px border on each side
                    label_size.height() - 4,
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation,
                )
            )

            # Create a pixmap for the label with centered image
            label_pixmap = QPixmap(label_size)
            label_pixmap.fill(QColor(0, 0, 0, 0))  # Transparent background

            painter = QPainter(label_pixmap)

            # Calculate position to center the image
            x = (label_size.width() - scaled_pixmap.width()) // 2
            y = (label_size.height() - scaled_pixmap.height()) // 2

            # Draw the scaled image
            painter.drawPixmap(x, y, scaled_pixmap)

            # Draw the selection rectangle if it exists
            if self.current_selection and not self.current_selection.isEmpty():
                painter.setPen(QPen(QColor(0, 120, 215), 2, Qt.SolidLine))
                painter.setBrush(QColor(0, 120, 215, 40))  # Semi-transparent blue
                painter.drawRect(self.current_selection)

            # Draw overlay buttons at the bottom
            button_y = label_size.height() - 50
            button_spacing = 20
            total_button_width = (
                100 + 140 + button_spacing
            )  # Cancel + Confirm + spacing
            start_x = (label_size.width() - total_button_width) // 2

            # Draw Cancel button
            cancel_rect = QRect(start_x, button_y, 100, 30)
            painter.fillRect(cancel_rect, QColor(68, 68, 68))
            painter.setPen(QPen(QColor(102, 102, 102), 1))
            painter.drawRect(cancel_rect)
            painter.setPen(QColor(255, 255, 255))
            painter.drawText(cancel_rect, Qt.AlignCenter, "Cancel")

            # Draw Confirm button
            confirm_rect = QRect(start_x + 100 + button_spacing, button_y, 140, 30)
            painter.fillRect(confirm_rect, QColor(0, 120, 212))
            painter.setPen(QPen(QColor(0, 90, 158), 1))
            painter.drawRect(confirm_rect)
            painter.setPen(QColor(255, 255, 255))
            painter.drawText(confirm_rect, Qt.AlignCenter, "Confirm Selection")

            painter.end()
            self.image_label.setPixmap(label_pixmap)

        except Exception as e:
            logger.error(f"Error updating display: {e}")
