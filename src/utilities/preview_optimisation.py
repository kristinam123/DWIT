"""Preview performance optimization utilities for DWIT.

Provides caching, debouncing, and optimized image processing for rapid preview updates.
"""

import os
import threading
import time
from typing import Any

import cv2
import numpy as np
from PySide6.QtCore import QObject, QTimer, Signal

from src.utilities.core_utils import get_logger
from src.utilities.image_utils import (
    create_background_image,
    crop_image,
    rotate_image,
    safe_imread,
)

logger = get_logger(__name__)


class PreviewCache:
    """Thread-safe cache for preview images and processed data."""

    def __init__(self, max_size: int = 50):
        """Initialize the cache with maximum size."""
        self.max_size = max_size
        self._cache: dict[str, dict[str, Any]] = {}
        self._access_times: dict[str, float] = {}
        self._lock = threading.RLock()

    def _generate_key(self, folder_path: str, **params) -> str:
        """Generate cache key from parameters."""
        key_parts = [folder_path]
        for k, v in sorted(params.items()):
            key_parts.append(f"{k}:{v}")
        return "|".join(key_parts)

    def get(self, folder_path: str, **params) -> dict[str, Any] | None:
        """Get cached data if available."""
        key = self._generate_key(folder_path, **params)

        with self._lock:
            if key in self._cache:
                self._access_times[key] = time.time()
                logger.debug(f"Cache HIT for key: {key[:50]}...")
                return self._cache[key].copy()

            logger.debug(f"Cache MISS for key: {key[:50]}...")
            return None

    def put(self, folder_path: str, data: dict[str, Any], **params) -> None:
        """Store data in cache."""
        key = self._generate_key(folder_path, **params)

        with self._lock:
            # Evict oldest entries if cache is full
            if len(self._cache) >= self.max_size:
                self._evict_oldest()

            self._cache[key] = data.copy()
            self._access_times[key] = time.time()
            logger.debug(f"Cache PUT for key: {key[:50]}...")

    def _evict_oldest(self):
        """Remove the least recently used entry."""
        if not self._access_times:
            return

        oldest_key = min(self._access_times.keys(), key=lambda k: self._access_times[k])
        del self._cache[oldest_key]
        del self._access_times[oldest_key]
        logger.debug(f"Cache evicted: {oldest_key[:50]}...")

    def clear(self):
        """Clear all cached data."""
        with self._lock:
            self._cache.clear()
            self._access_times.clear()
            logger.debug("Preview cache cleared")

    def size(self) -> int:
        """Get current cache size."""
        with self._lock:
            return len(self._cache)


