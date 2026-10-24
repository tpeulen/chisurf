"""Large files, chunk by chunk: the same bursts as a whole-file analysis."""
import pathlib

import numpy as np
import pytest

tttrlib = pytest.importorskip("tttrlib")

from chisurf.plugins.burst.fret_check import chunked, jobs  # noqa: E402
from chisurf.plugins.burst.fret_check.detect import detect_experiment, load  # noqa: E402
from chisurf.plugins.burst.fret_check.pipeline import BurstSettings, analyse  # noqa: E402

DATA = pathlib.Path(__file__).resolve().parents[2] / "tttr-data"
SPC = DATA / "bh/bh_spc132_sm_dna/m000.spc"


def _ptu(tmp_path):
    if not hasattr(tttrlib, "SimEngine"):
        pytest.skip("tttrlib without the simulator")
    from chisurf.plugins.burst.fret_check.sim import SCENARIOS, simulate

    path = tmp_path / "pie.ptu"
    simulate(next(s for s in SCENARIOS if s.name == "PIE 2c")).write(str(path))
    return path


def _files(tmp_path):
    out = [_ptu(tmp_path)]
    if SPC.is_file():
        out.append(SPC)
    return out


def test_chunks_decode_like_a_full_read(tmp_path):
    for path in _files(tmp_path):
        full = load(path)
        parts = list(chunked.iter_chunks(str(path), records=20_000))
        assert len(parts) > 1, path
        macro = np.concatenate([np.asarray(c.macro_times) for c, _, _ in parts])
        routing = np.concatenate([np.asarray(c.routing_channels) for c, _, _ in parts])
        assert np.array_equal(macro, np.asarray(full.macro_times))
        assert np.array_equal(routing, np.asarray(full.routing_channels))


def test_chunked_analysis_finds_the_same_bursts(tmp_path):
    for path in _files(tmp_path):
        data = load(path)
        exp = detect_experiment(data)
        whole = analyse(data, exp, BurstSettings())
        _, _, parts, trace, micro = chunked.analyse_chunked(
            lambda *a: None, str(path), BurstSettings(), experiment=exp, records=20_000)
        assert np.array_equal(whole.start, parts.start) and np.array_equal(whole.stop, parts.stop), path
        assert np.allclose(whole.E, parts.E)
        assert np.allclose(whole.t_start, parts.t_start)
        for stream, rate in whole.background.items():
            assert parts.background[stream] == pytest.approx(rate, rel=0.02, abs=1.0)
        if "Tau (green)" in whole.extra:
            assert np.nanmax(np.abs(whole.extra["Tau (green)"] - parts.extra["Tau (green)"])) < 0.05
        assert trace["rates"] and micro


def test_the_job_takes_large_files_in_chunks(tmp_path, monkeypatch):
    path = _ptu(tmp_path)
    monkeypatch.setattr(chunked, "LARGE_BYTES", 1)
    monkeypatch.setattr(chunked, "CHUNK_RECORDS", 20_000)
    jobs._CACHE.clear()
    out = jobs.analyse(lambda *a: None, key=f"file:{path}", path=str(path))
    assert out["chunked"]
    bursts = jobs.bursts_from_dict(out["bursts"])
    exp = jobs.experiment_from_dict(out["experiment"])
    assert exp.alternation == "PIE" and bursts.n > 50
    jobs._CACHE.clear()


def test_a_burst_that_never_ends_is_closed_not_carried(monkeypatch, tmp_path):
    """Bulk-like data (one 'burst' as long as the file) must not pile up."""
    import tttrlib as t

    n = 60_000
    macro = np.arange(n, dtype=np.uint64) * 10          # 125 ns apart: always in a burst
    data = t.TTTR(macro, np.zeros(n, np.uint16), (np.arange(n) % 2).astype(np.int8), np.zeros(n, np.int8))
    data.header.set_macro_time_resolution(12.5e-9)
    path = tmp_path / "bulk.ptu"
    data.write(str(path))
    monkeypatch.setattr(chunked, "MAX_CARRY", 5_000)
    exp = detect_experiment(load(path))
    _, used, bursts, _, _ = chunked.analyse_chunked(lambda *a: None, str(path), BurstSettings(),
                                                    experiment=exp, records=10_000)
    assert bursts.n >= 2                                  # split at chunk ends
    assert int(bursts.size.sum()) <= n
    assert any("never ended" in w for w in used.warnings)
