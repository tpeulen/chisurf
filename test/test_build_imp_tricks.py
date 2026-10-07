"""Declared builds install the structural provider without a source path override."""

import os
import subprocess
import sys
from pathlib import Path

import tomllib


def test_structural_provider_is_in_the_extension_build_chain():
    """A fresh test/runtime build cannot omit the required structural provider."""
    tasks = tomllib.loads(Path("pixi.toml").read_text())["tasks"]
    assert "build-imp-tricks" in tasks["build-extensions"]["depends-on"]
    task = tasks["build-imp-tricks"]
    assert "--no-deps" in task["cmd"]
    assert "-e modules/imp-tricks" in task["cmd"]
    assert "modules/imp-tricks/pyproject.toml" in task["inputs"]
    assert "modules/imp-tricks/src/**" in task["inputs"]


def test_installed_structural_kernels_and_databases_work_in_a_cold_process(tmp_path):
    """Isolated Python discovers kernels and their real resource arrays by installation."""
    code = """
from importlib.resources import files
from IMP.cgmol.statpot import _kernels, _io
for name in ('mj.json', 'hb.json', 'unres.json', 'rama_ala_pro_gly.json'):
    path = files('IMP.cgmol.statpot').joinpath('data', name)
    assert path.is_file(), str(path)
    array = _io.load_json_array(str(path))
    assert array.size > 0, name
assert callable(_kernels._data_path)
print('installed structural kernels and four potential databases')
"""
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    result = subprocess.run(
        [sys.executable, "-I", "-c", code],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
