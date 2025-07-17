# MesszelleApp Documentation

---

## Table of Contents

- [Getting Started](#getting-started)
- [Core Concepts & Architecture](#core-concepts--architecture)
- [Tutorials & Walkthroughs](#tutorials--walkthroughs)
- [UI Reference](#ui-reference)
- [API Reference (Internal)](#api-reference-internal)
- [Configuration & Deployment](#configuration--deployment)
- [Troubleshooting & FAQs](#troubleshooting--faqs)
- [Best Practices & Pro Tips](#best-practices--pro-tips)
- [Development Guide](#development-guide)
- [Credits & Contact](#credits--contact)

---

## Getting Started

### Prerequisites
- Python 3.x (Windows/macOS/Linux)
- [venv](https://docs.python.org/3/library/venv.html) for virtual environments

### Installation
```sh
python -m venv venv
venv\Scripts\activate  # On Windows
# or
source venv/bin/activate  # On macOS/Linux
pip install -r config/requirements.txt
```

### First Run
- **Windows:** Double-click `MesszelleApp.exe` (if available) for zero-setup.
- **Any OS:** `python app.py` (after activating your venv)

---

## Core Concepts & Architecture

### What is MesszelleApp?
MesszelleApp is a scientific tool for automating droplet experiments, image analysis, and experiment planning—built.

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


---


## 🧬 Detailed Image Analysis Pipeline (All Modes)

This section documents the **full image analysis pipeline** in MesszelleApp, including step-by-step explanations, mode-specific logic, and a clear flowchart. Each step is described with its purpose, inputs/outputs, and when it is executed. This is essential for debugging, extending, or understanding the analysis process.

---

### ⏩ **Processing Steps: Sequence, Explanations, and Mode Applicability**

| Step | Name | Purpose & Description | Inputs | Outputs | Modes | Notes |
|------|------|----------------------|--------|---------|-------|-------|
| 1 | **Crop and Rotate Image** | Preprocesses the raw input image: crops to ROI and applies rotation if needed. Ensures all downstream analysis uses a consistent, user-defined region and orientation. | Raw image, ROI, rotation angle | Preprocessed image | All | Always first; ensures correct geometry |
| 2 | **Remove Background** | Loads or computes a background image for subtraction or normalization. Used to enhance contrast and remove static artifacts. | Image(s), background config | Background image (or None) | All | May be skipped if not needed |
| 3 | **Detect Baselines** | Finds the baseline(s) where the droplet sits. For channel/contact angle: detects one or two baselines (e.g., top/bottom). For other modes, may be skipped. | Preprocessed image | Baseline positions (y1_left, y1_right, etc.) | Channel, Contact Angle | 🚫 Skipped for free sedimentation, structured packing |
| 4 | **Contour Measurements** | Detects the droplet contour, computes geometric features (area, bounding box, center). Foundation for all further analysis. | Image, baselines (if any) | Contour(s), center point, bounding box | All | Core measurement step |
| 5 | **Process Intersection Points** | Finds where the contour intersects the baseline(s). Used for contact angle and channel analysis. | Contour, baselines | Intersection points | Channel, Contact Angle | 🚫 Skipped for free sedimentation, structured packing |
| 6 | **Contact Line Values** | Calculates the length/position of the contact line (in px/mm) at the baseline. Key for wetting analysis. | Intersection points, pixel size | Contact line px/mm | Channel, Contact Angle | 🚫 Skipped for free sedimentation, structured packing |
| 7 | **Contact Angle** | Computes advancing/receding contact angles at the intersection points. May use arc, tangent, or other methods. | Contour, intersection points, baselines | Contact angles (left/right) | Channel, Contact Angle | 🚫 Skipped for free sedimentation, structured packing |
| 8 | **Vertical Lines** | Detects vertical boundaries (e.g., for structured packing). Used to check for wall contact and trigger special logic. | Image | Vertical line positions | Structured Packing | 🚫 Skipped for other modes |
| 9 | **Calculate Center Points** | Computes the droplet's center (in px/mm), used for velocity and tracking. | Contour | Center point | All | Used for velocity, plotting |
| 10 | **Calculate Velocity** | Computes velocity from center point trajectory. For structured packing: also computes discrete (jump) velocity between wall contacts. | Center points, frame index, pixel size, FPS | Velocity (continuous/discrete) | All (discrete only for structured packing) | Discrete velocity: only for structured packing |
| 11 | **Save Results & Create Plots** | Saves all results (angles, positions, velocities, images) and generates plots/tables for user. | All previous outputs | Files, plots, tables | All | Always last |

---

### 🗂️ **Step-by-Step Explanations**

#### 1. Crop and Rotate Image
**Purpose:** Ensures only the region of interest (ROI) is analyzed, and that the image is correctly oriented. This is critical for reproducibility and accurate measurement.
**Inputs:** Raw image, user-defined ROI, rotation angle.
**Outputs:** Cropped and rotated image.
**Modes:** All.

#### 2. Remove Background
**Purpose:** Removes static background features, improves contrast, and normalizes lighting. May use the first image as background or a computed background from a set.
**Inputs:** Image(s), background config.
**Outputs:** Background image (or None).
**Modes:** All (may be skipped if not needed).

#### 3. Detect Baselines *(Channel, Contact Angle)*
**Purpose:** Finds the horizontal line(s) where the droplet sits. Used to anchor all further geometric analysis. Dual baselines for channel mode; single for contact angle.
**Inputs:** Preprocessed image.
**Outputs:** Baseline positions (y1_left, y1_right, etc.).
**Modes:** Channel, Contact Angle. 🚫 Skipped for free sedimentation, structured packing.

#### 4. Contour Measurements
**Purpose:** Finds the droplet's outline, computes area, bounding box, and center. All further analysis depends on this step.
**Inputs:** Image, baselines (if any).
**Outputs:** Contour(s), center point, bounding box.
**Modes:** All.

#### 5. Process Intersection Points *(Channel, Contact Angle)*
**Purpose:** Finds where the contour crosses the baseline(s). These points are used for contact angle and channel-specific calculations.
**Inputs:** Contour, baselines.
**Outputs:** Intersection points.
**Modes:** Channel, Contact Angle. 🚫 Skipped for free sedimentation, structured packing.

#### 6. Contact Line Values *(Channel, Contact Angle)*
**Purpose:** Measures the length and position of the contact line (where the droplet meets the baseline), in both pixels and mm. Used for wetting analysis.
**Inputs:** Intersection points, pixel size.
**Outputs:** Contact line length (px, mm).
**Modes:** Channel, Contact Angle. 🚫 Skipped for free sedimentation, structured packing.

#### 7. Contact Angle *(Channel, Contact Angle)*
**Purpose:** Calculates advancing and receding contact angles at the intersection points. May use arc, tangent, or other methods. Key for surface science.
**Inputs:** Contour, intersection points, baselines.
**Outputs:** Contact angles (left/right).
**Modes:** Channel, Contact Angle. 🚫 Skipped for free sedimentation, structured packing.

#### 8. Vertical Lines *(Structured Packing)*
**Purpose:** Detects vertical boundaries (e.g., walls or packing structures). Used to check for wall contact and trigger discrete velocity logic.
**Inputs:** Image.
**Outputs:** Vertical line positions.
**Modes:** Structured Packing only. 🚫 Skipped for other modes.

#### 9. Calculate Center Points
**Purpose:** Finds the droplet's center (in px and mm). Used for velocity calculation and plotting.
**Inputs:** Contour.
**Outputs:** Center point.
**Modes:** All.

#### 10. Calculate Velocity
**Purpose:** Computes the droplet's velocity from the center point trajectory. For structured packing, also computes discrete (jump) velocity between wall contacts.
**Inputs:** Center points, frame index, pixel size, FPS.
**Outputs:** Velocity (continuous for all, discrete for structured packing).
**Modes:** All (discrete only for structured packing).

#### 11. Save Results & Create Plots
**Purpose:** Saves all computed results (angles, positions, velocities, images) and generates plots/tables for user review.
**Inputs:** All previous outputs.
**Outputs:** Files, plots, tables.
**Modes:** All.

---

## 🔀 **Full Pipeline Flowchart**

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
%%     L([Save Results & Create Plots])
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

![Flowchart](resources/screenshots/Flowchart_Analysis.png)

**Legend:**
- <span style="background-color:#ffd54f;color:#222;padding:2px 6px;border-radius:3px;">Channel/Contact Angle</span>: Steps E1, G1, H1, I1
- <span style="background-color:#81c784;color:#222;padding:2px 6px;border-radius:3px;">Structured Packing</span>: Step E2
- <span style="background-color:#64b5f6;color:#222;padding:2px 6px;border-radius:3px;">Free Sedimentation/Structured Packing</span>: Steps E3, G2
- <span style="background-color:#b0bec5;color:#222;padding:2px 6px;border-radius:3px;">All Modes</span>: Steps B, C, F, J, K, L

---

### 📝 **Summary Table: Step Applicability by Mode**

| Step | Free Sedimentation | Contact Angle | Channel | Structured Packing |
|------|:-----------------:|:-------------:|:-------:|:------------------:|
| Crop & Rotate Image | ✅ | ✅ | ✅ | ✅ |
| Remove Background | ✅ | ✅ | ✅ | ✅ |
| Detect Baselines | 🚫 | ✅ | ✅ | 🚫 |
| Contour Measurements | ✅ | ✅ | ✅ | ✅ |
| Process Intersection Points | 🚫 | ✅ | ✅ | 🚫 |
| Contact Line Values | 🚫 | ✅ | ✅ | 🚫 |
| Contact Angle | 🚫 | ✅ | ✅ | 🚫 |
| Vertical Lines | 🚫 | 🚫 | 🚫 | ✅ |
| Calculate Center Points | ✅ | ✅ | ✅ | ✅ |
| Calculate Velocity | ✅ | ✅ | ✅ | ✅ (discrete only) |
| Save Results & Plots | ✅ | ✅ | ✅ | ✅ |

---

## 📌 **How to Debug or Extend the Pipeline**

- **Check mode logic:** Many steps are conditional on the selected analysis mode. Always verify which steps are executed for your mode.
- **Intermediate results:** Each step produces outputs that are used by later steps. If a result is missing, check the previous step.
- **Error handling:** If a step fails (e.g., no contour found), downstream steps may be skipped or produce NaN/None results.
- **Extending:** To add a new measurement, insert it after the relevant step and update both the code and this documentation.

---

**For further details, see the code in `src/core/analysis_core.py` and related helpers.**

---

### Graph Generation Workflow

`core.process(data, mode)` → returns a structured result with all necessary fields.

`widget.render(processedData, mode)` → draws graph with the right layers, titles, controls, and any mode-specific annotations.

---

**UI:** All main UI in `src/widgets/` (Controller, Analysis, Table, etc.)

**Core:** Business logic in `src/core/` (cell, camera, analysis, table, pump, dosage)

**Helpers:** Image processing, analysis, and saving in `src/helpers/`

**Threads:** Background processing in `src/threads/` (keeps UI responsive)

**Utilities:** Port, ROI, camera helpers in `src/utilities/`

**Config/data:** Conversion tables, requirements in `config/`

**Test images:** Provided in `test_data/` (organized by experiment type)

---

## Tutorials & Walkthroughs

### Hello, World! (Batch Analysis)
1. Place your experiment images in a folder (or use `test_data/` samples).
2. Start MesszelleApp and open the **Analysis** tab.
3. Add or remove folders for batch processing.
4. Adjust ROI, threshold, and baseline as needed.
5. Click **Preview** for a quick check, or **Full Analysis** to process all images.
6. Results (plots, tables) are saved in the output directory.

### Advanced: Multi-Folder Batch & Custom ROI
1. Queue multiple folders in the Analysis tab.
2. Use the context menu to preview, analyze, or set main folder.
3. Use drag-and-drop or numeric input for ROI selection.
4. Use the log overlay to monitor progress and errors.

### Pro Tip
> Use the log overlay (bottom left) to catch errors and warnings in real time. Click the indicator for full details.

---

## Configuration & Deployment

| Setting                | How to Change                | Default/Example                |
|------------------------|------------------------------|-------------------------------|
| Working Directory      | Set via UI in Controller Tab | (User-selected)                |
| ROI, Baseline, Params  | Set via UI in Analysis Tab   | (User-selected)                |
| Experiment Table       | Configure in Table Tab       | (User input, CSV export)       |
| Dependencies           | `config/requirements.txt`    | See file                       |
| Linting/Formatting     | `pyproject.toml`             | Ruff, Black-style, isort rules |

**No environment variables, CLI flags, or config files required.**

### Building the Executable
```sh
python build_exe.py
# Output: dist/MesszelleApp.exe
```

---

## Best Practices & Pro Tips

✅ **Always use a virtual environment** to avoid dependency conflicts.

✅ **Keep dependencies up to date**—check `config/requirements.txt` regularly.

✅ **Use test images in `test_data/`** to validate your setup before real experiments.

✅ **Check the log overlay** for errors/warnings after every run.

⚠️ **Watchout:** Always set the working directory before running automation or analysis.


⚠️ **Watchout:** Remove default folders and add your own for custom analysis.

---

## Development Guide

### Workflow
1. Fork or branch (GitLab) from `development`.
2. Create a feature/fix branch.
3. Code—follow style in `pyproject.toml` and use Ruff:
    ```sh
    pip install ruff
    ruff check .
    ruff format .
    ```
4. Test manually with the app and `test_data/` images.
5. PR/MR: Submit a pull/merge request with a clear description.

### Coding Conventions
- Double quotes, 88-char lines, spaces for indent, LF endings (see `pyproject.toml`)
- Absolute imports within `src/` (e.g., `from src.core.cell_core import ...`)
- Docstrings required for all public functions/classes
- Use try/except for hardware/IO; log errors, don’t crash UI
- Qt signal/slot for UI updates and thread communication

---

## Credits & Contact


MesszelleApp is developed and maintained by the team at RWTH AVT.FVT.

- **GitLab:** [arraca22](https://git.rwth-aachen.de/arraca22)
- For questions, open an issue or reach out via GitLab.

---

# Core Module Reference

## `analysis_core.py`

**Role:**  
Implements the main analysis logic for droplet and experiment image analysis. Handles image processing, baseline/contact detection, contour analysis, result calculation, and saving. Manages analysis modes (e.g., contact angle, free sedimentation, structured packing, channel), settings, and batch processing.

**Key Class:**  
- `AnalysisCore(QObject)`:  
    - **Purpose:** Central class for all analysis operations.  
    - **Inputs:**  
        - `folder_path` (optional): Path to images for analysis  
        - `analysis_mode`: Mode string (e.g., "contact_angle", "free_sedimentation")  
    - **Outputs:**  
        - Emits Qt signals for UI updates, errors, and progress  
        - Returns structured results (angles, velocities, dimensions, etc.)  
    - **Side Effects:**  
        - Reads/writes settings via QSettings  
        - Saves results to disk  
        - Creates output folders  
        - Logs errors/warnings  
    - **Edge Cases:**  
        - Handles missing/invalid folders, special characters in paths  
        - Defensive against missing/corrupt images  
        - Mode-specific logic for baseline/contact detection  
        - Handles both images and videos (extracts frames)  
        - Skips/continues on errors, logs but does not crash UI  
    - **Notable Methods:**  
        - `process_images`: Main entry for batch/preview analysis  
        - `_main`: Orchestrates the full analysis pipeline  
        - `_detect_baselines`, `_detect_single_baseline`, `_detect_structured_packing_lines`: Mode-specific baseline/contact detection  
        - `_process_all_images`, `_process_single_file`: Per-image processing  
        - `_finalize_results`: Calculates velocities, saves results  
        - Many setters/getters for analysis parameters, all with Qt signals and settings persistence

**Constants:**  
- `headers`: List of result column names  
- `image_extensions`: Supported image file types

**Assumptions:**  
- Images are organized in folders, filenames encode experiment parameters  
- Settings are persisted per analysis mode  
- Results are saved in an "Output" subfolder

**Non-obvious:**  
- Handles both images and videos (auto-extracts frames)  
- Preloads images for small datasets for speed  
- Mode-specific logic for baseline/contact/contour  
- Emits signals for UI reactivity

---

## `camera_core.py`

**Role:**  
Handles camera hardware integration, live feed, recording, and image acquisition. Manages camera settings, ROI, and threading for non-blocking UI.

**Key Class:**  
- `CameraCore(QObject)`:  
    - **Purpose:** Controls camera hardware, manages live/recording threads, and image acquisition.  
    - **Inputs:**  
        - Camera parameters (exposure, FPS, period, ROI)  
        - User actions (start/stop live, record, change ROI)  
    - **Outputs:**  
        - Emits Qt signals for image updates, errors, and state changes  
        - Provides images as PIL objects  
    - **Side Effects:**  
        - Interacts with hardware via XsCamera SDK  
        - Reads/writes settings  
        - Saves images to disk  
        - Logs errors/warnings  
    - **Edge Cases:**  
        - Handles missing camera, hardware errors, invalid ROI  
        - Defensive against thread errors, ensures cleanup  
        - Validates image data shape/type  
    - **Notable Methods:**  
        - `initialize_camera`: Loads SDK, enumerates and opens camera  
        - `start_live`/`stop_live`: Manages live feed thread  
        - `start_record`/`stop_record`: Manages recording thread  
        - `save_images`: Saves acquired images to disk  
        - `_process_image_data`: Converts raw data to PIL images  
        - `close`: Ensures all resources are released

**Constants:**  
- Camera parameter limits (exposure, FPS, ROI, etc.)  
- `DEFAULT_RECORD_SECONDS`, `DEFAULT_SAVE_FOLDER`, `CAMERA_LIB_PATH`

**Assumptions:**  
- Only one camera is used at a time  
- Camera SDK is available and compatible  
- Threading is used for UI responsiveness

**Non-obvious:**  
- Handles both 8/16/24-bit images  
- Uses custom thread classes for live/record  
- Emits signals for UI reactivity

---

## `cell_core.py`

**Role:**  
Coordinates the overall experiment automation, including camera, pump, dosage, and table. Manages experiment state, parameters, and automation threads.

**Key Class:**  
- `CellCore(QObject)`:  
    - **Purpose:** Orchestrates experiment runs, manages state, and automates multi-step procedures.  
    - **Inputs:**  
        - Experiment table (from TableCore)  
        - User actions (start/stop automation, select folder)  
    - **Outputs:**  
        - Emits Qt signals for prompts, progress, errors, and status  
        - Updates UI components (camera, pump, dosage, table)  
    - **Side Effects:**  
        - Reads/writes settings  
        - Controls hardware via GUI references  
        - Runs automation in a background thread  
        - Logs errors/warnings  
    - **Edge Cases:**  
        - Handles user cancellation, missing table, hardware errors  
        - Waits for user acknowledgment on parameter changes  
        - Defensive against missing/invalid experiment parameters  
    - **Notable Methods:**  
        - `run_cell`: Runs a single experiment trial (controls pump, camera, dosage)  
        - `start_automation`/`stop_automation`: Manages automation thread  
        - `_prepare_experiment_table`, `_update_experiment_parameters`: Table management  
        - `_wait_for_dosage_initialization`, `_wait_for_user_acknowledgment`: Ensures readiness  
        - `_automatisation`: Main automation loop (called by thread)

**Constants:**  
- `TIME_TO_STABILIZE_FLOW`, `TIME_AFTER_INJECTION`

**Assumptions:**  
- All hardware GUIs are set before automation  
- Table is loaded and valid  
- User can interrupt at any time

**Non-obvious:**  
- Tracks both current and previous experiment parameters for change detection  
- Waits for user input if angle/cannula changes  
- Handles flushing logic based on flow/angle

---

## `dosage_core.py`

**Role:**  
Controls the dosage system via serial communication. Manages port selection, command sending, and value persistence.

**Key Class:**  
- `DosageCore(QObject)`:  
    - **Purpose:** Handles all communication with the dosage hardware (serial), manages steps/time, and port usage.  
    - **Inputs:**  
        - Steps, time, port selection  
        - User actions (initialize, refill, stroke, resolution)  
    - **Outputs:**  
        - Emits Qt signals for value changes, errors, and status  
        - Returns responses from hardware  
    - **Side Effects:**  
        - Reads/writes settings  
        - Registers/unregisters ports with shared manager  
        - Logs errors/warnings  
    - **Edge Cases:**  
        - Handles port conflicts, serial errors, missing port  
        - Defensive against invalid values  
    - **Notable Methods:**  
        - `initialise`: Initializes the dosage system  
        - `refill`: Refills the system  
        - `stroke`: Performs a stroke operation  
        - `resolution`: Sets device resolution  
        - `set_port`, `close_port`: Manages port usage

**Constants:**  
- `BAUD_RATE`, `TIMEOUT`, `DEFAULT_STEPS`, `COMPONENT_NAME`

**Assumptions:**  
- Only one component uses a port at a time  
- Serial settings are fixed (baud, parity, etc.)

**Non-obvious:**  
- Uses a shared port manager to avoid conflicts  
- All commands are sent as strings with specific protocol

---

## `pump_core.py`

**Role:**  
Controls the pump hardware via serial communication. Handles port management, setpoint conversion, and command sending.

**Key Class:**  
- `PumpCore(QObject)`:  
    - **Purpose:** Manages pump setpoint, port selection, and serial communication.  
    - **Inputs:**  
        - Setpoint (user or pump value), port selection  
        - User actions (write setpoint, close port)  
    - **Outputs:**  
        - Emits Qt signals for port/status/errors  
        - Returns success/failure for commands  
    - **Side Effects:**  
        - Reads/writes settings  
        - Registers/unregisters ports  
        - Logs errors/warnings  
    - **Edge Cases:**  
        - Handles port conflicts, serial errors, invalid setpoints  
        - Defensive against missing port or invalid values  
    - **Notable Methods:**  
        - `write_setpoint`: Converts and sends setpoint to pump  
        - `convert_user_setpoint_to_pump_value`: Maps user value (L/h) to pump value (0-255)  
        - `set_port`, `close_port`: Manages port usage

**Constants:**  
- `MAX_PUMP_VALUE`, `MAX_USER_VALUE`, `COMPONENT_NAME`

**Assumptions:**  
- Only one component uses a port at a time  
- Setpoint is always in range 0-88 (user) or 0-255 (pump)

**Non-obvious:**  
- Uses a shared port manager to avoid conflicts  
- Converts user-friendly flow rates to hardware values

---

## `table_core.py`

**Role:**  
Manages experiment table data, parameter calculation, and conversion table lookup. Handles experiment planning and parameter generation.

**Key Class:**  
- `TableCore(QObject)`:  
    - **Purpose:** Generates experiment tables, manages parameters, and looks up conversion data.  
    - **Inputs:**  
        - Substance, droplet diameters, counter flows, tilts, trials  
        - User actions (set parameters, process data)  
    - **Outputs:**  
        - Emits Qt signals for parameter changes, errors, and status  
        - Provides experiment table as a list of dicts  
    - **Side Effects:**  
        - Reads/writes settings  
        - Loads conversion table from JSON  
        - Logs errors/warnings  
    - **Edge Cases:**  
        - Handles missing/invalid conversion table  
        - Defensive against invalid input values  
    - **Notable Methods:**  
        - `process_data`: Generates all experiment combinations  
        - `find_closest_setpoint`: Looks up best match in conversion table  
        - `load_conversion_table`: Loads JSON data  
        - `convert_counter_flow`: Converts flow units

**Assumptions:**  
- Conversion table JSON is present and valid  
- All parameters are provided as comma-separated strings

**Non-obvious:**  
- Sorts results by droplet size, tilt, and flow  
- Handles fallback/default values for first-time users

---

## Credits & Contact

MesszelleApp is developed and maintained by the team at RWTH AVT.FVT.


---

# Helper Module Reference

## `area_calculation.py`

**Role:**
Area calculation utilities for droplet analysis. This module is currently a placeholder and **not implemented**. It is intended to restore the green pixel-based area calculation functionality from the old `drop_area.py`, which is critical for accurate droplet area measurements.

**Key Functions (to be implemented):**
- `calculate_green_pixel_area(img, intersection_points, cnt, y1_left, y1_right, pixel_conversion=None)`: Main function for area calculation using green pixel detection.
- `extract_green_pixels(img)`: Extracts green pixels using BGR thresholds.
- `calculate_green_center(green_pixels)`: Finds the center of green pixels.
- `accumulate_distance_area(cnt, intersection_points, line_y, superhydrophobic=True)`: Sums vertical distances for area calculation.
- `apply_conversion_factors(sum_distance_y)`: Converts pixel area to mm² and μm².

**Constants:**
- Green pixel thresholds: lower=[0,100,0], upper=[50,255,50] (BGR)
- Conversion: 1 pixel = 187.1424 μm², 0.0001871424 mm²

**Edge Cases:**
- Superhydrophobic extension: ±50px beyond intersection points
- Handles missing/invalid images and contours

**Status:**
Not implemented; area calculations will be inaccurate until restored.

---

## `baseline.py`

**Role:**
Baseline detection utilities for droplet and experiment analysis. Provides robust, multi-strategy baseline detection for both single and dual baseline scenarios, with support for manual override.

**Key Functions:**
- `find_single_baseline(image, baseline_offset=0, baseline_tf=False, manual_offset=0)`: Detects the baseline (where the droplet sits) using edge detection, Hough transform, and fallback to manual offset.
- `find_dual_baseline(middle_src, baseline_offset=0, baseline_tf=False, manual_offset=0)`: Finds baselines in both upper and lower regions (for channel mode), using axisymmetric axis detection.
- `_find_axisymmetric_axis_channel(image)`: Identifies the horizontal axis dividing the channel for dual baseline detection.

**Edge Cases:**
- Handles missing/invalid images, fallback to image center if detection fails
- Supports both automatic and manual baseline selection

**Side Effects:**
- Uses OpenCV for image processing
- Logs errors and warnings

---

## `batch.py`

**Role:**
Batch processing utilities for folder-based analysis. Provides a Qt delegate for folder progress visualization and a worker for batch processing of multiple folders, with progress, error, and preview image signals.

**Key Classes:**
- `FolderItemDelegate(QStyledItemDelegate)`: Renders folder items with progress bars and highlights the main folder.
- `BatchProcessingWorker(QObject)`: Processes multiple folders in a batch, emits progress, completion, error, and preview signals, and supports pause/resume/stop.

**Signals:**
- `progress_updated`, `folder_completed`, `all_completed`, `error_occurred`, `overall_progress_updated`, `preview_image_updated`

**Edge Cases:**
- Handles user pause/stop, errors in folder/image processing, and UI updates
- Defensive against missing folders or controller errors

---

## `contact_angle.py`

**Role:**
Contact angle calculation utilities. Implements multiple methods (arc, tangent, ellipse, polynomial) for contact angle measurement, with method selection and fallback logic. Handles visualization and edge-case logic for research-grade wetting analysis.

**Key Functions:**
- `calculate_contact_angles(...)`: Main entry for arc method (default), with detailed handling of intersection, tangent, and baseline logic.
- `calculate_tangent_contact_angles(...)`: Implements the tangent method for contact angle calculation.
- `calculate_ellipse_contact_angle(...)`, `fit_left_polynomial(...)`, `fit_right_polynomial(...)`: Ellipse and polynomial fitting methods.
- Many internal helpers for slope, angle, and visualization.

**Constants:**
- `RADIUS`: Arc radius for visualization

**Edge Cases:**
- Handles missing/invalid baselines, contours, or intersection points
- Supports fallback between methods and logs warnings for invalid data
- Handles superhydrophobic/hydrophilic scenarios and movement pattern analysis

---

## `contact_detection.py`

**Role:**
Contact detection utilities for droplet analysis. Detects whether a droplet contour makes contact with vertical lines (e.g., channel or packing boundaries) and provides status reporting and visualization.

**Key Functions:**
- `detect_vertical_line_contact(contour, vertical_left, vertical_right, contact_threshold=3)`: Checks for contact with left/right vertical lines.
- `draw_contact_indicators(image, vertical_left, vertical_right, left_contact, right_contact, ...)`: Draws visual indicators for contact status.
- `get_contact_frame_status(left_contact_frame, right_contact_frame)`: Returns a status string for display.

**Edge Cases:**
- Handles missing/invalid contours, lines, or images
- Defensive against errors in drawing or contact logic

**Side Effects:**
- Uses OpenCV for drawing
- Logs errors and warnings

---

## `contour.py`

**Role:**
Contour analysis and filtering utilities. Provides functions for center point calculation, area visualization, extension area, and filtering contours by baseline slope. Handles both visualization and (partially) area measurement.

**Key Functions:**
- `process_contour(...)`: Processes contour to extract left/right points and mean X.
- `filter_contour_by_baseline_slope(contour, y1_left, y1_right)`: Filters contour to remove points below the baseline.
- Many internal helpers for intersection, baseline, and cropping logic.

**Edge Cases:**
- Handles missing/invalid contours, baselines, or images
- Defensive against edge cases in contour format
- Fallbacks for free sedimentation mode (no baseline)

---

## `drawing.py`

**Role:**
Drawing utilities for experiment visualization. Provides functions to draw baselines, intersection points, rectangles, center points, and highlight interaction zones on images.

**Key Functions:**
- `draw_dual_baselines(img, y1_left, y1_right, ...)`: Draws two horizontal baselines.
- `draw_axis_line(img, y, ...)`: Draws a horizontal axis line.
- `draw_intersection_points(img, points, y1_left, y1_right, mode)`: Draws intersection points, colored by proximity.
- `draw_connection_line`, `draw_rectangle`, `draw_center_point`, `highlight_interaction_zone`: Various drawing helpers.

**Edge Cases:**
- Handles missing/invalid images or points
- Defensive against drawing errors

**Side Effects:**
- Uses OpenCV for all drawing
- Logs errors and warnings

---

## `initialisation.py`

**Role:**
Experiment and application initialization utilities. Handles image loading, path validation, and result list initialization for analysis runs.

**Key Functions:**
- `start_run(img_names, q, save_files, folder_path)`: Loads a single image and initializes lists for analysis.
- `initiate_run(files, save_files, folder_path, fps)`: Initializes the angle measurement program, result lists, and background image.
- Internal helpers for path validation and timestamp calculation.

**Edge Cases:**
- Handles missing/invalid images, paths, or indices
- Defensive against file not found, type errors, and OpenCV load failures

**Side Effects:**
- Uses OpenCV for image loading
- Logs errors and warnings

---

## `intersection.py`

**Role:**
Intersection and geometry utilities for contour analysis. Finds intersection points between baselines and droplet contours, detects and filters contours, and calculates shifted points for tangent analysis.

**Key Functions:**
- `find_intersection_points(y1_left, y1_right, src, threshold=50, q=0, contours=None, pixel=1.0)`: Main entry for intersection analysis.
- Internal helpers for contour detection, filtering, and intersection logic.

**Edge Cases:**
- Handles missing/invalid images, baselines, or contours
- Defensive against empty or malformed data
- Fallbacks for intersection detection if no points are found

**Side Effects:**
- Uses OpenCV for all image processing
- Logs errors and warnings

---

## `packing.py`

**Role:**
Packing utilities for droplet and experiment analysis. Detects vertical lines representing the edges of structured packing in images.

**Key Functions:**
- `find_vertical_lines(image)`: Finds left/right vertical lines at the edges of the detected packing object.

**Edge Cases:**
- Handles missing/invalid images or contours
- Defensive against no contours found

**Side Effects:**
- Uses OpenCV for image processing
- Logs errors and warnings

---

## `preview.py`

**Role:**
Preview utilities for displaying images and analysis results. Provides a click-through, see-through preview dialog for images, with auto-close and instant update features.

**Key Functions:**
- `show_preview(image, parent)`: Shows a preview dialog for a given image, centered and scaled to the screen.
- Internal helpers for pixmap conversion, screen detection, scaling, and dialog management.

**Edge Cases:**
- Handles missing/invalid images or parent widgets
- Defensive against screen geometry errors

**Side Effects:**
- Uses PySide6 and OpenCV for image display
- Logs errors and warnings

---

## `save_results.py`

**Role:**
Result saving utilities for exporting experiment data. Handles saving results as Excel files, generating plots, and performing wobble analysis (oscillation of drops).

**Key Functions:**
- `save_results(output_dir, times, result_lists)`: Main entry for saving results, plots, and Excel exports.
- Internal helpers for data extraction, filtering, plotting, and Excel writing.
- `_analyze_wobble(...)`: Analyzes drop oscillation and fits damped sine waves.

**Edge Cases:**
- Handles missing/invalid data, directories, or file permissions
- Defensive against plotting or Excel errors

**Side Effects:**
- Uses matplotlib, pandas, xlsxwriter, and OpenCV
- Logs errors and warnings

---

## `velocity.py`

**Role:**
Velocity calculation utilities for experiment analysis. Calculates velocities from center points, with robust input validation and normalization.

**Key Functions:**
- `calculate_velocities(center_points_px, pixel=None, fps=None, time_values=None, velocities=None)`: Main entry for velocity calculation.
- Internal helpers for input validation, normalization, and velocity computation.

**Edge Cases:**
- Handles missing/invalid points, pixel/fps values, or time arrays
- Defensive against NaN/None values and division by zero

**Side Effects:**
- Uses numpy for calculations
- Logs errors and warnings

---

# Main Module Reference

## `analysis.py`

**Role:**
Main application window for experiment analysis. Integrates the analysis core logic with the GUI, providing a complete interface for analyzing droplet contact angles and related experiments.

**Key Class:**
- `AnalysisWindow(QWidget)`: Main widget for analysis mode.
    - **Inputs:**
        - `parent`: Optional parent widget
        - `folder_path`: Path to images for analysis (optional)
        - `analysis_mode`: Analysis mode string (e.g., "contact_angle")
    - **Outputs:**
        - Embeds the `AnalysisGUI` and connects to `AnalysisCore`
        - Sets up the main layout and window title
    - **Side Effects:**
        - Logs initialization, errors, and path extraction
        - Handles path extraction from various object types
    - **Edge Cases:**
        - Handles invalid/missing folder paths
        - Defensive against initialization errors (logs and raises)

---

## `camera.py`

**Role:**
Main application window for camera control. Connects the camera core logic to the GUI, providing a user interface for live view, recording, and camera settings.

**Key Class:**
- `CameraWindow(QWidget)`: Main widget for camera control.
    - **Inputs:**
        - `parent`: Optional parent widget
    - **Outputs:**
        - Embeds the `CameraGUI` and connects to `CameraCore`
        - Sets up the main layout and window title
    - **Side Effects:**
        - Logs initialization and errors
        - Handles camera resource cleanup on close
    - **Edge Cases:**
        - Handles errors in camera initialization or GUI creation
        - Ensures camera is closed on window close

---

## `cell.py`

**Role:**
Main application window for cell (experiment automation) control. Integrates the cell core logic and GUI, orchestrating experiment runs and hardware control.

**Key Class:**
- `CellWindow(QMainWindow)`: Main window for experiment automation.
    - **Inputs:**
        - No arguments (standalone main window)
    - **Outputs:**
        - Embeds the `CellGUI` and connects to `CellCore`
        - Sets up the main layout and window title
        - Sets application icon if available
    - **Side Effects:**
        - Logs initialization, icon search, and errors
        - Searches for icon in multiple locations
    - **Edge Cases:**
        - Handles missing icon gracefully
        - Defensive against errors in controller/GUI creation

---

## `dosage.py`

**Role:**
Main application window for dosage control. Connects the dosage core logic to the GUI, providing a user interface for controlling the dosage hardware.

**Key Class:**
- `DosageWindow(QMainWindow)`: Main window for dosage control.
    - **Inputs:**
        - `parent`: Optional parent widget
    - **Outputs:**
        - Embeds the `DosageGUI` and connects to `DosageCore`
        - Sets up the main layout and window title
    - **Side Effects:**
        - Logs initialization and errors
    - **Edge Cases:**
        - Handles errors in controller/GUI creation

---

## `pump.py`

**Role:**
Main application window for pump control. Connects the pump core logic to the GUI, providing a user interface for controlling the pump hardware.

**Key Class:**
- `PumpWindow(QMainWindow)`: Main window for pump control.
    - **Inputs:**
        - `parent`: Optional parent widget
    - **Outputs:**
        - Embeds the `PumpGUI` and connects to `PumpCore`
        - Sets up the main layout and window title
    - **Side Effects:**
        - Logs initialization and errors
    - **Edge Cases:**
        - Handles errors in controller/GUI creation

---

## `table.py`

**Role:**
Main application window for experiment table management. Connects the table core logic to the GUI, providing a user interface for planning and managing experiment tables.

**Key Class:**
- `TableWindow(QMainWindow)`: Main window for table management.
    - **Inputs:**
        - `parent`: Optional parent widget
    - **Outputs:**
        - Embeds the `TableGUI` and connects to `TableCore`
        - Sets up the main layout and window title
        - Loads saved data and updates the UI after initialization
    - **Side Effects:**
        - Logs initialization, data loading, and errors
        - Uses a QTimer to load data after UI setup
    - **Edge Cases:**
        - Handles missing/invalid data gracefully
        - Defensive against errors in controller/GUI creation or data loading

# Threads Module Reference

## `analysis_threads.py`

**Role:**
Thread for running analysis operations in a separate QThread. Handles image analysis in a background thread, emitting progress, finished, and error signals for UI updates.

**Key Class:**
- `AnalysisThread(QThread)`: Runs analysis logic in the background.
    - **Inputs:**
        - `controller`: Analysis controller object
        - `save_files`, `preview_middle`, `use_first_as_background`: Analysis options
    - **Outputs:**
        - Emits `progress_signal`, `finished_signal`, and `error_signal` for UI
    - **Side Effects:**
        - Updates controller parameters before running
        - Handles pause/resume/stop state
    - **Edge Cases:**
        - Defensive against errors in analysis logic (logs and emits error)

---

## `camera_threads.py`

**Role:**
Camera threading utilities for image acquisition. Provides threads for live camera feed and recording, with a helper for thread-safe stop requests.

**Key Classes:**
- `StoppableThread(QObject)`: Helper for thread stop/clear/is_stop_requested with mutex protection.
- `LiveFeedThread(QThread)`: Runs the live camera feed loop in a thread.
- `RecordingThread(QThread)`: Runs the camera recording loop in a thread.
    - **Inputs:**
        - `camera_core`: Camera core logic object
    - **Outputs:**
        - Calls camera core's live/record feed loops
    - **Side Effects:**
        - Logs thread start/stop and errors
    - **Edge Cases:**
        - Defensive against errors in camera core logic
        - Thread stop is checked via `StoppableThread`

---

## `cell_threads.py`

**Role:**
Cell threading utilities for automation and experiment control. Provides a custom QThread for experiment automation and a thread-safe stop event.

**Key Classes:**
- `AutomatisationThread(QThread)`: Handles experiment automation in a thread, emits prompt and progress signals.
- `StopEvent(QObject)`: Thread-safe event for stopping threads, with wait/clear/set/is_set methods.
    - **Inputs:**
        - `controller`: Cell core logic object
    - **Outputs:**
        - Emits `prompt_signal` and `progress_signal` for UI
    - **Side Effects:**
        - Logs thread start, completion, and errors
    - **Edge Cases:**
        - Defensive against errors in automation logic
        - StopEvent uses mutex and wait condition for thread safety

---

## `dosage_threads.py`

**Role:**
Dosage threading utilities for automated injection and refill. Provides a QThread for handling dosage button actions (init, refill, inject) in the GUI.

**Key Class:**
- `DosageButtonThread(QThread)`: Handles dosage button actions in a thread, emits finished and steps_left_update signals.
    - **Inputs:**
        - `controller`: Dosage core logic object
        - `button_type`: Action type ("Init.", "Refill", "Inject")
        - `steps_value`, `time_value`: Parameters for injection
    - **Outputs:**
        - Emits `finished` and `steps_left_update` signals for UI
    - **Side Effects:**
        - Logs thread start, completion, and errors
    - **Edge Cases:**
        - Handles errors in dosage logic and parameter validation
        - Defensive against unknown button types and injection errors

# Utilities Module Reference

## `conversion.py`
**Purpose:**  
Provides robust utilities for converting lists of mixed-type values to floats, handling non-numeric values gracefully and logging conversion issues.

**Key Functions:**
- `convert_to_float_list(values: list[Any]) -> list[float]`  
  Converts a list of values to floats, replacing non-numeric or nested lists with `NaN`.  
  - **Inputs:** `values` (list of any type)  
  - **Outputs:** List of floats (non-numeric entries become `NaN`)  
  - **Side Effects:** Logs warnings for conversion failures and info on conversion summary.

---

## `image.py`
**Purpose:**  
Image processing utilities for experiment analysis, including background image creation, rotation, cropping, and video-to-image conversion.

**Key Functions:**
- `create_background_image(...)`  
  Builds a background image from a set of images, with options for rotation, cropping, and using the first image or a median of several.
- `rotate_image(image, angle)`  
  Rotates an image by a specified angle, expanding the canvas to avoid clipping.
- `crop_image(image, crop_params)`  
  Crops an image to user-specified dimensions, with boundary checks.
- `convert_videos_to_images(folder_path, progress_callback=None, use_simple_method=False)`  
  Converts all video files in a folder to image sequences, supporting both simple and advanced extraction methods.

**Side Effects:**  
Logs all major steps, errors, and warnings. Handles file I/O and OpenCV operations robustly.

---

## `logging_manager.py`
**Purpose:**  
Centralized logging system for the entire application, routing logs to both the terminal and a custom log overlay in the UI, with filtering and color coding.

**Key Classes/Functions:**
- `LoggingManager(QObject)`  
  Singleton managing log levels, filtering, and integration with the UI overlay. Emits signals for log level changes.
- `ColoredLogHandler(logging.Handler)`  
  Custom handler for sending formatted logs to the overlay.
- `TerminalStyleFormatter(logging.Formatter)`  
  Formats logs in a terminal-like style.
- `StdCapture`  
  Captures stdout/stderr and routes to logging.
- Utility functions: `get_logger`, `log_debug`, `log_info`, `log_warning`, `log_error`.

**Side Effects:**  
Replaces system stdout/stderr, manages log overlay, and persists filter settings via QSettings.

---

## `overlays.py`
**Purpose:**  
Provides improved overlay widgets for the UI, including animated log and navigation overlays that follow their parent windows and support filtering, color coding, and smooth transitions.

**Key Classes:**
- `SmoothOverlay(QFrame)`  
  Base class for overlays with smooth show/hide animations and geometry management.
- `LogOverlay(SmoothOverlay)`  
  Log overlay with filtering, color coding, and message buffering.
- `NavigationOverlay(SmoothOverlay)`  
  Overlay for navigation between main pages and analysis modes.

**Side Effects:**  
Directly manipulates UI elements, handles user interaction, and integrates with the logging manager.

---

## `port.py`
**Purpose:**  
Manages serial port enumeration and usage across the application, ensuring that ports are not double-assigned and providing signals for port status changes.

**Key Classes:**
- `SharedPortManager(QObject)`  
  Singleton tracking which ports are in use by which components, emitting signals on changes.
- `PortManager`  
  Enumerates available serial ports using `serial.tools.list_ports`.

**Side Effects:**  
Emits Qt signals, logs port usage, and handles hardware enumeration errors.

---

## `roi.py`
**Purpose:**  
Utilities for selecting and manipulating regions of interest (ROI) in images, including a dialog for user selection and conversion between display and image coordinates.

**Key Classes:**
- `ROISelector(QDialog)`  
  Dialog for interactive ROI selection on an image, supporting rotation and scaling.
- `RoiVar`  
  Simple variable class mimicking Tkinter-style variables for ROI dialog state.

**Side Effects:**  
Handles user interaction, emits signals, and updates the UI in real time.

---

## `XsCamera.py`
**Purpose:**  
Comprehensive Python wrapper for IDT (Integrated Design Tools) cameras, exposing the C SDK via ctypes. Handles camera enumeration, configuration, acquisition, and error management.

**Key Components:**
- **Constants and Enums:**  
  Defines all camera models, parameters, error codes, and configuration options as Python classes.
- **Data Structures:**  
  Maps C structs (e.g., `XS_ENUMITEM`, `XS_SETTINGS`, `XS_FRAME`) to Python classes for use with ctypes.
- **Error Handling:**  
  Custom exceptions for all camera error codes, with detailed mapping.
- **Core Functions:**  
  - `XsGetVersion()`, `XsLoadDriver()`, `XsEnumCameras()`, `XsOpenCamera()`, `XsCloseCamera()`, etc.
  - Camera configuration, parameter get/set, memory acquisition, and callback registration.

**Side Effects:**  
Directly interfaces with hardware via DLLs, raises exceptions on hardware errors, and logs all major operations.

---

**Note:**  
All utilities follow the application's logging and error handling conventions, use absolute imports, and are designed for robust integration with the PySide6 UI and experiment workflow.

---

# Widgets Module Reference

---

## `analysis_widgets.py`

**Purpose:**
Provides the main analysis GUI for experiment visualization, parameter configuration, batch processing, and preview/result display. Integrates with analysis threads, helpers, and core logic for interactive experiment analysis.

**Key Class:**
- `AnalysisGUI(QWidget)`
  - **Role:** Main widget for analysis mode. Handles UI layout, parameter controls, preview/result display, batch processing, and context-sensitive previews.
  - **Key Methods:**
    - `__init__(parent, controller)`: Initializes the widget, sets up UI, connects signals, and loads folder lists.
    - `create_widgets()`: Builds all UI components (action controls, parameter panels, preview/result area, stats section).
    - `main()`: Starts the main analysis thread for processing images/folders.
    - `preview()`: Starts a preview thread for quick parameter feedback.
    - `_trigger_preview_update(param_type)`: Debounces and triggers context-sensitive previews on parameter changes.
    - `_show_*_preview()`: Shows visual previews for ROI, threshold, rotation, and baseline adjustments.
    - `open_roi_selector()`: Opens a dialog for visual ROI selection on the middle image.
    - `apply_selected_roi(left, top, right, bottom)`: Applies selected ROI to controller and updates spinboxes.
    - `display_image_in_canvas(img, canvas)`: Converts and displays OpenCV images in Qt labels.
    - `_enable_buttons()/_handle_error()`: UI state management after thread completion or errors.
  - **Inputs/Outputs:**
    - Inputs: User actions (button clicks, parameter changes), controller state, image folders.
    - Outputs: Updates UI, triggers analysis/preview threads, saves results, shows previews.
  - **Side Effects:**
    - Starts/stops threads, updates controller state, logs errors, interacts with file system for image folders.
  - **Edge Cases:**
    - Handles missing/invalid folders, disables UI during processing, robust error handling/logging.

---

## `camera_widgets.py`

**Purpose:**
Implements the camera control GUI for live image acquisition, recording, and ROI selection. Integrates with the camera controller and provides real-time feedback and controls.

**Key Class:**
- `CameraGUI(QWidget)`
  - **Role:** Main camera interface. Provides live feed, recording controls, ROI selection, and camera parameter adjustment.
  - **Key Methods:**
    - `__init__(parent, controller)`: Initializes UI, loads icons, connects controller signals.
    - `_create_widgets()`: Builds the main layout, control panels, and preview area.
    - `display_image_on_canvas()`: Converts PIL images to QImage/QPixmap for display.
    - `toggle_live_feed()`, `toggle_recording()`: Start/stop live feed and recording.
    - `_on_fps_changed(value)`, `_on_exp_changed(value)`: Update camera parameters from UI.
    - `update_live_button_state(is_live)`, `update_record_button_state(is_recording)`: Update button icons based on state.
  - **Inputs/Outputs:**
    - Inputs: User button presses, controller signals, camera images.
    - Outputs: Updates UI, triggers camera actions, displays images.
  - **Side Effects:**
    - Changes camera state, updates controller, logs errors.
  - **Edge Cases:**
    - Handles missing images, invalid ROI, and fallback to standard icons if custom icons are missing.

---

## `cell_widgets.py`

**Purpose:**
Provides the main measurement cell GUI, integrating all major experiment controls (camera, pump, dosage, table, analysis) into a single interface. Manages navigation, overlays, and logging.

**Key Class:**
- `CellGUI(QWidget)`
  - **Role:** Main cell control interface. Hosts navigation, overlays, and all experiment/control pages.
  - **Key Methods:**
    - `__init__(parent, controller)`: Initializes overlays, connects logging, sets up widgets.
    - `_create_widgets()`: Builds main layout, content area, navigation, and bottom controls.
    - `_create_content_pages()`: Sets up stacked widget for all experiment/control pages.
    - `_init_*_page()`: Lazy-initializes each page (controllers, analysis modes, table).
    - `_show_terminal_overlay()`, `_update_log_status_indicator()`: Manages log overlay and status indicator.
    - `refresh_all_ports()`: Refreshes hardware ports in pump/dosage widgets.
    - `_change_page(index)`: Switches between content pages and saves state.
  - **Inputs/Outputs:**
    - Inputs: User navigation, controller signals, log events.
    - Outputs: Updates UI, overlays, and page content.
  - **Side Effects:**
    - Manages persistent settings (QSettings), updates overlays, logs errors.
  - **Edge Cases:**
    - Handles invalid page indices, missing data, and overlay visibility.

---

## `dosage_widgets.py`

**Purpose:**
Implements the dosage device control GUI, including port selection, initialization, injection/refill actions, and progress feedback. Integrates with threaded operations for responsive UI.

**Key Class:**
- `DosageGUI(QWidget)`
  - **Role:** Dosage control panel. Manages port selection, action buttons, progress, and parameter input.
  - **Key Methods:**
    - `__init__(parent, controller)`: Sets up UI, schedules port population, connects signals.
    - `_create_widgets()`: Builds layout, port selection, action buttons, and progress bar.
    - `refresh_ports()`, `refresh_ports_internal()`, `_populate_ports()`: Refreshes available COM ports.
    - `threaded_button(button_type)`: Starts threaded operation for actions (Init, Inject, Refill).
    - `_update_steps_left(value)`: Updates progress bar and label during operation.
    - `_on_button_operation_finished()`: Re-enables UI after thread completion.
  - **Inputs/Outputs:**
    - Inputs: User actions, controller state, available ports.
    - Outputs: Updates UI, triggers threaded actions, logs events.
  - **Side Effects:**
    - Starts/stops threads, updates controller, logs errors.
  - **Edge Cases:**
    - Handles missing/invalid ports, disables UI during operations, robust error handling.

---

## `pump_widgets.py`

**Purpose:**
Provides the pump control GUI, including port selection, flow rate input (L/h or Hz), unit conversion, and action buttons. Integrates with the pump controller and supports port refresh and error handling.

**Key Class:**
- `PumpGUI(QWidget)`
  - **Role:** Pump control panel. Manages port selection, flow rate input, unit switching, and action buttons.
  - **Key Methods:**
    - `__init__(parent, controller)`: Sets up UI, schedules port population.
    - `_setup_ui()`: Builds layout, port selection, unit selection, and flow rate input.
    - `refresh_ports()`, `refresh_ports_internal()`, `_populate_ports()`: Refreshes available COM ports.
    - `_on_unit_changed(checked)`: Handles unit switching and value conversion.
    - `update_setpoint()`: Applies flow rate to the pump.
    - `stop()`: Stops the pump (sets flow rate to zero).
  - **Inputs/Outputs:**
    - Inputs: User actions, controller state, available ports.
    - Outputs: Updates UI, triggers pump actions, logs events.
  - **Side Effects:**
    - Updates controller, logs errors, manages port state.
  - **Edge Cases:**
    - Handles missing/invalid ports, disables UI during operations, robust error handling.

---

## `table_widgets.py`

**Purpose:**
Implements the experiment configuration and results table GUI. Allows input of experiment parameters, displays generated configurations/results, and supports CSV export.

**Key Class:**
- `TableGUI(QWidget)`
  - **Role:** Table interface for experiment setup and results display. Manages parameter input, table update, and export.
  - **Key Methods:**
    - `__init__(parent, controller)`: Sets up UI, loads existing data if available.
    - `_create_widgets()`: Builds left (inputs) and right (results table) panels.
    - `update_table()`: Processes input data, updates the table, and handles validation/errors.
    - `export_results()`: Exports table results to CSV, handling locale and formatting.
  - **Inputs/Outputs:**
    - Inputs: User input fields, controller state, experiment results.
    - Outputs: Updates table, exports CSV, logs events.
  - **Side Effects:**
    - Reads/writes files, logs errors, shows dialogs for errors/exports.
  - **Edge Cases:**
    - Handles missing/invalid input, empty results, and locale-specific CSV formatting.

---

**Note:** All widgets follow the application's style and error handling conventions, use absolute imports, and integrate with the logging infrastructure. Signals/slots are used for UI updates and thread communication. Each widget is designed for modularity and reusability within the main application windows.