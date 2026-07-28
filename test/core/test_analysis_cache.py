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
    algorithm_tag,
    file_identity,
    fingerprint,
    is_current,
    library_version,
    outputs_present,
    outputs_unchanged,
    photon_read_context,
    read_stamp,
    stamp_entry,
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
    assert payload["tool"] == "bva"
    entry = stamp_entry(stamp, fp)
    assert entry["fingerprint"] == fp
    assert entry["params"] == {"tau": 1}

    assert is_current(stamp, fp) is True
    assert is_current(stamp, "0" * 16) is False, "a different fingerprint is stale"

    out.unlink()
    assert is_current(stamp, fp) is False, "results that are gone are not current"


def test_a_rewritten_output_is_not_current(tmp_path, burst_files):
    """Existence is not enough: the file must be the one that was written."""
    out = tmp_path / "bv4" / "m000.bv4"
    out.parent.mkdir()
    out.write_text("results")
    stamp = tmp_path / "bv4" / "bva.stamp.json"
    fp = fingerprint(burst_files, {"tau": 1})
    write_stamp(stamp, fp, outputs=[out], tool="bva")
    assert is_current(stamp, fp) is True

    out.write_text("something else entirely")
    assert is_current(stamp, fp) is False, "an edited result is not the recorded one"


def test_two_selections_of_one_folder_remember_each_other(tmp_path, burst_files):
    """Switching between two subsets must not make each recompute the other."""
    out_a = tmp_path / "out" / "a.bg4"
    out_b = tmp_path / "out" / "b.bg4"
    out_a.parent.mkdir()
    out_a.write_text("A")
    out_b.write_text("B")
    stamp = tmp_path / "out" / "burst_mle.stamp.json"

    fp_a = fingerprint(burst_files[:2], {"model": "fit23"})
    fp_b = fingerprint(burst_files, {"model": "fit23"})
    write_stamp(stamp, fp_a, outputs=[out_a], tool="burst_mle")
    write_stamp(stamp, fp_b, outputs=[out_b], tool="burst_mle")

    assert is_current(stamp, fp_b) is True
    assert is_current(stamp, fp_a) is True, "the earlier selection is still recorded"


def test_a_stamp_does_not_grow_without_bound(tmp_path):
    from chisurf.core.analysis_cache import MAX_STAMP_ENTRIES

    out = tmp_path / "o.bv4"
    out.write_text("x")
    stamp = tmp_path / "s.json"
    for i in range(MAX_STAMP_ENTRIES + 5):
        write_stamp(stamp, f"{i:016x}", outputs=[out], tool="bva")
    payload = read_stamp(stamp)
    assert len(payload["entries"]) == MAX_STAMP_ENTRIES
    assert payload["entries"][0]["fingerprint"] == f"{MAX_STAMP_ENTRIES + 4:016x}"


def test_writing_the_same_fingerprint_twice_replaces_its_entry(tmp_path):
    out = tmp_path / "o.bv4"
    out.write_text("x")
    stamp = tmp_path / "s.json"
    write_stamp(stamp, "abc", params={"tau": 1}, outputs=[out], tool="bva")
    write_stamp(stamp, "abc", params={"tau": 2}, outputs=[out], tool="bva")
    payload = read_stamp(stamp)
    assert len(payload["entries"]) == 1
    assert stamp_entry(stamp, "abc")["params"] == {"tau": 2}


def test_outputs_unchanged_needs_something_recorded(tmp_path):
    assert outputs_unchanged([]) is False, "nothing recorded is not 'unchanged'"
    p = tmp_path / "a.bv4"
    p.write_text("x")
    from chisurf.core.analysis_cache import output_identities

    ident = output_identities([p])
    assert outputs_unchanged(ident) is True
    p.unlink()
    assert outputs_unchanged(ident) is False


def test_a_stamp_from_the_previous_format_reads_as_no_stamp(tmp_path):
    """The v1 shape kept one fingerprint at the top level. It must not be trusted."""
    stamp = tmp_path / "old.stamp.json"
    stamp.write_text(json.dumps({"version": 1, "fingerprint": "abc", "outputs": []}))
    assert read_stamp(stamp) is None
    assert is_current(stamp, "abc") is False


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


def test_a_setting_that_cannot_be_described_forces_a_recompute(burst_files):
    """An object whose repr says nothing must never read as 'unchanged'.

    Falling back to ``str`` collapses two different settings onto one text
    whenever ``__repr__`` does not carry the object's state — the one direction
    this module must not fail in.
    """

    class Opaque:  # no __str__, no __dict__ worth reading
        __slots__ = ()

    a = fingerprint(burst_files, {"thing": Opaque()})
    b = fingerprint(burst_files, {"thing": Opaque()})
    assert a != b, "an undescribable setting recomputes rather than pretending"


def test_the_code_that_computed_the_result_is_part_of_the_fingerprint(burst_files):
    """A corrected estimator must not inherit the previous version's results."""
    before = fingerprint(burst_files, {"tau": 1}, extra=algorithm_tag("burst_mle", 1))
    after = fingerprint(burst_files, {"tau": 1}, extra=algorithm_tag("burst_mle", 2))
    assert before != after

    # A library that is not installed is reported, not raised.
    assert library_version("definitely_not_a_module_xyz") == (
        "definitely_not_a_module_xyz=absent"
    )
    tag = algorithm_tag("burst_mle", 1, "definitely_not_a_module_xyz")
    assert tag.startswith("burst_mle/v1|")


def test_the_ambient_read_context_is_reported(monkeypatch):
    """A LUT is not a setting of any tool, and it changes every micro-time."""
    context = photon_read_context()
    assert isinstance(context, dict)
    if context.get("available") is False:
        pytest.skip("LUT context subsystem is not importable here")

    from chisurf.core.fio import lut_context

    lut_context.clear_active_setup_lut()
    off = photon_read_context()

    np = pytest.importorskip("numpy")
    lut_context.set_active_setup_lut(
        channel_luts={0: np.arange(8)}, channel_shifts={}, apply_lut=True
    )
    try:
        on = photon_read_context()
        assert on != off, "switching the active setup LUT is a change"
        # …and a different LUT is a different change.
        lut_context.set_active_setup_lut(
            channel_luts={0: np.arange(8)[::-1]}, channel_shifts={}, apply_lut=True
        )
        assert photon_read_context() != on
    finally:
        lut_context.clear_active_setup_lut()


def test_a_stopped_run_is_neither_reusable_nor_restarted():
    """Stop has to mean 'not this, not now' — see the auto-start on revisit."""
    cache = ResultCache()
    cache.remember("abc")
    cache.abandon("abc")
    assert cache.matches("abc") is False, "a partial answer is not an answer"
    assert cache.was_abandoned("abc") is True
    assert cache.was_abandoned("def") is False, "only the stopped run is suppressed"

    cache.allow()
    assert cache.was_abandoned("abc") is False, "asking again clears the stop"

    cache.abandon("abc")
    cache.remember("abc")
    assert cache.was_abandoned("abc") is False, "a finished run clears the stop"


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
