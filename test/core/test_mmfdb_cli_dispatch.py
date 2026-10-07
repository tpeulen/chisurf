"""The manifest preserves the actual headless MMFDB curation command."""

from __future__ import annotations

import importlib
import json
import socket
from pathlib import Path

import pytest
from click.testing import CliRunner


@pytest.fixture
def isolated_cli(tmp_path, monkeypatch):
    """Use production discovery/dispatch with scratch settings and no user plugins/network."""
    cli_module = importlib.import_module("chisurf.core.cli")
    monkeypatch.setattr(cli_module, "_PLUGINS_REGISTERED", False)
    monkeypatch.setattr(cli_module.cli, "commands", {})
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "home"))
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "settings"))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "curation.sqlite"))
    monkeypatch.setenv("MMFDB_OBJECT_STORE_ROOT", str(tmp_path / "objects"))

    def forbidden(*args, **kwargs):
        """A local headless help/read command cannot contact a user daemon."""
        raise AssertionError("unexpected network access")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    return cli_module, tmp_path


def test_actual_manifest_route_dispatches_owning_fluorophore_help(isolated_cli, caplog):
    """The production csc route reaches the actual owning Click group and subcommands."""
    cli_module, scratch = isolated_cli
    owner = importlib.import_module("mmfdb.admin.cli")
    assert owner.cli.commands["list"].callback.__module__ == "mmfdb.admin.cli"
    result = CliRunner().invoke(cli_module.cli, ["fluorophore", "--help"])
    assert result.exit_code == 0, result.output
    assert "Manage and curate fluorophores" in result.output
    assert "import-reference-set" in result.output and "review-queue" in result.output
    assert "mmfdb_admin" not in caplog.text
    assert not (scratch / "curation.sqlite").exists()


def test_actual_manifest_route_reads_only_the_configured_scratch_database(isolated_cli):
    """Real list dispatch reads the owning repository instead of a replacement command."""
    from mmfdb.config import configure_runtime, reset_runtime_config
    from mmfdb.repository import MFDatabase

    cli_module, scratch = isolated_cli
    path = scratch / "curation.sqlite"
    configure_runtime(
        settings_dir=scratch / "settings",
        database_path=path,
        object_store_root=scratch / "objects",
        source_database_path=scratch / "missing.db",
    )
    try:
        with MFDatabase(path) as db:
            types = db.get_probe_types()
            if not types:
                db.dao.insert(
                    "probe_types", {"type_name": "organic_dye", "display_name": "Organic dye"}
                )
                types = db.get_probe_types()
            db.add_probe("ScratchCLIProbe", int(types[0]["type_id"]), category="organic_dye")
        result = CliRunner().invoke(cli_module.cli, ["fluorophore", "list", "--json"])
        assert result.exit_code == 0, result.output
        rows = json.loads(result.output)
        assert [row["chromophore_name"] for row in rows] == ["ScratchCLIProbe"]
        assert all(row["category"] == "organic_dye" for row in rows)
        assert not (scratch / "objects").exists()
    finally:
        reset_runtime_config()


def test_manifest_is_the_single_cli_authority():
    """The actual declaration owns its alias without redundant module metadata."""
    from chisurf.core.plugin import load_manifest

    path = Path(__file__).resolve().parents[2] / "chisurf/plugins/core/mmfdb_admin/manifest.json"
    manifest = load_manifest(path)
    assert manifest.entrypoints.cli == "fluorophore=mmfdb.admin.cli:cli"
    module = importlib.import_module("chisurf.plugins.core.mmfdb_admin")
    assert "cli_entrypoint" not in module.__dict__ and "cli_entrypoint" not in module.__all__
