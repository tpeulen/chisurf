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


def _fill_metadata(m: ZenodoDepositModel) -> None:
    """Step 3 of Create, as a person types it."""
    m.meta_title = "T4L demo"
    m.meta_description = "Demo record."
    m.meta_creators = "Peulen, Thomas-Otavio; Stanford University"
    m.meta_keywords = "smFRET, demo"


def test_review_opens_the_gate_and_upload_reaches_a_verified_draft(model, fake):
    model.select_record(model.records[0])
    assert not model.enabled("approve_item") and not model.enabled("upload_draft")
    _fill_metadata(model)
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
    assert text.index("⚠ role inferred") < text.index("README.md")  # what to check comes first
    assert "`*_10.dat`" in text  # globs are shown as code, not read as emphasis
    row = next(r for r in model.items if r["id"] == "README.md")
    assert row["detail"].startswith("⚠ role inferred")  # the tooltip leads with the flag


def test_a_row_is_approved_from_its_button_and_undone_from_its_menu(model):
    model.select_record(model.records[0])
    model.select_item({"id": "README.md"})
    model.note = "typed for README"
    row = next(r for r in model.items if r["id"] == "measurements/2014-08-12_7.5M-urea")
    assert row["act"] == "Approve" and model.can_approve(row)
    model.approve_item(row)
    assert model.record.item("measurements/2014-08-12_7.5M-urea").status == "approved"
    assert model.item_id == "measurements/2014-08-12_7.5M-urea"  # the row acted on is the one shown
    row = next(r for r in model.items if r["id"] == "measurements/2014-08-12_7.5M-urea")
    assert row["act"] == "" and not model.can_approve(row) and model.can_decide(row)
    model.reset_item(row)
    assert model.record.item("measurements/2014-08-12_7.5M-urea").status == "pending"


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


def test_a_folder_lists_a_numbered_series_as_one_row(model):
    model.select_record(model.records[0])
    meas = model.record.folder / "measurements/2014-08-12_7.5M-urea"
    for n in (1, 2):
        (meas / f"Split-000{n}.ht3").write_bytes(b"ph")
    (meas / "Split-0001_10.dat").write_bytes(b"t")
    model.select_item({"id": "measurements/2014-08-12_7.5M-urea"})
    assert model.editor_kind == "listing" and model.preview_cif == ""
    rows = {r["key"]: r for r in model.item_files}
    top = rows["Split-{0000…0002}.ht3"]
    assert top["parent"] == "" and top["count"] == "3 files" and top["kind"] == "PicoQuant HT3 photons"
    assert rows["Split-0001.ht3"]["parent"] == "Split-{0000…0002}.ht3"
    assert rows["Split-0001_10.dat"]["parent"] == ""  # a series of one is a row of its own


def test_create_lists_configs_and_builds_through_the_project_commands(model, tmp_path):
    cfgs = tmp_path / "configs"
    cfgs.mkdir()
    (cfgs / "t4l-demo.json").write_text('{"record": "t4l-demo"}')
    (cfgs / "t4l-new.json").write_text('{"record": "t4l-new"}')
    model.configs_dir = str(cfgs)
    states = {r["name"]: r["state"] for r in model.configs}
    assert states == {"t4l-demo": "built, not scanned", "t4l-new": "not built"}
    ran = []

    class R:
        returncode, stdout, stderr = 0, "VERIFY_OK\n", ""

    model._runner = lambda cmd: ran.append(cmd) or R()
    model.select_config({"name": "t4l-new"})
    assert model.enabled("build_record") and '"t4l-new"' in model.config_text
    model.build_record()
    _wait(model)
    assert len(ran) == 2 and "t4l-new.json" in ran[0] and ran[1].endswith("t4l-new")
    assert "VERIFY_OK" in model.message


def test_a_failed_build_shows_its_output(model, tmp_path):
    cfgs = tmp_path / "configs"
    cfgs.mkdir()
    (cfgs / "x.json").write_text("{}")
    model.configs_dir = str(cfgs)

    class R:
        returncode, stdout, stderr = 1, "", "metadata.cif does not conform: ..."

    model._runner = lambda cmd: R()
    model.select_config({"name": "x"})
    model.build_record()
    _wait(model)
    assert "failed" in model.message and "does not conform" in model.build_log


def test_a_record_is_made_by_hand_in_four_steps(model, tmp_path):
    """New record -> add data -> Zenodo metadata -> scan, with no build script."""
    src = tmp_path / "raw"
    (src / "run").mkdir(parents=True)
    (src / "run" / "a-0000.ht3").write_bytes(b"photons")
    model.new_name = "Bad Name"
    assert not model.enabled("create_record")
    model.new_name, model.new_title = "k60-n132c", "T4L K60/N132C"
    assert model.enabled("create_record")
    model.create_record()
    assert model.record.name == "k60-n132c"
    assert "add data" in model.next_step
    assert not model.enabled("add_files")  # no item named yet
    model.add_name = "2014-08-12_0M-urea"
    model.add_files()
    assert model.pick == "files"  # the host shows its file dialog now
    model.add_paths([str(src / "run")])
    assert model.pick == "" and "1 linked" in model.message
    assert "Zenodo metadata" in model.next_step
    model.meta_creators = "Thomas Peulen"
    assert "Family, Given" in model.metadata_status
    _fill_metadata(model)
    assert model.metadata_status.startswith("**Complete.**")
    model.select_item({"id": "Zenodo metadata"})
    assert model.preview_kind == "json" and '"T4L demo"' in model.preview_json
    model.approve_item()
    model.meta_keywords = "smFRET, demo, edited"  # an edit voids the approval
    assert model.record.item("Zenodo metadata").status == "pending"


