# TTTR Header Editor Plugin

View and edit the header tags of any time-tagged time-resolved (TTTR) file that
`tttrlib` can read — PicoQuant PTU and HT3, Becker&Hickl SPC, and Photon-HDF5.

## Features

- Open and inspect PTU, HT3, SPC and Photon-HDF5 files (container auto-detected)
- View all header tags and their values in a tabular format
- Edit existing tag values
- Add new custom tags to the header
- Remove unwanted tags
- Live read-only JSON view of the full header
- Save the edited header to a new PTU file, copying the source photon events verbatim

## Overview

TTTR files carry important experimental metadata in their headers. `tttrlib`
normalises every supported container into the same `{name, type, value, idx}` tag
list, so the editor reads them all through one code path and presents them in an
intuitive table. A JSON view mirrors the complete header structure live.

### Why the output is always PTU

Reading is format-agnostic, but writing is not: among the containers `tttrlib`
can write, only **PTU** persists arbitrary edited tags. The HT3 and SPC writers
regenerate a fixed binary header from their built-in fields and would silently
drop custom tags. To keep edits lossless, a header opened from any format is
saved as a PTU file; the photon events of the source are copied unchanged.

## Requirements

- `tttrlib`
- Qt (via `qtpy`) and the ChiSurf core modules

## Usage

1. Launch from the ChiSurf menu: **TTTR > TTTR Header editor** (or inside the
   **TTTR Tools** toolbox).
2. Open a file: click **📂 Open** (or drag-and-drop a file onto the table) and pick
   a PTU/HT3/SPC/HDF5 file. The status line shows the detected format and tag count.
3. View and edit tags: double-click a **Value** cell to edit it; pick the tag type
   from the **Type** combobox. Values are coerced to the type on edit.
4. Add a tag: click **➕ Add** and enter name, value and index.
5. Remove a tag: select a row and click **➖ Remove**.
6. Save: click **💾 Save as PTU** and choose a location. The `.ptu` extension is
   appended automatically.

## Applications

- Correcting metadata in experimental TTTR files
- Adding missing information to headers
- Standardising metadata across files and converting non-PTU sources to annotated PTU
- Preparing files for specialised analysis and troubleshooting metadata issues
- Educational use to understand TTTR file structure

## License

This plugin is part of the ChiSurf package and is distributed under the same license.

## Author

This plugin was created as part of the ChiSurf project.
