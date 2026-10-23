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
        self.files, self.published, self.reserved = {}, False, False

    def _dep(self):
        meta = {"prereserve_doi": {"doi": "10.5281/zenodo.9", "recid": 9}} if self.reserved else {}
        return {"id": 9, "state": "done" if self.published else "unsubmitted", "metadata": meta,
                "doi": "10.5281/zenodo.9" if self.published else "",
                "links": {"bucket": "https://z/bucket/9"}}

    def post(self, url, json=None, headers=None):
        self.reserved |= bool(((json or {}).get("metadata") or {}).get("prereserve_doi"))
        if url.endswith("/actions/publish"):
            self.published = True
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
    m = ZenodoDepositModel(client_factory=lambda base: ZenodoClient(base=base, token="t", session=fake))
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
                              "remote": "", "pick": False}]
    model.select_record(model.records[0])
    # the item ids, with the files interleaved as their children in the tree
    assert [r["id"] for r in model.items if not r.get("file")][:2] == [
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
    assert model.upload_label() == "Draft is up to date" and not model.enabled("upload_draft")
    assert "| new | 9 |" in model.uploads_text


def test_the_upload_tab_shows_the_plan_before_anything_is_sent(model, fake):
    model.select_record(model.records[0])
    _fill_metadata(model)
    model.build_package()
    _wait(model)
    for row in model.items:
        model.select_item(row)
        model.note = "checked"
        model.approve_item()

    # before the first upload: every file is named as to-be-sent
    rows = {(r["file"], r["action"]) for r in model.preflight_rows}
    assert rows == {("t4l-demo.zip", "→ upload"), ("README.md", "→ upload")}
    assert "First upload" in model.preflight_text and "2 new file(s)" in model.preflight_text
    assert "Nothing is on Zenodo yet." in model.preflight_text

    model.upload_draft()
    _wait(model)
    # after the verified upload: nothing left to send
    assert {r["action"] for r in model.preflight_rows} == {"= identical"}
    assert "nothing to send" in model.preflight_text

    # a changed record closes the gate AND names the changed file in the plan
    (model.record.folder / "README.md").write_text("# changed\n")
    model.rescan()
    for row in model.items:
        model.select_item(row)
        model.approve_item()
    model.build_package()
    _wait(model)
    by_file = {r["file"]: r for r in model.preflight_rows}
    assert by_file["t4l-demo.zip"]["action"] == "→ replace"
    assert by_file["README.md"]["action"] == "→ replace"
    assert "replace 2" in model.preflight_text


def test_publishing_asks_three_times(model, fake):
    test_review_opens_the_gate_and_upload_reaches_a_verified_draft(model, fake)
    model.publish_record()
    assert model.publish_question()[2] == "Yes, publish (1/3)"
    model.cancel_publish()
    assert model.publish_stage == 0 and not fake.published
    model.publish_record()
    model.confirm_publish()
    assert model.publish_question()[2] == "Yes, I am sure (2/3)"
    model.confirm_publish()
    assert model.publish_question()[2] == "Publish now (3/3)"
    assert not fake.published and not model.job.running
    model.confirm_publish()
    _wait(model)
    assert fake.published and "DOI 10.5281/zenodo.9" in model.message
    assert model.publish_question() == ("", "", "")
    assert model.upload_label() == "Upload new version"


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
    assert "Add data" in model.next_step
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


def test_the_review_tree_draws_the_files(model):
    """Tab 2 is one tree: item rows carry their files; no separate file table."""
    from emtk.testing import Driver

    from chisurf.plugins.core.zenodo_deposit.gui.app import ZenodoDepositApp

    app = ZenodoDepositApp(model)
    ui = Driver(app, (1400, 900))
    model.select_record(next(r for r in model.records if r["name"] == "t4l-demo"))
    ui.click("2 · Review")
    ui.frame(2)
    texts = [t[5] for t in ui.painter.texts]
    assert "measurements/2014-08-12_7.5M-urea" in texts
    assert any(t.strip().startswith("Split-0000.ht3") for t in texts), "file row not drawn"
    # the old separate table (its Type column header) is gone
    assert "Type" not in texts


def test_flipping_the_sandbox_switch_keeps_the_states_apart(model, fake):
    """A sandbox trial run never mixes into what the tool knows of production."""
    model.select_record(model.records[0])
    _fill_metadata(model)
    model.build_package()
    _wait(model)
    for row in model.items:
        model.select_item(row)
        model.approve_item()

    # trial run on the sandbox
    model.sandbox = True
    assert model.upload_label() == "Upload draft" and "Nothing is on Zenodo yet." in model.preflight_text
    model.upload_draft()
    _wait(model)
    assert "md5 verified" in model.message
    assert "matches the package" in model.remote_text
    assert {r["action"] for r in model.preflight_rows} == {"= identical"}

    # back on production: nothing was uploaded there, nothing is claimed
    model.sandbox = False
    assert model.upload_label() == "Upload draft"
    assert "Zenodo: not uploaded." in model.remote_text
    assert "Nothing is on Zenodo yet." in model.preflight_text
    assert all(r["action"] == "→ upload" for r in model.preflight_rows)

    # and the sandbox state is still there when the switch goes back
    model.sandbox = True
    assert "matches the package" in model.remote_text


def test_the_plan_panel_draws_with_its_table(model):
    """The upload tab opens on the Before-upload plan; its table scrolls."""
    from emtk.testing import Driver

    from chisurf.plugins.core.zenodo_deposit.gui.app import ZenodoDepositApp

    app = ZenodoDepositApp(model)
    ui = Driver(app, (1400, 900))
    model.select_record(next(r for r in model.records if r["name"] == "t4l-demo"))
    model.build_package()
    _wait(model)
    for row in model.items:
        model.select_item(row)
        model.approve_item()
    ui.click("3 · Upload")
    ui.frame(2)
    texts = [t[5] for t in ui.painter.texts]
    assert "Before upload" in texts, "the plan panel is not drawn"
    assert "First upload" in " ".join(texts), "the plan line is not drawn"
    assert any(t.startswith("t4l-demo.zip") for t in texts), "the plan table is not drawn"


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
    assert "1 · Create" in texts and "×" not in texts


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
    model._files_of = {}  # the shown files follow the new nesting
    rows = model.items
    keys = [r["key"] for r in rows]
    # the calibration nests under its measurement (which now also carries its files)
    assert keys.index(meas) < keys.index(f"{meas}>{irf}")
    child = rows[keys.index(f"{meas}>{irf}")]
    assert child["parent"] == meas and child["id"] == irf
    assert child["item"] == "2014-08-12_pq-hydraharp/h2o-scatter-irf"
    assert irf not in keys  # listed under its measurement, not again on its own
    assert meas in model.expanded
    model.approve_item(child)  # a decision on the nested row is on the one item
    assert rec.item(irf).status == "approved"


def test_the_files_live_in_the_review_tree(model):
    """A folder item's files are its children; a series is one foldable row;
    double click opens a file in the modal, not the separate table of old."""
    model.select_record(model.records[0])
    meas = "measurements/2014-08-12_7.5M-urea"
    rows = {r["key"]: r for r in model.items}
    file_row = rows[f"{meas}|Split-0000.ht3"]
    assert file_row["parent"] == meas and file_row["id"] == meas
    assert file_row["item"].strip() == "Split-0000.ht3"
    assert file_row["role"] == "PicoQuant HT3 photons"
    # selecting a file row selects its item
    model.select_item(file_row)
    assert model.item.id == meas
    # a double click opens the file in the modal viewer
    model.open_tree_row(file_row)
    assert model.file_view["kind"] == "tttr" and model.file_view["title"] == "Split-0000.ht3"
    # an item row keeps opening ndX
    opened = []
    model._ndx_opener = opened.append
    (model.record.folder / meas / "2014-08-12_7.5M-urea.mmfdb.pto").write_bytes(b"pto")
    model.open_tree_row(rows[meas])
    assert opened and opened[0].name.endswith(".mmfdb.pto")


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


def test_a_doi_is_reserved_from_the_upload_tab(model, fake):
    model.select_record(model.records[0])
    _fill_metadata(model)
    assert not model.enabled("reserve_doi_action")  # the metadata is not approved yet
    model.approve_item({"id": "Zenodo metadata", "act": "Approve"})
    assert model.enabled("reserve_doi_action")
    model.reserve_doi_action()
    _wait(model)
    assert "10.5281/zenodo.9" in model.message
    assert "Reserved DOI:** `10.5281/zenodo.9`" in model.reserved_doi_text
    assert not model.enabled("reserve_doi_action")


def test_the_example_config_is_edited_and_saved_as_a_new_config(model, tmp_path):
    model.configs_dir = str(tmp_path / "configs")
    model.show_example()
    example = json.loads(model.config_edit)
    assert example["record"] == "example-t4l-s44-n132c-2014" and example["units"]
    assert model.config_status.startswith("Unsaved") and not model.enabled("build_record")
    model.config_edit = model.config_edit.replace("example-t4l-s44-n132c-2014", "Bad Name")
    assert '"record" is not a record name' in model.config_status
    assert not model.enabled("save_config")
    model.config_edit = "{ not json"
    assert model.config_status.startswith("**Not valid JSON")
    model.config_edit = json.dumps(dict(example, record="t4l-k60-n132c"), indent=2)
    model.save_config()
    saved = tmp_path / "configs" / "t4l-k60-n132c.json"
    assert json.loads(saved.read_text())["record"] == "t4l-k60-n132c"
    assert model.config_name == "t4l-k60-n132c" and model.config_draft is None
    assert model.enabled("build_record")
    model.show_example()
    model.config_edit = json.dumps(dict(example, record="t4l-k60-n132c"))
    assert "exists already" in model.config_status  # another config is never overwritten


def test_an_experiment_of_the_local_mmfdb_is_added_as_a_measurement(model, tmp_path):
    raw = tmp_path / "lab" / "148L_tcspc_001.ptu"
    raw.parent.mkdir()
    raw.write_bytes(b"photons")

    class Client:
        def list_experiments(self):
            return [{"experiment_id": "148L tcspc/001", "sample_id": "148L_65_141",
                     "project_id": "demo", "started_at": "2026-06-11T09:15:00"}]

        def get_experiment(self, exp_id):
            return {"experiment_id": exp_id, "data": [
                {"data_type": "tcspc", "storage_mode": "link", "file_path": str(raw)},
                {"data_type": "spectra", "storage_mode": "embedded"}]}

    model._mmfdb_factory = Client
    model.select_record(model.records[0])
    model.load_mmfdb()
    _wait(model)
    assert [r["sample"] for r in model.mmfdb_experiments] == ["148L_65_141"]
    model.select_mmfdb_experiment(model.mmfdb_experiments[0])
    assert model.enabled("add_from_mmfdb")
    model.add_from_mmfdb()
    _wait(model)
    assert "measurements/148L_tcspc_001" in [i.id for i in model.record.items], model.message
    assert (model.record.folder / "measurements/148L_tcspc_001/148L_tcspc_001.ptu").read_bytes() \
        == b"photons"
    assert "from mmfdb experiment 148L tcspc/001" in model.message


def test_an_unreachable_mmfdb_says_so(model):
    def down():
        raise RuntimeError("timeout: no response within 5000ms")

    model._mmfdb_factory = down
    model.load_mmfdb()
    _wait(model)
    assert "did not answer" in model.message and model.mmfdb_experiments == []


def test_the_record_table_says_what_is_uploaded_and_uploads_the_checked(model, fake):
    test_review_opens_the_gate_and_upload_reaches_a_verified_draft(model, fake)
    model.refresh_records()
    (row,) = model.records
    assert row["upload"] == "✓ uploaded, current" and row["last"]
    model.pick_record(row, "pick", True)
    assert model.upload_checked_label() == "Upload / update checked (0 of 1)"
    assert not model.enabled("upload_checked")  # current: nothing to send
    model.record.metadata["description"] = "Demo record, described better."
    from mmfdb.deposit.record import refresh_metadata_item

    refresh_metadata_item(model.record)
    model.record.approve("Zenodo metadata", by="tester")
    model.record.save()
    model.refresh_records()
    (row,) = model.records
    assert row["upload"] == "changed since upload" and row["pick"]
    assert model.enabled("upload_checked")
    model.upload_checked()
    _wait(model)
    assert "t4l-demo: update ok" in model.message, model.message
    model.refresh_records()
    assert model.records[0]["upload"] == "✓ uploaded, current"


def test_the_shared_metadata_editor_fills_a_record_and_opens_the_gate(model, fake):
    """The one metadata editor (core plugin) drives step 3 of Create."""
    from chisurf.plugins.core.metadata_editor.core import EditorModel, zenodo_schema

    model.select_record(model.records[0])
    editor = EditorModel(zenodo_schema(), model.metadata_values())
    editor.values["title"] = "T4L demo"
    editor.values["description"] = "Demo record."
    editor.values["creators"] = "Peulen, Thomas-Otavio; Stanford University"
    editor.values["keywords"] = "smFRET, demo"
    editor.values["upload_type"] = "dataset"
    model.apply_metadata(editor.entries())
    m = model.record.metadata
    assert m["title"] == "T4L demo" and m["upload_type"] == "dataset"
    assert m["keywords"] == ["smFRET", "demo"]
    assert m["creators"] == [{"name": "Peulen, Thomas-Otavio", "affiliation": "Stanford University"}]
    model.build_package()
    _wait(model)
    for row in model.items:
        model.select_item(row)
        model.note = "checked"
        model.approve_item()
    assert model.enabled("upload_draft"), model.gate_text


def _sandbox_trial(model: ZenodoDepositModel) -> None:
    """A verified draft on the sandbox, exactly as the plugin's flow builds it."""
    model.select_record(model.records[0])
    _fill_metadata(model)
    model.build_package()
    _wait(model)
    for row in model.items:
        model.select_item(row)
        model.approve_item()
    model.sandbox = True
    model.upload_draft()
    _wait(model)
    assert "md5 verified" in model.message, model.message


def test_approve_publish_unlocks_for_a_verified_sandbox_draft(model, fake):
    """The approve-publish gate reads THIS host's remote state. It used to read
    the flat ``remote["deposition_id"]`` that the per-host migration empties,
    so the button stayed grey forever and the GUI publish flow was dead."""
    _sandbox_trial(model)
    assert model.enabled("approve_publish"), model.remote_text
    model.approve_publish()
    assert model.enabled("publish_record"), model.gate_text
    # production has no draft: over there the gate stays shut
    model.sandbox = False
    assert not model.enabled("approve_publish")


def test_check_remote_reports_the_host_it_checked(model, fake):
    """Checking on the sandbox compares the sandbox draft; the compare used to
    run against production and claimed "not uploaded" about a verified draft."""
    _sandbox_trial(model)
    model.check_remote()
    _wait(model)
    assert "not uploaded" not in model.message, model.message
    assert "remote matches the package" in model.message, model.message


def test_a_record_with_a_quarantined_legacy_remote_says_so(model, fake):
    """A legacy flat remote is surfaced as waiting for a host -- not silently
    shown as just another 'not uploaded' record."""
    model.select_record(model.records[0])
    state = model.record.folder.parent / "t4l-demo.deposit.json"
    d = json.loads(state.read_text())
    d["remote"] = {"deposition_id": 624694, "state": "unsubmitted", "files": [],
                   "uploads": [{"at": "2026-10-22T10:00:00", "kind": "new",
                                "deposition_id": 624694, "md5": "x", "verified": True}]}
    state.write_text(json.dumps(d))
    model.refresh_records()
    row = next(r for r in model.records if r["name"] == "t4l-demo")
    assert "legacy" in row["remote"], row
    model.select_record(row)
    text = model.remote_text
    assert "legacy" in text and "migrate-remote" in text, text
