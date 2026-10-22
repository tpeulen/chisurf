"""Example data for the LlTF tool: the simulated VV/VH pair the tool writes itself.

The model already knows how to build its example (``load_example``: a polarised
decay pair with known τ, ρ, r0 and G, written beside the settings). ``make_demo``
produces that pair for scripts and tests; *Load example* selects it in VV/VH mode.
"""

from __future__ import annotations

from pathlib import Path

STEM = "lltf_demo"


def demo_folder() -> Path:
    """The settings-owned demonstration folder of the LlTF tool."""
    from chisurf.core.settings import get_path

    return get_path("settings") / "demos" / "lltf"


def make_demo(folder: Path | None = None, *, overwrite: bool = False) -> dict[str, Path]:
    """Write (or reuse) the simulated VV/VH decay/IRF pair."""
    from chisurf.plugins.fluorescence_decay.lltf.core.polarized import write_demo

    folder = demo_folder() if folder is None else Path(folder)
    decay_file, irf_file = write_demo(folder)
    return {"decay": Path(decay_file), "irf": Path(irf_file)}


def load_into(app) -> dict[str, Path]:
    """The tool's own Load example (writes the pair and selects it in VV/VH mode)."""
    app.model.load_example(demo_folder())
    return make_demo()
