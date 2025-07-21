"""Image processing utilities for droplet and experiment analysis in MesszelleApp."""

import glob
import os
from collections import Counter

import cv2
import numpy as np

from src.utilities.logging_manager import get_logger

# Setup logger for this module
logger = get_logger(__name__)


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
        bg_img = cv2.imread(image_path)
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
            img = cv2.imread(image_paths[idx])
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
