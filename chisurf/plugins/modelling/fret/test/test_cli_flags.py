"""Headless CLI-contract tests for PRD-58 (R09 / R16).

* R16 — the ``evaluate`` command's ``--pdb-dir`` / ``--top`` + ``--traj`` flags and
  the pure ``_resolve_evaluate_mode`` selector.
* R09 — ``--av-backend`` on ``imp dock`` routes into the docking request.

The AV-computing / IMP functions are monkeypatched, so nothing here needs an AV
backend, IMP, or external data — only flag parsing and dispatch wiring are tested.
"""
from __future__ import annotations

import pytest
from click.testing import CliRunner

from ..cli.main import _resolve_evaluate_mode, main


# --------------------------------------------------------------------------------------
# R16 — _resolve_evaluate_mode (pure)
# --------------------------------------------------------------------------------------
def test_resolve_single_pdb():
    assert _resolve_evaluate_mode("s.pdb", None, None, None, None) == ("Single PDB File", "s.pdb", None)


def test_resolve_pdb_dir_flag_wins():
    assert _resolve_evaluate_mode("s.pdb", "d/", None, None, None) == ("PDB Directory", "d/", None)


def test_resolve_top_and_traj():
    assert _resolve_evaluate_mode(None, None, "t.pdb", "j.xtc", None) == ("MDTraj Trajectory", "t.pdb", "j.xtc")


def test_resolve_pdb_as_topology_with_traj():
    assert _resolve_evaluate_mode("t.pdb", None, None, "j.xtc", None) == ("MDTraj Trajectory", "t.pdb", "j.xtc")


def test_resolve_legacy_input_type_directory():
    assert _resolve_evaluate_mode("d/", None, None, None, "PDB Directory") == ("PDB Directory", "d/", None)


def test_resolve_requires_some_input():
    with pytest.raises(ValueError):
        _resolve_evaluate_mode(None, None, None, None, None)


def test_resolve_traj_without_topology_raises():
    with pytest.raises(ValueError):
        _resolve_evaluate_mode(None, None, None, "j.xtc", None)


# --------------------------------------------------------------------------------------
# R16 — evaluate CLI dispatch (monkeypatched)
# --------------------------------------------------------------------------------------
class _FakeStorage:
    def add_frame(self, *a, **k):
        pass

    def to_csv(self, path):
        with open(path, "w") as f:
            f.write("ok\n")


def _stub_evaluate_env(monkeypatch):
    from ..core import av, evaluate, io
    monkeypatch.setattr(av, "select_backend", lambda *a, **k: None)
    monkeypatch.setattr(io, "read_fps_json", lambda p: ({}, {}, None, None))
    monkeypatch.setattr(io, "read_evaluators_json", lambda p: [object()])  # non-empty
    return evaluate


def test_evaluate_cli_pdb_dir_dispatches_to_directory(tmp_path, monkeypatch):
    evaluate = _stub_evaluate_env(monkeypatch)
    calls = {}
    monkeypatch.setattr(evaluate, "evaluate_directory",
                        lambda pdb, pos, evs: calls.__setitem__("dir", pdb) or _FakeStorage())
    out = tmp_path / "o.csv"
    res = CliRunner().invoke(main, ["evaluate", "--fps", "f.json", "--pdb-dir", "/some/dir",
                                    "--output", str(out)])
    assert res.exit_code == 0, res.output
    assert calls["dir"] == "/some/dir"
    assert out.exists()


def test_evaluate_cli_top_traj_dispatches_to_trajectory(tmp_path, monkeypatch):
    evaluate = _stub_evaluate_env(monkeypatch)
    calls = {}
    monkeypatch.setattr(evaluate, "evaluate_trajectory",
                        lambda top, traj, pos, evs: calls.__setitem__("traj", (top, traj)) or _FakeStorage())
    out = tmp_path / "o.csv"
    res = CliRunner().invoke(main, ["evaluate", "--fps", "f.json", "--top", "T.pdb",
                                    "--traj", "J.xtc", "--output", str(out)])
    assert res.exit_code == 0, res.output
    assert calls["traj"] == ("T.pdb", "J.xtc")


def test_evaluate_cli_no_input_errors(tmp_path, monkeypatch):
    _stub_evaluate_env(monkeypatch)
    out = tmp_path / "o.csv"
    res = CliRunner().invoke(main, ["evaluate", "--fps", "f.json", "--output", str(out)])
    assert res.exit_code != 0
    assert "Provide one of" in res.output


# --------------------------------------------------------------------------------------
# R09 — --av-backend routes into the imp-dock request
# --------------------------------------------------------------------------------------
def test_imp_dock_passes_av_backend(monkeypatch):
    from ..api import operations as ops
    captured = {}
    monkeypatch.setattr(ops, "dock", lambda req, **k: (captured.update(req), {"status": "ok"})[1])
    res = CliRunner().invoke(main, ["imp", "dock", "--pdb", "a.pdb", "--fps", "f.json",
                                    "--out", "/o", "--av-backend", "labellib"])
    assert res.exit_code == 0, res.output
    assert captured["av_backend"] == "labellib"
