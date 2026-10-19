"""The deposit tool's model: review drives the gate, the gate drives the buttons.

Uses the same fake Zenodo as mmfdb's own deposit tests (no network), and a
small record built in a temporary data root.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

import pytest

pytest.importorskip("mmfdb.deposit")

from mmfdb.deposit import ZenodoClient  # noqa: E402

from chisurf.plugins.core.zenodo_deposit.gui.model import ZenodoDepositModel  # noqa: E402


class FakeZenodo:
    class R:
        def __init__(self, code, body=None):
            self.status_code, self._b = code, body
            self.content = b"" if body is None else b"1"
            self.text = json.dumps(body)

        def json(self):
            return self._b

    def __init__(self):
        self.files = {}

    def _dep(self):
        return {"id": 9, "state": "unsubmitted", "links": {"bucket": "https://z/bucket/9"}}

    def post(self, url, json=None, headers=None):
        return self.R(201, self._dep())

    def put(self, url, data=None, json=None, headers=None):
        if "/bucket/" in url:
            self.files[url.rsplit("/", 1)[1]] = data.read()
            return self.R(201, {})
        return self.R(200, self._dep())

    def get(self, url, headers=None, params=None):
        if url.endswith("/files"):
            return self.R(200, [{"filename": n, "checksum": hashlib.md5(b).hexdigest(),
                                 "filesize": len(b), "id": n} for n, b in self.files.items()])
        return self.R(200, self._dep())

    def delete(self, url, headers=None):
        return self.R(204)


@pytest.fixture()
def fake() -> FakeZenodo:
    return FakeZenodo()


@pytest.fixture()
def model(tmp_path: Path, monkeypatch, fake: FakeZenodo) -> ZenodoDepositModel:
    root = tmp_path / "records"
    rec = root / "t4l-demo"
    for rel, data in {
        "measurements/2014-08-12_7.5M-urea/Split-0000.ht3": b"photons",
        "calibrations/2014-08-12_pq-hydraharp/h2o-scatter-irf/Split_irf-0000.ht3": b"irf",
        "README.md": b"# demo\n",
    }.items():
        (rec / rel).parent.mkdir(parents=True, exist_ok=True)
        (rec / rel).write_bytes(data)
    monkeypatch.setenv("MMFDB_DEPOSIT_ROOT", str(root))
    m = ZenodoDepositModel(client_factory=lambda base: ZenodoClient(token="t", session=fake))
    return m


def _wait(m: ZenodoDepositModel) -> None:
    for _ in range(200):
        m.poll()
        if not m.job.running:
            m.poll()
            return
        time.sleep(0.02)
    raise AssertionError("worker did not finish")


def test_an_unscanned_folder_is_listed_and_scanned_on_open(model):
    assert model.records == [{"name": "t4l-demo", "state": "not scanned", "review": "",
                              "remote": ""}]
    model.select_record(model.records[0])
    assert [r["id"] for r in model.items][:2] == [
        "measurements/2014-08-12_7.5M-urea",
        "calibrations/2014-08-12_pq-hydraharp/h2o-scatter-irf"]
    assert (model.record.folder.parent / "t4l-demo.deposit.json").is_file()


def test_review_opens_the_gate_and_upload_reaches_a_verified_draft(model, fake):
    model.select_record(model.records[0])
    assert not model.enabled("approve_item") and not model.enabled("upload_draft")
    model.build_package()
    _wait(model)
    for row in model.items:
        model.select_item(row)
        model.note = "checked"
        model.approve_item()
    assert model.enabled("upload_draft"), model.gate_text
    model.upload_draft()
    _wait(model)
    assert "md5 verified" in model.message, model.message
    assert "t4l-demo.zip" in fake.files
    assert "matches the package" in model.remote_text
    assert not model.enabled("publish_record")  # needs its own approval
    model.approve_publish()
    assert model.enabled("publish_record")


def test_a_change_after_approval_closes_the_gate_again(model):
    model.select_record(model.records[0])
    model.build_package()
    _wait(model)
    for row in model.items:
        model.select_item(row)
        model.approve_item()
    (model.record.folder / "README.md").write_text("# changed\n")
    model.rescan()
    assert not model.enabled("upload_draft")
    assert "Approved (changed)" not in [r["status"] for r in model.items]
    assert "Pending (changed)" in [r["status"] for r in model.items]


def test_the_item_text_puts_flags_first(model):
    model.select_record(model.records[0])
    model.record.item("README.md").flags = ["role inferred from Info_file *_10.dat"]
    model.select_item({"id": "README.md"})
    text = model.item_text
    assert text.index("Needs your check") < text.index("Holds")
    assert "`*_10.dat`" in text  # globs are shown as code, not read as emphasis


def test_open_in_ndx_offers_the_items_container(model):
    opened = []
    model._ndx_opener = opened.append
    model.select_record(model.records[0])
    meas = model.record.folder / "measurements/2014-08-12_7.5M-urea"
    (meas / "2014-08-12_7.5M-urea.mmfdb.pto").write_bytes(b"pto")
    model.select_item({"id": "README.md"})
    assert not model.enabled("open_in_ndx")
    model.select_item({"id": "measurements/2014-08-12_7.5M-urea"})
    assert model.enabled("open_in_ndx")
    model.open_in_ndx()
    assert opened == [meas / "2014-08-12_7.5M-urea.mmfdb.pto"]


def test_a_folder_is_listed_file_by_file_in_the_text_editor(model):
    model.select_record(model.records[0])
    model.select_item({"id": "measurements/2014-08-12_7.5M-urea"})
    assert model.editor_kind == "text"
    assert "Split-0000.ht3" in model.preview_txt and model.preview_cif == ""
