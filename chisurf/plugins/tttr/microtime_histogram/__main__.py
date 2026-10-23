"""Launch the native histogram workflow with optional burst-container startup inputs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def _measurement_setup(folder: Path) -> str | None:
    """Read the existing parent/grandparent measurement setup selection."""
    info = folder.parent / "Info"
    if not info.exists():
        info = folder.parent.parent / "Info"
    parameters = info / "photon_selection_parameters.json"
    if not parameters.is_file():
        return None
    try:
        payload = json.loads(parameters.read_text())
    except (OSError, ValueError) as error:
        print(f"Error reading photon_selection_parameters.json: {error}")
        return None
    name = payload.get("selected_setup") if isinstance(payload, dict) else None
    return str(name) if name else None


def main(argv: list[str] | None = None) -> int:
    """Launch the native app, optionally starting from a folder of burst containers."""
    parser = argparse.ArgumentParser(
        description="Create microtime histograms, optionally burst-restricted from .pto provenance."
    )
    parser.add_argument("--pto-folder", help="Folder containing .pto burst containers")
    parser.add_argument(
        "--setup-name", help="Saved setup; otherwise read measurement Info metadata"
    )
    parser.add_argument(
        "--auto-transfer", action="store_true", help="Transfer the computed histogram to ChiSurf"
    )
    args = parser.parse_args(argv)
    folder = Path(args.pto_folder) if args.pto_folder else None
    if folder is not None and not folder.is_dir():
        print(f"Error: container folder '{folder}' does not exist or is not a directory")
        return 1

    from emtk.native import NativeHost

    from chisurf.core.support.i18n import tr

    from .gui.app import create_app

    control = create_app()
    if folder is not None:
        setup = args.setup_name or _measurement_setup(folder)
        control.load_burst_folder(folder, setup_name=setup, auto_transfer=args.auto_transfer)
    host = NativeHost(control, title=tr("Histogram-Microtime"))
    try:
        host.run()
    finally:
        host.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
