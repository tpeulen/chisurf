# Chimol — a highly opinionated 3D viewer for ChiSurf

Chimol is ChiSurf's molecular viewer (class name `Viewer`). It is
deliberately opinionated, and it borrows from three places on purpose:
**ChimeraX** for how a viewer should handle volumes, surfaces and large
assemblies; **PyMOL** for the command language, the selection algebra and the
representation model; and **Dear ImGui** for the interface, which is drawn
inside the viewport rather than assembled out of toolkit widgets.

## Why it exists

It was not written because the world needs another molecular viewer. It was
written because the viewer this project needed did not exist:

- **It has to run on the web, in Python, without compiling anything.** The
  target is a Pyodide-capable stack: no C extension to build, no native
  toolkit to ship, no per-platform wheel. That single constraint is the reason
  the interface is drawn as quads through a six-operation painter rather than
  built from Qt widgets, and the reason the renderer talks WebGPU.
- **It has to be embeddable — in a web app and in Python.** A viewer that can
  only be a window is not much use inside an analysis tool. Chimol is a
  renderer with hosts around it: a Qt widget, a toolkit-free desktop window,
  and a browser canvas, all driving the same code.
- **It has to scale to large integrative models.** Not one protein — nuclear
  pores, bead models, assemblies with millions of copies of a handful of
  shapes. That is a different engineering problem from drawing a single PDB
  entry well, and it is the one that decides the architecture.

## What it is not

**It is not trying to replace anything.** ChimeraX and PyMOL are mature,
excellent and enormous; this is a personal project inside a larger one, and it
is built by reading them rather than by competing with them. Where chimol
does something differently it is because of the constraints above, not because
the reference got it wrong — and where it simply has less, that is expected.
Use PyMOL or ChimeraX for what they are good at. Chimol is here so that the
3-D view inside ChiSurf is not a second application.

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
- Keep user-visible strings using the Chimol name; class names remain `Viewer`
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
  `chimol/cmtk/` is a port of its widget stack, one module per section
  of `imgui_widgets.cpp` and `imgui_tables.cpp`, with its `StyleColorsDark`
  palette. The controls are re-expressed as retained objects drawn through a
  six-operation painter, because chimol has no per-frame immediate-mode
  context; the behaviour, the layout arithmetic and the naming are the
  reference's.
- **[ImGuiColorTextEdit](https://github.com/goossens/ImGuiColorTextEdit)**
  (Johan A. Goossens, after Balázs Jákó and Santiago; MIT) —
  `chimol/cmtk/text_editor.py`. The colouriser state machine, the
  multi-cursor model, the transaction-based undo and the language definitions
  come from it; its keyword tables are extracted from the source rather than
  retyped, and a test re-extracts them to prove they have not drifted.
- **[imgui_club](https://github.com/ocornut/imgui_club)** (Omar Cornut, MIT) —
  `chimol/cmtk/memory_editor.py`, the hex view over host arrays and
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
order. `chimol/cmtk/control.py` supplies the contract the skeleton
subclasses, and `chimol/cmtk/qt_host.py` is what makes any of them
usable in a Qt form without a second implementation.

### Licences

Every reference above is MIT or an equivalently permissive licence except
ChimeraX, which was read but not transcribed from. Ported files name their
source in the module docstring; chimol itself is MIT (see `LICENSE`).
