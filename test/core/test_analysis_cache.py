"""A result stays valid until its inputs or its settings change.

These pin the two halves of that sentence, because getting either wrong is
expensive in a different direction: too eager, and the workflow recomputes
minutes of BVA/MLE work it already did; too lazy, and it shows a stale plot for
settings the user has changed — which is worse, because it looks like an answer.
"""

from __future__ import annotations

import json

import pytest

from chisurf.core.analysis_cache import (
    ResultCache,
    file_identity,
    fingerprint,
    is_current,
    outputs_present,
    read_stamp,
    write_stamp,
)


@pytest.fixture
def burst_files(tmp_path):
    files = []
    for i in range(3):
        p = tmp_path / f"m00{i}.bur"
        p.write_bytes(b"x" * (10 + i))
        files.append(p)
    return files


def test_same_inputs_and_params_give_the_same_fingerprint(burst_files):
    params = {"tau": 100.0, "kernel": "laplace"}
    assert fingerprint(burst_files, params) == fingerprint(burst_files, params)


def test_file_order_is_not_a_change(burst_files):
    """A file list read in a different order is the same set of inputs."""
    params = {"tau": 100.0}
    assert fingerprint(burst_files, params) == fingerprint(reversed(burst_files), params)


def test_key_order_is_not_a_change(burst_files):
    assert fingerprint(burst_files, {"a": 1, "b": 2}) == fingerprint(
        burst_files, {"b": 2, "a": 1}
    )


def test_a_changed_setting_changes_the_fingerprint(burst_files):
    before = fingerprint(burst_files, {"tau": 100.0, "kernel": "laplace"})
    assert before != fingerprint(burst_files, {"tau": 50.0, "kernel": "laplace"})
    # Including a nested one — settings arrive as per-detector mappings.
    assert fingerprint(burst_files, {"det": {"green": 1}}) != fingerprint(
        burst_files, {"det": {"green": 2}}
    )


def test_a_rewritten_input_changes_the_fingerprint(burst_files):
    before = fingerprint(burst_files, {"tau": 1})
    p = burst_files[0]
    p.write_bytes(b"y" * 999)  # different size
    assert fingerprint(burst_files, {"tau": 1}) != before


def test_an_added_or_removed_input_changes_the_fingerprint(burst_files, tmp_path):
    before = fingerprint(burst_files, {})
    extra = tmp_path / "m003.bur"
    extra.write_bytes(b"z")
    assert fingerprint(burst_files + [extra], {}) != before
    assert fingerprint(burst_files[:-1], {}) != before


def test_a_missing_input_is_identified_rather_than_raising(tmp_path):
    ident = file_identity(tmp_path / "not_here.bur")
    assert ident["missing"] is True
    # …and its later appearance is a change.
    absent = fingerprint([tmp_path / "later.bur"], {})
    (tmp_path / "later.bur").write_bytes(b"data")
    assert fingerprint([tmp_path / "later.bur"], {}) != absent


def test_content_mode_sees_a_rewrite_that_keeps_the_size(tmp_path):
    """Same size, same mtime granularity — only the bytes differ."""
    p = tmp_path / "same_size.bur"
    p.write_bytes(b"aaaa")
    by_content = fingerprint([p], {}, content=True)
    mtime = p.stat().st_mtime_ns
    p.write_bytes(b"bbbb")
    import os

    os.utime(p, ns=(mtime, mtime))  # restore the timestamp: only content differs
    assert fingerprint([p], {}, content=True) != by_content
    assert fingerprint([p], {}) == fingerprint([p], {}), "stat-based is stable"


def test_settings_that_are_not_plain_json_still_fingerprint(tmp_path, burst_files):
    """Settings arrive as numpy values, Paths and dataclass-like objects."""
    np = pytest.importorskip("numpy")

    class Settings:
        def __init__(self, tau):
            self.tau = tau
            self._cache = object()  # private state must not enter the fingerprint

    a = fingerprint(burst_files, {"chans": np.array([0, 1]), "out": tmp_path,
                                  "s": Settings(1.0)})
    b = fingerprint(burst_files, {"chans": np.array([0, 1]), "out": tmp_path,
                                  "s": Settings(1.0)})
    c = fingerprint(burst_files, {"chans": np.array([0, 2]), "out": tmp_path,
                                  "s": Settings(1.0)})
    d = fingerprint(burst_files, {"chans": np.array([0, 1]), "out": tmp_path,
                                  "s": Settings(2.0)})
    assert a == b
    assert a != c, "a changed channel list must recompute"
    assert a != d, "a changed settings object must recompute"


def test_stamp_round_trip_and_is_current(tmp_path, burst_files):
    out = tmp_path / "bv4" / "m000.bv4"
    out.parent.mkdir()
    out.write_text("results")
    stamp = tmp_path / "bv4" / "bva.stamp.json"
    fp = fingerprint(burst_files, {"tau": 1})

    write_stamp(stamp, fp, params={"tau": 1}, inputs=burst_files, outputs=[out],
                tool="bva")
    payload = read_stamp(stamp)
    assert payload["fingerprint"] == fp
    assert payload["tool"] == "bva"
    assert payload["params"] == {"tau": 1}

    assert is_current(stamp, fp) is True
    assert is_current(stamp, "0" * 16) is False, "a different fingerprint is stale"

    out.unlink()
    assert is_current(stamp, fp) is False, "results that are gone are not current"


def test_an_unreadable_stamp_reads_as_no_stamp(tmp_path):
    """Anything we cannot parse must mean 'recompute', never 'reuse'."""
    stamp = tmp_path / "broken.stamp.json"
    stamp.write_text("{not json")
    assert read_stamp(stamp) is None
    assert is_current(stamp, "abc") is False

    stamp.write_text(json.dumps({"version": 999, "fingerprint": "abc"}))
    assert read_stamp(stamp) is None, "a newer format is not ours to interpret"

    assert read_stamp(tmp_path / "never_written.json") is None


def test_outputs_present_needs_something_to_be_present(tmp_path):
    assert outputs_present([]) is False
    p = tmp_path / "a.bv4"
    assert outputs_present([p]) is False
    p.write_text("x")
    assert outputs_present([p]) is True


def test_result_cache_tracks_one_fingerprint():
    cache = ResultCache()
    assert cache.matches("a") is False, "an empty cache never matches"
    cache.remember("a")
    assert cache.matches("a") is True
    assert cache.matches("b") is False
    cache.remember("b")
    assert cache.matches("a") is False, "only the newest result is held"
    cache.invalidate()
    assert cache.matches("b") is False
    assert cache.fingerprint is None
