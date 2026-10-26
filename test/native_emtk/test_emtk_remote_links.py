"""Linked MMFDB objects in the shell: a picked artifact is linked, a missing session shows a key.

The shell has no MMFDB session in tests, so the fetch after linking reports *sign-in needed* -- the
row's Source shows a key and the menu offers *Sign in to MMFDB…* and *Fetch again*. Locate missing
data finds an MMFDB copy by checksum. Both are rendered for inspection.
"""

from __future__ import annotations

import hashlib
from types import SimpleNamespace

import pytest
from emtk.testing import Driver

from chisurf.emtk.fit_docks import DATASETS_KEY
from test.native_emtk.test_emtk_shell_fits import (  # noqa: F401  (the fixture and the helpers)
    SHOTS,
    _idle,
    _settle,
    shell,
)

mmfdb_links = pytest.importorskip("mmfdb.links")

DATA = b"photons " * 512
SHA = hashlib.sha256(DATA).hexdigest()


def _rows(shell):  # noqa: F811
    return [r for r in shell.data.datasets.datasets if r.get("kind") == "photons"]


def test_a_picked_mmfdb_artifact_is_linked_and_asks_for_a_sign_in(shell, monkeypatch):  # noqa: F811
    from chisurf.core.project import remote_links

    monkeypatch.setattr(remote_links, "_STATE", {})

    def no_session(server=""):
        raise mmfdb_links.LinkError("no MMFDB session for https://mmfdb.lab.example (log in first)")

    monkeypatch.setattr(mmfdb_links, "default_transport", no_session)
    monkeypatch.setattr(remote_links, "server_of", lambda uri: "https://mmfdb.lab.example")
    driver = Driver(shell, (1300, 900))
    driver.frame(4)
    selection = SimpleNamespace(
        artifact_id="42",
        label="m000.spc",
        metadata={"checksum": SHA, "size_bytes": len(DATA), "original_filename": "m000.spc"},
    )
    assert shell.data.link_selection(selection)
    _settle(
        driver,
        lambda: (
            _idle(shell)
            and not shell.data._fetch_jobs
            and _rows(shell)
            and _rows(shell)[0]["source"].startswith("🔑")
        ),
        "the linked artifact waiting for a sign-in",
    )
    (row,) = _rows(shell)
    assert row["source_address"].startswith("mmfdb://artifact/42")
    assert "sign-in needed for https://mmfdb.lab.example" in row["source_address"]
    assert shell.data.datasets.can_sign_in() and shell.data.datasets.can_fetch_again()
    shell.docks.focus(DATASETS_KEY)
    shell.data.datasets.select_dataset(row)
    driver.frame(4)
    driver.screenshot(SHOTS / "datasets_sign_in_needed.png")


def test_locate_lists_an_mmfdb_copy(tmp_path):
    from chisurf.core.project import links
    from chisurf.plugins.core.project_data.gui.app import ProjectDataApp, ProjectDataModel

    class Server:
        base_url = "https://mmfdb.lab.example"

        async def rpc(self, method, params):
            return {
                "objects": [
                    {
                        "object_uuid": "0f1e2d3c",
                        "content_sha256": SHA,
                        "original_filename": "m000.spc",
                    }
                ]
            }

    gone = tmp_path / "data" / "m000.spc"
    gone.parent.mkdir()
    gone.write_bytes(DATA)
    link = links.add_link(gone)
    gone.unlink()
    dataset = SimpleNamespace(
        unique_identifier="d1",
        name="m000.spc",
        link=link,
        address=str(gone),
        link_status="missing",
        link_problem="m000.spc was not found where it was linked",
    )
    source = SimpleNamespace(
        linked_datasets=lambda: [dataset], project_path=lambda: None, changed=lambda: None
    )
    model = ProjectDataModel(source)
    model.refresh()
    model.select_dataset(model.dataset_rows()[0])
    rows = model.search_mmfdb(transport=Server())
    assert rows and rows[0]["mmfdb"]
    app = ProjectDataApp(model)
    driver = Driver(app, (980, 700))
    driver.frame(4)
    driver.screenshot(SHOTS / "locate_mmfdb_copy.png")
