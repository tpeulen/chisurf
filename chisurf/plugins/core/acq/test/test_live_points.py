"""Point measurements (``live.points``): settled moves on the PI stage, one recording per point,
a point ending early when its molecule bleaches.

The source is a simulated immobilised molecule: Poisson photons at a bright level until its
bleaching time, then background only. Each point gets its own bleaching time, so the detector's
calls can be checked against the truth.
"""

from __future__ import annotations

import numpy as np
import pytest

from chisurf.plugins.core.acq.live.points import (
    BleachDetector,
    PiScanner,
    PointSequence,
)
from chisurf.plugins.core.acq.live.scanner import ScanSettings
from chisurf.plugins.core.acq.live.sources import PhotonBatch, PhotonSource, SourceInfo

CLOCK = 50e-9  # 20 MHz sync


class BleachingMolecule(PhotonSource):
    """One molecule per start(): ``bright_kcps`` until ``bleach_s[k]``, then ``background_kcps``.
    Batches of ``batch_s`` come as fast as they are read (no real time)."""

    info = SourceInfo("bleaching molecule", CLOCK, 25e-12, 2000)

    def __init__(self, bleach_s, bright_kcps=60.0, background_kcps=2.0, batch_s=0.02, seed=1):
        self.bleach_s = list(bleach_s)
        self.bright = bright_kcps * 1e3
        self.background = background_kcps * 1e3
        self.batch_s = batch_s
        self.rng = np.random.default_rng(seed)
        self.starts = 0
        self._t = 0.0
        self._on = False
        self._macro0 = 0

    def start(self):
        self._t = 0.0
        self._on = True
        self._bleach = self.bleach_s[self.starts % len(self.bleach_s)]
        self._macro0 += int(1000 / CLOCK)  # a new run, later on the device clock
        self.starts += 1

    def stop(self):
        self._on = False

    @property
    def finished(self):
        return not self._on

    def read(self, timeout=0.2):
        if not self._on:
            return None
        t0, t1 = self._t, self._t + self.batch_s
        self._t = t1
        rate = self.background + (self.bright if t1 <= self._bleach else 0.0)
        n = self.rng.poisson(rate * self.batch_s)
        t = np.sort(self.rng.uniform(t0, t1, n))
        macro = (self._macro0 + t / CLOCK).astype(np.uint64)
        return PhotonBatch(macro, self.rng.integers(0, 2000, n).astype(np.uint16),
                           self.rng.integers(0, 2, n).astype(np.int8))


def test_the_detector_calls_the_bleaching_step():
    rng = np.random.default_rng(0)
    det = BleachDetector(background_kcps=2.0)
    t = np.sort(np.concatenate([rng.uniform(0, 1.2, int(1.2 * 62e3)),
                                rng.uniform(1.2, 4, int(2.8 * 2e3))]))
    called = None
    for lo in np.arange(0, 4, 0.1):
        chunk = t[(t >= lo) & (t < lo + 0.1)]
        if det.push((chunk / CLOCK).astype(np.uint64), CLOCK):
            called = lo
            break
    assert called is not None
    assert det.level_kcps == pytest.approx(62, rel=0.1)
    assert abs(det.bleached_at_s - 1.2) <= 0.1
    assert called < 1.2 + det.hold_s + 0.2   # stops soon after the step, not at the end


def test_no_call_while_the_molecule_shines():
    rng = np.random.default_rng(3)
    det = BleachDetector(background_kcps=2.0)
    t = np.sort(rng.uniform(0, 5, int(5 * 60e3)))
    assert not det.push((t / CLOCK).astype(np.uint64), CLOCK)
    assert det.bleached_at_s is None


class FakeStage:
    """A scanner that only parks the focus (records where it was sent)."""

    def __init__(self):
        self.moves = []

    def move_to(self, x, y):
        self.moves.append((x, y))
        return x, y


def _scan(points, point_ms):
    return ScanSettings(points=list(points), point_ms=point_ms)


def test_points_in_turn_each_until_bleached(tmp_path):
    points = [(32.5, 26.875), (59.375, 35.0), (36.25, 56.25)]
    source = BleachingMolecule(bleach_s=[0.6, 1.5, 0.9])
    stage = FakeStage()
    seen = []
    seq = PointSequence(stage, source, _scan(points, 3000), out_dir=tmp_path, name="mol",
                        until_bleached=True,
                        bleach=lambda: BleachDetector(background_kcps=2.0),
                        on_point=seen.append)
    results = seq.run()
    assert stage.moves == points
    assert source.starts == 3 and len(results) == 3 and seen == results
    for r, truth in zip(results, [0.6, 1.5, 0.9]):
        assert r.run.stop_reason == "bleached"
        assert abs(r.bleached_at_s - truth) <= 0.1
        assert r.run.elapsed_s < 3.0
        assert r.run.ptu.exists() and r.run.ptu.name == f"mol_p{r.index:03d}.ptu"


def test_points_for_their_full_time_and_the_point_in_the_header(tmp_path):
    from chisurf.plugins.core.acq.live import settings_file

    source = BleachingMolecule(bleach_s=[0.3])
    seq = PointSequence(FakeStage(), source, _scan([(10.0, 20.0), (11.0, 21.0)], 800),
                        out_dir=tmp_path, name="fixed")
    results = seq.run()
    assert [r.run.stop_reason for r in results] == ["duration reached"] * 2
    assert all(r.bleached_at_s is None for r in results)
    tags = settings_file.read_ptu_tags(results[1].run.ptu)
    assert tags["ChiSurf_Point_Index"] == 1
    assert tags["ChiSurf_Point_X_um"] == pytest.approx(11.0)
    assert tags["ChiSurf_Point_Y_um"] == pytest.approx(21.0)
    # SymPhoTime's point measurement header
    assert tags["ImgHdr_Dimensions"] == 1 and tags["ImgHdr_Ident"] == 6
    assert tags["ImgHdr_X0"] == pytest.approx(11.0) and tags["ImgHdr_Y0"] == pytest.approx(21.0)


def test_stop_aborts_the_sequence(tmp_path):
    source = BleachingMolecule(bleach_s=[1e9], batch_s=0.001)
    seq = PointSequence(FakeStage(), source, _scan([(1, 1), (2, 2), (3, 3)], 1e7), out_dir=None)
    seq.start()
    import time

    deadline = time.monotonic() + 5
    while seq.current is None and time.monotonic() < deadline:
        time.sleep(0.01)
    seq.stop()
    results = seq.wait(5)
    assert not seq.running
    assert len(results) == 1 and results[0].run.stop_reason == "stopped"


def test_the_pi_stage_through_phacq():
    phacq = pytest.importorskip("phacq")
    if "pi" not in list(phacq.DriverRegistry.instance().driver_names()):
        pytest.skip("this phacq has no pi driver")
    stage = PiScanner("sim:", learn_s=0.5)
    assert stage.move_to(59.375, 35.0) == pytest.approx((59.375, 35.0))
    raster = ScanSettings(pixels_x=32, pixels_y=16, area_x_um=8, area_y_um=4, x0_um=10,
                          y0_um=10, dwell_ms=1.0)
    assert stage.configure(raster) == []
    assert stage.device.get_parameter("lines") == 16
    assert stage.device.get_parameter("line_pitch_um") == pytest.approx(0.25)
    stage.start()
    while stage.status()["running"]:
        pass
    stage.stop()
    assert stage.position() == pytest.approx((50.0, 50.0))   # parked at the centre
    stage.close()
