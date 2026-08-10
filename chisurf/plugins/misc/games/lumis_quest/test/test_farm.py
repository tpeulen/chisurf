"""Cultures mature on a real clock, and the bench never eats a creature."""

from __future__ import annotations

from chisurf.plugins.misc.games.lumis_quest.api import farm


def test_maturation_is_real_time_and_stable_per_creature():
    """The growth timer is a physical property, not an invented wait."""
    first = farm.maturation_seconds(42)
    assert farm.MATURE_MIN <= first <= farm.MATURE_MAX
    assert farm.maturation_seconds(42) == first, "the same dye matures alike"
    assert farm.maturation_seconds(43) != first, "different dyes differ"


def test_a_culture_cannot_be_harvested_early():
    """An early click must not lose the culture."""
    lab = farm.Lab()
    lab.plant(7, now=1000.0)
    assert lab.harvest(0, now=1000.0 + 60.0) is None
    assert len(lab.plots) == 1, "the immature culture stays on the bench"

    duration = lab.plots[0].duration
    assert lab.harvest(0, now=1000.0 + duration + 1.0) == 7
    assert lab.plots == []


def test_the_bench_is_finite():
    """A rhythm between sessions, not a factory."""
    lab = farm.Lab()
    for index in range(farm.PLOTS):
        assert lab.plant(index, now=0.0) is not None
    assert not lab.can_plant()
    assert lab.plant(99, now=0.0) is None


def test_the_bench_survives_the_save_file():
    """Wall-clock timestamps persist, so growth continues across sessions."""
    lab = farm.Lab()
    lab.plant(7, now=500.0)
    lab.plant(9, now=600.0)

    restored = farm.Lab.from_rows(lab.as_rows())
    assert [(p.probe_id, p.planted_at) for p in restored.plots] == [
        (7, 500.0), (9, 600.0)
    ]


def test_a_malformed_save_row_is_dropped_not_fatal():
    """Losing one culture beats refusing the whole save."""
    restored = farm.Lab.from_rows([[7, 500.0, 1200.0], ["junk"], None])
    assert [p.probe_id for p in restored.plots] == [7]


def test_progress_is_clamped():
    """Before planting time and long after maturity both stay in 0..1."""
    plot = farm.Plot(probe_id=1, planted_at=1000.0, duration=100.0)
    assert plot.progress(now=900.0) == 0.0
    assert plot.progress(now=1050.0) == 0.5
    assert plot.progress(now=99999.0) == 1.0
