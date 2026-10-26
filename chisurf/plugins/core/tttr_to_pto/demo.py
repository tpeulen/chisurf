"""Example data for the TTTR→PTO importer: one small synthetic photon stream.

``make_demo`` writes ``tttr_to_pto_demo.spc`` with the ``tttr`` family's shared
generator (:mod:`chisurf.plugins.tttr.demo_lib`) — the same seeded stream the
tttr plugins' demos use — so the importer converts a file shaped like a real
SPC-132 measurement. The conversion is coordinated with the tttr lane's
generator; if that module moves, this demo moves with it.
"""

from __future__ import annotations

from pathlib import Path

from chisurf.plugins.tttr import demo_lib

STEM = "tttr_to_pto_demo"
#: The shared tttr generator's full configuration: the cached stream is this, seeded.
DEMO = dict(demo_lib.config())


def demo_folder() -> Path:
    """The settings-owned demonstration folder of the importer."""
    from chisurf.core.settings import get_path

    return get_path("settings") / "demos" / "tttr_to_pto"


def make_demo(folder: Path | None = None, *, overwrite: bool = False) -> Path:
    """Write (or reuse) the synthetic SPC photon stream."""
    folder = demo_folder() if folder is None else Path(folder)
    path = folder / f"{STEM}.spc"
    if overwrite or not path.is_file():
        folder.mkdir(parents=True, exist_ok=True)
        c = DEMO
        macro, micro, routing = demo_lib.photon_stream(c)
        info = demo_lib.write_spc(path, c, macro, micro, routing)
        if not path.is_file() or path.stat().st_size == 0:
            raise OSError(f"could not write the demo stream to {path} ({info})")
    return path


def load_into(model) -> Path:
    """Put the example in the workspace and hand it to the converter as a picked row would be;
    the model's worker writes the container (a child of the example in the workspace)."""
    from chisurf.plugins.tttr.workspace_io import add_photons, example_into_workspace

    path = make_demo()
    app = getattr(model, "workspace_input_app", None)
    if app is None:  # the model alone (scripts, tests): straight into its own queue
        dataset = add_photons(str(path))
        model.add_paths([str(path)], source=str(getattr(dataset, "unique_identifier", "") or ""))
        return path
    from chisurf.plugins.core.tttr_to_pto.gui.app import receive_photons

    example_into_workspace(path, receive_photons, app, key="files", many=True)
    return path