class OptimizedPreviewGenerator(QObject):
    """Optimized preview generator with caching and performance improvements."""

    # Signals for async processing
    preview_ready = Signal(object, str)  # image, preview_type

    def __init__(self):
        """Initialize the optimized preview generator."""
        super().__init__()
        self.cache = PreviewCache(max_size=20)
        self._debounce_timers: dict[str, QTimer] = {}
        self._folder_metadata: dict[str, dict[str, Any]] = {}

    def _get_folder_metadata(self, folder_path: str) -> dict[str, Any]:
        """Get or create metadata for a folder."""
        if folder_path not in self._folder_metadata:
            metadata = self._analyze_folder(folder_path)
            self._folder_metadata[folder_path] = metadata
        return self._folder_metadata[folder_path]

    def _analyze_folder(self, folder_path: str) -> dict[str, Any]:
        """Analyze folder to extract image information."""
        try:
            # Find all images
            extensions = ["*.jpg", "*.jpeg", "*.png", "*.bmp", "*.tiff"]
            image_files = []
            for ext in extensions:
                import glob

                image_files.extend(glob.glob(os.path.join(folder_path, ext)))

            if not image_files:
                return {"image_files": [], "middle_image": None, "image_count": 0}

            image_files.sort()
            middle_idx = len(image_files) // 2
            middle_image = image_files[middle_idx]

            # Get image dimensions from middle image
            temp_img = safe_imread(middle_image)
            original_shape = temp_img.shape if temp_img is not None else (480, 640, 3)

            return {
                "image_files": image_files,
                "middle_image": middle_image,
                "image_count": len(image_files),
                "original_shape": original_shape,
            }
        except Exception as e:
            logger.error(f"Error analyzing folder {folder_path}: {e}")
            return {"image_files": [], "middle_image": None, "image_count": 0}

    def _get_base_image(
        self, folder_path: str, rotation_angle: float = 0.0
    ) -> np.ndarray | None:
        """Get base image with rotation applied and cached."""
        cache_key = f"base_image_rot{rotation_angle}"
        cached = self.cache.get(folder_path, operation=cache_key)

        if cached and "base_image" in cached:
            return cached["base_image"]

        # Load and process base image
        metadata = self._get_folder_metadata(folder_path)
        if not metadata["middle_image"]:
            return None

        try:
            image = safe_imread(metadata["middle_image"])
            if image is None:
                return None

            # Apply rotation
            if abs(rotation_angle) > 0.001:
                image = rotate_image(image, rotation_angle)

            # Cache the result
            self.cache.put(folder_path, {"base_image": image}, operation=cache_key)
            return image

        except Exception as e:
            logger.error(f"Error loading base image: {e}")
            return None

    def _get_background_image(
        self,
        folder_path: str,
        rotation_angle: float = 0.0,
        crop_params: tuple[int, int, int, int] = (0, 640, 0, 480),
    ) -> np.ndarray | None:
        """Get background image with aggressive caching."""
        cache_key = f"background_rot{rotation_angle}_crop{crop_params}"
        cached = self.cache.get(folder_path, operation=cache_key)

        if cached and "background" in cached:
            return cached["background"]

        # Create background image
        metadata = self._get_folder_metadata(folder_path)
        if not metadata["image_files"]:
            return None

        try:
            # Use fewer images for faster background creation in preview mode
            background = create_background_image(
                metadata["image_files"],
                use_first_as_background=False,
                num_images=5,  # Reduced from default for speed
                rotate_angle=rotation_angle,
                crop_params=crop_params,
            )

            if background is not None:
                # Cache the result
                self.cache.put(
                    folder_path,
                    {"background": background},
                    operation=cache_key,
                )

            return background

        except Exception as e:
            logger.error(f"Error creating background image: {e}")
            return None

    def generate_roi_preview(
        self,
        folder_path: str,
        roi_params: tuple[int, int, int, int],
        rotation_angle: float = 0.0,
        analysis_mode: str = "contact_angle",
    ) -> np.ndarray | None:
        """Generate ROI preview with caching."""
        left, top, right, bottom = roi_params

        # Check cache first
        cache_key = f"roi_{left}_{top}_{right}_{bottom}_rot{rotation_angle}"
        cached = self.cache.get(folder_path, operation=cache_key)

        if cached and "roi_preview" in cached:
            return cached["roi_preview"]

        # Generate ROI preview
        try:
            # For structured_packing and free_sedimentation, user expects
            # 90° rotation by default
            if (
                analysis_mode in ["structured_packing", "free_sedimentation"]
                and rotation_angle == 0.0
            ):
                rotation_angle = 90.0  # Default to 90° for these modes

            base_image = self._get_base_image(folder_path, rotation_angle)
            if base_image is None:
                return None

            # Create ROI overlay
            roi_image = base_image.copy()
            cv2.rectangle(roi_image, (left, top), (right, bottom), (0, 0, 255), 2)

            # Cache the result
            self.cache.put(folder_path, {"roi_preview": roi_image}, operation=cache_key)
            return roi_image

        except Exception as e:
            logger.error(f"Error generating ROI preview: {e}")
            return None

    def generate_threshold_preview(
        self,
        folder_path: str,
        threshold: int,
        rotation_angle: float = 0.0,
        crop_params: tuple[int, int, int, int] = (0, 640, 0, 480),
        analysis_mode: str = "contact_angle",
    ) -> np.ndarray | None:
        """Generate threshold preview with caching."""
        cache_key = f"threshold_{threshold}_rot{rotation_angle}_crop{crop_params}"
        cached = self.cache.get(folder_path, operation=cache_key)

        if cached and "threshold_preview" in cached:
            return cached["threshold_preview"]

        # Generate threshold preview
        try:
            # For structured_packing and free_sedimentation, user expects
            # 90° rotation by default
            if (
                analysis_mode in ["structured_packing", "free_sedimentation"]
                and rotation_angle == 0.0
            ):
                rotation_angle = 90.0  # Default to 90° for these modes

            # Get processed image
            base_image = self._get_base_image(folder_path, rotation_angle)
            if base_image is None:
                return None

            # Apply cropping
            processed_image = crop_image(base_image, crop_params)
            if processed_image is None:
                return None

            # ALL modes use background subtraction in main analysis
            # Get background image for proper threshold processing
            background = self._get_background_image(
                folder_path, rotation_angle, crop_params
            )
            if background is None:
                # Fallback to simple background
                background = processed_image.copy()

            # Ensure shape compatibility
            if processed_image.shape != background.shape:
                background = cv2.resize(
                    background,
                    (processed_image.shape[1], processed_image.shape[0]),
                )

            # Apply threshold processing like main analysis does
            diff = cv2.absdiff(processed_image, background)
            gray = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)
            gray = cv2.GaussianBlur(gray, (5, 5), 0)
            _, thresh_image = cv2.threshold(gray, threshold, 255, cv2.THRESH_BINARY)

            # Cache the result
            self.cache.put(
                folder_path,
                {"threshold_preview": thresh_image},
                operation=cache_key,
            )
            return thresh_image

        except Exception as e:
            logger.error(f"Error generating threshold preview: {e}")
            return None

    def generate_baseline_preview(
        self,
        folder_path: str,
        baseline_offset: int,
        manual_baseline: int | None = None,
        rotation_angle: float = 0.0,
        crop_params: tuple[int, int, int, int] = (0, 640, 0, 480),
        analysis_mode: str = "contact_angle",
    ) -> np.ndarray | None:
        """Generate baseline preview with caching."""
        cache_key = (
            f"baseline_{baseline_offset}_{manual_baseline}"
            f"_rot{rotation_angle}_crop{crop_params}"
        )
        cached = self.cache.get(folder_path, operation=cache_key)

        if cached and "baseline_preview" in cached:
            return cached["baseline_preview"]

        # Generate baseline preview
        try:
            # Get processed image
            base_image = self._get_base_image(folder_path, rotation_angle)
            if base_image is None:
                return None

            # Apply cropping
            processed_image = crop_image(base_image, crop_params)
            if processed_image is None:
                return None

            baseline_image = processed_image.copy()
            img_h, img_w = baseline_image.shape[:2]

            # Calculate baseline position using the same logic as main analysis
            if manual_baseline is not None:
                baseline_y = img_h - manual_baseline
            else:
                # Use actual baseline detection like in main analysis with
                # proper cropping
                from src.utilities.measurement_utils import find_single_baseline

                # Crop to middle 40%-60% width like main analysis does
                _, w_img = processed_image.shape[:2]
                crop_left_baseline = int(w_img * 0.4)
                crop_right_baseline = int(w_img * 0.6)
                cropped_for_baseline = processed_image[
                    :, crop_left_baseline:crop_right_baseline
                ]

                y1_left, _y1_right = find_single_baseline(
                    cropped_for_baseline, baseline_offset, False, 0
                )
                if y1_left is not None:
                    baseline_y = y1_left
                else:
                    baseline_y = img_h - 100 + baseline_offset  # Fallback

            # Draw baseline
            if 0 <= baseline_y < img_h:
                cv2.line(
                    baseline_image,
                    (0, int(baseline_y)),
                    (img_w, int(baseline_y)),
                    (0, 0, 255),
                    2,
                )

            # Cache the result
            self.cache.put(
                folder_path,
                {"baseline_preview": baseline_image},
                operation=cache_key,
            )
            return baseline_image

        except Exception as e:
            logger.error(f"Error generating baseline preview: {e}")
            return None

    def debounced_preview_update(
        self, preview_type: str, preview_func, delay_ms: int = 50
    ):
        """Generate preview with debouncing to handle rapid updates."""
        # Cancel existing timer for this preview type
        if preview_type in self._debounce_timers:
            self._debounce_timers[preview_type].stop()

        # Create new timer
        timer = QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(
            lambda: self._execute_debounced_preview(preview_type, preview_func)
        )

        self._debounce_timers[preview_type] = timer
        timer.start(delay_ms)

    def _execute_debounced_preview(self, preview_type: str, preview_func):
        """Execute the actual preview generation after debounce delay."""
        try:
            start_time = time.perf_counter()
            result = preview_func()
            end_time = time.perf_counter()

            response_time = (end_time - start_time) * 1000
            logger.debug(f"{preview_type} preview generated in {response_time:.1f}ms")

            if result is not None:
                self.preview_ready.emit(result, preview_type)

        except Exception as e:
            logger.error(f"Error in debounced {preview_type} preview: {e}")
        finally:
            # Clean up timer
            if preview_type in self._debounce_timers:
                del self._debounce_timers[preview_type]


# Global optimized preview generator instance
_optimized_preview_generator = None


def get_optimized_preview_generator() -> OptimizedPreviewGenerator:
    """Get or create the global optimized preview generator."""
    global _optimized_preview_generator

    if _optimized_preview_generator is None:
        _optimized_preview_generator = OptimizedPreviewGenerator()

    return _optimized_preview_generator
