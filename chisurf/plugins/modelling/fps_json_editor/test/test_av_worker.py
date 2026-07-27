"""The AV worker has to name an unresolvable labelling site (RF-379).

``av._find_attachment_point`` used to answer every in-range residue number with
*the resseq-th atom of the file*, so the worker's "not found" branch was
unreachable — and stale: it called a ``PdbCoordinates`` class that no longer
exists. Now that a miss really returns ``None``, this pins that the worker turns
it into one readable message on the ``error`` signal.
"""

from __future__ import annotations

import os
import pathlib

import pytest

try:
    from qtpy import QtWidgets
except ImportError:
    QtWidgets = None  # type: ignore[assignment]

_needs_qt = pytest.mark.skipif(QtWidgets is None, reason="Qt bindings not available")
_needs_offscreen = pytest.mark.skipif(
    os.environ.get("QT_QPA_PLATFORM", "") != "offscreen",
    reason="Set QT_QPA_PLATFORM=offscreen for headless test",
)

_PDB_148L = (
    pathlib.Path(__file__).resolve().parents[5]
    / "test" / "data" / "atomic_coordinates" / "pdb_files" / "148l.pdb"
)

#: Keeps the QApplication alive for the duration of the module.
_APP: list = []


@_needs_qt
@_needs_offscreen
def test_missing_attachment_atom_is_reported() -> None:
    """ALA 134 has no CG, so the worker reports the site instead of computing."""
    if not _PDB_148L.is_file():
        pytest.skip(f"missing test structure {_PDB_148L}")
    _APP[:] = [QtWidgets.QApplication.instance() or QtWidgets.QApplication([])]

    from chisurf.plugins.modelling.fps_json_editor.gui.av_worker import AVWorker

    worker = AVWorker(
        chain="E", res_id=134, atom="CG",
        linker_length=20.0, linker_width=1.0, radii=(3.5, 0.0, 0.0),
        pdb_path=str(_PDB_148L),
    )
    messages: list[str] = []
    worker.error.connect(messages.append)
    results: list[tuple] = []
    worker.result_ready.connect(lambda *args: results.append(args))

    worker.run()

    assert not results
    assert len(messages) == 1
    assert "E:134:CG" in messages[0]
    assert "not found" in messages[0]
