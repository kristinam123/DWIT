# Droplet Wall Interaction Tool

<!-- Badges: Replace URLs with actual badge links as appropriate -->
[![JOSS](https://joss.theoj.org/papers/XX.XXXXX/joss.XXXXXXX/status.svg)](https://doi.org/XX.XXXXX/joss.XXXXXXX)
![Build Status](https://img.shields.io/badge/build-passing-brightgreen)
![Python Version](https://img.shields.io/badge/python-3.10%2B-blue)
![License](https://img.shields.io/badge/license-EPL%202.0-blue)

> Droplet Wall Interaction Tool (DWIT) is a research-oriented platform for automated droplet experimentation, qualitative image analysis, and experiment planning. Designed for academic and scientific workflows, it provides a reproducible, extensible, and user-friendly environment for laboratory automation and data analysis.

---



## Table of Contents
- [Features](#features)
- [Project Structure](#project-structure)
- [Screenshots](#screenshots)
- [Quick Start](#quick-start)
- [Usage Examples](#usage-examples)
- [Configuration](#configuration)
- [Troubleshooting](#troubleshooting)
- [Detailed Image Analysis Pipeline](#detailed-image-analysis-pipeline)
- [Contributing](#contributing)
- [Test Data and Usage](#test-data-and-usage)
- [License](#license)
- [Citation](#citation)
- [Contact](#contact)
- [Credits / Acknowledgments](#credits--acknowledgments)
---


<a name="features"></a>
## Features

- 🎛️ **Controller Tab:** Integrates camera, pump, and dosage automation for streamlined experimental control.
- 📊 **Analysis Tab:** Enables batch image processing, contact angle measurement.
- 📋 **Table Tab:** Facilitates experiment planning, calculation, and export of experiment matrices.
- 🖼️ **Visual ROI & Baseline:** Provides both graphical and numeric interfaces for region selection and baseline adjustment.
- 🗂️ **Batch Processing:** Supports analysis of multiple datasets with progress visualization.
- 📈 **Wobble & Velocity Analysis:** Advanced tools for droplet dynamics and time-series analysis.
- 📝 **Log Overlay:** Real-time logging of errors, warnings, and informational messages with status indicators.
- 🧪 **Manual Testing:** Includes curated test images for rapid validation and reproducibility.
- ⚡ **Modern UI:** Built with PySide6 (Qt for Python) for cross-platform compatibility and performance.

---


<a name="project-structure"></a>
## Project Structure

| Directory         | Purpose                                              |
|-------------------|------------------------------------------------------|
| `src/core/`       | Core business logic (cell, camera, analysis, etc.)   |
| `src/widgets/`    | Main UI components (cell, camera, analysis, etc.)    |
| `src/helpers/`    | Image processing, analysis, and data saving helpers  |
| `src/threads/`    | Background processing for UI responsiveness          |
| `src/utilities/`  | Utilities for port, ROI, and camera management       |
| `config/`         | Conversion tables and requirements                   |
| `test_data/`      | Test images organized by experiment type             |

---


<a name="screenshots"></a>
## Screenshots

<p align="center">
  <img src="resources/screenshots/Tab1_Controllers.png" alt="Controller Tab UI" width="400"/>
  <br><em>Controller Tab: Unified control for hardware automation.</em>
</p>

<p align="center">
  <img src="resources/screenshots/Tab2_Table.png" alt="Table Tab UI" width="400"/>
  <br><em>Table Tab: Experiment planning and matrix export.</em>
</p>

<p align="center">
  <img src="resources/screenshots/Tab3_Analysis.png" alt="Analysis Tab UI" width="400"/>
  <br><em>Analysis Tab: Batch image analysis and visualization.</em>
</p>

---


<a name="quick-start"></a>
## Quick Start

To install and launch Droplet Wall Interaction Tool (DWIT):

```sh
python -m venv venv
venv\Scripts\activate  # On Windows
# or
source venv/bin/activate  # On macOS/Linux
pip install -r config/requirements.txt
python app.py
```

Alternatively, double-click `DWIT.exe` (Windows, prebuilt) or run `app.py` from your IDE with the correct Python environment.

---


<a name="usage-examples"></a>
## Usage Examples

### Batch Analysis (UI-driven)

1. Organize experiment images in a folder (see `test_data/` for examples).
2. Launch DWIT and navigate to the **Analysis** tab.
3. Add or remove folders for batch processing as needed.
4. Adjust ROI, threshold, and baseline parameters.
5. Use **Preview** for a preliminary check, or **Full Analysis** for comprehensive processing.
6. Results (plots, tables) are saved in structured subfolders according to analysis mode.

### Logging & Troubleshooting

- All logs, warnings, and errors are displayed in the log overlay (bottom left).
- The log status indicator reflects error (red), warning (orange), or normal (green) states.
- Click the indicator to access the full log overlay and review details.

---


<a name="configuration"></a>
## Configuration

| Setting                | How to Change                | Default/Example                |
|------------------------|------------------------------|-------------------------------|
| Working Directory      | Set via UI in Controller Tab | (User-selected)                |
| ROI, Baseline, Params  | Set via UI in Analysis Tab   | (User-selected)                |
| Experiment Table       | Configure in Table Tab       | (User input, CSV export)       |
| Dependencies           | `config/requirements.txt`    | See file                       |
| Linting/Formatting     | `pyproject.toml`             | Ruff, Black-style, isort rules |

No environment variables or CLI flags are required.

---


<a name="troubleshooting"></a>
## Troubleshooting

**App will not start / missing DLL:**
- Ensure all dependencies are installed: `pip install -r config/requirements.txt`
- On Windows, use the provided `.exe` or activate your virtual environment.

**No images found / cannot select folder:**
- Remove default folders and add your own via the UI.
- Verify folder structure and permissions.

**Analysis results appear incorrect:**
- Use preview mode before full analysis.
- Confirm ROI, threshold, and baseline settings.
- Increase ROI if images are cropped too small.
- Lower threshold for dark images.
- Rotate images if detection fails.

**Log overlay shows errors:**
- Click the log indicator for details.
- Most issues are resolved by restarting the application or adjusting parameters.

**Output folder did not update:**
- Set the working directory in the Controller tab before starting analysis.

---


<a name="detailed-image-analysis-pipeline"></a>
## Detailed Image Analysis Pipeline

<p align="center">
  <img src="resources/screenshots/Flowchart_Analysis.png" alt="Image analysis pipeline flowchart" width="500"/>
  <br><em>Figure: Overview of the image analysis pipeline implemented in Droplet Wall Interaction Tool.</em>
</p>

---


<a name="contributing"></a>
## Contributing

We welcome academic and research contributions. To contribute:

1. Fork this repository or create a branch (GitLab).
2. Branch off `development` for your feature or fix.
3. Follow the style in `pyproject.toml` and use Ruff for linting and formatting:
   ```sh
   pip install ruff
   ruff check .
   ruff format .
   ```
4. Test manually with the application and `test_data/` images.
5. Submit a pull/merge request with a clear description of your changes.

**Development notes:**
- UI: `src/widgets/` | Core: `src/core/` | Helpers: `src/helpers/`
- Use absolute imports (e.g., `from src.core.cell_core import ...`)
- Update documentation if you add features.

---


<a name="test-data-and-usage"></a>
## Test Data and Usage

The application includes sample test datasets that are loaded by default on first launch. These are located in `resources/test_data/` and include various test cases for different analysis modes.

### Running an Analysis

1. **Organize your data**:
   - Create a folder for each experimental trial
   - Each folder should contain either:
     - A single video file (e.g., `trial1.mp4`), or
     - A sequence of images (e.g., `frame_001.jpg`, `frame_002.jpg`, etc.)

2. **Launch the application**:
   ```sh
   python app.py
   ```
   - The application will start with the Controller tab active
   - Test datasets will be loaded automatically on first run

3. **Run an analysis**:
   - Navigate to the **Analysis** tab
   - Use **Add Folder** to select your trial folder(s)
   - Adjust analysis parameters as needed
   - Click **Preview** to verify settings
   - Click **Full Analysis** to process all queued trials
   - Results are saved in structured subfolders within each trial directory
2. For subsequent use, you can add the test folders from `resources/test_data/` in the Analysis tab
3. The test data includes sample images with known expected results for validation

---


<a name="license"></a>
## License

This project is licensed under the Eclipse Public License 2.0 (EPL-2.0). See [LICENSE](LICENSE) for details.

---


<a name="citation"></a>
## Citation

If you use Droplet Wall Interaction Tool in your research, please cite it as:

```
@software{droplet_wall_interaction_tool_2025,
  title = {Droplet Wall Interaction Tool: A Python Platform for Automated Droplet Experiments and Qualitative Image Analysis},
  author = {Mielke, Kristina Ulla Margareta and Can, Arif Rasim},
  year = {2025},
  publisher = {Journal of Open Source Software},
  doi = {XX.XXXXX/joss.XXXXXXX},
  url = {https://doi.org/XX.XXXXX/joss.XXXXXXX}
}
```

---


<a name="contact"></a>
## Contact

- **GitLab:** [arraca22](https://git.rwth-aachen.de/arraca22)
- **GitHub:** [arraca22](https://github.com/arraca22)
- For questions, open an issue or reach out via GitLab.

---


<a name="credits--acknowledgments"></a>
## Credits / Acknowledgments

This project makes use of the following open-source libraries:

- **PySide6**  
  Official Python bindings for Qt 6 (part of the Qt for Python project)  
  Copyright © The Qt Company  
  Licensed under LGPLv3  
  [Documentation](https://doc.qt.io/qtforpython-6/) | [License](https://www.gnu.org/licenses/lgpl-3.0.html)

- **NumPy**  
  Harris, Charles R., et al. "Array programming with NumPy." Nature 585, 357–362 (2020).  
  [License: CC BY 4.0](https://creativecommons.org/licenses/by/4.0)

- **Pandas**  
  The pandas development team. "pandas-dev/pandas: Pandas." Zenodo (2025).  
  [Zenodo](https://zenodo.org/) | [License: BSD]

- **SciPy**  
  Virtanen, Pauli, et al. "SciPy 1.0: fundamental algorithms for scientific computing in Python." Nat. Methods 17, 261–272 (2020).  
  [License: CC BY 4.0](https://creativecommons.org/licenses/by/4.0)

- **Pillow**  
  Murray, Andrew, et al. "python-pillow/Pillow: 11.3.0." Zenodo (2025).  
  [Pillow Docs](https://pillow.readthedocs.io/en/stable/releasenotes/11.3.0.html) | [License: HPND or PIL License]

- **OpenCV-Python**  
  Bradski, G. "The OpenCV Library." Dr. Dobb's Journal of Software Tools (2000).  
  [License: Apache 2.0 or BSD]

- **Matplotlib**  
  Hunter, J. D. "Matplotlib: A 2D graphics environment." Computing in Science & Engineering 9.3 (2007): 90-95.  
  [License: Matplotlib License (BSD-like)](https://matplotlib.org/stable/users/project/license.html)

- **XlsxWriter**  
  McNamara, John. "XlsxWriter: A Python module for creating Excel XLSX files." (2025).  
  [Docs](https://xlsxwriter.readthedocs.io/) | [License: BSD]

- **pySerial**  
  Liechti, Chris. "pySerial: Python serial port access library." (2020).  
  [GitHub](https://github.com/pyserial/pyserial) | [License: BSD]

Please refer to the respective project documentation for detailed license information.

A copy of the full LGPL v3 license is provided in this repository as LICENSES/LGPL-3.0.txt. If not present, you may obtain it at: https://www.gnu.org/licenses/lgpl-3.0.html