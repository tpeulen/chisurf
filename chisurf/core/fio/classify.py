"""What a dropped path is: the one place the workspace decides how a file enters it.

The shell has one way in — a file drop (``okf/specs/data-workspace.md``) — and every dropped path is
sorted here by what it holds, not by which reader happens to be selected:

* ``"project"`` — a ChiSurf project (``.cs.pto``): opened, not imported;
* ``"container"`` — a measurement container (``.pto``): its photon streams and its burst runs
  become workspace datasets (:func:`container_entries`);
* ``"photons"`` — a vendor photon file (PTU, HT3, SPC, …): one photon dataset;
* ``"structure"`` — a molecular structure (PDB, mmCIF);
* ``"image"`` — an image stack (TIFF);
* ``"companion"`` — a file that only exists beside a primary one (an SPC's ``.set``): taken with
  its primary, never on its own;
* ``"curve"`` — anything else: read by the selected reader, as before.
"""

from __future__ import annotations

from pathlib import Path

__all__ = [
    "IMAGE_EXTENSIONS",
    "STRUCTURE_EXTENSIONS",
    "classify",
    "container_entries",
]

#: Molecular structures a workspace drop reads as a structure.
STRUCTURE_EXTENSIONS: tuple[str, ...] = (".pdb", ".ent", ".cif", ".mmcif", ".pdb.gz", ".cif.gz")

#: Image stacks a workspace drop links as an image.
IMAGE_EXTENSIONS: tuple[str, ...] = (".tif", ".tiff")


def _suffix(path: Path) -> str:
    name = path.name.lower()
    for compound in (".cs.pto", ".pdb.gz", ".cif.gz"):
        if name.endswith(compound):
            return compound
    return path.suffix.lower()


def classify(path: str | Path) -> str:
    """Return what *path* holds — one of the kinds in the module docstring."""
    from chisurf.core.fio.pto import SIDECAR_ONLY_EXTENSIONS
    from chisurf.core.fio.staging import VENDOR_EXTENSIONS
    from chisurf.core.project.pto import PROJECT_SUFFIX

    suffix = _suffix(Path(path))
    if suffix == PROJECT_SUFFIX:
        return "project"
    if suffix == ".pto":
        return "container"
    if suffix in SIDECAR_ONLY_EXTENSIONS:
        return "companion"
    if suffix in VENDOR_EXTENSIONS:
        return "photons"
    if suffix in STRUCTURE_EXTENSIONS:
        return "structure"
    if suffix in IMAGE_EXTENSIONS:
        return "image"
    return "curve"


def container_entries(path: str | Path) -> list[tuple[str, str]]:
    """The datasets a measurement container contributes: ``[(kind, address), ...]``.

    One ``("photons", "<path>/<stream>")`` per photon stream, then one ``("bursts",
    "<path>/<run>")`` per burst run (the runs a burst search wrote), oldest first.
    """
    from chisurf.core.fio.address import join_address
    from chisurf.core.fio.analysis_path import list_runs
    from chisurf.core.fio.pto import Measurement

    path = Path(path)
    entries: list[tuple[str, str]] = []
    with Measurement.open(path, writable=False) as measurement:
        for name in measurement.photon_member_names():
            entries.append(("photons", join_address(path, name)))
    for run in list_runs(path, operation="burst_selection"):
        entries.append(("bursts", join_address(path, run) if run else str(path)))
    return entries
