"""Importing the settings editor must not change how the rest of the app writes YAML.

``yaml.add_representer(float, ...)`` registers on ``yaml.Dumper`` itself, which
is process-global, and the settings editor did it at *import* time. From the
moment anything pulled the module in, every unrelated ``yaml.dump`` in the
session -- a project file, a curve saved to YAML -- was silently rounded to ten
decimal digits, where a double needs seventeen.

The symptom was a test that passed alone and failed in company
(``test/fitting/test_scientific_notation.py::test_the_global_dumper_is_not_mutated``);
the cost in the application is saved files that no longer round-trip.
"""

import pytest
import yaml

pytest.importorskip("qtpy")

#: A value that needs all seventeen significant digits to survive a round trip.
TINY = 2.4492935982947064e-16


def test_importing_the_settings_editor_leaves_the_global_dumper_alone():
    """The representer belongs to the editor's own dumper subclass."""
    from chisurf.gui.widgets import settings_editor

    assert yaml.Dumper.yaml_representers[float] is not settings_editor.float_representer


def test_an_unrelated_dump_keeps_full_precision():
    """The failure this actually prevents: a value that no longer round-trips."""
    from chisurf.gui.widgets import settings_editor  # noqa: F401  (import is the trigger)

    assert yaml.safe_load(yaml.dump({"tiny": TINY}))["tiny"] == TINY


def test_the_settings_dumper_still_writes_scientific_notation():
    """The editor keeps the formatting it registered the representer for."""
    from chisurf.gui.widgets.settings_editor import SettingsDumper

    text = yaml.dump({"small": 1.23e-6}, Dumper=SettingsDumper)

    assert "1.23e-6" in text
