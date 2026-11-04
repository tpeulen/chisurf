"""Post-session transfer: atomic copies, verification, no overwrite, resume, guarded move."""

from __future__ import annotations

import errno
import hashlib
import json
import pathlib

import pytest

from chisurf.plugins.core.acq.live import transfer as transfer_module
from chisurf.plugins.core.acq.live.transfer import (
    PART_SUFFIX,
    STATE_NAME,
    DestinationUnavailable,
    Progress,
    SessionTransfer,
    is_reachable,
)


def make_session(tmp_path, name="TP_20261030_JH_FluoresceinFCS"):
    """A session directory laid out like the MT200 writes one."""
    session = tmp_path / name
    session.mkdir()
    (session / "CF532_1.ptu").write_bytes(b"photons" * 1000)
    (session / "CF532_1.pck").write_bytes(b"package" * 200)
    (session / "CF532_1_OFCS.pqres").write_bytes(b"fcs result" * 50)
    group = session / "GroupMeas_1"
    group.mkdir()
    (group / "Trace_1.ptu").write_bytes(b"group trace" * 300)
    (session / "WSLogfile.sptl").write_bytes(b"workspace log")
    return session


def sha_of(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def archive(tmp_path):
    """A reachable archive root, like Z:\\microtime200 when the share is up."""
    root = tmp_path / "microtime200"
    root.mkdir()
    return root


def listen(phases):
    def callback(progress: Progress) -> None:
        phases.append(progress)
    return callback


# -- the happy path ------------------------------------------------------------

def test_copy_verifies_every_file_and_reports_it(tmp_path):
    session, root = make_session(tmp_path), archive(tmp_path)
    transfer = SessionTransfer(session, root)
    report = transfer.run()
    assert report.ok and not report.failures()
    copied = {result.rel: result for result in report.files}
    assert set(copied) == {"CF532_1.ptu", "CF532_1.pck", "CF532_1_OFCS.pqres",
                           "GroupMeas_1/Trace_1.ptu", "WSLogfile.sptl"}
    for result in report.files:
        assert result.status == "copied"
        assert result.destination.exists()
        assert result.sha256 == sha_of(result.destination)
    assert report.bytes_total == report.bytes_transferred > 0
    assert not list(root.rglob(f"*{PART_SUFFIX}"))


def test_report_document_is_written_and_checkable(tmp_path):
    session, root = make_session(tmp_path), archive(tmp_path)
    report = SessionTransfer(session, root).run()
    path = report.write(root / "transfer-report.json")
    document = json.loads(path.read_text(encoding="utf-8"))
    assert document["ok"] is True and document["moved"] is False
    assert len(document["files"]) == len(report.files)
    assert all(entry["sha256"] for entry in document["files"])


def test_progress_reports_accurate_byte_and_file_totals(tmp_path):
    session, root = make_session(tmp_path), archive(tmp_path)
    seen: list[Progress] = []
    report = SessionTransfer(session, root).run(progress=listen(seen))
    assert seen, "the callback was never invoked"
    assert seen[-1].phase == "done"
    assert seen[-1].bytes_done == report.bytes_total
    assert seen[-1].files_done == len(report.files)
    assert any(p.phase == "copying" and p.current_file for p in seen)
    assert max(p.bytes_done for p in seen) == report.bytes_total  # never beyond the total


def test_a_raising_progress_callback_cannot_break_the_transfer(tmp_path):
    session, root = make_session(tmp_path), archive(tmp_path)

    def angry(_progress):
        raise AssertionError("UI blew up")

    assert SessionTransfer(session, root).run(progress=angry).ok


# -- idempotence, resume, conflicts ---------------------------------------------

def test_rerun_skips_every_identical_file(tmp_path):
    session, root = make_session(tmp_path), archive(tmp_path)
    first = SessionTransfer(session, root).run()
    second = SessionTransfer(session, root).run()
    assert second.ok
    assert all(result.status == "skipped-identical" for result in second.files)
    assert second.bytes_transferred == 0
    assert second.bytes_skipped == first.bytes_total


def test_interrupted_file_leaves_a_part_file_and_resumes_cleanly(tmp_path):
    session, root = make_session(tmp_path), archive(tmp_path)
    destination = root / session.name
    destination.mkdir()
    (destination / f"CF532_1.ptu{PART_SUFFIX}").write_bytes(b"half a copy")

    report = SessionTransfer(session, root).run()
    assert report.ok
    assert (destination / "CF532_1.ptu").read_bytes() == (session / "CF532_1.ptu").read_bytes()
    assert not (destination / f"CF532_1.ptu{PART_SUFFIX}").exists()
    state = json.loads((destination / STATE_NAME).read_text(encoding="utf-8"))
    assert state["files"]["CF532_1.ptu"]["status"] == "copied"


def test_a_different_destination_file_is_a_conflict_and_never_overwritten(tmp_path):
    session, root = make_session(tmp_path), archive(tmp_path)
    SessionTransfer(session, root).run()
    victim = root / session.name / "CF532_1_OFCS.pqres"
    victim.write_bytes(b"different data from someone else")

    second = SessionTransfer(session, root).run()
    statuses = {result.rel: result for result in second.files}
    assert statuses["CF532_1_OFCS.pqres"].status == "conflict"
    assert "never overwritten" in statuses["CF532_1_OFCS.pqres"].error
    assert victim.read_bytes() == b"different data from someone else"   # untouched
    assert statuses["CF532_1.ptu"].status == "skipped-identical"        # the rest resumes
    assert not second.ok


# -- transient network errors ---------------------------------------------------

def test_a_dropped_share_is_retried_and_the_run_recovers(tmp_path, monkeypatch):
    session, root = make_session(tmp_path), archive(tmp_path)
    real_copy = SessionTransfer._copy_stream
    calls = {"n": 0}

    def flaky(self, source, part, progress):
        calls["n"] += 1
        if calls["n"] == 1:
            raise OSError(errno.EIO, "network cable pulled")
        return real_copy(self, source, part, progress)

    monkeypatch.setattr(SessionTransfer, "_copy_stream", flaky)
    report = SessionTransfer(session, root, attempts=3, retry_delay_s=0.0).run()
    assert report.ok
    by_rel = {result.rel: result for result in report.files}
    assert by_rel["CF532_1.pck"].attempts == 2      # the first copy hit the dropped share
    assert by_rel["CF532_1.ptu"].attempts == 1      # everything after it was untouched


def test_a_permanent_failure_fails_one_file_and_still_transfers_the_rest(tmp_path, monkeypatch):
    session, root = make_session(tmp_path), archive(tmp_path)
    real_copy = SessionTransfer._copy_stream        # captured before the patch

    def broken(self, source, part, progress):
        if source.name == "CF532_1.ptu":
            raise OSError(errno.EIO, "share gone for good")
        return real_copy(self, source, part, progress)

    monkeypatch.setattr(SessionTransfer, "_copy_stream", broken)
    report = SessionTransfer(session, root, attempts=2, retry_delay_s=0.0).run()
    by_rel = {result.rel: result for result in report.files}
    assert by_rel["CF532_1.ptu"].status == "failed"
    assert by_rel["CF532_1.pck"].status == "copied"
    assert not report.ok
    assert (root / session.name / "CF532_1.ptu").exists() is False


def test_a_source_still_being_written_is_reported_not_copied(tmp_path, monkeypatch):
    session, root = make_session(tmp_path), archive(tmp_path)
    real_listing = SessionTransfer._rel_files

    def stale_sizes(self):
        # Pretend the listing saw the file smaller than it is now (a live writer).
        return [(rel, path, max(1, size - 8)) for rel, path, size in real_listing(self)]

    monkeypatch.setattr(SessionTransfer, "_rel_files", stale_sizes)
    report = SessionTransfer(session, root).run()
    assert all(result.status == "failed" for result in report.files)
    assert "still being written" in report.files[0].error
    assert not (root / session.name / "CF532_1.ptu").exists()


# -- the destination may be gone -------------------------------------------------

def test_disconnected_share_fails_loudly(tmp_path, monkeypatch):
    session = make_session(tmp_path)
    monkeypatch.setattr(transfer_module, "is_reachable", lambda path: False)
    with pytest.raises(DestinationUnavailable):
        SessionTransfer(session, tmp_path / "microtime200").run()


def test_missing_destination_root_is_never_created(tmp_path):
    session = make_session(tmp_path)
    root = tmp_path / "microtime200"          # Z: without the share: not a directory
    assert is_reachable(root)                 # the drive answers (POSIX root here)
    with pytest.raises(NotADirectoryError):
        SessionTransfer(session, root).run()
    assert not root.exists()                  # and nothing was silently created


def test_destination_root_inside_the_source_is_refused(tmp_path):
    session = make_session(tmp_path)
    with pytest.raises(ValueError):
        SessionTransfer(session, session).run()


def test_custom_session_name_lands_under_the_root(tmp_path):
    session = make_session(tmp_path)
    root = archive(tmp_path)
    report = SessionTransfer(session, root, session_name="MT200_archive").run()
    assert report.destination_dir == root / "MT200_archive"
    assert (root / "MT200_archive" / "CF532_1.ptu").exists()


# -- verified relocation (move) --------------------------------------------------

def test_move_deletes_the_source_only_after_verification(tmp_path):
    session, root = make_session(tmp_path), archive(tmp_path)
    report = SessionTransfer(session, root).move()
    assert report.ok and report.moved
    assert all(result.status == "moved" for result in report.files)
    assert not session.exists()                                  # relocation complete
    for result in report.files:
        assert result.destination.exists()
        assert result.sha256 == sha_of(result.destination)


def test_move_is_cancelled_when_the_source_changed_after_the_copy(tmp_path, monkeypatch):
    session, root = make_session(tmp_path), archive(tmp_path)
    real_copy = SessionTransfer._copy_stream

    def copy_then_someone_appends(self, source, part, progress):
        copied = real_copy(self, source, part, progress)
        with open(source, "ab") as handle:      # a live writer touches the source mid-move
            handle.write(b"late byte")
        return copied

    monkeypatch.setattr(SessionTransfer, "_copy_stream", copy_then_someone_appends)
    report = SessionTransfer(session, root).move()
    assert report.moved is False
    assert all(result.status == "copied" for result in report.files)   # the copy itself is fine
    assert any("move cancelled" in result.error for result in report.files)
    assert all(result.source.exists() for result in report.files)      # every source kept


def test_move_stops_at_an_undeletable_file_and_keeps_the_rest(tmp_path, monkeypatch):
    session, root = make_session(tmp_path), archive(tmp_path)
    real_unlink = pathlib.Path.unlink

    def busy_file(self, missing_ok=False):
        if self.name == "CF532_1.ptu":
            raise PermissionError(errno.EACCES, "opened by the acquisition app")
        return real_unlink(self, missing_ok=missing_ok)

    monkeypatch.setattr(pathlib.Path, "unlink", busy_file)
    report = SessionTransfer(session, root).move()
    assert report.moved is False
    by_rel = {result.rel: result for result in report.files}
    assert "move incomplete" in by_rel["CF532_1.ptu"].error
    assert session.exists()                                       # whatever stayed, stayed


def test_plain_run_never_deletes_anything(tmp_path):
    session, root = make_session(tmp_path), archive(tmp_path)
    before = sorted(p.relative_to(session).as_posix() for p in session.rglob("*"))
    assert SessionTransfer(session, root).run().ok
    after = sorted(p.relative_to(session).as_posix() for p in session.rglob("*"))
    assert before == after and session.exists()


# -- configuration ----------------------------------------------------------------

@pytest.mark.parametrize("verify", ["size", "none"])
def test_lighter_verification_still_transfers_and_resumes(tmp_path, verify):
    session, root = make_session(tmp_path), archive(tmp_path)
    first = SessionTransfer(session, root, verify=verify).run()
    assert first.ok
    second = SessionTransfer(session, root, verify=verify).run()
    assert second.ok and all(r.status == "skipped-identical" for r in second.files)


def test_an_empty_session_transfers_as_a_trivial_success(tmp_path):
    session = tmp_path / "TP_20261030_empty"
    session.mkdir()
    report = SessionTransfer(session, archive(tmp_path)).run()
    assert report.ok and report.files == []


def test_verify_rejects_an_unknown_mode(tmp_path):
    with pytest.raises(ValueError):
        SessionTransfer(tmp_path, archive(tmp_path), verify="vibes")
