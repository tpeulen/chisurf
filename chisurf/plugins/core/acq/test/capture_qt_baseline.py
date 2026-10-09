"""Repeatably capture the legacy acquisition dock for native-port control parity."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def control_inventory(widget) -> dict:
    """Collect visible legacy labels without importing the native parity harness."""
    from qtpy import QtWidgets

    controls = []
    for child in [widget, *widget.findChildren(QtWidgets.QWidget)]:
        for attr in ("text", "title", "windowTitle", "toolTip"):
            value = getattr(child, attr, None)
            if callable(value):
                try:
                    value = value()
                except RuntimeError:
                    value = ""
            if isinstance(value, str) and value.strip():
                controls.append(value)
    return {"controls": sorted(set(controls))}


def capture(out: Path) -> Path:
    """Render the legacy dock offscreen without initialising an acquisition device."""
    from qtpy import QtWidgets

    from chisurf.plugins.core.acq.gui.tool import SMAcquisitionManager
    out.mkdir(parents=True, exist_ok=True)
    application = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    host = QtWidgets.QMainWindow()
    manager = SMAcquisitionManager(host)
    dock = manager.acquisition_dock
    dock.resize(1200, 800)
    dock.show()
    for _ in range(20):
        application.processEvents()
    path = out / "before.png"
    dock.grab().save(str(path))
    inventory = control_inventory(dock)
    inventory["entrypoint"] = "chisurf.plugins.core.acq.gui.tool:SMAcquisitionManager"
    inventory["size"] = [1200, 800]
    (out / "before.json").write_text(json.dumps(inventory, indent=2, ensure_ascii=False), encoding="utf-8")
    dock.close()
    return path


def main() -> None:
    """Capture the legacy dock at the requested evidence directory."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    print(capture(args.out))


if __name__ == "__main__":
    main()
