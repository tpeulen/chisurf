"""Shared test helpers for the burst tools fed from the Datasets workspace.

A burst tool takes a burst run from the workspace (``accepts[].from_workspace``), never from a file
dialog or a drop. These helpers put a real run into the session's workspace the way the drop does
(the photon stream, the run as its child row), guard against input dialogs, click a row of the
generated Input section, and save the window as a PNG to read.
"""

from __future__ import annotations

import time
from pathlib import Path

from emtk.testing import RecordingPainter

__all__ = [
    "burst_run_in_workspace",
    "run_columns",
    "click",
    "draw",
    "no_input_dialog",
    "pick_row",
    "restore_workspace",
    "save_png",
    "settle",
    "text_rect",
]

SIZE = (1200, 800)


def burst_run_in_workspace(root: Path, run: str = "runBursts#1"):
    """A demo measurement in the workspace as a session holds it: the photon file (a dataset), and
    a burst run of it in that dataset's analysis container of the project (its child row).
    Returns the run's dataset (``.address``, ``.unique_identifier``)."""
    from chisurf.core.fio.classify import container_entries
    from chisurf.core.fio.fluorescence.burst import read_bur_file
    from chisurf.core.fio.fluorescence.burst_container import deinterleave_bursts
    from chisurf.core.plugin.workspace_input import register_result
    from chisurf.core.project.analysis import container_dir
    from chisurf.plugins.burst.burst_2cde.tests.demo_folder import build
    from chisurf.plugins.burst.burst_selection.api.io import write_container

    measurement = build(Path(root) / "measurement")
    photons = measurement.parent / "m000.spc"
    stream = register_result(str(photons), kind="photons", name=photons.name)
    bur = sorted((measurement / "bi4_bur").glob("*.bur"))[0]
    container = write_container(
        photons,
        deinterleave_bursts(read_bur_file(bur)),  # a container holds the bursts, not the .bur grid
        parameters={"run": 1},
        out_dir=container_dir(stream.unique_identifier),
        run=run,
        raw_data="sidecar",  # the project's analysis container links the photons
    )
    (burst_run,) = [a for kind, a in container_entries(container) if kind == "bursts"]
    return register_result(burst_run, kind="bursts", result_of=stream.unique_identifier)


def restore_workspace():
    """Context for a test: the session's dataset list is process-wide, so put it back afterwards."""
    from contextlib import contextmanager

    from chisurf.core.api import dataset_container

    @contextmanager
    def _restore():
        held = dataset_container()
        before = list(held)
        try:
            yield held
        finally:
            held[:] = before

    return _restore()


def no_input_dialog(monkeypatch):
    """The input comes from the workspace: any dialog but a save dialog fails the test."""
    import emtk.file_dialog

    real = emtk.file_dialog.FileDialog

    def guarded(title, mode="open", **kwargs):
        assert mode == "save", f"an input dialog opened: {title!r}"
        return real(title, mode=mode, **kwargs)

    monkeypatch.setattr(emtk.file_dialog, "FileDialog", guarded)


def draw(app, size=SIZE, frames=2):
    painter = None
    for _ in range(frames):
        painter = RecordingPainter()
        app.draw(painter, 0, 0, *size)
    return painter


def click(app, rect, size=SIZE, fx=0.5):
    """Press and release the pointer on *rect* (a frame is drawn between, as a host does)."""
    x, y, w, h = rect
    app.pointer_move(x + w * fx, y + h / 2)
    draw(app, size, frames=1)
    app.press(x + w * fx, y + h / 2)
    draw(app, size, frames=1)
    app.release()
    draw(app, size, frames=1)


def text_rect(painter, label, last=True):
    hits = [t[:4] for t in painter.texts if t[5] == label]
    assert hits, f"{label!r} is not drawn: {[t[5] for t in painter.texts][:60]}"
    return hits[-1] if last else hits[0]


def pick_row(app, label, size=SIZE):
    """Click the Input section's row drawn as *label* (a run's name)."""
    click(app, text_rect(draw(app, size), label), size)


def settle(app, running=lambda app: app.controller.running, size=SIZE, timeout=90.0):
    """Draw frames until the tool's worker is done (the host would draw them on request)."""
    end = time.monotonic() + timeout
    draw(app, size, frames=1)
    while running(app):
        assert time.monotonic() < end, "the computation did not finish"
        time.sleep(0.02)
        draw(app, size, frames=1)
    return draw(app, size, frames=1)


def save_png(app, path, size=SIZE) -> Path:
    """The window as a PNG (for reading by eye)."""
    from emtk.export import save_png as _save

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    _save(app, str(path), size=size)
    return path


def run_columns(run_address) -> list[str]:
    """The columns ndX reads for the burst run *run_address* -- its burst table and every companion
    table joined to it -- through ndX's own reader (``ndxplorer.io.pto_reader``), not ChiSurf's."""
    from ndxplorer.io.pto_reader import list_tables, read_container

    from chisurf.core.fio.address import container_of, split_address

    container = container_of(run_address)
    _box, run = split_address(str(run_address))
    names = [t["name"] for t in list_tables(container) if t["run"] == str(run).strip("/")]
    assert names, f"{run!r} is not a run of {container}"
    return list(read_container(container, table=names[-1]).parameter_names)
