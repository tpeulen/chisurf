"""Adding files without an MMFDB login is not an error (no request per file, one notice).

MMFDB stores objects only for a signed-in user. Data Selection registered every added file, so on a fresh
profile (or the ALEX Suite's *Load example*) each file logged ``ERROR MMFDB RPC failed: mmfdb.objects.put:
Authentication required`` and was listed as an import *error*, although nothing was wrong: the file is used
from disk. Without a session the file is now skipped with one notice, and listed as "not signed in".
"""

from __future__ import annotations

import logging

from chisurf.plugins.burst.burst_analysis.gui.data_selection_app import (
    NOT_SIGNED_IN,
    BurstDataSelectionModel,
    _status,
)


class _Client:
    """An MMFDB client as the dataset picker makes one: ``token`` is ``None`` until someone signs in."""

    def __init__(self, token=None):
        self.token = token
        self.calls: list[str] = []

    def call(self, method, params):
        self.calls.append(method)
        if not self.token:
            raise RuntimeError("Authentication required")
        return {"object": {"object_uuid": "u1"}} if method == "mmfdb.objects.put" else {"raw_data": {}}


def _files(tmp_path, n=3):
    paths = []
    for i in range(n):
        path = tmp_path / f"m{i:03d}.spc"
        path.write_bytes(b"\0" * 64)
        paths.append(path)
    return paths


def test_files_added_without_a_login_send_nothing_and_log_no_error(tmp_path, caplog):
    client = _Client(token=None)
    model = BurstDataSelectionModel(client)
    with caplog.at_level(logging.INFO):
        model.add_paths(_files(tmp_path))

    assert client.calls == []  # no refused upload per file
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]
    notices = [r for r in caplog.records if NOT_SIGNED_IN in r.getMessage()]
    assert len(notices) == 1  # one notice, not one per file
    entries = list(model.imports.values())
    assert len(entries) == 3 and all(_status(e) == "not signed in" for e in entries)
    assert model.imported_count() == 0
    assert "not signed in" in model.status_text


def test_a_signed_in_client_still_registers_each_file(tmp_path):
    client = _Client(token="t")
    model = BurstDataSelectionModel(client)
    model.add_paths(_files(tmp_path, 2))
    assert client.calls.count("mmfdb.objects.put") == 2
    assert model.imported_count() == 2
    assert all(_status(e) == "in MMFDB" for e in model.imports.values())


def test_the_details_offer_import_now_for_a_file_that_was_not_registered(tmp_path):
    from emtk.testing import Driver

    from chisurf.plugins.burst.burst_analysis.gui.data_selection_app import make_app

    app = make_app(source=BurstDataSelectionModel(_Client(token=None)))
    driver = Driver(app, (1200, 800))
    driver.frame(2)
    app.files_dropped([str(p) for p in _files(tmp_path, 1)])
    driver.frame(3)
    drawn = [entry[5] for entry in driver.painter.texts]
    assert "Import now" in drawn and "Import again" not in drawn
