"""Gear is real optics, and it decides what you can see."""

from __future__ import annotations

import numpy as np
import pytest

from chisurf.plugins.misc.games.lumis_quest.api import gear


def _band(centre: float, width: float, name="test", slot="emission", probe_id=-1) -> gear.Gear:
    """A synthetic bandpass, so tests do not depend on which parts ship."""
    curve = np.exp(-0.5 * ((gear.GRID - centre) / (width / 2.355)) ** 2)
    return gear.Gear(probe_id=probe_id, name=name, slot=slot, curve=curve)


@pytest.fixture(scope="module")
def parts():
    """Gear from the shipped database.

    Returns
    -------
    tuple of Gear
        Skips the module when the database is absent.
    """
    loaded = gear.load_gear()
    if not loaded:
        pytest.skip("spectra.db is not present in this install")
    return loaded


def test_the_catalogue_is_real_and_varied(parts):
    """Hundreds of parts, across the visible range, in several slots."""
    assert len(parts) > 300
    slots = {part.slot for part in parts}
    assert {"emission", "detector"} <= slots
    assert all(part.curve.shape == gear.GRID.shape for part in parts)
    assert all(0.0 <= part.curve.min() and part.curve.max() <= 1.0 for part in parts)


def test_it_reads_as_a_spectrum(parts):
    """Sorted by passband centre."""
    centres = [part.center_nm for part in parts]
    assert centres == sorted(centres)


def test_a_bandpass_reports_its_own_centre_and_width():
    """The two numbers the player actually chooses on."""
    part = _band(525.0, 50.0)
    assert part.center_nm == pytest.approx(525.0, abs=2.0)
    assert part.bandwidth_nm == pytest.approx(50.0, abs=3.0)
    assert part.passes(525.0) > 0.9
    assert part.passes(700.0) < 0.01


def test_a_matched_filter_amplifies_and_a_mismatched_one_blocks():
    """Gear is a decision, not a stat stick."""
    loadout = gear.Loadout(emission=_band(525.0, 40.0))
    assert loadout.response(525.0) > 1.2
    assert loadout.response(650.0) < 0.2


def test_the_wrong_filter_actually_blinds_you():
    """Regression: the blocked floor sat above the visibility threshold.

    With a floor of 0.25 against a 0.22 threshold nothing was ever invisible,
    so the whole loot loop -- re-walk cleared ground with different optics and
    see what was always there -- silently did nothing.
    """
    loadout = gear.Loadout(emission=_band(500.0, 20.0))
    assert loadout.sees(500.0)
    assert not loadout.sees(600.0)
    assert not loadout.sees(430.0)


def test_nothing_fitted_sees_everything():
    """A bare eye, not a blind one."""
    loadout = gear.Loadout()
    assert loadout.response(450.0) == 1.0
    assert loadout.sees(450.0) and loadout.sees(700.0)
    assert "no filter" in loadout.summary


def test_a_detector_narrows_further():
    """Two elements multiply, as they do on a bench."""
    filter_only = gear.Loadout(emission=_band(525.0, 60.0))
    both = gear.Loadout(
        emission=_band(525.0, 60.0),
        detector=_band(525.0, 60.0, slot="detector", probe_id=-2),
    )
    assert both.response(525.0) > filter_only.response(525.0) * 0.9
    assert both.response(700.0) < filter_only.response(700.0)


def test_loot_is_seeded_by_the_page(parts):
    """The same room always yields the same part; no farming for rerolls."""
    first = gear.loot_for("docs/concepts/fret.md", 0.8, parts)
    second = gear.loot_for("docs/concepts/fret.md", 0.8, parts)
    assert first is not None and first.name == second.name
    other = gear.loot_for("docs/guides/01_start.md", 0.8, parts)
    assert other.name != first.name


def test_a_remote_room_yields_a_narrower_filter(parts):
    """The prize for going far is selectivity, which cuts both ways."""
    near = [gear.loot_for(f"p{i}", 0.05, parts).bandwidth_nm for i in range(10)]
    far = [gear.loot_for(f"p{i}", 0.95, parts).bandwidth_nm for i in range(10)]
    assert sum(far) / len(far) < sum(near) / len(near)


def test_the_starting_filter_is_forgiving(parts):
    """A new player must not be blinded to most of the roster before they know why."""
    loadout = gear.starting_loadout(parts)
    assert loadout.emission is not None
    assert loadout.emission.bandwidth_nm > 80.0
    visible = sum(loadout.sees(nm) for nm in range(420, 760, 10))
    assert visible > 12, "the starting filter blocks too much"


def test_an_empty_catalogue_degrades_rather_than_raising():
    """A stripped install still starts the game."""
    assert gear.loot_for("x", 0.5, []) is None
    assert gear.starting_loadout([]).emission is None
