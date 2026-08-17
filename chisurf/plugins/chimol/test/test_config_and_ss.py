"""Regression tests for Chimol config loading and SS assignment."""

from __future__ import annotations

import copy
import importlib
from types import SimpleNamespace

import numpy as np
import pytest

from chimol.core.settings import config
from chimol.analysis.ss import assign_ss_c3_from_atoms


@pytest.fixture(autouse=True)
def _restore_display_config():
    """Put the config dict back — the *same object*, not just the same contents.

    Eight modules do ``from ..config import _DISPLAY_CONFIG`` at import time and
    hold that dict for the life of the process. ``importlib.reload(config)``
    rebinds the name to a **new** dict, so every one of those modules is left
    reading an orphan while anything importing the name afresh reads the new one.
    The renderer and the command layer then disagree about the configuration, and
    the symptom appears in an unrelated test file: ``cartoon putty`` wrote a style
    the renderer never saw, so the tube kept its old radius.

    Restoring identity as well as contents is what makes these reload tests safe
    to run alongside anything that reads the config.
    """
    original = config._DISPLAY_CONFIG
    snapshot = copy.deepcopy(original)
    yield
    original.clear()
    original.update(snapshot)
    config._DISPLAY_CONFIG = original


def _build_minimal_atoms(n_res: int) -> np.ndarray:
    """Construct a tiny ChiSurf-style atoms array with N/CA/C/O per residue."""

    # Simple straight backbone along x-axis; spacing 1.5 Å.
    coords = []
    for i in range(n_res):
        base = float(i) * 1.5
        coords.extend(
            [
                ("N", np.array([base, 0.0, 0.0]), i),
                ("CA", np.array([base + 0.5, 0.0, 0.0]), i),
                ("C", np.array([base + 1.0, 0.0, 0.0]), i),
                ("O", np.array([base + 1.2, 0.2, 0.0]), i),
            ]
        )
    dtype = [("atom_name", "U4"), ("xyz", float, (3,)), ("res_id", int)]
    return np.array(coords, dtype=dtype)


def test_display_config_prefers_settings_dir(tmp_path, monkeypatch):
    """Ensure config reads chimol_display.json from the settings directory.

    Pointed through ``CHIMOL_SETTINGS_DIR``, the documented override. This
    used to monkeypatch ``config._cs_settings`` -- ChiSurf's settings module,
    imported by name -- which no longer exists: `config` resolves its
    directory through :mod:`chimol.core.settings.dirs` so that chimol can find its
    own settings with no ChiSurf to ask.
    """

    cfg_path = tmp_path / "chimol_display.json"
    cfg_path.write_text('{"background": "w", "camera": {"near_clip": 0.5}}', encoding="utf-8")

    monkeypatch.setenv("CHIMOL_SETTINGS_DIR", str(tmp_path))
    monkeypatch.setenv("CHIMOL_DISPLAY_CONFIG", str(cfg_path))

    importlib.reload(config)

    assert config._DISPLAY_CONFIG["background"] == "w"
    # camera keys should be merged with defaults
    assert config._DISPLAY_CONFIG["camera"]["near_clip"] == 0.5
    assert "far_clip" in config._DISPLAY_CONFIG["camera"]


def test_display_config_falls_back_to_defaults(tmp_path, monkeypatch):
    """When no config files exist, defaults should be loaded.

    Pointed at a path that does not exist, through the **environment**. This
    used to monkeypatch ``config._cs_settings`` and then reload the module --
    which re-runs the import and throws the patch away, so the load read the
    machine's own settings file and the test passed only while that file
    happened to agree with the package. Any earlier test that autosaved a
    setting made it fail, and made it look like the loader had broken.
    """
    monkeypatch.setenv("CHIMOL_DISPLAY_CONFIG", str(tmp_path / "absent.json"))

    importlib.reload(config)

    assert config._DISPLAY_CONFIG["background"] == "k"
    assert config._DISPLAY_CONFIG["cartoon"]["style"] == "ribbon"


def test_assign_ss_c3_from_atoms_returns_codes():
    """Basic sanity: SS assignment returns H/E/C codes with requested length."""

    atoms = _build_minimal_atoms(6)
    codes = assign_ss_c3_from_atoms(atoms, n_res=6, verbose=False)
    assert codes is not None
    assert len(codes) == 6
    assert set(codes).issubset({"H", "E", "C"})


# --------------------------------------------------------------------------- #
# Author-deposited HELIX/SHEET records
# --------------------------------------------------------------------------- #

