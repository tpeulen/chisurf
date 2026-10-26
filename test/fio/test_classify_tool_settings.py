"""A tool's own settings or project file drops into the workspace as a ``setup``.

Tools read their settings back from the Datasets workspace (the one input entry point), so the
drop must recognise them: by the ``chisurf.tool/`` schema a tool now writes, or -- files written
before -- by keys only that tool writes together.
"""

from __future__ import annotations

import json

from chisurf.core.fio.classify import classify


def _write(tmp_path, name, data):
    path = tmp_path / name
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_a_tool_schema_makes_a_settings_file_a_setup(tmp_path):
    path = _write(tmp_path, "s.json", {"schema": "chisurf.tool/fcs_calculator/1", "dye": "x"})
    assert classify(path) == "setup"


def test_legacy_tool_settings_are_setups_by_their_keys(tmp_path):
    calc = _write(tmp_path, "calc.json", {"fix_mode": "conc", "shape_type": "Sphere", "w0": 0.2})
    proj = _write(tmp_path, "proj.json", {"species_patterns": [], "total_path": [], "x": 1})
    assert classify(calc) == "setup" and classify(proj) == "setup"


def test_a_json_with_only_one_signature_key_is_not_a_setup(tmp_path):
    path = _write(tmp_path, "other.json", {"fix_mode": "conc", "values": [1, 2, 3]})
    assert classify(path) != "setup"
