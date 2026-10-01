"""traj_energy opens the same emtk app as traj_energy_calculator, and stays Qt-free until asked.

The app itself is tested in ``chisurf/plugins/traj/potential_energy`` (the calculator's parity tests);
this plugin only declares it.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
REPO = next(p for p in HERE.parents if (p / "pyproject.toml").exists())


def test_the_manifest_declares_the_calculators_app_and_widget():
    ours = json.loads((HERE.parent / "manifest.json").read_text())["entrypoints"]
    calculator = next(json.loads(p.read_text()) for p in REPO.glob("chisurf/plugins/traj/potential_energy/**/manifest.json")
                      if json.loads(p.read_text()).get("id") == "traj_energy_calculator")["entrypoints"]
    assert ours["emtk"] == calculator["emtk"] == "chisurf.plugins.traj.potential_energy.app:make_app"
    assert ours["gui"] == calculator["gui"]


def test_importing_the_package_loads_no_qt_and_the_widget_on_request():
    code = (
        "import sys\n"
        "import chisurf.plugins.traj.traj_energy as p\n"
        "assert not [m for m in sys.modules if m.split('.')[0] in ('qtpy','PyQt5','PyQt6','PySide2','PySide6')]\n"
        "from chisurf.plugins.traj.potential_energy.app import make_app\n"
        "app = make_app()\n"
        "assert callable(app.draw)\n"
        "assert 'PotentialEnergyWidget' in p.__all__\n"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=str(REPO))
    assert result.returncode == 0, result.stderr[-800:]


def test_port_is_qt_free():
    sys.path.insert(0, str(REPO))
    from test.gui.emtk_port_parity import qt_free

    result = qt_free("traj_energy")
    assert result["ok"], result["output"]
