"""The calibration report's file hashes are the project's digests: the same SHA-256, read once."""

import hashlib


def test_file_entry_is_the_sha256_and_reuses_the_project_digest(tmp_path, monkeypatch):
    from chisurf.core.project import links
    from chisurf.plugins.burst.burst_analysis.calibration_report import file_entry

    path = tmp_path / "m.ptu"
    path.write_bytes(bytes(range(256)) * 5000)
    entry = file_entry(path)
    assert entry["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert entry["size"] == path.stat().st_size
    reads = []
    monkeypatch.setattr(links, "_hash_file", lambda *a, **k: reads.append(a) or (0, "x"))
    assert file_entry(path)["sha256"] == entry["sha256"] and reads == []  # not read again
    assert file_entry(tmp_path / "missing.ptu")["sha256"] is None
