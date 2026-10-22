"""Example data for the TTTR→PTO importer: one small synthetic photon stream.

``make_demo`` writes ``tttr_to_pto_demo.spc`` with the ``tttr`` family's shared
generator (:mod:`chisurf.plugins.tttr.demo_lib`) — the same seeded stream the
tttr plugins' demos use — so the importer converts a file shaped like a real
SPC-132 measurement. The conversion is coordinated with the tttr lane's
generator; if that module moves, this demo moves with it.
"""

from __future__ import annotations

from pathlib import Path

STEM = "tttr_to_pto_demo"


def demo_folder() -> Path:
    """The settings-owned demonstration folder of the importer."""
    from chisurf.core.settings import get_path

    return get_path("settings") / "demos" / "tttr_to_pto"


def make_demo(folder: Path | None = None, *, overwrite: bool = False) -> Path:
    """Write (or reuse) the synthetic SPC photon stream."""
    from chisurf.plugins.tttr import demo_lib

    folder = demo_folder() if folder is None else Path(folder)
    path = folder / f"{STEM}.spc"
    if overwrite or not path.is_file():
        folder.mkdir(parents=True, exist_ok=True)
        c = demo_lib.config()
        macro, micro, routing = demo_lib.photon_stream(c)
        info = demo_lib.write_spc(path, c, macro, micro, routing)
        if not path.is_file() or path.stat().st_size == 0:
            raise OSError(f"could not write the demo stream to {path} ({info})")
    return path


def load_into(model) -> Path:
    """Queue the example for conversion; the model's worker writes the container."""
    path = make_demo()
    model.add_paths([str(path)])
    return path
