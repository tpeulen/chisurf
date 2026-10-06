"""Fixtures of the native MMFDB Admin tests: a seeded temporary MMFDB per test, hermetic.

Seeding (:func:`seeded_admin.seed`) takes a second or two, so it is done once per
session into a template folder; every test gets a copy of that folder and points
``CHISURF_SETTINGS_DIR`` / ``MMFDB_SETTINGS_DIR`` / ``MMFDB_DATABASE_PATH`` /
``MMFDB_OBJECT_STORE`` and ``HOME`` at it, so nothing reads or writes the user's own
settings, database or keyring. The client is the real in-process one (the real RPC
services, the real ACL), logged in as the bootstrap administrator; calls run inline
(:class:`~..gui.native.runner.InlineRunner`) so a test drives the app frame by frame.
"""

from __future__ import annotations

import shutil

import pytest

from . import seeded_admin as sa


@pytest.fixture(scope="session")
def seeded_template(tmp_path_factory):
    """A seeded MMFDB folder, made once (the tests copy it)."""
    folder = tmp_path_factory.mktemp("mmfdb_template")
    mp = pytest.MonkeyPatch()
    try:
        sa.use_folder(folder, mp)
        mp.setenv("HOME", str(folder))
        sa.seed(folder, sa.admin_client())
    finally:
        mp.undo()
    return folder


@pytest.fixture
def admin_folder(seeded_template, tmp_path, monkeypatch):
    """This test's own copy of the seeded database, with the environment pointed at it."""
    folder = tmp_path / "mmfdb"
    shutil.copytree(seeded_template, folder)
    sa.use_folder(folder, monkeypatch)
    monkeypatch.setenv("HOME", str(tmp_path))
    from chisurf.plugins.core.mmfdb_admin.gui import session

    monkeypatch.setattr(session, "_SESSION", dict(session._SESSION, user=None, token=None))
    return folder


@pytest.fixture
def client(admin_folder):
    return sa.admin_client()


@pytest.fixture
def admin(client):
    """A connected :class:`AdminModel` over the seeded database (calls inline)."""
    from chisurf.plugins.core.mmfdb_admin.gui.native.model import AdminModel
    from chisurf.plugins.core.mmfdb_admin.gui.native.runner import InlineRunner

    model = AdminModel(client=client, runner=InlineRunner())
    model.user = "admin"
    model.start()
    assert model.connected, model.status
    model.opened = []
    model.opener = model.opened.append
    yield model
    model.close()


@pytest.fixture
def app(client):
    """The native app over the seeded database, connected on its first frame."""
    from chisurf.plugins.core.mmfdb_admin.gui.app import MMFDBAdminApp
    from chisurf.plugins.core.mmfdb_admin.gui.native.runner import InlineRunner

    application = MMFDBAdminApp(client=client, runner=InlineRunner())
    application.model.user = "admin"
    application.model.opened = []
    application.model.opener = application.model.opened.append
    yield application
    application.close()


def answer(model, label: str = "yes") -> None:
    """Press *label* (an action name) on the top dialog."""
    dialog = model.dialog
    assert dialog is not None, "no dialog is open"
    getattr(dialog, label)()


def rows_by_id(panel) -> dict[str, dict]:
    return {r["_id"]: r for r in panel.rows}


__all__ = ["admin", "admin_folder", "answer", "app", "client", "rows_by_id", "seeded_template"]


def offline_app():
    """The app without a connection attempt (Qt-free / draw checks that must not touch a server)."""
    from chisurf.plugins.core.mmfdb_admin.gui.app import MMFDBAdminApp
    from chisurf.plugins.core.mmfdb_admin.gui.native.runner import InlineRunner

    return MMFDBAdminApp(runner=InlineRunner(), autoconnect=False)
