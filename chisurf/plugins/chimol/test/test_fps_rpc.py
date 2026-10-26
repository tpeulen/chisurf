"""The ChiMOL host's RPC: the fps.json plan and AV maps, answered in service envelopes.

The handlers moved here with the editor's move into ChiMOL (the fps_json_editor plugin is
gone); the document logic itself is chimol's and tested there (chimol tests/test_fps_payload.py).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from chisurf.plugins.chimol import rpc

POINTS = [[0.0, 0.0, 0.0, 1.0], [1.0, 0.0, 0.0, 2.0], [1.0, 1.0, 0.0, 3.0]]


def test_the_manifest_declares_every_handler_and_the_dispatcher_gets_them():
    manifest = json.loads((Path(rpc.__file__).with_name("manifest.json")).read_text())
    declared = {m["name"] for m in manifest["rpc_methods"]}
    assert declared == {
        rpc.METHOD_VALIDATE,
        rpc.METHOD_SUMMARIZE,
        rpc.METHOD_NORMALIZE,
        rpc.METHOD_FETCH_PDB,
        rpc.METHOD_SAVE_AV_MRC,
    }
    assert manifest["entrypoints"]["services"] == "chisurf.plugins.chimol.rpc:register_services"

    registered = {}

    class Dispatcher:
        def register(self, name, handler):
            registered[name] = handler

    rpc.register_services(Dispatcher())
    assert set(registered) == declared
    payload = {"Positions": {"A1": {}}, "Distances": {}}
    assert registered[rpc.METHOD_VALIDATE]({"payload": payload})["result"]["valid"]


def test_payload_handlers_answer_in_envelopes():
    pytest.importorskip("chimol")
    payload = {"Positions": {"A1": {}}, "Distances": {}}
    assert rpc.validate_handler(payload)["result"]["valid"]
    assert rpc.summarize_handler(payload)["result"]["n_positions"] == 1
    assert rpc.normalize_handler(payload)["result"]["payload"]["Positions"] == {"A1": {}}
    bad = {
        "Positions": {"A1": {}},
        "Distances": {"x": {"position1_name": "A1", "position2_name": "A2"}},
    }
    result = rpc.validate_handler(bad)["result"]
    assert not result["valid"] and "missing position" in result["errors"][0]


def test_a_bad_pdb_id_is_reported_not_raised():
    result = rpc.fetch_pdb_handler("148")
    assert not result.get("ok", False), result


def test_av_points_become_a_readable_mrc_map(tmp_path):
    mrcfile = pytest.importorskip("mrcfile")
    pytest.importorskip("IMP.bff")
    result = rpc.save_av_mrc_handler(str(tmp_path / "av_export"), POINTS, 1.0)
    assert result["ok"], result
    out = Path(result["result"]["path"])
    assert out.suffix == ".mrc" and out.is_file()
    with mrcfile.open(str(out)) as m:
        assert float(m.data.max()) == pytest.approx(3.0)


def test_a_bad_grid_step_is_reported_not_raised(tmp_path):
    pytest.importorskip("IMP.bff")
    result = rpc.save_av_mrc_handler(str(tmp_path / "bad"), POINTS, 0.0)
    assert not result.get("ok", False), result
