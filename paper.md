---
title: 'Droplet Wall Interaction Tool: A Python Platform for Automated Droplet Experiments and Quantitative Image Analysis'
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

Droplet Wall Interaction Tool is a research-oriented, Python-based platform for automated droplet experimentation, quantitative image analysis, and experiment planning. Designed for academic and scientific workflows, it provides a reproducible, extensible, and user-friendly environment for laboratory automation and data analysis. Droplet Wall Interaction Tool integrates hardware control (camera, pump, dosage), advanced image processing, and experiment planning tools within a modern PySide6 (Qt for Python) interface. Its modular architecture and batch processing capabilities enable high-throughput, reproducible experiments and facilitate rapid development of new workflows for surface science and fluid dynamics research.

# Statement of need

Automated droplet experimentation and quantitative image analysis are essential in surface science, microfluidics, and materials research. Existing tools often lack integration, reproducibility, or extensibility. Droplet Wall Interaction Tool addresses these gaps by providing:
- Unified control of experimental hardware (camera, pump, dosage) for streamlined workflows.
- Robust batch image analysis, including contact angle measurement, droplet quantification, and velocity analysis.
- Interactive experiment planning, calculation, and export of experiment matrices.
- Visual and numeric interfaces for region-of-interest (ROI) selection and baseline adjustment.
- Real-time logging and status indicators for transparency and troubleshooting.

Droplet Wall Interaction Tool is designed for researchers, educators, and students who require a flexible, reproducible, and extensible platform for laboratory automation and quantitative analysis.

# Features and implementation

## Key Features
- **Controller Tab:** Integrates camera, pump, and dosage automation for experimental control.
- **Analysis Tab:** Batch image processing, contact angle measurement, and droplet quantification.
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

## Example: AnalysisCore Initialization

```python
from src.core.analysis_core import AnalysisCore

core = AnalysisCore(folder_path="test_data/", analysis_mode="contact_angle")
# Set parameters as needed, then run analysis pipeline
```

## Usage Example: Batch Analysis

1. Organize experiment images in a folder (see `test_data/`).
2. Launch Droplet Wall Interaction Tool and open the **Analysis** tab.
3. Add folders for batch processing, adjust ROI, threshold, and baseline.
4. Use **Preview** for a check, or **Full Analysis** for comprehensive processing.
5. Results are saved in structured subfolders according to analysis mode.

# Mathematics

# Citations

Citations to entries in paper.bib should be in APA-style, e.g., [@astropy], [@joss], etc.

# Figures

Figures can be included like this:
![Controller Tab UI.](resources/screenshots/Tab1_Controllers.png){ width=40% }

# Acknowledgements

We acknowledge contributions from all Droplet Wall Interaction Tool contributors and thank the open-source scientific Python community for foundational libraries. This work is inspired by the principles of open, reproducible science and supported by Fluid Process Engineering (AVT.FVT), RWTH Aachen University