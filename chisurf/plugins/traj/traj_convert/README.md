# Trajectory Converter Plugin

This plugin provides tools for converting molecular dynamics trajectory files between different formats.

## Features

- DCD and multi-model PDB output, as one file or one file per frame
- A frame range (first to last, inclusive) and a stride
- A folder of PDBs read as consecutive frames

## Overview

The Trajectory Converter plugin enables users to convert molecular dynamics trajectory files between different 
formats. This functionality is essential for working with trajectories from different simulation packages or for 
preparing data for specific analysis tools.

The plugin provides a user-friendly interface for selecting input files, specifying output formats, and configuring 
conversion parameters. Users can select specific frames or time ranges to extract from larger trajectories, filter 
specific atoms or residues of interest, and ensure that topology information is properly preserved during conversion.

By supporting a wide range of file formats, the plugin serves as a bridge between different molecular dynamics software 
packages, allowing researchers to leverage the strengths of multiple tools in their analysis workflows.

## Requirements

- ChiSurf's trajectory readers and writers (`chisurf.core.structure.trajectory_data`); no Qt for
  the emtk window (`app.py`), Qt only for the legacy AutoForm widget (`widget.py`).

## Usage

1. Open *Structure > Trajectory > Convert* (or the *Convert* panel of Traj Tools).
2. Choose the topology, the trajectory (or, with *Input is a folder of PDBs*, a folder) and the
   target folder (**…**, or drop files and folders).
3. Set *First frame*, *Last frame* (inclusive; −1 = the end) and *Stride*.
4. Set *Filename* and *Format* (`.dcd` or `.pdb`); tick *Split* for one file per frame.
5. Press **▶ Convert**; the log says how many frames or files were written.

**📖 Guide** walks through these steps; **❓ Help** has the details.

## Applications

The Trajectory Converter plugin can be used for:
- Converting trajectories between different molecular dynamics software formats
- Extracting specific portions of trajectories for focused analysis
- Preparing trajectories for visualization in different software packages
- Reducing file sizes by selecting only relevant atoms or frames
- Standardizing trajectory formats across a research project
- Creating input files for specialized analysis tools
- Archiving trajectories in preferred formats

## License

This plugin is part of the ChiSurf package and is distributed under the same license.

## Author

This plugin was created as part of the ChiSurf project.