def test_a_layout_saved_with_the_panel_closed_still_shows_it(model):
    """The window was empty once its only panel had been closed and that layout saved."""
    from emtk.testing import Driver

    from chisurf.plugins.core.zenodo_deposit.gui.app import ZenodoDepositApp

    app = ZenodoDepositApp(model)
    app.docks.hide("deposit")
    assert not app.docks.window("deposit").visible
    ui = Driver(app, (1200, 800))
    ui.frame(3)
    texts = [t[5] for t in ui.painter.texts]
    assert "0 · Create" in texts and "×" not in texts


def test_approve_all_leaves_rejections_and_failed_checks(model):
    model.select_record(model.records[0])
    rec = model.record
    rec.set_review("README.md", "rejected", "wrong title")
    failing = rec.items[0]
    failing.errors = ["checksum mismatch"]
    open_ = [i.id for i in rec.items if i.id != "README.md" and not i.errors
             and i.status != "approved"]
    assert model.approve_all_label() == f"Approve all ({len(open_)})"
    model.approve_all()
    assert all(rec.item(i).status == "approved" for i in open_)
    assert rec.item("README.md").review.status == "rejected"
    assert rec.item(open_[0]).review.note == "approve all"


def test_a_markdown_file_is_previewed_rendered_or_as_source(model):
    model.select_record(model.records[0])
    model.select_item({"id": "README.md"})
    assert model.md_view == "preview" and model.preview_md_rendered
    model.md_mode = "Source"
    assert model.md_view == "source" and not model.preview_md_rendered and model.preview_md
    model.select_item({"id": "metadata.cif"})
    assert model.md_view == ""


def test_calibrations_are_nested_under_the_measurements_that_use_them(model):
    model.select_record(model.records[0])
    rec = model.record
    irf = "calibrations/2014-08-12_pq-hydraharp/h2o-scatter-irf"
    meas = "measurements/2014-08-12_7.5M-urea"
    rec.item(meas).uses = [irf]
    rows = model.items
    keys = [r["key"] for r in rows]
    assert keys.index(meas) + 1 == keys.index(f"{meas}>{irf}")
    child = rows[keys.index(f"{meas}>{irf}")]
    assert child["parent"] == meas and child["id"] == irf
    assert child["item"] == "2014-08-12_pq-hydraharp/h2o-scatter-irf"
    assert irf not in keys  # listed under its measurement, not again on its own
    assert meas in model.expanded
    model.approve_item(child)  # a decision on the nested row is on the one item
    assert rec.item(irf).status == "approved"


def test_an_approval_takes_the_warning_off_its_row(model):
    model.select_record(model.records[0])
    model.record.item("README.md").flags = ["role inferred"]
    row = next(r for r in model.items if r["id"] == "README.md")
    assert row["flags"] == "⚠ 1"
    model.approve_item(row)
    row = next(r for r in model.items if r["id"] == "README.md")
    assert row["flags"] == "" and "✓ checked: role inferred" in row["detail"]
    assert "⚠" not in model.item_text and "✓ checked: role inferred" in model.item_text


def test_drawing_the_window_never_reads_the_keychain(model, monkeypatch):
    """Every frame asks where the token comes from; only a press may launch the keychain."""
    from mmfdb.deposit import credentials

    reads = []
    monkeypatch.setattr(credentials, "_KNOWN", {})
    monkeypatch.setattr(credentials._store, "load_session_token",
                        lambda h, p, u: reads.append(h) or "kept")
    monkeypatch.delenv("ZENODO_TOKEN", raising=False)
    model.select_record(model.records[0])
    for _ in range(20):
        model.next_step, model.token_text, model.upload_hint  # noqa: B018 -- drawn values
        [model.enabled(n) for n in ("test_token", "forget_token", "upload_draft")]
    assert reads == []
    assert model.token_source == credentials.UNCHECKED
    assert "not looked up yet" in model.token_text
    # the user's press reads it -- in the worker -- and the window then knows
    model._client_factory = lambda base: ZenodoClient(base=base, session=FakeZenodo())
    model.test_token()
    _wait(model)
    assert reads and model.token_source == "keychain"


def test_a_running_job_shows_a_modal_progress_window(model):
    import threading

    from emtk.testing import Driver

    from chisurf.plugins.core.zenodo_deposit.gui.app import ZenodoDepositApp

    model.select_record(model.records[0])
    release = threading.Event()
    model._run("uploading the draft", lambda: release.wait(5) and "uploaded")
    app = ZenodoDepositApp(model)
    ui = Driver(app, (1200, 800))
    ui.frame(2)
    texts = " ".join(t[5] for t in ui.painter.texts)
    assert "Uploading the draft" in texts and "elapsed" in texts
    assert "Cancel" not in texts  # an upload runs to its end
    release.set()
    _wait(model)
    ui.frame(2)
    assert "elapsed" not in " ".join(t[5] for t in ui.painter.texts)
    assert model.message == "uploaded"
