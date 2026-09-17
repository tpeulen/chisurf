"""Burstwise-folder file list for the burst-FCS correlator.

No custom widget: the file list is the unified checkable ``PathListWidget`` (the
``path_list`` AutoForm section) configured with a burst-specific *folder expander*
so that dropping a burst-analysis folder resolves to the concrete BUR/BST index
files that will be processed.
"""

from __future__ import annotations

import pathlib


def expand_burst_folder(folder: pathlib.Path) -> list[str]:
    """Return BUR (preferred) or BID/BST files inside a burstwise folder.

    When a user drops a burst analysis folder (e.g. ``burstwise_*``), resolve it to
    the ``.bur`` files under its ``bi4_bur``/``bur`` subfolders, or, if none exist,
    the ``BID/*.bst`` files — so the list explicitly shows every index file that
    will be processed. If nothing is found, the folder itself is kept.
    """
    if not folder.is_dir():
        return [folder.as_posix()]

    # Prefer bi4_bur/bur with .bur files.
    bur_files: list[pathlib.Path] = []
    for sub_name in ("bi4_bur", "bur"):
        subdir = folder / sub_name
        if not subdir.is_dir():
            continue
        try:
            bur_files.extend(sorted(subdir.glob("*.bur")))
        except Exception:
            continue
    if bur_files:
        return [b.as_posix() for b in bur_files]

    # Fallback: BID/*.bst.
    out: list[str] = []
    bid_dir = folder / "BID"
    if bid_dir.is_dir():
        try:
            out = [bst.as_posix() for bst in sorted(bid_dir.glob("*.bst"))]
        except Exception:
            out = []

    # If nothing was found at all, keep the folder so the user sees it.
    return out or [folder.as_posix()]


class _BurstFileListModel:
    """Minimal model backing the unified file list (``files`` + no-op ``update``)."""

    def __init__(self) -> None:
        self.files: list[str] = []

    def update(self) -> None:  # PathListWidget calls this on every change
        pass


def make_burst_file_list():
    """Return a checkable ``PathListWidget`` with burstwise-folder expansion + MMFDB."""
    from chisurf.gui.autoform.sections.path_list_section import PathListWidget

    return PathListWidget(
        _BurstFileListModel(),
        "files",
        extensions=[".bur", ".bst", ".spc", ".ht3", ".ptu", ".hdf", ".h5"],
        checkable=True,
        folder_expander=expand_burst_folder,
    )
