"""All three surfaces of the burstwise_import plugin work: API, CLI, GUI.

The API is the single implementation; the CLI and the RPC services are thin
layers over it and the GUI wraps the same core module. What these tests pin
is the wiring — that each entrypoint loads, dispatches, and returns — plus
one end-to-end CLI conversion against the real legacy sample.
"""

from __future__ import annotations

import pathlib
from types import SimpleNamespace

import pytest

from chisurf.core.plugin import load_manifest

PLUGIN_DIR = pathlib.Path(__file__).resolve().parents[1]
MANIFEST = PLUGIN_DIR / "manifest.json"
SAMPLE = (
    pathlib.Path.home()
    / ".hermes"
    / "cache"
    / "scratch"
    / "burstwise_samples"
    / "burstwise_All 0.1066#60"
)


# -- manifest carries all three entrypoints --------------------------------------


def test_manifest_declares_cli_services_and_emtk():
    m = load_manifest(MANIFEST)
    assert m.id == "burstwise_import"
    entry = m.entrypoints
    assert entry.cli == "chisurf.plugins.burst.burstwise_import.cli.main:cli"
    assert (
        entry.services
        == "chisurf.plugins.burst.burstwise_import.backend.services:register_services"
    )
    assert entry.emtk == "chisurf.plugins.burst.burstwise_import.gui.app:create_app"


# -- API --------------------------------------------------------------------------


def test_api_settings_from_dict_roundtrip():
    from chisurf.plugins.burst.burstwise_import.api import settings_from_dict

    s = settings_from_dict(
        {"source_mode": "mti_prefix", "dry_run": True, "mti_prefix_map": {"N:\\": "/data/"}}
    )
    assert s.source_mode == "mti_prefix"
    assert s.dry_run is True
    assert s.mti_prefix_map == {"N:\\": "/data/"}


def test_api_resolver_beside_mode(tmp_path: pathlib.Path):
    from chisurf.plugins.burst.burstwise_import.api import ImportSettings, make_resolver

    # primary layout: <stem>.ht3 in the PARENT of the burstwise folder
    (tmp_path / "stemA.ht3").write_bytes(b"x")
    folder = tmp_path / "burstwise_x"
    folder.mkdir()
    r = make_resolver(folder, ImportSettings(source_mode="beside"))
    assert r("stemA", {}) == tmp_path / "stemA.ht3"
    assert r("missing", {}) is None

    # fallback: instrument file inside the folder itself
    (folder / "stemB.spc").write_bytes(b"x")
    assert r("stemB", {}) == folder / "stemB.spc"


def test_api_resolver_mti_prefix_mode(tmp_path: pathlib.Path):
    from chisurf.plugins.burst.burstwise_import.api import ImportSettings, make_resolver

    real = tmp_path / "day" / "stemA.ht3"
    real.parent.mkdir()
    real.write_bytes(b"x")
    settings = ImportSettings(
        source_mode="mti_prefix", mti_prefix_map={"N:\\Singlem\\": str(tmp_path) + "/"}
    )
    mti = {"N:\\Singlem\\day\\stemA.ht3": 42.0}
    r = make_resolver(tmp_path, settings, mti)
    assert r("stemA", mti) == real


@pytest.mark.skipif(not SAMPLE.is_dir(), reason="pulled burstwise sample not present")
def test_api_import_folder_reports_stems():
    from chisurf.plugins.burst.burstwise_import.api import import_folder

    report = import_folder(SAMPLE, {"source_mode": "none"})
    assert len(report.stems) == 87
    assert not report.containers  # nothing resolved -> nothing written


# -- CLI --------------------------------------------------------------------------


def test_cli_group_loads_and_has_commands():
    from chisurf.plugins.burst.burstwise_import.cli import cli

    names = {c.name for c in cli.commands.values()}
    assert {"convert", "scan"} <= names


def test_cli_scan_runs_on_sample(capsys):
    pytest.importorskip("click")
    from click.testing import CliRunner

    from chisurf.plugins.burst.burstwise_import.cli import cli

    runner = CliRunner()
    res = runner.invoke(cli, ["scan", str(SAMPLE)])
    assert res.exit_code == 0, res.output
    assert "stems: 87" in res.output


@pytest.mark.skipif(not SAMPLE.is_dir(), reason="pulled burstwise sample not present")
def test_cli_convert_end_to_end(tmp_path: pathlib.Path):
    """One-stem mini-copy of the sample, a stand-in TTTR beside it, convert."""
    import shutil

    pytest.importorskip("click")
    from click.testing import CliRunner

    from chisurf.plugins.burst.burstwise_import.cli import cli

    stem = "Split_44_132_75murea_sm-0000"
    day = tmp_path / "exp"
    work = day / "mini"
    for sub, ext in (("bi4_bur", ".bur"), ("bg4", ".bg4"), ("br4", ".br4"), ("BIDs", ".ht3.bst")):
        (work / sub).mkdir(parents=True)
        shutil.copy(SAMPLE / sub / f"{stem}_0{ext}", work / sub / f"{stem}_0{ext}")
    shutil.copytree(SAMPLE / "Info", work / "Info")
    # stand-in instrument file in the measurement folder -> 'beside' resolves
    tttr = pathlib.Path(__file__).resolve().parents[5] / "test" / "data" / "clsm" / "Leica_SP5.ptu"
    shutil.copy(tttr, day / f"{stem}.ht3")

    out_dir = tmp_path / "pto"
    runner = CliRunner()
    res = runner.invoke(cli, ["convert", str(work), "--source-mode", "beside", "-o", str(out_dir)])
    assert res.exit_code == 0, res.output
    # one container per MEASUREMENT folder ("exp" here), named after it
    assert (out_dir / "exp.mmfdb.pto").is_file(), res.output


# -- RPC services -----------------------------------------------------------------


def test_services_register_and_dispatch():
    from chisurf.plugins.burst.burstwise_import.backend.services import register_services

    registered = {}

    class Dispatcher(SimpleNamespace):
        def register(self, name, handler):
            registered[name] = handler

    register_services(Dispatcher())
    assert "burstwise_import.jobs.import_folder" in registered
    assert "burstwise_import.contract.describe" in registered

    contract = registered["burstwise_import.contract.describe"]({})
    assert contract["status"] == "ok"
    assert contract["result"]["plugin"] == "burstwise_import"

    missing = registered["burstwise_import.jobs.import_folder"]({})
    assert missing["status"] == "error"


# -- GUI ---------------------------------------------------------------------------


def test_gui_create_app_returns_imtk_app():
    emtk_app = pytest.importorskip("emtk.app").ImApp
    from chisurf.plugins.burst.burstwise_import.gui.app import create_app

    app = create_app()
    assert isinstance(app, emtk_app)
