(plugin-traj_convert)=
# Convert

Convert molecular dynamics trajectory files between supported formats.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `traj_convert` |
| Menu path | Structure → Trajectory → **Convert** |
| Categories | Structure, Trajectory |
| Version | 1.0.0 |
| Surfaces | gui |
| State namespace | `traj_convert` |

## Parameters

Editable parameters exposed by the plugin's declarative (AutoForm) interface, grouped by panel.

### Input

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Input is a folder of PDBs | `use_folder` | bool |  |  | When on, every *.pdb file in the chosen folder is processed instead of a single trajectory file. |
| First frame | `first_frame` | int |  | 0 … 99999999 | First frame of the processed range. |
| Last frame | `last_frame` | int |  | -1 … 9999999 | Last frame of the processed range (-1 = all frames). |
| Stride | `stride` | int |  | 1 … 99999 | Write only every Nth frame to the output. |

### Output

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Filename | `filename` | str |  |  | Output base name; the extension below is appended. |
| Format | `ending` | choice |  | choices: `output_formats` | Output file extension / format. |
| Split into one file per frame | `split` | bool |  |  | Write each frame to its own {filename}_%08d{ending} file instead of one combined file. |

## Source

- Plugin package: `chisurf/plugins/traj/traj_convert/`
- Manifest: {src}`chisurf/plugins/traj/traj_convert/manifest.json`
- UI spec: {src}`chisurf/plugins/traj/traj_convert/convert_structures.view.json`
