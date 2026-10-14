"""ChiMOL density figure for guide 44: a model inside its own simulated map.

Run from the repository root with the project environment:
``python docs/guides/screenshots/chimol_map_shot.py``. Builds chimol's
toolkit-free app on the offscreen canvas, loads T4 lysozyme (148L, shipped
with chimol's demos), draws it as an orange cartoon, simulates its density at
6 A with ``molmap`` and contours that map at one level, restyled as a sky-blue ``isomesh``, then
writes ``docs/guides/figures/chimol_map_isomesh.png`` with ``png``.
"""

from __future__ import annotations

import pathlib
import tempfile

FIG = pathlib.Path(__file__).resolve().parents[1] / "figures"


def main() -> None:
    """Render the isomesh figure headlessly."""
    import chimol
    from chimol.core.settings.dirs import set_settings_dir

    set_settings_dir(tempfile.mkdtemp(prefix="chimol-shot-"))
    from chimol.hosts.native.app import ChimolApp

    pdb = pathlib.Path(chimol.__file__).parent / "data" / "demos" / "148l.pdb"
    app = ChimolApp(size=(900, 650), backend="offscreen")
    app.cmd.set_message_callback(print)
    app.cmd.set_error_callback(lambda error: print("error:", error))
    app.load(str(pdb))
    for line in (
        "hide everything",
        "show cartoon",
        "color orange",
        "molmap all, 6.0, sim",
        "volume_level sim, 0.25",
        "isomesh sim, 0.25, color=skyblue",
        "orient 148l",
    ):
        app.cmd.do(line)
    app.draw_frame()
    app.cmd.do(f"png {FIG / 'chimol_map_isomesh.png'}")
    app.close()


if __name__ == "__main__":
    main()
