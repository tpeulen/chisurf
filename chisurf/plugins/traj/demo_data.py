"""The example data shared by the trajectory tools of the ``traj`` family.

The family demos reference the MD example that ships in-repo with the FRET
modelling plugin (``modelling/fret/examples/olga_t4l``): 894 frames of the NMSim
T4-lysozyme run with its PDB topology. Nothing is copied: the tools read the
shipped files where they are, and each tool writes its own demo output into a
settings-owned folder, which is what the tests assert on.

``run_plugin_demo`` is the affordance behind every tool's *Load example* button:
it fills the tool's file rows from the example (a DCD row gets the trajectory, a
PDB row the topology, a folder row the demo output folder), applies the tool's
own extras from its ``demo`` module (a potential to add, atom picks) and submits
the tool's action.
"""

from __future__ import annotations

import importlib
from pathlib import Path

EXAMPLE_DIR = (
    Path(__file__).resolve().parents[1] / "modelling" / "fret" / "examples" / "olga_t4l"
)
TRAJECTORY = EXAMPLE_DIR / "3GUN_NMSim_cl-rep_894.dcd"
TOPOLOGY = EXAMPLE_DIR / "3GUN_NMSim_cl-rep-001.pdb"


def example_paths() -> tuple[Path, Path]:
    """Return the shipped example (DCD, PDB) the family demos run on."""
    for path in (TRAJECTORY, TOPOLOGY):
        if not path.is_file():
            raise FileNotFoundError(f"the traj family example is missing: {path}")
    return TRAJECTORY, TOPOLOGY


def demo_folder(plugin: str) -> Path:
    """The settings-owned demonstration folder of one traj tool (created on demand)."""
    from chisurf.core.settings import get_path

    folder = get_path("settings") / "demos" / plugin
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def family_demo(plugin: str) -> dict[str, Path]:
    """The family producer: the example files the tool named by *plugin* runs on.

    Returns the shipped DCD and PDB (referenced where they are) plus the demo
    output folder, created so the tool has somewhere to write its result.
    """
    dcd, pdb = example_paths()
    return {"trajectory": dcd, "topology": pdb, "output_folder": demo_folder(plugin)}


def _set_row(app, field, path: Path) -> None:
    """Put *path* into a file row the way the row's own setter does."""
    setter = getattr(field, "setter", "")
    fn = getattr(app.model, setter, None) if setter else None
    if callable(fn):
        fn(str(path))
    else:  # a row without a setter is written through directly
        setattr(app.model, field.attr, str(path))


def _fill_rows(app, folder: Path) -> None:
    """Fill the tool's file rows from the family example (folder rows get *folder*)."""
    dcd, pdb = example_paths()
    for field in app.paths:
        if field.takes_folder(app.model):
            _set_row(app, field, folder)
            continue
        globs = [g.lower() for _label, globs in field.filters for g in globs]
        if any("*.dcd" in g for g in globs):
            _set_row(app, field, dcd)
        elif any("*.pdb" in g for g in globs):
            _set_row(app, field, pdb)


def run_demo(app, output: str, prepare=None) -> Path:
    """Point a trajectory tool at the family example, then run its action.

    ``prepare(app, folder)`` is the tool's own extra wiring (called with the rows
    already filled). The action is submitted with *output* (a file name inside
    the demo folder) as the save target; tools without a save dialog run at once
    and write into the folder themselves. Returns the expected output path.
    """
    plugin = Path(app.folder).name
    folder = demo_folder(plugin)
    _fill_rows(app, folder)
    if prepare is not None:
        prepare(app, folder)
    target = folder / output
    app.save(None if app.action.dialog_title is None else str(target))
    return target


def run_plugin_demo(app) -> Path:
    """The *Load example* affordance of one tool: its ``demo`` module says how."""
    plugin = Path(app.folder).name
    demo = importlib.import_module(f"chisurf.plugins.traj.{plugin}.demo")
    return run_demo(
        app,
        getattr(demo, "OUTPUT"),
        getattr(demo, "prepare", None),
    )


__all__ = [
    "EXAMPLE_DIR",
    "TRAJECTORY",
    "TOPOLOGY",
    "demo_folder",
    "example_paths",
    "family_demo",
    "run_demo",
    "run_plugin_demo",
]
