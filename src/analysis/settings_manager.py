"""Settings manager for the core module."""

import os
from pathlib import Path
from typing import Any

from PySide6.QtCore import QSettings

from src.utilities.core_utils import get_logger

logger = get_logger(__name__)


class SettingsManager:
    """Manages settings persistence and loading for analysis configurations."""

    def __init__(self, analysis_mode: str = "free_sedimentation"):
        """Initialize the SettingsManager.

        Args:
        ----
            analysis_mode: The analysis mode for which to manage settings

        """
        self.analysis_mode = analysis_mode
        self.settings = QSettings("CellSettings", "DWIT")

    def save_setting(self, key: str, value: Any) -> None:
        """Save a specific setting for the current analysis_mode.

        Args:
        ----
            key: The setting key
            value: The value to save

        """
        try:
            self.settings.beginGroup(f"Analysismode_{self.analysis_mode}")
            self.settings.setValue(key, value)
            self.settings.endGroup()
            self.settings.sync()
        except Exception as e:
            logger.error(f"Failed to save setting {key}: {e}")

    def load_settings(self) -> dict:
        """Load settings from persistent storage for the current analysis mode.

        Returns
        -------
            dict: Dictionary containing all loaded settings

        """
        logger.info(f"Loading settings for analysis mode: {self.analysis_mode}")

        try:
            # Handle legacy-to-new-settings migration
            try:
                self._migrate_legacy_settings()
            except Exception:
                logger.debug("Legacy settings migration failed or not present")

            # Load settings under the analysis-mode group
            self.settings.beginGroup(f"Analysismode_{self.analysis_mode}")
            common_settings = self._load_common_settings()
            mode_settings = self._load_mode_specific_settings()
            self.settings.endGroup()

            # Combine settings
            settings_dict = {**common_settings, **mode_settings}

            # Log final state
            try:
                logger.debug(
                    "Final folderPaths after load: %r",
                    settings_dict.get("folder_paths"),
                )
                logger.debug(
                    "Final mainFolderPath after load: %r",
                    settings_dict.get("main_folder_path"),
                )
            except Exception:
                pass

            return settings_dict

        except Exception as e:
            logger.error(f"Failed to load settings for {self.analysis_mode}: {e}")
            raise

    def _migrate_legacy_settings(self) -> None:
        """Migrate legacy settings stored under the old QSettings pattern."""
        legacy = QSettings("CellSettings", f"Analysismode_{self.analysis_mode}")
        legacy_folder_paths = legacy.value("folderPaths", None)

        # Normalize legacy paths if present
        if legacy_folder_paths is not None:
            try:
                legacy_folder_paths = [
                    str(Path(p).resolve())
                    for p in self._normalize_folder_paths(legacy_folder_paths)
                ]
            except Exception:
                pass

        # Check if migration is needed
        self.settings.beginGroup(f"Analysismode_{self.analysis_mode}")
        existing_folder_paths = self.settings.value("folderPaths", None)
        if existing_folder_paths is not None:
            try:
                existing_folder_paths = [
                    str(Path(p).resolve())
                    for p in self._normalize_folder_paths(existing_folder_paths)
                ]
            except Exception:
                pass
        self.settings.endGroup()

        if legacy_folder_paths is None:
            return

        logger.debug("Found legacy folderPaths: %r", legacy_folder_paths)
        logger.debug("Existing folderPaths in new storage: %r", existing_folder_paths)

        if existing_folder_paths is None or existing_folder_paths == []:
            logger.info("Migrating legacy settings from old storage location")

        # Copy keys into the new storage
        self.settings.beginGroup(f"Analysismode_{self.analysis_mode}")
        self.settings.setValue("folderPaths", legacy_folder_paths)
        for k in ("folderPath", "mainFolderPath"):
            v = legacy.value(k, None)
            if v is not None:
                self.settings.setValue(k, v)
        self.settings.endGroup()
        self.settings.sync()

        # Attempt to remove legacy keys
        self._remove_legacy_keys_if_needed(legacy)

    def _remove_legacy_keys_if_needed(self, legacy: QSettings) -> None:
        """Remove legacy keys from the legacy QSettings instance."""
        try:
            legacy.remove("folderPaths")
            legacy.remove("folderPath")
            legacy.remove("mainFolderPath")
            legacy.sync()
            logger.debug("Legacy settings removed after migration")
        except Exception:
            logger.debug("Could not remove legacy settings after migration")

    def _load_common_settings(self) -> dict:
        """Load settings that apply regardless of analysis mode.

        Returns
        -------
            dict: Common settings

        """
        return {
            "pixel": self.settings.value("pixel_per_mm", 55.00, type=float),
            "fps": self.settings.value("fps", 100, type=int),
            "manual_baseline": self.settings.value("manual_baseline", 0, type=int),
            "rotate_angle": self.settings.value("rotateAngle", 0.0, type=float),
            "baseline": self.settings.value("baseline", 0, type=int),
            "fitting_mode": self.settings.value("fitting_mode", "Arc", type=str),
            "polynom": self.settings.value("polynom", 3, type=int),
        }

    def _load_mode_specific_settings(self) -> dict:
        """Load settings that depend on the selected analysis mode.

        Returns
        -------
            dict: Mode-specific settings

        """
        if self.analysis_mode == "free_sedimentation":
            return self._load_free_sedimentation_settings()
        elif self.analysis_mode == "channel":
            return self._load_channel_settings()
        elif self.analysis_mode == "structured_packing":
            return self._load_structured_packing_settings()
        else:
            return self._load_contact_wall_settings()

    def _load_free_sedimentation_settings(self) -> dict:
        """Load free sedimentation mode settings."""
        default = os.path.abspath(
            self.settings.value("folderPath", "tests/free_sedimentation (BuAc_d_large)")
        )
        default_list = [
            os.path.abspath(p)
            for p in self.settings.value(
                "folderPaths",
                ["tests/free_sedimentation (BuAc_d_large)"],
                type=list,
            )
        ]
        return {
            "y_img": self.settings.value("yImg", 300, type=int),
            "h_img": self.settings.value("hImg", 800, type=int),
            "x_img": self.settings.value("xImg", 0, type=int),
            "w_img": self.settings.value("wImg", 2900, type=int),
            "folder_path": self.settings.value("folderPath", default),
            "folder_paths": self.settings.value("folderPaths", default_list, type=list),
            "main_folder_path": self.settings.value(
                "mainFolderPath", default, type=str
            ),
            "baseline_tf": self.settings.value("baselineTF", True, type=bool),
            "threshold": self.settings.value("threshold", 5, type=int),
            "rotate_angle": self.settings.value("rotateAngle", 0.0, type=float),
        }

    def _load_channel_settings(self) -> dict:
        """Load channel mode settings."""
        default = os.path.abspath(
            self.settings.value("folderPath", "tests/channel (BuAc_d_large)")
        )
        default_list = [
            os.path.abspath(p)
            for p in self.settings.value(
                "folderPaths", ["tests/channel (BuAc_d_large)"], type=list
            )
        ]
        return {
            "y_img": self.settings.value("yImg", 900, type=int),
            "h_img": self.settings.value("hImg", 1200, type=int),
            "x_img": self.settings.value("xImg", 0, type=int),
            "w_img": self.settings.value("wImg", 2500, type=int),
            "folder_path": self.settings.value("folderPath", default),
            "folder_paths": self.settings.value("folderPaths", default_list, type=list),
            "main_folder_path": self.settings.value(
                "mainFolderPath", default, type=str
            ),
            "baseline_tf": self.settings.value("baselineTF", False, type=bool),
            "threshold": self.settings.value("threshold", 20, type=int),
            "rotate_angle": self.settings.value("rotateAngle", 46.70, type=float),
        }

    def _load_structured_packing_settings(self) -> dict:
        """Load structured packing mode settings."""
        default = os.path.abspath(
            self.settings.value("folderPath", "tests/structured_packing (BuAc_d_large)")
        )
        default_list = [
            os.path.abspath(p)
            for p in self.settings.value(
                "folderPaths",
                ["tests/structured_packing (BuAc_d_large)"],
                type=list,
            )
        ]
        return {
            "y_img": self.settings.value("yImg", 900, type=int),
            "h_img": self.settings.value("hImg", 1300, type=int),
            "x_img": self.settings.value("xImg", 0, type=int),
            "w_img": self.settings.value("wImg", 2900, type=int),
            "folder_path": self.settings.value("folderPath", default),
            "folder_paths": self.settings.value("folderPaths", default_list, type=list),
            "main_folder_path": self.settings.value(
                "mainFolderPath", default, type=str
            ),
            "baseline_tf": self.settings.value("baselineTF", True, type=bool),
            "threshold": self.settings.value("threshold", 5, type=int),
            "rotate_angle": self.settings.value("rotateAngle", 0.0, type=float),
        }

    def _load_contact_wall_settings(self) -> dict:
        """Load contact wall mode settings."""
        default = os.path.abspath(
            self.settings.value("folderPath", "tests/contact_wall (BuAc_d_large)")
        )
        default_list = [
            os.path.abspath(p)
            for p in self.settings.value(
                "folderPaths", ["tests/contact_wall (BuAc_d_large)"], type=list
            )
        ]
        return {
            "y_img": self.settings.value("yImg", 1300, type=int),
            "h_img": self.settings.value("hImg", 1700, type=int),
            "x_img": self.settings.value("xImg", 300, type=int),
            "w_img": self.settings.value("wImg", 2500, type=int),
            "folder_path": self.settings.value("folderPath", default),
            "folder_paths": self.settings.value("folderPaths", default_list, type=list),
            "main_folder_path": self.settings.value(
                "mainFolderPath", default, type=str
            ),
            "baseline_tf": self.settings.value("baselineTF", False, type=bool),
            "threshold": self.settings.value("threshold", 20, type=int),
            "rotate_angle": self.settings.value("rotateAngle", 42.60, type=float),
        }

    def _normalize_folder_paths(self, paths) -> list:
        """Return a list of folder paths normalized from stored value.

        Args:
        ----
            paths: Paths to normalize (can be string or list)

        Returns:
        -------
            list: Normalized paths

        """
        result = []
        try:
            if isinstance(paths, str):
                paths = [paths]
            if paths is None:
                return []
            for p in paths:
                if not p:
                    continue
                try:
                    resolved = Path(p).resolve()
                    result.append(str(resolved))
                except Exception as e:
                    logger.debug(f"Could not normalize path {p}: {e}")
                    result.append(p)
        except Exception as e:
            logger.error(f"Error normalizing folder paths: {e}")
        return result

    def reset_to_defaults(self) -> dict:
        """Reset all settings to default values and return them.

        Returns
        -------
            dict: Default settings for the current analysis mode

        """
        logger.info(f"Resetting settings to defaults for {self.analysis_mode}")

        try:
            # Clear all settings for this mode
            self.settings.beginGroup(f"Analysismode_{self.analysis_mode}")
            self.settings.remove("")  # Remove all keys in this group
            self.settings.endGroup()
            self.settings.sync()

            # Return default settings
            return self.load_settings()

        except Exception as e:
            logger.error(f"Failed to reset settings: {e}")
            raise
