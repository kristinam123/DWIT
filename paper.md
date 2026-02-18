---
title: 'Droplet Wall Interaction Tool: A Python Platform for Droplet Experiments and Qualitative Image Analysis'
tags:
  - Python
  - laboratory automation
  - image analysis
  - droplet experiments
  - scientific software
  - droplet deformation
  - droplet movement
  - contact angle measurement
authors:
  - name: Kristina Mielke
    orcid: 0009-0009-9946-3315
    corresponding: true
    affiliation: "1"
  - name: Arif Rasim Can
    corresponding: false
    affiliation: "1"
  - name: Andreas Jupke
    orcid: 0000-0001-6551-5695
    corresponding: false
    affiliation: "1, 2"

affiliations:
 - name: Fluid Process Engineering (AVT.FVT), RWTH Aachen University, 52074 Aachen, Germany
   index: 1
   ror: https://ror.org/04xfq0f34
 - name: Institute for Bio- and Geosciences (IBG-2), Forschungszentrum Jülich GmbH, 52428 Jülich, Germany
   index: 2

date: 18 February 2026
bibliography: paper.bib
---

# Summary
TEST
Droplet Wall Interaction Tool is a research-oriented, Python-based platform for qualitative image analysis of droplet experiments. Designed for academic and scientific workflows, it emphasizes reproducible batch processing and workflow automation for image analysis rather than hardware control. It integrates advanced image processing within a modern PySide6 (Qt for Python) interface and builds on NumPy, SciPy, pandas, and OpenCV [@NumPy; @SciPy; @Pandas; @OpenCV; @PySide6]. Its modular architecture and batch processing capabilities enable high-throughput, reproducible analyses and facilitate rapid development of new workflows for surface science and fluid dynamics research.

# Statement of need

Automated droplet experimentation and qualitative image analysis are essential in surface science, microfluidics, and materials research. Existing tools often lack integration, reproducibility, or extensibility. Droplet Wall Interaction Tool addresses these gaps by providing:
- Robust batch image analysis, including contact angle measurement, droplet diameter calculation, and velocity analysis.
- Automated droplet characterization using equivalent diameter formula (D=√(4A/π)) and area measurements.
- Visual area representation through transparent overlays for immediate visual feedback.
- Visual ROI selection and baseline adjustment with both numeric and graphical controls.
- Visual and numeric interfaces for region-of-interest (ROI) selection and baseline adjustment.
- Real-time logging and status indicators for transparency and troubleshooting.
- Robust handling of open or incomplete contours through conservative estimation methods.

Droplet Wall Interaction Tool is designed for researchers who require a flexible, reproducible, and extensible platform for laboratory automation and qualitative analysis.

# Features and implementation

## Key Features
- **Analysis Tab:** Batch image processing, contact angle measurement, droplet area and diameter calculation.
- **Droplet Measurements:** Automatic calculation of droplet area and equivalent diameter using D=√(4A/π) formula.
- **Visual ROI & Baseline:** Graphical and numeric interfaces for ROI selection and baseline adjustment.
- **Batch Processing:** Analysis of multiple datasets with progress visualization.
- **Velocity Analysis:** Advanced tools for droplet dynamics and time-series analysis.
- **Log Overlay:** Real-time logging with error/warning indicators.
- **Manual Testing:** Includes curated test images for rapid validation.
- **Modern UI:** Built with PySide6 for cross-platform compatibility and performance.
 - **Modes:** free_sedimentation, contact_angle, channel, structured_packing (lazy-initialized in the app entrypoint).
 - **Channel mode note:** Automatic baseline detection is currently disabled; channel overlays/metrics require externally provided baselines.

## Architecture

Droplet Wall Interaction Tool follows a modular architecture:

```text
┌────────────┐      ┌────────────┐      ┌────────────┐
│   UI/Qt    │◀──▶ │   Core     │◀──▶ │  Helpers   │
│ (widgets)  │      │ (logic)    │      │ (analysis) │
└────────────┘      └────────────┘      └────────────┘
      │                  │                   │
      ▼                  ▼                   ▼
  Threads/Signals   Data/Params/State   Results/Exports
```

The application is organized into core logic (`src/core.py`), UI widgets (`src/gui.py` and `src/widgets/`), helpers for image processing and analysis (`src/helpers/`), utilities (`src/utilities/` for image processing, logging, overlays, ROI management), and background threading (`src/utilities/threading.py`).

## Image Analysis Pipeline

The image analysis pipeline is central to Droplet Wall Interaction Tool. It consists of:

1. **Crop and Rotate Image:** Preprocesses input images to ensure consistent ROI and orientation.
2. **Remove Background:** Enhances contrast and removes static artifacts.
3. **Detect Baselines:** Finds the baseline(s) where the droplet sits (mode-dependent).
4. **Contour Measurements:** Detects droplet contour and computes geometric features.
5. **Process Intersection Points:** Finds where the contour intersects the baseline(s).
6. **Contact Line Values:** Calculates the length/position of the contact line.
7. **Contact Angle:** Computes advancing/receding contact angles.
8. **Vertical Lines:** Detects vertical boundaries for wall contact analysis.
9. **Calculate Center Points:** Computes droplet center for velocity/tracking.
10. **Calculate Velocity:** Computes velocity from center point trajectory.
11. **Save Results (Excel):** Saves raw results to an Excel file with consistent formatting.
  - Implementation detail: per-frame overlays are saved under the selected folder; the Excel file is written to the same folder as `results_raw.xlsx`.

## Usage Example: Batch Analysis

1. Launch the application by running `python dwit.py`.
2. In the main window, open the **Analysis** tab.
3. For each experimental trial, ensure the data is organized in a separate folder containing either:
   - A video file (e.g., `trial1.mp4`), or
   - A sequence of images (e.g., `frame_001.jpg`, `frame_002.jpg`, etc.)
4. Add the trial folders to the analysis queue using the **Add Folder** button.
5. Adjust analysis parameters (ROI, threshold, baseline) as needed.
6. Use **Preview** to verify settings or **Full Analysis** to process all queued trials.
7. Per-frame overlays are saved to the selected folder. The raw-results Excel is saved to `<trial>/results_raw.xlsx`.

# Citations

This work builds upon several key open-source libraries and tools:

- NumPy [@NumPy] for efficient numerical computations
- Pandas [@Pandas] for data manipulation and analysis
- SciPy [@SciPy] for scientific computing
- OpenCV [@OpenCV] for image processing and computer vision
- PySide6 [@PySide6] for the graphical user interface
