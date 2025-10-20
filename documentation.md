# Droplet Wall Interaction Tool (DWIT) Documentation

[![JOSS](https://joss.theoj.org/papers/XX.XXXXX/joss.XXXXX/status.svg)](https://doi.org/XX.XXXXX/joss.XXXXXXX)
[![EPL-2.0](https://img.shields.io/badge/License-EPL_2.0-blue.svg)](https://opensource.org/licenses/EPL-2.0)

## Table of Contents

- [Getting Started](#getting-started)
- [Core Concepts & Architecture](#core-concepts--architecture)
- [Full Pipeline Flowchart](#full-pipeline-flowchart)
- [Modes](#modes)
- [Project Structure](#project-structure)
- [Summary Table: Step Applicability by Mode](#summary-table-step-applicability-by-mode)
- [References](#references)
    - [Core Application](#core-application)
    - [Analysis Modules](#analysis-modules)
    - [Helper Modules](#helper-modules)
    - [Utilities Modules](#utilities-modules)
    - [Widgets Modules](#widgets-modules)

---

## Getting Started

### Prerequisites
- Python 3.10+ (Windows/macOS/Linux)
- [venv](https://docs.python.org/3/library/venv.html) for virtual environments
- Required packages (automatically installed via requirements.txt):
  - PySide6>=6.0.0 (GUI framework)
  - NumPy>=1.20.0 (numerical computing)
  - pandas>=1.3.0 (data manipulation)
  - SciPy>=1.7.0 (scientific computing)
  - OpenCV-Python>=4.5.0 (computer vision)

### Installation
```sh
python -m venv venv
venv\Scripts\activate  # On Windows
# or
source venv/bin/activate  # On macOS/Linux
pip install -r requirements.txt
```

### First Run
- **Any OS:** `python dwit.py` (after activating your venv)

---

## Core Concepts & Architecture

### What is Droplet Wall Interaction Tool?
Droplet Wall Interaction Tool (DWIT) is a scientific tool for automating droplet experiments, image analysis, and experiment planning.

### High-Level Architecture

```text
┌────────────┐      ┌────────────┐      ┌────────────┐
│   UI/Qt    │◀───▶│   Core     │◀───▶│  Helpers   │
│ (widgets)  │      │ (logic)    │      │ (analysis) │
└────────────┘      └────────────┘      └────────────┘
      │                  │                   │
      ▼                  ▼                   ▼
  Threads/Signals   Data/Params/State   Results/Exports
```

## Full Pipeline Flowchart

```mermaid
%% flowchart TD
%%     A([Start: Load Image])
%%     B([Crop & Rotate Image])
%%     C([Remove Background])
%%     D{Mode?}
%%     E1([Detect Baselines])
%%     E2([Detect Vertical Lines])
%%     E3([Skip: No Baseline/Vertical])
%%     F([Contour Measurements])
%%     D2{Mode?}
%%     G1([Process Intersection Points])
%%     H1([Contact Line Values])
%%     I1([Contact Angle])
%%     G2([Skip: No Intersection])
%%     H2([Skip: No Contact Line])
%%     I2([Skip: No Contact Angle])
%%     J([Calculate Center Points])
%%     K([Calculate Velocity])
%%     L([Save Results (Excel)])
%%     Z([End])
%%
%%     A --> B --> C --> D
%%     D -- "Channel/Contact Angle" --> E1
%%     D -- "Structured Packing" --> E2
%%     D -- "Free Sedimentation" --> E3
%%     E1 --> F
%%     E2 --> F
%%     E3 --> F
%%     F --> D2
%%     D2 -- "Channel/Contact Angle" --> G1
%%     D2 -- "Structured Packing/Free Sedimentation" --> G2
%%     G1 --> H1 --> I1 --> J
%%     G2 --> H2 --> I2 --> J
%%     I1 --> J
%%     J --> K --> L --> Z
%%
%%     %% Mode tags
%%     classDef all fill:#b0bec5,stroke:#333,stroke-width:1px,color:#222;
%%     classDef channel fill:#ffd54f,stroke:#333,stroke-width:1px,color:#222;
%%     classDef packing fill:#81c784,stroke:#333,stroke-width:1px,color:#222;
%%     classDef sediment fill:#64b5f6,stroke:#333,stroke-width:1px,color:#222;
%%     class B,C,F,J,K,L all;
%%     class E1,G1,H1,I1 channel;
%%     class E2 packing;
%%     class E3,G2,H2,I2 sediment,packing;
```

![Flowchart](resources/Flowchart_Analysis.png)

### **Legend**
- <span style="background-color:#ffd54f;color:#222;padding:2px 6px;border-radius:3px;">Channel/Contact Angle</span>: Steps E1, G1, H1, I1
- <span style="background-color:#81c784;color:#222;padding:2px 6px;border-radius:3px;">Structured Packing</span>: Step E2
- <span style="background-color:#64b5f6;color:#222;padding:2px 6px;border-radius:3px;">Free Sedimentation/Structured Packing</span>: Steps E3, G2
- <span style="background-color:#b0bec5;color:#222;padding:2px 6px;border-radius:3px;">All Modes</span>: Steps B, C, F, J, K, L

---

### Modes

- Free sedimentation
    - No baselines or contact angles. Computes geometry (width/height), center points, and velocity.
- Contact angle
    - Detects a single baseline automatically and computes advancing/receding angles, contact line, geometry, and velocity.
- Channel
    - Baseline auto-detection is currently disabled. To compute intersections, contact line, and contact angles, provide upper/lower baselines externally. Without baselines, these metrics are skipped and reported as NaN; geometry and velocity still compute.
- Structured packing
    - Detects two vertical lines (left/right packing edges). Reports first-contact flags and may compute discontinuous velocity. No contact angles.

Note: Per-frame overlays are saved to the selected folder. The Excel file with raw results is saved in the same folder as `results_raw.xlsx`.

Results export now appends parameter settings inline at the bottom of the same sheet. Two extra columns, `Parameter` and `Value`, are added and populated after the data rows, separated by one blank row. Example:

```
FileName | Time | … | Value               | Parameter
---------+------+---+---------------------+-----------------------------------------
img001   | 0.0  | … | Folder              | tests/free_sedimentation (BuAc_d_large)
img002   | 0.1  | … | FPS [1/s]           | 199
…        | …    | … | Pixel [px/mm]       | 55
         |      |   | Threshold           | 13
```

This keeps parameters visible in the same table for easy filtering and reproducibility. When no parameters are provided, no `Parameter`/`Value` rows are appended.

Mode-specific parameter omission:
- Free Sedimentation and Structured Packing do not use rotation/baseline fitting parameters; therefore these are omitted from the export: `Rotate Angle`, `Baseline Offset`, `Fitting Mode`, `Polynom`, `Manual Baseline`, and `Manual Baseline Height`.

---

## Project Structure

- Application code
    - Entry point: `dwit.py` (application initialization and lifecycle management)
    - UI: `src/gui.py` (main analysis GUI) and `src/widgets/` (reusable UI components)
        - `src/widgets/batch_control_panel.py` (batch processing controls)
        - `src/widgets/display_panel.py` (image display, slider, stats overlay)
        - `src/widgets/folder_manager.py` (folder selection and management)
        - `src/widgets/parameter_panel.py` (parameter input controls)
    - Core: `src/core.py` (analysis engine)
    - Analysis: `src/analysis/` (analysis pipeline and contact angle methods)
        - `src/analysis/workflow.py` (analysis orchestration)
        - `src/analysis/processors.py` (image and data processors)
        - `src/analysis/settings_manager.py` (settings persistence)
        - `src/analysis/contact_angle/` (contact angle calculation methods)
            - `arc_method.py` (arc-based calculation)
            - `tangent_method.py` (tangent-based calculation)
            - `ellipse_method.py` (ellipse fitting calculation)
            - `polynomial_method.py` (polynomial fitting calculation)
    - Helpers: `src/helpers/` (specialized helper functions)
        - `batch.py` (batch processing helpers)
        - `contact_detection.py` (contact detection with vertical lines)
        - `geometry.py` (geometric calculations)
        - `initialisation.py` (experiment initialization)
        - `preview.py` (preview utilities)
        - `save_results.py` (results export to Excel)
        - `visualisation.py` (visualization and drawing helpers)
    - Utilities: `src/utilities/` (cross-cutting utilities)
        - `core_utils.py` (logging and core utilities)
        - `image_utils.py` (image processing and ROI)
        - `measurement_utils.py` (measurement calculations, re-exports contact angle methods)
        - `overlays.py` (LogOverlay, NavigationOverlay)
        - `preview_optimisation.py` (preview caching)
        - `processors.py` (batch and results processors)
        - `threading.py` (background thread management)
- Data and assets
    - Test images: `tests/` (organized by experiment type)
    - Resources: `resources/` (icons and diagrams like `DWIT.png`, `avt.ico`, `Flowchart_Analysis.png`)
- Repo & docs
    - `readme.md` (overview and quickstart)
    - `documentation.md` (comprehensive documentation)
    - `paper.md`, `paper.bib` (publication materials)
    - `requirements.txt` (Python dependencies)
    - `pyproject.toml` (tooling config, e.g., Ruff)
    - `LICENSE`, `CITATION.cff`
    - `.pre-commit-config.yaml` (optional dev hooks)

---

### Summary Table: Step Applicability by Mode

| Step | Free Sedimentation | Contact Angle | Channel | Structured Packing |
|------|:-----------------:|:-------------:|:-------:|:------------------:|
| Crop & Rotate Image | ✅ | ✅ | ✅ | ✅ |
| Remove Background | ✅ | ✅ | ✅ | ✅ |
| Detect Baselines | 🚫 | ✅ | ⚠️ Manual/External | 🚫 |
| Contour Measurements | ✅ | ✅ | ✅ | ✅ |
| Process Intersection Points | 🚫 | ✅ | ⚠️ Requires baselines | 🚫 |
| Contact Line Values | 🚫 | ✅ | ⚠️ Requires baselines | 🚫 |
| Contact Angle | 🚫 | ✅ | ⚠️ Requires baselines | 🚫 |
| Vertical Lines | 🚫 | 🚫 | 🚫 | ✅ |
| Calculate Center Points | ✅ | ✅ | ✅ | ✅ |
| Calculate Velocity | ✅ | ✅ | ✅ | ✅ (discrete only) |
| Save Results (Excel) | ✅ | ✅ | ✅ | ✅ |

Notes:
- Channel mode requires externally provided baselines; otherwise intersection/contact metrics are skipped and stored as NaN.
- Per-frame overlays are saved under the selected folder, while the Excel file is saved in the same folder as `results_raw.xlsx`.

---

# References

This section provides detailed documentation for individual modules and classes.

## Core Application

### `dwit.py`
**File Path**: `/dwit.py` (root directory)

**Purpose**:
Main application entry point and window management for the Droplet Wall Interaction Tool (DWIT). Implements a sophisticated Qt-based GUI with multiple analysis modes, lazy loading, and comprehensive state management.

**Key Components**:
1. **Main Application Class**:
   - `DWIT(QMainWindow)`: Main application window with navigation and state management
   - `CellGUI`: Central GUI controller managing multiple analysis modes
   - `AnalysisWindow`: Individual analysis mode containers with lazy initialization

2. **Architecture Features**:
   - Multi-mode interface (Free Sedimentation, Contact Angle, Channel, Structured Packing)
   - Lazy loading for performance optimization
   - Persistent window state and settings
   - Comprehensive error handling and logging
   - Memory management with periodic garbage collection

3. **Navigation System**:
   - Tabbed interface with mode-specific pages
   - Persistent page state across application restarts
   - Real-time mode switching with proper cleanup

**Key Functions**:
- `main()`: Application initialization and Qt event loop management
- `setup_memory_management()`: Configures periodic garbage collection
- `handle_exception()`: Global exception handler for uncaught exceptions

**Dependencies**:
- PySide6.QtCore: For QSettings, QTimer, application management
- PySide6.QtWidgets: For QApplication, main window components
- PySide6.QtGui: For QIcon and window management
- Standard library: sys, traceback, gc, os

**Integration**:
- Entry point for the entire DWIT application
- Coordinates all analysis modes and GUI components
- Manages application lifecycle and state persistence

---

## Analysis Modules

### `core.py`
**File Path**: `/src/core.py`

**Purpose**:
Core analysis engine for DWIT. Orchestrates the pipeline, per-mode behavior, contact metrics, and export.

#### `AnalysisCore` Class
Drives analysis operations, exposes Qt Properties/Signals, and persists per-mode settings.

**Highlights**:
- Pipeline: rotate + crop → background → threshold/contour → area/diameter calculation → intersections/lines → metrics → save.
- Modes: `free_sedimentation`, `contact_angle`, `channel`, `structured_packing`.
- Measurements: Droplet area, equivalent diameter (D=√(4A/π)), contour dimensions, center coordinates.
- Visualization: 30% transparent green area overlay, contour outlines, measurement annotations.
- Fitting: Arc (default), Tangent, Polynom, Ellipse.
 - Saving: Per-frame overlays to the selected folder; raw Excel is written to the same folder as `results_raw.xlsx`.

**Properties** (subset):
- Paths: `folder_path`, `folder_paths`, `main_folder_path`.
- Mode/fit: `analysis_mode`, `fitting_mode`, `polynom`.
- Calibration: `pixel` (px/mm), `fps`, `threshold`, `rotate_angle`.
- ROI: `x_img`, `w_img`, `y_img`, `h_img`.
- Baseline: `baseline_tf`, `manual_baseline`, `baseline`.

**Signals** (subset):
- `image_processed(int, dict)`, `error_occurred(str)`, `folder_path_changed(str)`, and per-property change signals.
- Used with `AnalysisThread.progress_signal(float, list, list, list, dict)` for UI updates.

**Primary API**:
- `process_images(progress_cb, save_files, preview_middle, use_first_as_background)` → `(time, time_int, result_lists)`
    - Returns time arrays and a dict of lists with one entry per processed frame.
    - `result_lists` keys include:
        - `advancing_contact_angles`, `receding_contact_angles`
        - `rect_width_px`, `rect_height_px`, `rect_width_mm`, `rect_height_mm`
        - `center_points_px`, `center_points_mm`
        - `velocity`
        - `contact_line_px`, `contact_line_mm`
        - Channel mode adds `upper_*`/`lower_*` contact line values in `result_images` for previews.
        - Structured packing adds `left/right_contact_detected` (per-frame), `left/right_contact_frame`, `contact_status`, and possibly `discontinuous_velocity_{px_s,mm_s}`.

Mode specifics:
- `free_sedimentation`: No baselines or contact angles; still computes center, dimensions, velocity.
- `channel`: Auto-detection of baselines is disabled. If baselines are provided externally, intersections/contact lines/angles are computed; otherwise these metrics are skipped (NaN). Geometry and velocity still compute; previews may include upper/lower overlays when baselines exist.
- `structured_packing`: Detects two vertical lines; flags first contact frames and computes a discontinuous velocity.

Examples by mode (result_lists keys):
- Free sedimentation:
    - rect_width/height_{px,mm}, center_points_{px,mm}, velocity; contact angle arrays are NaN.
- Contact angle:
    - advancing_contact_angles, receding_contact_angles, rect_width/height_{px,mm}, center_points_{px,mm}, velocity, contact_line_{px,mm}.
- Channel:
    - Same as contact angle when baselines are provided; previews may include upper/lower contact line overlays in result_images.
- Structured packing:
    - rect_width/height_{px,mm}, center_points_{px,mm}, discontinuous_velocity_{px_s,mm_s}; flags like left/right_contact_detected (per frame), left/right_contact_frame, contact_status if available.

**Dependencies**:
- OpenCV, NumPy, PySide6, helpers in `src/helpers/*`, and utilities in `src/utilities/*`.

**Integration**:
- Consumed by `AnalysisThread` (from `src/utilities/threading.py`) and UI components in `src/gui.py` and `src/widgets/*`
- Settings persisted via QSettings through `SettingsManager` in `src/analysis/settings_manager.py`

---

### Contact Angle Calculation Methods

The contact angle calculation methods are located in `src/analysis/contact_angle/` and are re-exported through `src/utilities/measurement_utils.py` for backward compatibility.

#### `src/analysis/contact_angle/arc_method.py`
- `calculate_contact_angles()`: Main function for arc-based contact angle calculation
- Uses circular arc fitting to determine contact angles
- Visualizes contact angles with arcs and tangent lines
- Constant arc radius (RADIUS = 30 pixels)

#### `src/analysis/contact_angle/ellipse_method.py`
- `calculate_ellipse_contact_angle()`: Fits an ellipse to droplet contour
- `calculate_contact_angle_left()`: Calculates left contact angle from ellipse fit
- `calculate_contact_angle_right()`: Calculates right contact angle from ellipse fit
- `_fit_ellipse()`: Internal function for ellipse fitting
- `_ellipse_slope()`: Calculates slope of ellipse at given angle
- `_calculate_contact_angle()`: Converts slope to contact angle
- Good for symmetric droplets

#### `src/analysis/contact_angle/polynomial_method.py`
- `fit_left_polynomial()`: Fits polynomial to left contact angle region
- `fit_right_polynomial()`: Fits polynomial to right contact angle region
- `rotate_coordinates_90()`: Helper for coordinate transformation
- Uses polynomial curve fitting for angle determination

**Common Parameters** (for `calculate_contact_angles()` and similar):
- `cols`: Image width
- `shifted_points`: Contour data points
- `intersection_points`: Detected intersection points with baseline
- `y1_left`, `y1_right`: Baseline y-coordinates
- `img`: Processed image
- `filename`: Current image filename
- `output_path`: Output directory
- `advancing_contact_angles`: List to store advancing angles
- `receding_contact_angles`: List to store receding angles
- `q`: Current image index (default: 0)
- `result_images`: Optional dict to store visualization images
- `save_files`: Whether to save intermediate outputs
- `contour`: Largest contour (required for arc method)

**Returns**:
- `tuple`: (advancing_angles, receding_angles, angle_img)

**Integration**:
- Called by analysis pipeline in `src/analysis/processors.py` and `src/core.py`
- Method selection controlled by `fitting_mode` parameter in `AnalysisCore`
- Visualization output integrated with result display system

#### `calculate_ellipse_contact_angle()`
Calculates contact angle using ellipse fitting.

**Parameters**:
- `x_left`, `y_left`: Left contour coordinates
- `x_right`, `y_right`: Right contour coordinates
- `intersection_points`: Intersection points with baseline

**Returns**:
- Combined contact angle

**Dependencies**:
- NumPy for numerical operations
- OpenCV for image processing
- SciPy for curve fitting
- Custom logging utilities

**Integration**:
- Used by core for contact angle measurements
- Supports multiple calculation methods
- Provides visualization capabilities
- Integrates with image processing pipeline

**Usage Example**:
```python
# Import from measurement_utils (re-exports from contact_angle/)
from src.utilities.measurement_utils import (
    calculate_contact_angles,
    calculate_tangent_contact_angles,
    calculate_ellipse_contact_angle,
)

# Or import directly from source modules
from src.analysis.contact_angle.arc_method import calculate_contact_angles
from src.analysis.contact_angle.tangent_method import calculate_tangent_contact_angles
from src.analysis.contact_angle.ellipse_method import calculate_ellipse_contact_angle

# Calculate contact angles using arc method
advancing_angles, receding_angles, vis_img = calculate_contact_angles(
    cols=image_width,
    shifted_points=contour_points,
    intersection_points=intersections,
    y1_left=baseline_left,
    y1_right=baseline_right,
    img=processed_image,
    filename='experiment_001',
    output_path='./results'
)

# Calculate using tangent method
advancing_angles, receding_angles, vis_img = calculate_tangent_contact_angles(
    # ... similar parameters ...
)

# Calculate using ellipse fitting
contact_angle = calculate_ellipse_contact_angle(
    x_left=left_x,
    y_left=left_y,
    x_right=right_x,
    y_right=right_y,
    intersection_points=intersections
)
```

**Maintenance Notes**:
- Keep numerical methods optimized for accuracy
- Document any changes to calculation algorithms
- Add unit tests for different droplet shapes
- Consider adding more robust error handling
- Optimize performance for real-time processing

---

#### `src/analysis/contact_angle/tangent_method.py`
- `calculate_tangent_contact_angles()`: Calculates contact angles using tangent method
- Fits tangents to droplet contour at contact points
- Handles both vertical and non-vertical tangents
- More sensitive to contour noise than arc method

**Note on Imports:** All contact angle calculation functions can be imported from either their original location in `src/analysis/contact_angle/` or from `src/utilities/measurement_utils.py`, which re-exports them for backward compatibility and convenience.

### `processors.py`
**File Path**: `/src/analysis/processors.py`

**Purpose**:
Provides specialized processors for different stages of the analysis pipeline, including image processing, contact angle calculations, and visualization generation.

**Key Classes**:
- `ImageProcessor`: Handles image preprocessing (rotation, cropping, background removal, thresholding)
- `ContactAngleProcessor`: Manages contact angle calculations using different methods (arc, tangent, ellipse, polynomial)
- `VisualizationProcessor`: Creates visualization overlays for results

**Integration**:
- Used by `AnalysisCore` in the main processing pipeline
- Coordinates with `src/analysis/workflow.py` for orchestration

### `settings_manager.py`
**File Path**: `/src/analysis/settings_manager.py`

**Purpose**:
Manages persistent settings storage and retrieval for analysis parameters using Qt's QSettings. Handles mode-specific settings with proper namespacing.

**Key Features**:
- Per-mode settings isolation using QSettings groups
- Automatic loading and saving of analysis parameters
- Default value management
- Type-safe parameter handling

**Integration**:
- Used by `AnalysisCore` for settings persistence
- Coordinates with Qt's QSettings for cross-platform storage

### `workflow.py`
**File Path**: `/src/analysis/workflow.py`

**Purpose**:
Orchestrates the analysis workflow by managing file handling, pipeline execution, and results assembly.

**Key Classes**:
- `FileHandler`: Manages file operations and path handling
- `Pipeline`: Orchestrates the analysis pipeline steps
- `ResultsAssembler`: Assembles and structures analysis results

**Integration**:
- Used by `AnalysisCore` to coordinate the analysis process
- Works with processors for step-by-step execution

## Helper Modules

### `batch.py`
**File Path**: `/src/helpers/batch.py`

**Purpose**:
Helper module for batch processing of multiple folders in the Droplet Wall Interaction Tool. Provides UI components and worker threads for processing multiple experiments in sequence.

**Key Components**:

#### `FolderItemDelegate` Class
Custom delegate for rendering folder items with progress bars in the batch processing UI.

**Key Features**:
- Visual progress indication for batch processing
- Support for main folder highlighting
- Error state visualization
- Custom styling with RWTH blue theme

**Methods**:
- `set_progress(folder_path, progress_value)`: Update progress for a specific folder
- `size_hint(option, index)`: Provide size hints for item rendering

**Usage Example**:
```python
# Create and configure the delegate
delegate = FolderItemDelegate()
list_view.setItemDelegate(delegate)

# Update progress for an item
delegate.set_progress(folder_path, 75)  # 75% complete
```

#### `BatchProcessingWorker` Class
Worker thread for processing multiple folders in a batch.

**Key Features**:
- Background processing of multiple experiment folders
- Progress tracking and reporting
- Pause/resume functionality
- Error handling and recovery

**Signals**:
- `progress_updated`: Emitted when progress updates for a folder
- `folder_completed`: Emitted when a folder is fully processed
- `all_completed`: Emitted when all folders are processed
- `error_occurred`: Emitted when an error occurs
- `overall_progress_updated`: Emitted with overall progress
- `preview_image_updated`: Emitted when preview images are available

**Methods**:
- `process_folders()`: Main method to start batch processing
- `resume()`: Resume processing
- `stop()`: Stop processing
- `_folder_progress_callback()`: Internal callback for progress updates

**Dependencies**:
- PySide6 for GUI components
- Custom controller for experiment management
- Threading for background processing

**Integration**:
- Works with the main application's batch processing UI
- Coordinates with experiment controller for processing
- Provides real-time feedback to the user interface

**Maintenance Notes**:
- Ensure thread safety for all operations
- Handle resource cleanup properly
- Add logging for debugging
- Consider adding more detailed progress reporting
- Test with large numbers of folders

---

### `contact_detection.py`
**File Path**: `/src/helpers/contact_detection.py`

**Purpose**:
Helper module for detecting and visualizing contact points between droplets and vertical boundaries in the Droplet Wall Interaction Tool. Provides functionality to detect when a droplet makes contact with vertical boundaries and visualize these contact events.

**Key Functions**:

#### `get_contact_frame_status(left_contact_frame, right_contact_frame)`
Generates a status string describing the current contact state.

**Parameters**:
- `left_contact_frame`: Frame number when left contact first occurred (None if not yet)
- `right_contact_frame`: Frame number when right contact first occurred (None if not yet)

**Returns**:
- `str`: Human-readable status string

**Internal Helper Functions**:
- `_prepare_contour_points()`: Prepares contour points for processing

**Dependencies**:
- OpenCV for image processing
- NumPy for numerical operations
- Custom logging utilities

**Integration**:
- Used by analysis pipeline for contact detection
- Integrates with visualization system
- Works with the main application's frame processing

**Usage Example**:
```python
# Get status message
status = get_contact_frame_status(left_contact_frame, right_contact_frame)
print(f"Status: {status}")
```

**Maintenance Notes**:
- Keep contact threshold configurable for different picture resolutions
- Add more sophisticated contact detection if needed
- Consider adding unit tests for different contact scenarios
- Document any changes to the visualization style
- Optimize for real-time performance

---

### `geometry.py`
**File Path**: `/src/helpers/geometry.py`

**Purpose**:
Comprehensive geometric calculations and contour processing for droplet analysis. Provides functions for intersection detection, contour filtering, area calculations, and shape processing.

**Key Functions**:
- `find_intersection_points()`: Finds intersection points between droplet contour and baseline
- `calculate_drop_area()`: Calculates droplet area with handling for open/closed contours
- `process_contour()`: Processes contour data for analysis

**Features**:
- Robust intersection detection with multiple fallback methods
- Area calculations with special handling for incomplete contours
- Contour filtering and cropping for different analysis modes
- Visualization support for debugging and result overlays

**Integration**:
- Used extensively by `AnalysisCore` for droplet geometry analysis
- Works with OpenCV contour data structures
- Provides foundation for contact angle and measurement calculations

**Dependencies**:
- OpenCV (cv2) for contour operations
- NumPy for numerical calculations
- Custom logging utilities

---

### `initialisation.py`
**File Path**: `/src/helpers/initialisation.py`

**Purpose**:
Helper module for experiment and application initialization in the Droplet Wall Interaction Tool. Provides functions for initializing analysis runs, validating inputs, and setting up data structures for image processing.

**Key Functions**:

#### `start_run(img_names, q, save_files, folder_path)`
Processes a single image for analysis with improved error handling.

**Parameters**:
- `img_names`: List of image filenames or paths
- `q`: Index of the image to process
- `save_files`: Boolean indicating whether to save intermediate files
- `folder_path`: Path to the folder containing images

**Returns**:
- `tuple`: Initialized data structures and loaded image

**Raises**:
- `ValueError`: If image loading fails or image data is invalid
- `TypeError`: If input types are incorrect
- `IndexError`: If the specified index is out of bounds

#### `initiate_run(files, save_files, folder_path, fps)`
Initializes the angle measurement program.

**Parameters**:
- `files`: List of image files to process
- `save_files`: Whether to save intermediate files
- `folder_path`: Path to the image folder
- `fps`: Frames per second for timestamp calculation

**Returns**:
- `tuple`: Initialized data structures including timestamps and analysis results

#### `_validate_and_resolve_image_path(img_names, q, folder_path)`
Validates inputs and resolves the image path and filename.

**Parameters**:
- `img_names`: List of image filenames or a single filename
- `q`: Index of the image to process
- `folder_path`: Path to the folder containing images

**Returns**:
- `tuple`: (img_names, image_path, filename)

**Raises**:
- `TypeError`: If img_names is not a list or string
- `ValueError`: If the image list is empty
- `IndexError`: If the specified index is out of bounds

#### `_calculate_timestamps(image_filenames, fps)`
Calculates timestamps for image files based on their numerical suffixes.

**Parameters**:
- `image_filenames`: List of image filenames
- `fps`: Frames per second for timestamp calculation

**Returns**:
- `tuple`: (timestamps_int, timestamps_str) - Lists of integer and string timestamps

#### `__extract_image_number(filename)`
Extracts the numerical part from an image filename with improved error handling.

**Parameters**:
- `filename`: Image filename

**Returns**:
- `int`: Extracted numerical value or 0 if extraction fails

**Dependencies**:
- OpenCV for image loading
- NumPy for numerical operations
- Regular expressions for filename parsing
- Custom logging utilities

**Integration**:
- Used at the start of the analysis pipeline
- Integrates with the main application's file handling system
- Works with the visualization and analysis modules

**Usage Example**:
```python
# Initialize a single image run
(
    y1_list, y2_list, x1_list, x2_list, y1_neu, xsp,
    shifted_points, shifted_x, shifted_y, cnt_y_neu,
    cnt_x_neu, cnt_x, cnt_y, x_left_cnt, y_left_cnt,
    x_right_cnt, y_right_cnt, src, filename
) = start_run(
    img_names=["image001.jpg", "image002.jpg", "image003.jpg"],
    q=0,  # Process first image
    save_files=True,
    folder_path="/path/to/images"
)

# Initialize a complete analysis run
(
    x1_list, y1_list, x2_list, y2_list, xsp, y1_neu,
    shifted_points, shifted_x, shifted_y, cnt_y_neu,
    cnt_x_neu, cnt_x, cnt_y, x_left_cnt, y_left_cnt,
    x_right_cnt, y_right_cnt, timestamps_int, timestamps_str,
    contact_angle_left, contact_angle_right, radius, area, volume,
    base_width, height, left_intersect_x, right_intersect_x,
    center_points_px, center_points_mm, velocity_px, velocity_mm,
    acceleration_px, acceleration_mm, contour_list, files, fps,
    baseline_y, baseline_y2, pixel_conversion, pixel_conversion_units
) = initiate_run(
    files=["image001.jpg", "image002.jpg", "image003.jpg"],
    save_files=True,
    folder_path="/path/to/images",
    fps=30.0
)
```

**Maintenance Notes**:
- Ensure robust error handling for various file formats
- Add validation for input parameters
- Document any changes to initialization procedures
- Consider adding support for additional image naming conventions
- Optimize for large numbers of images
- Add unit tests for different input scenarios

---

### `preview.py`
**File Path**: `/src/helpers/preview.py`

**Purpose**:
Helper module for displaying image previews in the Droplet Wall Interaction Tool. Provides functionality to show temporary, non-blocking preview windows for images with automatic scaling and timeout.

**Key Functions**:

#### `show_preview(image, parent)`
Displays a click-through, see-through preview of the given image.

**Parameters**:
- `image`: Image to display (numpy array, QPixmap, or QImage)
- `parent`: Parent widget for screen positioning

**Features**:
- Automatically scales the preview to 50% of the screen's longest side
- Centers the preview on the parent widget's screen
- Auto-closes after 3 seconds
- Updates instantly if a new image is shown
- Handles different image formats (grayscale, RGBA, BGR)
- Is click-through (doesn't steal focus)
- Is see-through (window is transparent except for the image)

**Internal Helper Functions**:

##### `_convert_to_pixmap(image)`
Converts a numpy array to QPixmap, handling different color formats.

##### `_get_target_screen(parent)`
Determines the appropriate screen to display the preview on.

##### `_calculate_scaled_pixmap(pixmap, screen_geometry)`
Calculates and creates a scaled version of the pixmap.

##### `_update_existing_dialog(scaled_pixmap, screen_geometry)`
Updates an existing preview dialog with a new image.

##### `_create_new_dialog(scaled_pixmap, parent, screen_geometry)`
Creates a new preview dialog with the given image.

##### `_setup_auto_close_timer()`
Sets up a timer to automatically close the preview after a delay.

**Dependencies**:
- PySide6 for GUI components
- OpenCV for image format conversion
- Custom logging utilities

**Integration**:
- Used throughout the application for image previews
- Integrates with the main UI thread
- Works with both Qt and OpenCV image formats

**Usage Example**:
```python
# Show a preview of a numpy array (OpenCV image)
import cv2
image = cv2.imread("example.jpg")
show_preview(image, parent_widget)

# Show a preview of a QPixmap
from PySide6.QtGui import QPixmap
pixmap = QPixmap("example.jpg")
show_preview(pixmap, parent_widget)
```

**Maintenance Notes**:
- Ensure proper cleanup of resources to prevent memory leaks
- Add validation for input image formats
- Consider adding support for custom preview durations
- Optimize performance for high-resolution images
- Add unit tests for different image formats and screen configurations
- Document any changes to the preview behavior or API
- Consider adding keyboard/mouse interaction (e.g., close on click)

---

### `save_results.py`
**File Path**: `/src/helpers/save_results.py`

**Purpose**:
Export module for saving raw measurement results to Excel in the Droplet Wall Interaction Tool. The Excel file is saved to the selected folder as `results_raw.xlsx`. Overlays are saved to the selected folder as well.

**Key Functions**:

#### `save_results(output_dir, times, result_lists)`
Main function to save measurement results to an Excel file.

**Parameters**:
- `output_dir`: Directory to save results
- `times`: Time values for x-axis
- `result_lists`: Dictionary containing measurement results

**Features**:
- Exports raw data to Excel with consistent formatting
- Handles different data types and shapes (fills missing with NaN)
- Includes error handling, path sanitization, and alternative filename fallback
- Exports optional fields when present (e.g., `Discontinuous Velocity [px/s]`, `[mm/s]`)
 - Writes Excel directly to `output_dir` using the filename `results_raw.xlsx`
 - Writes Excel directly to `output_dir` using the filename `results_raw.xlsx`

#### `_save_dataframe_to_excel(data_dict, output_dir, filename)`
Saves a data dictionary to Excel with consistent formatting and error handling.

**Parameters**:
- `data_dict`: Dictionary where keys are column names and values are lists of data
- `output_dir`: Directory to save the Excel file
- `filename`: Excel filename

**Internal Helper Functions**:
- `_extract_data_from_results()`: Processes raw result lists into structured data, including optional discontinuous velocity keys
- `_prepare_output_directory()`: Creates output directories
- `_check_data_availability()`: Validates available data types
- `_extract_center_coordinates()`: Processes center point data

**Dependencies**:
- pandas for data manipulation
- numpy for numerical operations
- Custom logging utilities

**Integration**:
- Works with the main analysis pipeline
- Integrates with the application's data structures
- Used for both real-time and batch processing

**Usage Example**:
```python
times = [0.0, 0.1, 0.2]
result_lists = {
    'advancing_contact_angles': [95.2, 94.9, 95.1],
    'receding_contact_angles': [82.3, 82.1, 82.0],
    'rect_width_px': [120, 121, 119],
    'rect_height_px': [80, 81, 80],
    'rect_width_mm': [1.20, 1.21, 1.19],
    'rect_height_mm': [0.80, 0.81, 0.80],
    'center_points_px': [(320, 240)]*3,
    'center_points_mm': [(3.2, 2.4)]*3,
    'velocity': [1.1, 1.2, 1.1],
    'contact_line_px': [210, 211, 209],
    'contact_line_mm': [2.10, 2.11, 2.09],
    # Optional keys
    'discontinuous_velocity_px_s': float('nan'),
    'discontinuous_velocity_mm_s': float('nan'),
}

save_results('trial_folder', times, result_lists)  # Excel will be saved to 'trial_folder/results_raw.xlsx'
```

**Maintenance Notes**:
- Ensure proper error handling for file I/O operations
- Add validation for input data formats
- Optimize performance for large datasets
- Add unit tests for all helper functions
- Document any changes to data structures or file formats
- Consider adding support for additional export formats
- Add memory management for large datasets
- Consider adding progress tracking for long-running operations

---

### `visualisation.py`
**File Path**: `/src/helpers/visualisation.py`

**Purpose**:
Drawing and visualization utilities for experiment visualization in Droplet Wall Interaction Tool. Contains visualization utilities extracted from core.py to improve code organization and maintainability.

**Key Functions**:
- `draw_intersection_points_and_angles()`: Draws intersection points and contact angle lines
- `draw_filled_contour()`: Draws filled contours on images
- `draw_rectangle()`: Draws bounding rectangles
- `draw_center_point()`: Draws center point markers
- Additional helper functions for overlays and annotations

**Integration**:
- Used by `AnalysisCore` and processors for result visualization
- Generates per-frame overlay images saved during analysis
- Works with OpenCV for image drawing operations

---

## Utilities Modules

This section documents the utility modules in the `src/utilities` directory that provide common functionality used throughout the application.

### `core_utils.py`
**File Path**: `/src/utilities/core_utils.py`

**Purpose**:
Centralized logging management and core utilities for the Droplet Wall Interaction Tool, providing a unified interface for application logging.

**Key Functions**:
- `get_logger(name)`: Get or create a logger instance with consistent configuration

**Key Components**:
- `LoggingManager` class: Singleton that manages log levels and handlers
- `ColoredLogHandler`: Custom log handler for rich text output
- `TerminalStyleFormatter`: Formats log messages in a terminal-like style
- Helper functions for common logging operations

**Features**:
- Multiple log levels (DEBUG, INFO, WARNING, ERROR)
- Color-coded output for different log levels
- Capture of stdout/stderr
- Thread-safe logging
- Log filtering and level control

**Dependencies**:
- PySide6 for GUI integration
- Python standard logging module

**Usage Example**:
```python
from src.utilities.core_utils import get_logger

logger = get_logger(__name__)
logger.info("Application started")
logger.debug("Debug information")
logger.warning("Warning message")
logger.error("Error occurred")
```

**Integration**:
- Used throughout the application for consistent logging
- Integrates with the GUI for log display
- Supports both console and file output

---

### `image_utils.py`
**File Path**: `/src/utilities/image_utils.py`

**Purpose**:
Comprehensive image processing utilities for the Droplet Wall Interaction Tool, including background creation, rotation, cropping, ROI selection, and video conversion.

**Key Functions**:
- `create_background_image()`: Creates a robust background image using multiple methods
- `rotate_image()`: Rotates images with proper handling of edges and corners
- `crop_image()`: Crops images using specified parameters
- `convert_videos_to_images()`: Converts video files to image sequences
- `safe_imread()`: Safely loads images with error handling

**Key Classes**:
- `ROISelector`: Interactive dialog for ROI selection with rotation support

**Features**:
- Support for various image formats and color spaces
- Advanced background calculation using median filtering
- Automatic handling of image orientation
- Batch processing of video files
- Interactive ROI selection with visual feedback

**Dependencies**:
- OpenCV (cv2)
- NumPy
- PySide6 for GUI components (ROISelector)
- Custom utilities: `core_utils.get_logger`

**Integration**:
- Used throughout the application for image manipulation
- Supports both single images and batch processing
- ROISelector integrates with AnalysisGUI for region selection

---

### `measurement_utils.py`
**File Path**: `/src/utilities/measurement_utils.py`

**Purpose**:
Consolidated measurement utilities module for Droplet Wall Interaction Tool. Provides:
- Baseline detection utilities
- Structured packing edge detection  
- Velocity calculations from center points
- Re-exports of contact angle calculation methods from `src/analysis/contact_angle/` for backward compatibility

This module centralizes common measurement helpers and provides a stable, single-location API for imports that were previously referenced from separate baseline, packing, velocity, or contact-angle helper modules.

**Key Functions**:

**Functions defined in this module:**
- `find_single_baseline()`: Baseline detection for droplet analysis
- `find_vertical_lines()`: Vertical line detection for structured packing mode
- `calculate_velocities()`: Velocity calculations from center points

**Re-exported from `src/analysis/contact_angle/`:**
- `calculate_contact_angles()` (from `arc_method.py`)
- `calculate_tangent_contact_angles()` (from `tangent_method.py`)
- `calculate_ellipse_contact_angle()` (from `ellipse_method.py`)
- `calculate_contact_angle_left()` (from `ellipse_method.py`)
- `calculate_contact_angle_right()` (from `ellipse_method.py`)
- `fit_left_polynomial()` (from `polynomial_method.py`)
- `fit_right_polynomial()` (from `polynomial_method.py`)
- `rotate_coordinates_90()` (from `polynomial_method.py`)

#### `find_single_baseline(image, baseline_offset=0, baseline_tf=False, manual_offset=0)`
Detects the baseline where a droplet sits using multiple detection strategies.

**Parameters**:
- `image`: Input image (numpy array)
- `baseline_offset`: Manual offset adjustment for baseline (pixels)
- `baseline_tf`: If True, use manual offset only
- `manual_offset`: Manual offset value when baseline_tf is True

**Returns**:
- `tuple[int|None, int|None]`: `(y1_left, y1_right)` baseline y-coordinates, or `(None, None)` if not found

**Features**:
- Automatic threshold determination
- Multiple detection strategies (Canny edge detection, Hough transform)
- Noise reduction with Gaussian blur
- Adaptive thresholding based on image statistics
- Scoring system for line selection

**Usage Example**:
```python
import cv2
from src.utilities.measurement_utils import find_single_baseline

# Load image
image = cv2.imread('droplet.jpg')

# Find baseline
y_left, y_right = find_single_baseline(
    image,
    baseline_offset=5,
    baseline_tf=False
)

# Draw baseline on image
height = image.shape[0]
cv2.line(image, (0, y_left), (image.shape[1], y_right), (0, 255, 0), 2)
```

**Notes**:
- Automatic mode uses Canny + HoughLinesP; favors lower-half, near-horizontal lines; tolerant to slight tilt
- Manual mode returns a flat baseline at `img_h - manual_offset`
- Baseline may be slightly sloped; downstream uses average y for some steps

**Integration**:
- Used by analysis pipeline for contact angle measurements
- Called from `src/analysis/processors.py` and `src/core.py`

### `overlays.py`
**File Path**: `/src/utilities/overlays.py`

**Purpose**:
Provides overlay widgets that enhance the user interface with additional functionality like logging and navigation. These overlays are positioned strategically on the UI for optimal user experience.

**Key Components**:
- `SmoothOverlay`: Base class for animated overlays with smooth show/hide transitions
- `LogOverlay`: Displays application logs with filtering (positioned at top-left corner)
- `NavigationOverlay`: Provides navigation controls (positioned at top-right corner)

**Features**:
- Smooth fade-in/fade-out animations using QPropertyAnimation
- Customizable appearance with semi-transparent backgrounds
- Responsive layout that follows parent widget
- Keyboard shortcuts for quick access
- Color-coded log levels (DEBUG: cyan, INFO: green, WARNING: orange, ERROR: red)
- Real-time log filtering by severity level
- Status indicator with colored dot showing highest severity

**Recent Updates** (from UI refactoring):
- Repositioned LogOverlay to top-left corner (previously bottom-left)
- Repositioned NavigationOverlay to top-right corner
- Updated log toggle button text and geometry
- Improved visual consistency with standardized UI indicators

**Dependencies**:
- PySide6 for GUI components (QFrame, QPropertyAnimation, QGraphicsOpacityEffect)
- Custom utilities: `core_utils.get_logger`

**Integration**:
- Used by the main application window for system-wide logging
- Integrates with the logging system through centralized logger
- Provides user interface enhancements for debugging and navigation

---

### `preview_optimisation.py`
**File Path**: `/src/utilities/preview_optimisation.py`

**Purpose**:
Provides optimized preview generation with caching to improve UI responsiveness during analysis.

**Key Classes**:
- `PreviewCache`: Caches preview images to avoid redundant processing
- `OptimizedPreviewGenerator`: Generates optimized previews with intelligent caching

**Key Functions**:
- `get_optimized_preview_generator()`: Returns singleton instance of the preview generator

**Features**:
- Automatic cache invalidation when parameters change
- Memory-efficient caching strategy
- Integration with Qt signals for UI updates
- Reduces redundant image processing

**Integration**:
- Used by `AnalysisGUI` for context-sensitive preview updates
- Coordinates with analysis controller for parameter tracking
- Improves UI responsiveness during parameter adjustments

---

### `processors.py`
**File Path**: `/src/utilities/processors.py`

**Purpose**:
Provides utility processors for batch operations, results handling, and statistics updates in the GUI.

**Key Classes**:
- `ResultsProcessor`: Processes and formats analysis results for display
- `StatsUpdater`: Updates statistics overlays in real-time during analysis
- `BatchProcessor`: Manages batch processing operations for multiple folders

**Features**:
- Efficient result aggregation and formatting
- Real-time statistics calculation and display
- Batch operation coordination
- Progress tracking and reporting

**Integration**:
- Used by `AnalysisGUI` for result display and batch operations
- Works with `AnalysisThread` for progress updates
- Coordinates with batch control panel for folder processing

---

### `threading.py`
**File Path**: `/src/utilities/threading.py`

**Purpose**:
Provides QThread implementations for running image analysis operations in background threads, allowing for responsive UI during processing.

**Key Classes**:

#### `AnalysisThread(QThread)`
Thread class for running analysis operations asynchronously without blocking the UI.

**Signals**:
- `progress_signal(progress, advancing_contact_angles, receding_contact_angles, center_points_px, result_images)`: Emitted during analysis to report progress (signature: float, list, list, list, dict)
- `finished_signal(results)`: Emitted when analysis completes successfully
- `error_signal(error_message)`: Emitted when an error occurs during analysis

**Key Methods**:
- `run()`: Main thread execution method that orchestrates the analysis
- `resume()`: Resume a paused analysis operation
- `stop()`: Stop the analysis operation gracefully
- `_progress_callback()`: Internal callback for progress updates from controller

**Usage Example**:
```python
# Create and start analysis thread
analysis_thread = AnalysisThread(
    controller=analysis_controller,
    save_files=True,
    preview_middle=True,
    use_first_as_background=False
)
analysis_thread.start()

# Connect signals
analysis_thread.progress_signal.connect(update_progress_ui)
analysis_thread.finished_signal.connect(handle_results)
analysis_thread.error_signal.connect(show_error)
```

**Behavior**:
- Pause: Thread waits between frames until resumed (uses sleep to reduce CPU usage)
- Stop: Requests early termination after current frame; progress callback returns False to abort processing
- Error handling: Captures exceptions and emits error_signal with descriptive message
- Resource cleanup: Ensures proper cleanup on thread completion

**Integration**:
- Used by `AnalysisGUI` for all preview and full analysis operations
- Coordinates with `AnalysisCore` controller for processing
- Integrates with batch processing for multi-folder operations

---

## Widgets Modules

This section documents the widget modules that provide the graphical user interface components for the Droplet Wall Interaction Tool. These widgets are built using PySide6 and organized into reusable components in the `src/widgets/` directory.

### `gui.py`
**File Path**: `/src/gui.py`

**Purpose**:
Provides the main analysis interface for processing and visualizing droplet interaction experiments.

**Key Components**:
- `AnalysisGUI`: Main analysis interface with image processing controls and visualization
- Interactive ROI (Region of Interest) selection
- Batch processing support for multiple experiments
- Real-time preview of analysis results with debounced updates
- Integration with specialized widget components from `src/widgets/`

**Features**:
- Multiple analysis modes (free sedimentation, contact angle, channel, structured packing)
- Interactive parameter adjustment with context-sensitive live preview
- Frame-by-frame navigation with embedded image slider
- Batch processing queue with progress tracking
- Result visualization with overlays and statistics
- Optimized preview generation with caching and debouncing

**Dependencies**:
- PySide6 for GUI components
- OpenCV for image processing
- NumPy for numerical operations
- Custom widgets: `BatchControlPanel`, `PreviewCanvas`, `ImageSlider`, `StatsOverlay`, `ParameterPanel`, `FolderManager`
- Custom utilities: `ROISelector`, `image_utils`, `core_utils`

**Integration**:
- Connects to analysis controller (`src/core.py`) for processing
- Displays results from analysis threads (`src/utilities/threading.py`)
- Integrates with the main application window
- Coordinates with specialized widget components

**Signals**:
- Subscribes to `controller.image_processed(int, dict)` to update previews
- Spawns `AnalysisThread` for preview/full runs and connects:
    - `progress_signal(float, list, list, list, dict)` → updates stats/preview
    - `finished_signal(tuple)` → saving and UI reset
    - `error_signal(str)` → error handling and UI reset
- `ROISelector` emits `roi_selected(left, top, right, bottom)` → `apply_selected_roi`
- `BatchProcessingWorker` emits per-folder progress for the list view

**Batch processing**:
- Controls: `Add Folders`, `Process All Folders`, `Pause/Resume`, `Stop`
- List view with `FolderItemDelegate` renders per-folder progress bars and statuses
- Uses a background worker (helpers.batch) to process folders sequentially
- Updates `overall_progress` (0–100%) and `folder_counter` (e.g., "2/5 folders")

### `batch_control_panel.py`
**File Path**: `/src/widgets/batch_control_panel.py`

**Purpose**:
Provides batch processing controls and folder list management for processing multiple experiment folders.

**Key Components**:
- Folder list widget with drag-and-drop support
- Batch processing control buttons (Add, Process, Pause/Resume, Stop)
- Progress tracking for individual folders
- Processing mode selection (undone only, redo all, redo failed)
- Results scanning for folder status indicators

**Features**:
- Custom folder item delegate with progress bars
- Context menu for folder operations
- Real-time progress updates
- Visual indicators for folder processing status
- Drag-and-drop folder addition

**Recent Updates** (from UI refactoring):
- Controls placed at top of panel for better accessibility
- Reordered folder list and progress display
- Removed deprecated `get_controls_layout()` method
- Improved layout consistency

**Dependencies**:
- PySide6 for GUI components
- Custom helpers: `FolderItemDelegate`, `FolderDropZone`
- Custom utilities: `core_utils.get_logger`

### `display_panel.py`
**File Path**: `/src/widgets/display_panel.py`

**Purpose**:
Provides specialized display components for image preview, frame navigation, and statistics overlay.

**Key Components**:

#### `ImageSlider` Class
Professional image slider widget for navigating through result images with playback controls.

**Features**:
- Frame navigation (previous/next buttons)
- Auto-play with adjustable speed (0.1×–4.0×)
- Direct frame selection via slider
- Keyboard shortcuts (arrow keys, space for play/pause)
- Focus handling with transparent/opaque styles
- Localized speed label formatting
- Custom speed steps for precise playback control

**Recent Updates** (from UI refactoring):
- Embedded into PreviewCanvas as an overlay (no longer external)
- Added focus handling for better keyboard interaction
- Implemented transparent style when unfocused, opaque when focused
- Custom speed steps for finer control (0.1, 0.2, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 4.0×)
- Improved speed label with localized formatting

**Signals**:
- `frame_changed(int)`: Emitted when the current frame changes

#### `PreviewCanvas` Class
Canvas widget for displaying analysis results with integrated image slider and stats toggle.

**Features**:
- Image display canvas with proper scaling and centering
- Statistics overlay toggle button (top-left)
- Automatic resize handling
- OpenCV to Qt image conversion
- Embedded image slider as an overlay

**Recent Updates** (from UI refactoring):
- Accepts and positions ImageSlider as an overlay component
- Lightened stats icon color for better visibility
- Improved layout management for embedded slider

**Methods**:
- `set_image(image, fit_to_window=True)`: Display an image on the canvas
- `clear_canvas()`: Clear the canvas display
- `resizeEvent(event)`: Handle resize to reposition stats icon and slider

#### `StatsOverlay` Class
Semi-transparent overlay that displays real-time analysis statistics.

**Features**:
- Displays contact angles (advancing/receding)
- Shows contour dimensions (width/height)
- Displays area and diameter measurements
- Shows velocity calculations
- Adapts content based on analysis mode
- Color-coded sections for easy reading

**Methods**:
- `update_from_numeric_data(...)`: Update overlay with numeric statistics
- `update_display()`: Refresh the visual display
- `show_overlay()` / `hide_overlay()`: Control visibility with animation

**Dependencies**:
- PySide6 for GUI components
- OpenCV (cv2) for image handling
- NumPy for numerical operations
- Custom utilities: `core_utils.get_logger`

**Integration**:
- Used by `AnalysisGUI` for result display and navigation
- Coordinates with analysis controller for frame data
- Provides user interface for reviewing analysis results

### `folder_manager.py`
**File Path**: `/src/widgets/folder_manager.py`

**Purpose**:
Provides folder selection and management widgets with drag-and-drop support.

**Key Components**:
- `FolderDropZone`: Widget for dragging and dropping folders
- Folder list management utilities
- Path validation and normalization

**Features**:
- Drag-and-drop folder addition
- Visual feedback during drag operations
- Path validation and error handling
- Multi-folder selection support

### `parameter_panel.py`
**File Path**: `/src/widgets/parameter_panel.py`

**Purpose**:
Provides parameter input controls for analysis configuration.

**Key Components**:
- `ParameterPanel`: Main panel for analysis parameters
- `FlexibleDoubleSpinBox`: Custom spinbox with flexible formatting
- Parameter grouping and organization

**Features**:
- ROI parameters (x, y, width, height)
- Calibration parameters (pixel/mm, FPS, threshold)
- Rotation and baseline controls
- Mode-specific parameter visibility
- Instant parameter validation
- Integration with controller property system

---
