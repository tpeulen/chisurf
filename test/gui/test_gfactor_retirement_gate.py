"""Caller acceptance gates for replacing the legacy G-factor widget with its native app.

The lifetime factory and shared detector launcher must construct the native host
without an obsolete Qt calculator import.
"""

from __future__ import annotations

import socket

import pytest
from qtpy import QtWidgets


@pytest.fixture(autouse=True)
def isolated_gfactor_callers(tmp_path, monkeypatch):
    """Keep caller construction local and prevent accidental daemon connections."""
    from mmfdb.config import configure_runtime, reset_runtime_config

    for key, path in {
        "CHISURF_SETTINGS_DIR": tmp_path / "settings",
        "MMFDB_SETTINGS_DIR": tmp_path / "mmfdb",
        "MMFDB_DATABASE_PATH": tmp_path / "mmfdb.db",
        "MMFDB_OBJECT_STORE": tmp_path / "objects",
    }.items():
        monkeypatch.setenv(key, str(path))
    configure_runtime(
        settings_dir=tmp_path / "mmfdb",
        database_path=tmp_path / "mmfdb.db",
        source_database_path=tmp_path / "missing.db",
        object_store_root=tmp_path / "objects",
    )

    def forbidden_connection(*args, **kwargs):
        raise AssertionError("G-factor caller attempted an external connection")

    monkeypatch.setattr(socket.socket, "connect", forbidden_connection)
    monkeypatch.setattr(socket, "create_connection", forbidden_connection)
    try:
        yield
    finally:
        reset_runtime_config()


@pytest.fixture
def native_host_type(qapp):
    """Resolve the lazy public ControlHost factory's actual QWidget type."""
    from emtk.qt_host import ControlHost

    from chisurf.plugins.vv_vh_g_factor.gui.app import GFactorApp

    probe = ControlHost(GFactorApp())
    try:
        return type(probe)
    finally:
        probe.close()
        qapp.processEvents()


def test_lifetime_factory_hosts_existing_native_app_and_preserves_qwidget_parent(
    qapp, native_host_type
):
    """The Qt-embeddable host wraps GFactorApp instead of constructing the retired UI."""
    from chisurf.plugins.vv_vh_g_factor.gui.app import GFactorApp, create_host

    parent = QtWidgets.QWidget()
    widget = create_host(parent=parent)
    try:
        assert isinstance(widget, native_host_type)
        assert isinstance(widget.control, GFactorApp)
        assert widget.parent() is parent
    finally:
        widget.close()
        parent.close()
        qapp.processEvents()


def test_detector_dynamic_export_launches_existing_native_host(qapp, native_host_type):
    """The detector launcher constructs the native host directly."""
    from chisurf.gui.widgets.wizard.tttr_channeldefinition.tttr_channel_definition_tttr_io import (
        _create_gfactor_host,
    )
    from chisurf.plugins.vv_vh_g_factor.gui.app import GFactorApp

    widget = _create_gfactor_host()
    try:
        assert isinstance(widget, native_host_type)
        assert isinstance(widget.control, GFactorApp)
    finally:
        widget.close()
        qapp.processEvents()
