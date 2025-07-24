---
title: 'Droplet Wall Interaction Tool: A Python Platform for Automated Droplet Experiments and Qualitative Image Analysis'
tags:
  - Python
  - laboratory automation
  - image analysis
  - droplet experiments
  - scientific software
  - contact angle measurement
authors:
  - name: Kristina Ulla Margareta Mielke
    # orcid: 0000-0000-0000-0000
    corresponding: true
    affiliation: 1
  - name: Arif Rasim Can
    corresponding: false
    affiliation: 1

affiliations:
 - name: Fluid Process Engineering (AVT.FVT), RWTH Aachen University
   index: 1
   ror: https://ror.org/04xfq0f34

date: 22 July 2025
bibliography: paper.bib
---

# Summary

Droplet Wall Interaction Tool is a research-oriented, Python-based platform for automated droplet experimentation, qualitative image analysis, and experiment planning. Designed for academic and scientific workflows, it provides a reproducible, extensible, and user-friendly environment for laboratory automation and data analysis. Droplet Wall Interaction Tool integrates hardware control (camera, pump, dosage), advanced image processing, and experiment planning tools within a modern PySide6 (Qt for Python) interface. Its modular architecture and batch processing capabilities enable high-throughput, reproducible experiments and facilitate rapid development of new workflows for surface science and fluid dynamics research.

# Statement of need

Automated droplet experimentation and qualitative image analysis are essential in surface science, microfluidics, and materials research. Existing tools often lack integration, reproducibility, or extensibility. Droplet Wall Interaction Tool addresses these gaps by providing:
- Unified control of experimental hardware (camera, pump, dosage) for streamlined workflows.
- Robust batch image analysis, including contact angle measurement, and velocity analysis.
- Interactive experiment planning, calculation, and export of experiment matrices.
- Visual and numeric interfaces for region-of-interest (ROI) selection and baseline adjustment.
- Real-time logging and status indicators for transparency and troubleshooting.

Droplet Wall Interaction Tool is designed for researchers who require a flexible, reproducible, and extensible platform for laboratory automation and qualitative analysis.

# Features and implementation

## Key Features
- **Controller Tab:** Integrates camera, pump, and dosage automation for experimental control.
- **Analysis Tab:** Batch image processing, contact angle measurement.
- **Table Tab:** Experiment planning, calculation, and CSV export of experiment matrices.
- **Visual ROI & Baseline:** Graphical and numeric interfaces for ROI selection and baseline adjustment.
- **Batch Processing:** Analysis of multiple datasets with progress visualization.
- **Wobble & Velocity Analysis:** Advanced tools for droplet dynamics and time-series analysis.
- **Log Overlay:** Real-time logging with error/warning indicators.
- **Manual Testing:** Includes curated test images for rapid validation.
- **Modern UI:** Built with PySide6 for cross-platform compatibility and performance.

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

The application is organized into core logic modules (`src/core/`), UI components (`src/widgets/`), helpers for image processing and analysis (`src/helpers/`), and utilities for hardware management and threading.

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
11. **Save Results & Create Plots:** Saves all results and generates plots/tables.

## Usage Example: Batch Analysis

1. Launch the application by running `python app.py` from the command line.
2. Navigate to the **Analysis** tab in the GUI.
3. For each experimental trial, ensure the data is organized in a separate folder containing either:
   - A video file (e.g., `trial1.mp4`), or
   - A sequence of images (e.g., `frame_001.jpg`, `frame_002.jpg`, etc.)
4. Add the trial folders to the analysis queue using the **Add Folder** button.
5. Adjust analysis parameters (ROI, threshold, baseline) as needed.
6. Use **Preview** to verify settings or **Full Analysis** to process all queued trials.
7. Results are automatically saved in structured subfolders within each trial directory.

# Citations

This work builds upon several key open-source libraries and tools:

- NumPy [@NumPy] for efficient numerical computations
- Pandas [@Pandas] for data manipulation and analysis
- SciPy [@SciPy] for scientific computing
- Pillow [@Pillow] for image processing
- OpenCV [@OpenCV] for image processing and computer vision
- Matplotlib [@Matplotlib] for plotting and visualization
- PySerial [@PySerial] for serial communication with hardware
- PySide6 [@PySide6] for the graphical user interface