# Verbatim records from RCSB entry 148L. HELIX and SHEET put the chain and
# sequence number in *different* columns, so these must not be re-typed by hand.
_PDB_WITH_RECORDS = """\
HEADER    HYDROLASE(O-GLYCOSYL)                   01-JAN-95   148L
HELIX    1  H1 ILE E    3  GLU E   11  1                                   9
HELIX    2  H2 LEU E   39  ILE E   50  1                                  12
SHEET    1   A 3 ARG E  14  LYS E  19  0
SHEET    2   A 3 TYR E  25  GLY E  28 -1  N  GLU E  26   O  TYR E  18
ATOM      1  N   MET E   1       0.000   0.000   0.000  1.00 41.09           N
ATOM      2  CA  MET E   1       1.000   0.000   0.000  1.00 41.86           C
END
"""


def _write(tmp_path, text, name="rec.pdb"):
    path = tmp_path / name
    path.write_text(text)
    return path


def test_secondary_structure_records_are_parsed(tmp_path):
    from chimol.io.structure import parse_pdb_secondary_structure

    records = parse_pdb_secondary_structure(_write(tmp_path, _PDB_WITH_RECORDS))
    assert records is not None
    # HELIX spans are inclusive of both endpoints
    assert records[("E", 3)] == "H"
    assert records[("E", 11)] == "H"
    assert ("E", 12) not in records
    assert records[("E", 39)] == "H"
    assert records[("E", 50)] == "H"
    # SHEET uses different columns from HELIX; getting them confused silently
    # yields empty or shifted spans
    assert records[("E", 14)] == "E"
    assert records[("E", 19)] == "E"
    assert records[("E", 25)] == "E"
    assert records[("E", 28)] == "E"
    assert ("E", 20) not in records
    assert sorted({chain for chain, _ in records}) == ["E"]


def test_no_records_returns_none(tmp_path):
    from chimol.io.structure import parse_pdb_secondary_structure

    stripped = "\n".join(
        ln for ln in _PDB_WITH_RECORDS.splitlines()
        if not ln.startswith(("HELIX", "SHEET"))
    )
    assert parse_pdb_secondary_structure(_write(tmp_path, stripped, "bare.pdb")) is None


def test_records_after_the_coordinates_are_not_read(tmp_path):
    from chimol.io.structure import parse_pdb_secondary_structure

    # The scan stops at the first coordinate record, so a stray HELIX line in
    # the middle of a large trajectory file cannot cost a full-file scan.
    text = _PDB_WITH_RECORDS + \
        "HELIX    9  H9 ALA E   90  ALA E   99  1                                  10\n"
    records = parse_pdb_secondary_structure(_write(tmp_path, text, "late.pdb"))
    assert records is not None
    assert ("E", 90) not in records


def test_dss_recomputes_and_reports(tmp_path):
    """``dss`` must reach the viewer's assignment, not just redraw."""
    from chimol.commands.command import Cmd
    from chimol.testing.mock_viewer import MockViewer, MockWindow

    viewer = MockViewer()
    cmd = Cmd(MockWindow(viewer))
    messages: list[str] = []
    errors: list[str] = []
    cmd.set_message_callback(messages.append)
    cmd.set_error_callback(errors.append)

    oid = viewer._create_object(name="m").object_id
    viewer.set_active_object(oid)
    viewer._objects[oid].state.atoms = _build_minimal_atoms(5)

    cmd.do("dss")
    assert errors == []
    assert viewer._ss_recomputes == 1
    assert "20 residues" in messages[-1]  # 5 residues x 4 backbone atoms


def test_dss_without_a_backbone_reports_an_error():
    from chimol.commands.command import Cmd
    from chimol.testing.mock_viewer import MockViewer, MockWindow

    viewer = MockViewer()
    cmd = Cmd(MockWindow(viewer))
    errors: list[str] = []
    cmd.set_error_callback(errors.append)

    cmd.do("dss")
    assert errors and "no backbone" in errors[-1]


def test_mismatched_chain_span_is_skipped(tmp_path):
    from chimol.io.structure import parse_pdb_secondary_structure

    text = _PDB_WITH_RECORDS.replace(
        "HELIX    1  H1 ILE E    3  GLU E   11  1",
        "HELIX    1  H1 ILE E    3  GLU F   11  1",
    )
    records = parse_pdb_secondary_structure(_write(tmp_path, text, "split.pdb"))
    assert records is not None
    assert ("E", 3) not in records      # start/end chains disagree -> not guessed at
    assert records[("E", 14)] == "E"    # the sheet records still load
