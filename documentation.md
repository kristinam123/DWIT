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
    - [Core Application (`dwit.py`)](#dwitpy)
    - [Core Modules (`src/core.py`)](#corepy)
    - [Helper Modules (`src/helpers/*`)](#helper-modules)
    - [Threading Modules (`src/threads.py`)](#threading-modules)
    - [Utilities Modules (`src/utilities/*`)](#utilities-modules)
    - [Widgets Modules (`src/widgets.py`)](#widgets-modules)

---

## Getting Started

### Prerequisites
- Python 3.10+ (Windows/macOS/Linux)
- [venv](https://docs.python.org/3/library/venv.html) for virtual environments

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
    - UI: `src/widgets.py` (analysis UI and controls)
    - Core: `src/core.py` (analysis engine)
    - Helpers: `src/helpers/` (baseline, contour, contact angle, intersections, batch, preview, save, velocity, structured_packing, drawing, initialisation)
    - Threads: `src/threads.py` (background processing)
    - Utilities: `src/utilities/` (`image.py`, `logging_manager.py`, `overlays.py`, `roi.py`)
- Data and assets
    - Test images: `tests/` (organized by experiment type)
    - Resources: `resources/` (icons and diagrams like `DWIT.png`, `avt.ico`, `Flowchart_Analysis.png`)
- Repo & docs
    - `README.md` (overview and quickstart)
    - `requirements.txt` (Python dependencies)
    - `pyproject.toml` (tooling config, e.g., Ruff)
    - `LICENSE`
    - `CITATION.cff` (how to cite)
    - `paper.md`, `paper.bib` (publication materials)
    - `.pre-commit-config.yaml` (optional dev hooks), `.vscode/` (editor settings)

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

## Core Application

### `dwit.py`
**File Path**: `/dwit.py`

**Purpose**:
The main entry point for the Droplet Wall Interaction Tool (DWIT) application. Initializes the Qt application, sets up global exception handling, manages application lifecycle, and handles window state persistence.

**Key Components**:
1. **Memory Management**:
   - Implements periodic garbage collection to prevent memory leaks
   - Uses Python's `gc` module with optimized thresholds
   - Runs cleanup every 30 seconds

2. **Error Handling**:
   - Global exception handler for uncaught exceptions
   - Graceful logging of errors before application termination
   - Attempts to continue running after non-fatal errors

3. **Application State**:
   - Saves and restores window geometry and state using QSettings
   - Manages application metadata (organization and application name)
   - Handles proper cleanup on application exit

**Key Functions**:
- `cleanup_logging()`: Restores original stdout/stderr streams on exit
- `setup_memory_management()`: Configures and starts periodic garbage collection
- `handle_exception()`: Global exception handler for uncaught exceptions
- `main()`: Application entry point (wrapped in `if __name__ == "__main__"`)

**Dependencies**:
- PySide6.QtCore: For QSettings, QTimer
- PySide6.QtWidgets: For QApplication
- Standard library: sys, traceback, gc

**Usage Example**:
```python
if __name__ == "__main__":
    dwit = QApplication(sys.argv)
    dwit.setOrganizationName("Droplet Wall Interaction Tool (DWIT)")
    dwit.setApplicationName("Droplet Wall Interaction Tool (DWIT)")
    
    # ... setup and run application ...
    
    sys.exit(dwit.exec())
```

**Integration**:
- Initializes the main application window (`DWIT` from `dwit.py`)
- Integrates with the logging system through `logging_manager`
- Manages application-wide settings and state

---

## Core Modules

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
- Consumed by `AnalysisThread` and UI in `widgets.py`; settings persisted via QSettings.

---

## Helper Modules

### `src/helpers/baseline.py`
**File Path**: `/src/helpers/baseline.py`

**Purpose**:
Helper module for baseline detection in droplet and experiment analysis. Provides functions to detect and analyze baselines in droplet images, which is crucial for accurate contact angle measurements.

**Key Functions**:

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
from src.helpers.baseline import find_single_baseline

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
- Automatic mode uses Canny + HoughLinesP; favors lower-half, near-horizontal lines; tolerant to slight tilt.
- Manual mode returns a flat baseline at `img_h - manual_offset`.
- Baseline may be slightly sloped; downstream uses average y for some steps.

### `src/helpers/batch.py`
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
- `set_progress(row, progress_value)`: Update progress for a specific row
- `size_hint()`: Provide size hints for item rendering

**Usage Example**:
```python
# Create and configure the delegate
delegate = FolderItemDelegate()
list_view.setItemDelegate(delegate)

# Update progress for an item
delegate.set_progress(row_index, 75)  # 75% complete
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
- `pause()`: Pause the batch processing
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

### `src/helpers/contact_angle.py`
**File Path**: `/src/helpers/contact_angle.py`

**Purpose**:
Core module for contact angle calculation in the Droplet Wall Interaction Tool. Implements multiple methods for calculating contact angles from droplet images, including arc, tangent, and ellipse fitting methods.

**Key Components**:

#### Contact Angle Calculation Methods

1. **Arc Method**
   - `calculate_contact_angles()`: Main function for arc-based contact angle calculation
   - Uses circular arc fitting to determine contact angles
   - Visualizes contact angles with arcs and tangent lines

2. **Tangent Method**
   - `calculate_tangent_contact_angles()`: Calculates contact angles using tangent method
   - Fits tangents to droplet contour at contact points
   - Handles both vertical and non-vertical tangents

3. **Ellipse Fitting**
   - `calculate_ellipse_contact_angle()`: Fits an ellipse to droplet contour
   - `_fit_ellipse()`: Internal function for ellipse fitting
   - `_ellipse_slope()`: Calculates slope of ellipse at given angle
   - `_calculate_contact_angle()`: Converts slope to contact angle

4. **Polynomial Fitting**
   - `fit_left_polynomial()`: Fits polynomial to left contact angle region
   - `fit_right_polynomial()`: Fits polynomial to right contact angle region
   - `rotate_coordinates_90()`: Helper for coordinate transformation

**Key Functions**:

#### `calculate_contact_angles()`
Calculates contact angles using the arc method.

**Parameters**:
- `cols`: Image width
- `shifted_points`: Contour data points
- `shifted_x`, `shifted_y`: Contour x/y coordinates (not used by arc method but kept for API parity)
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

#### `calculate_tangent_contact_angles()`
Calculates contact angles using the tangent method.

**Parameters**:
- `cols`: Image width
- `shifted_points`: List of shifted contour points
- `shifted_x`, `shifted_y`: X/Y of shifted contour points
- `intersection_points`: Detected intersection points
- `y1_left`, `y1_right`: Baseline y-coordinates
- `img`: Processed image
- `filename`: Current image filename
- `output_path`: Output directory
- `advancing_contact_angles`, `receding_contact_angles`: Optional angle lists
- `q`: Current image index (default: 0)
- `result_images`: Optional dict to store visualization images
- `save_files`: Whether to save intermediate outputs

**Returns**:
- `tuple`: (advancing_angles, receding_angles, angle_img)

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

### `src/helpers/contact_detection.py`
**File Path**: `/src/helpers/contact_detection.py`

**Purpose**:
Helper module for detecting and visualizing contact points between droplets and vertical boundaries in the Droplet Wall Interaction Tool. Provides functionality to detect when a droplet makes contact with vertical boundaries and visualize these contact events.

**Key Functions**:

#### `detect_vertical_line_contact(contour, vertical_left, vertical_right, contact_threshold=3)`
Detects if a contour makes contact with vertical boundary lines.

**Parameters**:
- `contour`: The contour to check for contact (numpy array of points)
- `vertical_left`: Tuple of (x1, y1, x2, y2) for left boundary line
- `vertical_right`: Tuple of (x1, y1, x2, y2) for right boundary line
- `contact_threshold`: Distance threshold in pixels for contact detection (default: 3)

**Returns**:
- `tuple[bool, bool]`: (left_contact, right_contact) indicating contact with each boundary

#### `get_contact_frame_status(left_contact_frame, right_contact_frame)`
Generates a status string describing the current contact state.

**Parameters**:
- `left_contact_frame`: Frame number when left contact first occurred (None if not yet)
- `right_contact_frame`: Frame number when right contact first occurred (None if not yet)

**Returns**:
- `str`: Human-readable status string

#### `draw_contact_indicators(image, vertical_left, vertical_right, left_contact, right_contact, left_contact_frame=None, right_contact_frame=None, current_frame=0)`
Draws visual indicators for contact detection on an image.

**Parameters**:
- `image`: Image to draw on (numpy array)
- `vertical_left`: Left boundary line coordinates (x1, y1, x2, y2)
- `vertical_right`: Right boundary line coordinates (x1, y1, x2, y2)
- `left_contact`: Boolean indicating current left contact
- `right_contact`: Boolean indicating current right contact
- `left_contact_frame`: Frame number of first left contact (optional)
- `right_contact_frame`: Frame number of first right contact (optional)
- `current_frame`: Current frame number (default: 0)

**Returns**:
- Modified image with visual indicators

**Internal Helper Functions**:
- `_check_single_line_contact()`: Checks contact with a single vertical line
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
# Define boundary lines
left_line = (100, 0, 100, 480)   # x1, y1, x2, y2
right_line = (540, 0, 540, 480)  # x1, y1, x2, y2

# Detect contact
left_contact, right_contact = detect_vertical_line_contact(
    contour=droplet_contour,
    vertical_left=left_line,
    vertical_right=right_line,
    contact_threshold=3
)

# Update contact frame counters
if left_contact and left_contact_frame is None:
    left_contact_frame = current_frame
if right_contact and right_contact_frame is None:
    right_contact_frame = current_frame

# Draw indicators
frame = draw_contact_indicators(
    image=frame,
    vertical_left=left_line,
    vertical_right=right_line,
    left_contact=left_contact,
    right_contact=right_contact,
    left_contact_frame=left_contact_frame,
    right_contact_frame=right_contact_frame,
    current_frame=current_frame
)

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

### `src/helpers/contour.py`
**File Path**: `/src/helpers/contour.py`

**Purpose**:
Helper module for contour processing and analysis in the Droplet Wall Interaction Tool. Provides functionality for contour manipulation, filtering, and analysis with respect to baseline and boundaries.

**Key Functions**:

#### `calculate_drop_area(y1_left, y1_right, intersection_points, cnt, img, center_points_px, center_points_mm, q, result_images, result_lists, pixel)`
Processes drop area and calculates center point and other geometric properties.

**Parameters**:
- `y1_left`, `y1_right`: Y-coordinates of baseline edges
- `intersection_points`: Points where contour intersects with baseline
- `cnt`: Contour data
- `img`: Image for visualization
- `center_points_px`: List to store center points in pixels
- `center_points_mm`: List to store center points in millimeters
- `q`: Current frame index
- `result_images`: Dictionary to store result images
- `result_lists`: Dictionary to store analysis results
- `pixel`: Pixels per millimeter conversion factor

**Returns**:
- `tuple`: (center_point_px, center_point_mm)

#### `process_contour(contour, cnt_x, cnt_y, x_left_cnt, y_left_cnt, x_right_cnt, y_right_cnt, line_y, cnt_x_neu, cnt_y_neu, q=0)`
Processes contour to separate left and right sides and calculate mean X value.

**Parameters**:
- `contour`: Input contour array
- `cnt_x`, `cnt_y`: Lists to store contour coordinates
- `x_left_cnt`, `y_left_cnt`: Lists to store left contour points
- `x_right_cnt`, `y_right_cnt`: Lists to store right contour points
- `line_y`: Y-coordinate of baseline
- `cnt_x_neu`, `cnt_y_neu`: Lists to store processed contour points
- `q`: Current frame index (default: 0)

**Returns**:
- `tuple`: (x_mean, x_left_cnt, y_left_cnt, x_right_cnt, y_right_cnt)

#### `filter_contour_by_baseline_slope(contour, y1_left, y1_right)`
Filters contour to remove points below baseline slope.

**Parameters**:
- `contour`: Input contour to filter
- `y1_left`: Y-coordinate at left edge of baseline
- `y1_right`: Y-coordinate at right edge of baseline

**Returns**:
- `numpy.ndarray`: Filtered contour

#### `crop_contour_points(x_left, y_left, x_right, y_right, threshold_y)`
Crops contour points above a certain Y threshold.

**Parameters**:
- `x_left`, `y_left`: Left contour coordinates
- `x_right`, `y_right`: Right contour coordinates
- `threshold_y`: Y threshold for cropping

**Returns**:
- `tuple`: Cropped coordinates (x_left, y_left, x_right, y_right)

**Internal Helper Functions**:
- `_calculate_center_point()`: Calculates center point from contour moments
- `_visualize_center_point()`: Draws center point and baseline on image
- `_calculate_area_between_intersections()`: Calculates area between intersection points
- `_calculate_left_extension_area()`: Calculates left extension area
- `_calculate_right_extension_area()`: Calculates right extension area
- `_prepare_contour_points()`: Converts contour to standard format
- `_calculate_baseline_slope()`: Calculates baseline slope and parameters
- `_calculate_baseline_y()`: Calculates Y-coordinate on baseline for given X
- `_calculate_intersection_point()`: Finds intersection between line segment and baseline
- `_find_contour_baseline_intersections()`: Finds all intersections between contour and baseline
- `_create_filtered_contour()`: Creates filtered contour from segments above baseline

**Dependencies**:
- OpenCV for contour processing
- NumPy for numerical operations
- Custom logging utilities

**Integration**:
- Used by analysis pipeline for contour processing
- Integrates with contact angle calculation
- Works with visualization system
- Processes data for center point and area calculations

**Usage Example**:
```python
# Process contour and separate left/right sides
x_mean, x_left, y_left, x_right, y_right = process_contour(
    contour=contour,
    cnt_x=[],
    cnt_y=[],
    x_left_cnt=[],
    y_left_cnt=[],
    x_right_cnt=[],
    y_right_cnt=[],
    line_y=baseline_y,
    cnt_x_neu=[],
    cnt_y_neu=[]
)

# Filter contour using baseline slope
filtered_contour = filter_contour_by_baseline_slope(
    contour=contour,
    y1_left=left_y,
    y1_right=right_y
)

# Crop contour points above threshold
x_left, y_left, x_right, y_right = crop_contour_points(
    x_left=x_left,
    y_left=y_left,
    x_right=x_right,
    y_right=y_right,
    threshold_y=100
)
```

**Maintenance Notes**:
- Ensure proper handling of different contour formats
- Add validation for input parameters
- Document any changes to contour processing logic
- Optimize performance for real-time processing
- Add unit tests for different contour shapes and baselines

---

### `src/helpers/drawing.py`
**File Path**: `/src/helpers/drawing.py`

**Purpose**:
Helper module for drawing and visualization in the Droplet Wall Interaction Tool. Provides functions for rendering various visual elements like baselines, intersection points, connection lines, and interaction zones on images.

**Key Functions**:

#### `draw_dual_baselines(img, y1_left, y1_right, color1=(0, 255, 0), color2=(0, 0, 255), thickness=4)`
Draws two horizontal baselines on an image with optional outlines.

**Parameters**:
- `img`: Target image (numpy array)
- `y1_left`, `y1_right`: Y-coordinates for the left and right baselines
- `color1`, `color2`: BGR tuples for baseline colors (default: green and red)
- `thickness`: Line thickness in pixels (default: 4)

#### `draw_axis_line(img, y, color=(255, 255, 0), thickness=1)`
Draws a horizontal axis line at the specified y-coordinate.

**Parameters**:
- `img`: Target image (numpy array)
- `y`: Y-coordinate for the axis line
- `color`: BGR color tuple (default: cyan)
- `thickness`: Line thickness in pixels (default: 1)

#### `draw_intersection_points(img, points, y1_left, y1_right, mode="channel")`
Draws intersection points on the image, colored by proximity to baselines.

**Parameters**:
- `img`: Target image (numpy array)
- `points`: List of (x,y) intersection points
- `y1_left`, `y1_right`: Y-coordinates of the baselines
- `mode`: Drawing mode ("channel" or other)

**Returns**:
- `tuple`: (upper_points, lower_points) - Lists of points above and below the baseline

#### `draw_connection_line(img, p1, p2, color=(0, 255, 0), thickness=2)`
Draws a line connecting two points on the image.

**Parameters**:
- `img`: Target image (numpy array)
- `p1`, `p2`: (x,y) tuples for start and end points
- `color`: BGR color tuple (default: green)
- `thickness`: Line thickness in pixels (default: 2)

#### `draw_rectangle(img, x, y, w, h, color=(0, 0, 255), thickness=2)`
Draws a rectangle on the image.

**Parameters**:
- `img`: Target image (numpy array)
- `x`, `y`: Top-left corner of the rectangle
- `w`, `h`: Width and height of the rectangle
- `color`: BGR color tuple (default: red)
- `thickness`: Border thickness in pixels (default: 2)

#### `draw_center_point(img, cx, cy, color=(0, 0, 255), crosshair_size=20, thickness=2)`
Draws a center point with crosshairs on the image.

**Parameters**:
- `img`: Target image (numpy array)
- `cx`, `cy`: Center point coordinates
- `color`: BGR color tuple (default: red)
- `crosshair_size`: Size of the crosshair in pixels (default: 20)
- `thickness`: Line thickness in pixels (default: 2)

#### `highlight_interaction_zone(img, contour, y, zone=10, color=[0, 255, 255])`
Highlights the interaction zone around a specified y-coordinate.

**Parameters**:
- `img`: Target image (numpy array)
- `contour`: Contour to analyze
- `y`: Y-coordinate of the interaction zone
- `zone`: Vertical range around y to highlight (default: 10 pixels)
- `color`: BGR color tuple (default: yellow)

**Dependencies**:
- OpenCV for image drawing operations
- NumPy for numerical operations
- Custom logging utilities

**Integration**:
- Used by visualization components for rendering analysis results
- Integrates with the main application's display system
- Works with contour processing and analysis modules

**Usage Example**:
```python
# Draw dual baselines
draw_dual_baselines(
    img=frame,
    y1_left=baseline_y - 10,
    y1_right=baseline_y + 10,
    color1=(0, 255, 0),  # Green
    color2=(0, 0, 255)   # Red
)

# Draw intersection points
upper_pts, lower_pts = draw_intersection_points(
    img=frame,
    points=intersection_points,
    y1_left=baseline_y - 10,
    y1_right=baseline_y + 10,
    mode="channel"
)

# Draw center point with crosshairs
draw_center_point(
    img=frame,
    cx=center_x,
    cy=center_y,
    color=(0, 0, 255),  # Red
    crosshair_size=20,
    thickness=2
)

# Highlight interaction zone
highlight_interaction_zone(
    img=frame,
    contour=droplet_contour,
    y=interaction_y,
    zone=15,
    color=[0, 255, 255]  # Yellow
)
```

**Maintenance Notes**:
- Ensure proper handling of different image formats and color spaces
- Add input validation for coordinates and parameters
- Document any changes to drawing styles or visual elements
- Consider adding more visualization options if needed
- Optimize drawing performance for real-time display

---

### `src/helpers/initialisation.py`
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

### `src/helpers/intersection.py`
**File Path**: `/src/helpers/intersection.py`

**Purpose**:
Helper module for detecting and analyzing intersections between droplet contours and baselines in the Droplet Wall Interaction Tool. Provides functionality for finding intersection points, calculating tangent points, and analyzing droplet geometry.

**Key Functions**:

#### `find_intersection_points(y1_left, y1_right, src, threshold=50, q=0, contours=None, pixel=1.0)`
Finds intersection points between a baseline and droplet contours.

**Parameters**:
- `y1_left`: Y-coordinate of the left baseline point
- `y1_right`: Y-coordinate of the right baseline point
- `src`: Source image for processing
- `threshold`: Threshold value for image processing (default: 50)
- `q`: Quality parameter (default: 0)
- `contours`: Pre-detected contours (optional)
- `pixel`: Pixel scaling factor (default: 1.0)

**Returns**:
- `tuple`: (intersection_points, img, cnt, shifted_points, shifted_x, shifted_y)

**Internal Helper Functions**:

##### `_setup_intersection_analysis(src, y1_left, y1_right)`
Sets up the intersection analysis with input validation and baseline calculation.

##### `_get_or_detect_contours(src, contours, threshold, pixel)`
Retrieves existing contours or detects new ones from the image.

##### `_detect_contours_from_image(src, threshold, pixel)`
Detects and filters contours from the source image.

##### `_filter_contours_by_size(all_contours, pixel)`
Filters contours based on size constraints (1-7mm).

##### `_find_baseline_intersections(contours, baseline_y, vis_img)`
Finds intersection points between the largest contour and baseline.

##### `_find_intersection_coordinates(contour_points, baseline_y)`
Finds left and right intersection coordinates with the baseline.

##### `_process_baseline_proximity_points(near_baseline_points, contour_points, baseline_y)`
Processes points found near the baseline to determine intersections.

##### `_find_baseline_crossings(contour_points, baseline_y, left_x)`
Finds baseline crossings when only one proximity point exists.

##### `_fallback_intersection_method(contour_points, baseline_y)`
Fallback method that projects contour points onto the baseline.

##### `_create_intersection_points(left_x, right_x, baseline_y, vis_img)`
Creates and visualizes the final intersection points.

##### `_calculate_shifted_points(intersection_points, cnt, baseline_y, vis_img, w)`
Calculates shifted points for tangent line analysis.

##### `_calculate_shift_distance(cnt, baseline_y, point_index)`
Calculates the shift distance based on contour size.

##### `_find_best_shifted_x(contour_points, x, y_shifted, point_index, w)`
Finds the best x-coordinate for a shifted point.

##### `_interpolate_shifted_x(contour_points, x, y_shifted, point_index)`
Interpolates x-coordinate when no close contour point is found.

**Dependencies**:
- OpenCV for image processing and contour analysis
- NumPy for numerical operations
- Custom logging utilities

**Integration**:
- Used in the analysis pipeline for droplet geometry analysis
- Integrates with contour detection and processing modules
- Works with visualization components for result display

**Usage Example**:
```python
# Find intersection points between baseline and droplet
intersection_points, vis_img, contour, shifted_points, shifted_x, shifted_y = find_intersection_points(
    y1_left=baseline_y - 10,
    y1_right=baseline_y + 10,
    src=image,
    threshold=50,
    pixel=pixel_conversion
)

# Visualize results
cv2.circle(vis_img, (int(intersection_points[0][0]), int(intersection_points[0][1])), 5, (0, 255, 0), -1)  # Left point
cv2.circle(vis_img, (int(intersection_points[1][0]), int(intersection_points[1][1])), 5, (0, 255, 0), -1)  # Right point

# Draw shifted points for tangent analysis
for point in shifted_points:
    if point is not None:
        cv2.circle(vis_img, (int(point[0]), int(point[1])), 3, (255, 0, 0), -1)
```

**Details**:
- Valid contours filtered by width (1–7 mm using `pixel`).
- Baseline y is average of `y1_left` and `y1_right` and drawn on `vis_img`.
- If no near-baseline points, falls back to segment-crossing or projection methods.
- Shifted points are placed above the baseline with adaptive vertical offset; x chosen by nearest contour point or interpolation.

**Maintenance Notes**:
- Ensure robust handling of various contour shapes and sizes
- Add validation for input parameters
- Document any changes to intersection detection algorithms
- Consider adding support for non-horizontal baselines
- Optimize performance for real-time processing
- Add unit tests for different intersection scenarios

---

### `src/helpers/structured_packing.py`
**File Path**: `/src/helpers/structured_packing.py`

**Purpose**:
Helper module for detecting and analyzing structured packing in droplet interaction experiments. Provides functionality to identify vertical boundaries of packing material in images.

**Key Functions**:

#### `find_vertical_lines(image)`
Finds two vertical lines representing the edges of a structured packing in an image.

**Parameters**:
- `image`: Input image (numpy array) containing the packing material

**Returns**:
- `tuple`: ((x1_left, y1_left, x2_left, y2_left), (x1_right, y1_right, x2_right, y2_right))
  - Left and right vertical line coordinates as tuples of (x1, y1, x2, y2)
  - Returns (None, None) if no packing is detected

**Algorithm**:
1. Converts the image to grayscale if it's in color
2. Applies Gaussian blur to reduce noise
3. Uses binary thresholding to highlight dark packing against a white background
4. Finds contours of the packing material
5. Identifies the leftmost and rightmost points of the largest contour
6. Adds a 1-pixel offset to place lines just outside the packing
7. Returns vertical lines spanning the full height of the image

**Dependencies**:
- OpenCV for image processing
- NumPy for array operations
- Custom logging utilities

**Integration**:
- Used in the analysis pipeline for packing boundary detection
- Integrates with the main application's image processing workflow
- Works with visualization components for result display

**Usage Example**:
```python
# Load an image containing structured packing
image = cv2.imread("packing_image.jpg")

# Find vertical lines representing packing boundaries
left_line, right_line = find_vertical_lines(image)

if left_line is not None and right_line is not None:
    # Draw the detected lines on the image
    cv2.line(image, (left_line[0], left_line[1]), 
             (left_line[2], left_line[3]), (0, 255, 0), 2)
    cv2.line(image, (right_line[0], right_line[1]), 
             (right_line[2], right_line[3]), (0, 255, 0), 2)
    
    # Display the result
    cv2.imshow("Packing Boundaries", image)
    cv2.waitKey(0)
    cv2.destroyAllWindows()
else:
    print("No packing detected in the image")
```

**Maintenance Notes**:
- The function assumes the packing is darker than the background
- The 1-pixel offset places lines just outside the packing boundaries
- May need adjustment for different lighting conditions or packing materials
- Add validation for input image format and size
- Consider adding support for non-vertical packing boundaries
- Add unit tests with various packing images
- Document any changes to the detection algorithm
- Optimize performance for high-resolution images

---

### `src/helpers/preview.py`
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

### `src/helpers/save_results.py`
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

### `src/helpers/velocity.py`
**File Path**: `/src/helpers/velocity.py`

**Purpose**:
Helper module for calculating velocities of droplets from center point data in the Droplet Wall Interaction Tool. Handles various input formats and provides robust error handling for invalid data.

**Key Functions**:

#### `calculate_velocities(center_points_px, pixel=None, fps=None, time_values=None, velocities=None)`
Main function to calculate velocities from center point data.

**Parameters**:
- `center_points_px`: List of center points in pixels
- `pixel`: Pixels per mm conversion factor (default: 1.0)
- `fps`: Frames per second (used when time_values not provided)
- `time_values`: Optional list of timestamps for each frame
- `velocities`: Optional pre-existing velocity list to append to

**Returns**:
- List of velocities in mm/s

**Features**:
- Handles various input formats for center points
- Converts pixel coordinates to real-world units
- Supports both fixed FPS and custom time values
- Includes comprehensive input validation
- Gracefully handles missing or invalid data points

**Internal Helper Functions**:

##### `_validate_inputs(center_points_px, pixel, fps, time_values, velocities)`
Validates and prepares input parameters for velocity calculation.

##### `_normalize_points(center_points_px)`
Normalizes center points to ensure consistent format and handles invalid data.

##### `_calculate_point_velocity(prev_point, curr_point, pixel, time_diff)`
Calculates velocity between two consecutive points.

##### `_ensure_complete_velocity_list(velocities, target_length)`
Ensures the velocity list matches the required length.

**Dependencies**:
- NumPy for numerical operations
- Custom logging utilities

**Integration**:
- Works with the main analysis pipeline
- Processes data from contour detection
- Provides input for trajectory analysis

**Usage Example**:
```python
# Example usage of calculate_velocities
import numpy as np

# Sample center points (x, y) in pixels
center_points = [(i, i**2) for i in range(100)]

# Calculate velocities with 100 pixels/mm and 30 fps
velocities = calculate_velocities(
    center_points_px=center_points,
    pixel=100.0,  # 100 pixels per mm
    fps=30.0      # 30 frames per second
)

# Print the first 5 velocity values
print(f"First 5 velocities: {velocities[:5]} mm/s")
```

**Maintenance Notes**:
- The function assumes linear motion between frames
- Add support for different motion models if needed
- Consider adding smoothing for noisy velocity data
- Add unit tests for edge cases and error conditions
- Document any changes to the velocity calculation algorithm
- Optimize for real-time processing if needed
- Consider adding support for 3D coordinates

---

## Threading Modules

### `src/threads.py`
**File Path**: `/src/threads.py`

**Purpose**:
Provides a QThread implementation for running image analysis operations in a background thread, allowing for responsive UI during processing.

**Key Classes**:

#### `AutomatisationThread(QThread)`
Thread for running automation tasks.

**Signals**:
- `prompt_signal(message)`: Emits status messages
- `progress_signal(progress)`: Emits progress updates

**Methods**:
- `run()`: Main thread execution method

#### `AnalysisThread(QThread)`
Thread class for running analysis operations asynchronously.

**Signals**:
- `progress_signal(progress, advancing_contact_angles, receding_contact_angles, center_points_px, result_images)`: Emitted during analysis to report progress (signature: float, list, list, list, dict)
- `finished_signal(results)`: Emitted when analysis completes successfully
- `error_signal(error_message)`: Emitted when an error occurs

**Key Methods**:
- `run()`: Main thread execution method
- `pause()`: Pause the analysis
- `resume()`: Resume a paused analysis
- `stop()`: Stop the analysis
- `_progress_callback()`: Internal callback for progress updates

**Usage Example**:
```python
# Create and start analysis thread
analysis_thread = AnalysisThread(
    controller=analysis_controller,
    save_files=True,
    preview_middle=True
)
analysis_thread.start()

# Connect signals
analysis_thread.progress_signal.connect(update_progress_ui)
analysis_thread.finished_signal.connect(handle_results)
analysis_thread.error_signal.connect(show_error)
```
Behavior:
 - Pause: waits between frames until resumed (thread sleeps to reduce CPU).
 - Stop: requests early termination after current frame; progress callback returns False to abort processing.

---

## Utilities Modules

This section documents the utility modules in the `src/utilities` directory that provide common functionality used throughout the application.

### `image.py`
**File Path**: `/src/utilities/image.py`

**Purpose**:
Comprehensive image processing utilities for the Droplet Wall Interaction Tool, including background creation, rotation, cropping, and video conversion.

**Key Functions**:
- `create_background_image()`: Creates a robust background image using multiple methods
- `rotate_image()`: Rotates images with proper handling of edges and corners
- `crop_image()`: Crops images using specified parameters
- `convert_videos_to_images()`: Converts video files to image sequences

**Features**:
- Support for various image formats and color spaces
- Advanced background calculation using median filtering
- Automatic handling of image orientation
- Batch processing of video files

**Dependencies**:
- OpenCV (cv2)
- NumPy
- Python standard libraries
- Custom utilities: `logging_manager.get_logger`

**Integration**:
- Used throughout the application for image manipulation
- Supports both single images and batch processing

---

### `logging_manager.py`
**File Path**: `/src/utilities/logging_manager.py`

**Purpose**:
Centralized logging management system for the Droplet Wall Interaction Tool, providing a unified interface for application logging.

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
from src.utilities.logging_manager import get_logger

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

### `overlays.py`
**File Path**: `/src/utilities/overlays.py`

**Purpose**:
Provides overlay widgets that enhance the user interface with additional functionality like logging and navigation.

**Key Components**:
- `SmoothOverlay`: Base class for animated overlays
- `LogOverlay`: Displays application logs with filtering
- `NavigationOverlay`: Provides navigation controls

**Features**:
- Smooth animations and transitions
- Customizable appearance
- Responsive layout
- Keyboard shortcuts

**Dependencies**:
- PySide6 for GUI components
- Custom utilities: `logging_manager.get_logger`

**Integration**:
- Used by the main application window
- Integrates with the logging system
- Provides user interface enhancements

---

### `roi.py`
**File Path**: `/src/utilities/roi.py`

**Purpose**:
Provides a graphical interface for selecting and manipulating regions of interest (ROI) in images. This module is essential for defining analysis areas in the Droplet Wall Interaction Tool.

**Key Components**:

#### `ROISelector` Class
A dialog for interactive ROI selection on images with rotation support.

**Key Features**:
- Interactive ROI selection with click-and-drag interface
- Support for image rotation before selection
- Real-time visual feedback during selection
- Coordinate conversion between display and image space
- Responsive layout that adapts to screen size

**Properties**:
- `image_path`: Path to the image for ROI selection
- `rotation_angle`: Current rotation angle of the image
- `current_selection`: Currently selected ROI as a QRect

**Signals**:
- `roi_selected`: Emitted when ROI selection is confirmed (left, top, right, bottom)

**Main Methods**:
- `set_roi(left, top, right, bottom)`: Programmatically set the ROI in image coordinates
- `load_and_rotate_image()`: Load and rotate the input image
- `auto_size_dialog()`: Adjust dialog size based on image and screen dimensions
- `update_display()`: Refresh the image display with current ROI
- `position_dialog_centered()`: Center the dialog on screen

**Dependencies**:
- OpenCV (cv2) for image processing
- PySide6 for GUI components
- NumPy for numerical operations
- Custom utilities: `image.rotate_image`, `logging_manager.get_logger`

**Usage Example**:
```python
# Create and show ROI selector
dialog = ROISelector(parent=main_window, image_path="image.png", rotation_angle=45)
dialog.roi_selected.connect(self.handle_roi_selected)
dialog.exec_()

def handle_roi_selected(self, left, top, right, bottom):
    print(f"Selected ROI: ({left}, {top}, {right}, {bottom})")
```

**Integration**:
- Used by analysis modules to define analysis regions
- Integrates with the main application's GUI components
- Works with the image processing pipeline for coordinate transformations

---

## Widgets Modules

This section documents the widget modules that provide the graphical user interface components for the Droplet Wall Interaction Tool. These widgets are built using PySide6 and follow the Model-View-Controller (MVC) pattern.

### `widgets.py`
**File Path**: `/src/widgets.py`

**Purpose**:
Provides the main analysis interface for processing and visualizing droplet interaction experiments.

**Key Components**:
- `AnalysisGUI`: Main analysis interface with image processing controls and visualization
- Interactive ROI (Region of Interest) selection
- Batch processing support for multiple experiments
- Real-time preview of analysis results

**Features**:
- Multiple analysis modes (free sedimentation, contact angle, etc.)
- Interactive parameter adjustment with live preview
- Frame-by-frame navigation
- Batch processing queue
- Result visualization with overlays

**Dependencies**:
- PySide6 for GUI components
- OpenCV for image processing
- NumPy for numerical operations
- Custom utilities: `image`, `roi`, `logging_manager`

**Integration**:
- Connects to analysis controller for processing
- Displays results from analysis threads
- Integrates with the main application window

**Signals**:
- Subscribes to `controller.image_processed(int, dict)` to update previews.
- Spawns `AnalysisThread` for preview/full runs and connects:
    - `progress_signal(float, list, list, list, dict)` → updates stats/preview
    - `finished_signal(tuple)` → saving and UI reset
    - `error_signal(str)` → error handling and UI reset
- `ROISelector` emits `roi_selected(left, top, right, bottom)` → `apply_selected_roi`.
- `BatchProcessingWorker` (helpers.batch) emits per-folder progress for the list view.

**Batch processing**:
- Controls: `Add Folders`, `Process All Folders`, `Pause/Resume`, `Stop`.
- List view with `FolderItemDelegate` renders per-folder progress bars and statuses.
- Uses a background worker (helpers.batch) to process folders sequentially.
- Updates `overall_progress` (0–100%) and `folder_counter` (e.g., "2/5 folders").

---