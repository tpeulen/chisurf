# PTU ALEX Creator Plugin

This plugin provides a graphical interface for converting and processing Alternating Laser Excitation (ALEX) data in 
Time-Tagged Time-Resolved (TTTR) files.

## Features

- Loading and conversion of various TTTR file formats
- Automatic detection of input file formats
- Conversion of SM files to PTU format
- Application of ALEX period and shift parameters
- Visualization of microtime histograms
- Saving processed data as new PTU files
- Security features to prevent data corruption

## Overview

The ALEX PTU Creator plugin enables the conversion and processing of Alternating Laser Excitation (ALEX) data in 
Time-Tagged Time-Resolved (TTTR) files. ALEX is a powerful technique in fluorescence spectroscopy that alternates 
between different excitation wavelengths, allowing for improved discrimination between fluorescent species.

This plugin implements essential module operations on macro time stored in micro time, enabling ALEX data to be 
processed with the same pipelines as Pulsed Interleaved Excitation (PIE) data. By transforming the time information 
while preserving all event data, the plugin makes ALEX data compatible with PIE analysis workflows.

The intuitive graphical interface allows users to visualize the distribution of photons in the ALEX period and 
optimize ALEX period and shift parameters for specific experiments.

## Requirements

- Python packages:
  - PyQt5
  - pyqtgraph
  - numpy
  - tttrlib
  - chisurf core modules

## Usage

1. Launch the plugin from the ChiSurf menu: TTTR > ALEX Creator
2. Load a TTTR file:
   - Click "Load..." to browse for a file
   - Or drag and drop a file into the input field
   - The file format will be automatically detected
3. Configure ALEX parameters:
   - Set the ALEX Period value (default: 8000)
   - Adjust the Period Shift value if needed
   - The microtime histogram will update automatically
4. Save the processed file:
   - Select the desired output format (default: PTU)
   - Click "Save PTU..." to choose a save location
   - The processed file will be saved with "_alex" appended to the original filename

## Applications

The ALEX PTU Creator plugin can be used for:
- Converting between different TTTR file formats
- Preparing ALEX data for analysis with standard PIE analysis tools
- Visualizing the distribution of photons in the ALEX period
- Optimizing ALEX period and shift parameters for specific experiments
- Enabling advanced fluorescence analysis techniques like FRET and FCS with ALEX data

## License

This plugin is part of the ChiSurf package and is distributed under the same license.

## Author

This plugin was created as part of the ChiSurf project.

## Native EMTK

The manifest exposes `gui.app:make_app`. The native tool uses the same
Qt-free core/API as Qt for phase preview, single-file conversion, batch
conversion and merge. It adds native file/database pickers, asynchronous work,
queue context removal, help/guide, six-language labels/tooltips and saved
settings/dock layout. Remembered files are loaded explicitly.

`test/test_native.py` compares real photon arrays and header JSON against the
shared core/API. `test/native-parity.json` records screenshots and outstanding
verification limits. The current Qt plugin is an ALEX converter, not a
synthetic photon generation wizard or detector preset editor.
