"""HydroPro — GUI front-end to the HYDROPRO / HYDRO++ hydrodynamics suite."""

from __future__ import annotations

from pathlib import Path

from chisurf.core.plugin import load_manifest

_manifest = load_manifest(Path(__file__).with_name("manifest.json"))
if _manifest is not None:
    name = _manifest.display_name
    cli_entrypoint = _manifest.entrypoints.cli or ""
else:
    name = "Structure:Computation:HydroPro"
    cli_entrypoint = ""

__all__ = ["name", "cli_entrypoint"]


if __name__ == "__main__":
    from chisurf.emtk.__main__ import main as _launch

    _launch(["--plugin", "hydropro"])

if __name__ == "plugin":  # pragma: no cover - the legacy macro launch; the manifest's emtk entry comes first
    from emtk.qt_host import ControlHost

    from chisurf.plugins.modelling.hydropro.app import make_app

    window = ControlHost(make_app())
    window.show()
