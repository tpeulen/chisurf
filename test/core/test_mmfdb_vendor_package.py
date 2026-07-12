"""Regression tests for the vendored MMFDB package boundary."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_mmfdb_canonical_import_exports_repository():
    """The vendored package is importable as ``mmfdb``."""
    import mmfdb
    from mmfdb.repository import MFDatabase

    assert mmfdb.MFDatabase is MFDatabase


def test_chisurf_compatibility_facade_is_removed():
    """Prerelease callers use the canonical package without import aliasing."""
    assert not (ROOT / "chisurf" / "core" / "mmfdb").exists()


def test_mmfdb_extraction_boundary_modules_do_not_import_chisurf():
    """No module in the standalone package may import the ChiSurf host."""
    package = ROOT / "modules" / "mmfdb" / "src" / "mmfdb"
    offenders: list[str] = []
    for path in package.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(), filename=str(path))):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            if any(name == "chisurf" or name.startswith("chisurf.") for name in names):
                offenders.append(f"{path.relative_to(ROOT)}:{node.lineno}")

    assert offenders == []


def test_chisurf_owns_host_specific_mmfdb_service_binding():
    """ChiSurf integrations live outside MMFDB and inject host-only workflows."""
    source = (ROOT / "chisurf" / "core" / "mmfdb_services.py").read_text()
    assert "from mmfdb.admin.backend.services import register_services" in source
    assert "from chisurf.core.pipeline import" in source
    assert "burst_selection_runner=" in source


def test_mmfdb_admin_uses_chisurf_binding_over_standalone_backend():
    """The host entrypoint injects ChiSurf workflows into the MMFDB backend."""
    import json

    manifest = json.loads(
        (ROOT / "chisurf" / "plugins" / "core" / "mmfdb_admin" / "manifest.json").read_text()
    )
    assert manifest["entrypoints"]["gui"] == "chisurf.plugins.core.mmfdb_admin.gui.tool:MMFDBWidget"
    assert manifest["entrypoints"]["services"] == "chisurf.core.mmfdb_services:register_services"

    host_source = (
        ROOT / "chisurf" / "plugins" / "core" / "mmfdb_admin" / "backend" / "services.py"
    ).read_text()
    assert "from mmfdb.admin.backend.services import *" in host_source
    assert "from chisurf.core.mmfdb_services import register_services" in host_source


def test_mmfdb_admin_manifest_declares_registered_methods():
    """The MMFDB Admin manifest should declare every registered RPC method."""
    import json

    from chisurf.core.mmfdb_services import register_services
    from chisurf.server.dispatcher import ServiceDispatcher
    from chisurf.server.session import SessionState

    manifest = json.loads(
        (ROOT / "chisurf" / "plugins" / "core" / "mmfdb_admin" / "manifest.json").read_text()
    )
    declared = {item["name"] for item in manifest.get("rpc_methods", [])}
    dispatcher = ServiceDispatcher(SessionState())
    register_services(dispatcher)
    registered = set(dispatcher.list_methods())

    assert sorted(registered - declared) == []
    assert sorted(declared - registered) == []
