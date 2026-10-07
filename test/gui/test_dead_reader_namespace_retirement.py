"""Retiring unreachable loader widgets preserves the remaining runtime namespaces."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _runtime_probe(code: str, scratch: Path) -> dict:
    """Import real packages in a fresh interpreter without inheriting cached exports."""
    environment = os.environ.copy()
    environment["QT_QPA_PLATFORM"] = "offscreen"
    environment["CHISURF_SETTINGS_DIR"] = str(scratch)
    environment["PYTHONPATH"] = os.pathsep.join([str(ROOT), environment.get("PYTHONPATH", "")])
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return json.loads(result.stdout.splitlines()[-1])


def test_live_accessible_volume_parameter_and_widget_bindings_survive(tmp_path):
    """The remaining Qt wrappers bind to the exact owning scientific parameter classes."""
    report = _runtime_probe(
        """
import json
from qtpy import QtWidgets
import chisurf.gui.widgets.fluorescence.av as widgets
from chisurf.core.structure.av import parameters
bindings = {}
for name in ('Dye', 'ProteinQuenching', 'Sticking'):
    model = getattr(parameters, name)
    widget = getattr(widgets, name + 'Widget')
    assert getattr(widgets, name) is model
    assert issubclass(widget, model) and issubclass(widget, QtWidgets.QGroupBox)
    bindings[name] = widget.__module__ + '.' + widget.__name__
print(json.dumps(bindings))
""",
        tmp_path,
    )
    assert report == {
        name: f"chisurf.gui.widgets.fluorescence.av.{name}Widget"
        for name in ("Dye", "ProteinQuenching", "Sticking")
    }


def test_live_wizard_exports_still_resolve_to_their_owning_classes(tmp_path):
    """Retirement retains the two neighboring live channel/filter wizard exports."""
    report = _runtime_probe(
        """
import importlib
import json
from qtpy import QtWidgets
import chisurf.gui.widgets.wizard as package
owners = {
    'DetectorWizardPage': 'tttr_channeldefinition.native_page',
    'WizardTTTRPhotonFilter': 'tttr_photonfilter.tttr_photon_filter',
}
for name, relative in owners.items():
    module = importlib.import_module('chisurf.gui.widgets.wizard.' + relative)
    cls = getattr(package, name)
    assert cls is getattr(module, name)
    assert issubclass(cls, QtWidgets.QWizardPage)
print(json.dumps(owners))
""",
        tmp_path,
    )
    assert set(report) == {
        "DetectorWizardPage",
        "WizardTTTRPhotonFilter",
    }


@pytest.mark.parametrize(
    ("module", "retired"),
    [
        ("chisurf.gui.widgets.fluorescence.av", ["AVProperties"]),
        ("chisurf.plugins.burst.burst_fcs_correlator", ["BurstWiseFCSWizard"]),
        ("chisurf.gui.widgets.wizard", ["WizardTTTRFileFormat", "FileFormatSettings", "WizardFcsMerger", "WizardTTTRCorrelator"]),
    ],
)
def test_dead_loader_classes_are_absent_from_fresh_public_namespaces(tmp_path, module, retired):
    """Fresh package imports cannot silently re-export either retired loader."""
    code = f"""
import importlib
import json
package = importlib.import_module({module!r})
print(json.dumps({{name: hasattr(package, name) for name in {retired!r}}}))
"""
    report = _runtime_probe(code, tmp_path)
    assert report == {name: False for name in retired}


@pytest.mark.parametrize(
    "module",
    [
        "chisurf.gui.widgets.fluorescence.av.accessible_volume",
        "chisurf.plugins.burst.burst_fcs_correlator.wizard",
        "chisurf.plugins.fcs.fcs_correlator.wizard",
        "chisurf.plugins.fcs.fcs_merger.wizard",
        "chisurf.gui.widgets.wizard.tttr_fileformat.tttr_file_format",
        "chisurf.gui.widgets.wizard.fcs_merger.fcs_merger",
        "chisurf.gui.widgets.wizard.tttr_correlator.tttr_correlator",
    ],
)
def test_retired_loader_implementation_is_not_importable(tmp_path, module):
    """A deleted implementation cannot linger behind a harmless export removal."""
    code = f"""
import importlib.util
import json
name = {module!r}
try:
    spec = importlib.util.find_spec(name)
except ModuleNotFoundError as error:
    if not (name == error.name or name.startswith(error.name + '.')):
        raise
    spec = None
print(json.dumps({{'available': spec is not None}}))
"""
    assert _runtime_probe(code, tmp_path) == {"available": False}


@pytest.mark.parametrize(
    "relative",
    [
        "chisurf/gui/widgets/fluorescence/av/accessible_volume.py",
        "chisurf/plugins/burst/burst_fcs_correlator/wizard.py",
        "chisurf/plugins/fcs/fcs_correlator/wizard.py",
        "chisurf/plugins/fcs/fcs_merger/wizard.py",
        "chisurf/gui/widgets/fluorescence/av/av_property.ui",
        "chisurf/gui/widgets/wizard/tttr_fileformat/__init__.py",
        "chisurf/gui/widgets/wizard/tttr_fileformat/tttr_file_format.py",
        "chisurf/gui/widgets/wizard/tttr_fileformat/tttr_file_format.ui",
        'chisurf/gui/widgets/wizard/fcs_merger/__init__.py',
        'chisurf/gui/widgets/wizard/fcs_merger/fcs_merger.py',
        'chisurf/gui/widgets/wizard/fcs_merger/fcs_merger.ui',
        'chisurf/gui/widgets/wizard/fcs_merger/fcs_merger_ui.py',
        'chisurf/gui/widgets/wizard/tttr_correlator/__init__.py',
        'chisurf/gui/widgets/wizard/tttr_correlator/tttr_correlator.py',
        'chisurf/gui/widgets/wizard/tttr_correlator/tttr_correlator.ui',
        'chisurf/gui/widgets/wizard/tttr_correlator/tttr_correlator_ui.py',
    ],
)
def test_retired_source_and_designer_files_are_not_shipped(relative):
    """Removing dead imports also removes their Python and designer resources."""
    assert not (ROOT / relative).exists(), relative
