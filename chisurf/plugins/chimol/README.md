# Chimol (MolView) protein viewer

Chimol is the integrated ChiSurf 3D protein viewer (class name `MolView`).
It provides fast cartoon/backbone rendering, simple selections, and
sequence/structure synchronization inside the ChiSurf GUI or as a
standalone Qt application.

## Features

- Cartoon, trace, atoms, sticks, surface, and dots render modes with
  ambient occlusion and configurable profiles.
- Integrated sequence panel for residue selection, coloring, and alignment.
- Basic selections: click-pick residue/atom, rectangular drag-select.
- Trajectory support (mdtraj), MRC map loading, and RMF frame loading
  when optional dependencies are installed.
- Secondary-structure assignment using a lightweight DSSP-like algorithm
  (no external DSSP binary required).
- Runs inside ChiSurf or as a standalone Qt app (`python -m chisurf.plugins.chimol`).

## Quickstart (ChiSurf)

1. Launch ChiSurf and open **Plugins → Structure → Structure → ChiMOL**.
2. Click **Open** and choose a PDB/mmCIF/trajectory.
3. Toggle representations (Cartoon/Atoms/Sticks/Trace/Dots/Surface) from the toolbar.
4. Color by secondary structure or sequence gradient using the color buttons.
5. Use the sequence panel to select residues; selections sync to 3D.

## Quickstart (standalone)

```bash
python -m chisurf.plugins.chimol
```

## Dependencies

- Required: Python 3.9+, Qt (via `qtpy`), NumPy.
- Optional:
  - `mdtraj` for trajectory loading and DSSP comparison tests.
  - `PyOpenGL` for explicit GL entry points (QtGL renderer).
  - `numba` to speed up secondary-structure assignment (falls back to NumPy).
  - `IMP` (via `chisurf.fio.structure.coordinates`) for structure IO when available.

## Configuration

- Display parameters (cartoon thickness, colors, AO strength, etc.) are read from
  `chimol_display.json`. Preferred location: the ChiSurf settings directory
  (`chisurf.settings.get_path("settings")`). Fallback: a JSON file next to
  `config.py`. Legacy `molview_display.json` or `protview_display.json` filenames
  are also accepted for backward compatibility.

## Developer notes

- Tests live under `chisurf/plugins/chimol/tests/`. To run a quick subset:
  ```bash
  pytest chisurf/plugins/chimol/tests -k chimol
  ```
  The `mdtraj`-based DSSP comparison test is skipped automatically if `mdtraj`
  or an external DSSP binary is unavailable.
- Key modules:
  - `chimol/app/molview_main_window.py`: UI wiring (Qt docks, sequence, object list).
  - `chimol/renderer/wgpu_view.py`: the Qt viewport, drawn with WebGPU from the
    shared WGSL in `chimol/renderer/wgsl/`.
  - `chimol/geometry/cartoon.py`: cartoon geometry generation.
  - `chimol/config.py`: display configuration loading and defaults.
- For standalone development, ensure `QT_API` is set (e.g., `PySide6` or `PyQt5`).
- Keep user-visible strings using the Chimol name; class names remain `MolView`
  for API compatibility.

## Credits — what chimol was built by reading

Chimol is not an original design. It is a molecular viewer, and molecular
viewers are a solved problem with thirty years of accumulated decisions behind
them; the working rule here has been to **read the reference and transcribe**,
and to say so. Everything below was read from source, not merely admired.

### Molecular viewers

- **[PyMOL](https://github.com/schrodinger/pymol-open-source)** (Schrödinger,
  Inc.; open-source PyMOL licence) — the command language is PyMOL's. Command
  names, the selection-algebra grammar (`byres`, `within`, `expand`, the
  `and`/`or`/`not` precedence), the representation model, the settings system
  and the menu layout are transcribed from it. Where chimol deliberately
  differs, the difference is written down in
  [`okf/plugins/pymol-parity.md`](../../../okf/plugins/pymol-parity.md).
- **[ChimeraX](https://www.cgl.ucsf.edu/chimerax/)** (UCSF RBVI; free for
  academic use, source available) — read for its volume and surface code. Its
  fast-contour habits are in `chimol/geometry/marching_cubes.py` (grid read in
  its own precision; normals as the negated symmetric-difference gradient
  sampled only at surface vertices), and `smooth_vertices` is transcribed to
  NumPy as `chimol/geometry/refine.py::smooth_vertex_positions`, at the same
  defaults.

### Interface

- **[Dear ImGui](https://github.com/ocornut/imgui)** (Omar Cornut, MIT) —
  `chimol/renderer/ui/` is a port of its widget stack, one module per section
  of `imgui_widgets.cpp` and `imgui_tables.cpp`, with its `StyleColorsDark`
  palette. The controls are re-expressed as retained objects drawn through a
  six-operation painter, because chimol has no per-frame immediate-mode
  context; the behaviour, the layout arithmetic and the naming are the
  reference's.
- **[ImGuiColorTextEdit](https://github.com/goossens/ImGuiColorTextEdit)**
  (Johan A. Goossens, after Balázs Jákó and Santiago; MIT) —
  `chimol/renderer/ui/text_editor.py`. The colouriser state machine, the
  multi-cursor model, the transaction-based undo and the language definitions
  come from it; its keyword tables are extracted from the source rather than
  retyped, and a test re-extracts them to prove they have not drifted.
- **[imgui_club](https://github.com/ocornut/imgui_club)** (Omar Cornut, MIT) —
  `chimol/renderer/ui/memory_editor.py`, the hex view over host arrays and
  device buffers, from `imgui_memory_editor`. Its layout arithmetic, HexII
  compression and data-preview footer are transcribed.

### Porting another one

The data half of a port — enums, palettes, option structs, keyword tables — is
mechanical and is *not* to be typed by hand:

```bash
python -m build_tools.dev_utils.port_imgui_widget \
    junk/imgui/imgui_widgets.cpp --module knobs --class Knob \
    --origin "junk/imgui -- Dear ImGui, MIT"
```

It extracts them, emits the module skeleton with the four required docstring
sections, writes the recording-painter test, registers the module in
`CONTROL_MODULES`, and prints the public methods still to implement in source
order. `chimol/renderer/ui/control.py` supplies the contract the skeleton
subclasses, and `chimol/renderer/ui/qt_host.py` is what makes any of them
usable in a Qt form without a second implementation.

### Licences

Every reference above is MIT or an equivalently permissive licence except
ChimeraX, which was read but not transcribed from. Ported files name their
source in the module docstring; chimol itself is MIT (see `LICENSE`).
