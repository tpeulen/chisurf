"""Sparks, orbs and rising numbers: the layer that tells you something happened."""

from __future__ import annotations

import math

import pytest

from chisurf.gui.chigame import particles


def test_a_rising_number_climbs_and_fades_out():
    """The whole point: it says what happened, where it happened."""
    field = particles.Field()
    one = field.rise("+40 XP", (100.0, 100.0), span=1.0, distance=20.0)
    assert one is not None
    start = one.y
    assert one.fade == pytest.approx(1.0)
    for _ in range(50):
        field.update(0.01)
    assert one.y < start
    assert 0.0 < one.fade < 1.0
    field.update(0.6)
    assert len(field) == 0


def test_the_climb_does_not_depend_on_the_frame_rate():
    """One coarse step and many fine ones land in the same place.

    The reference counted frames, so a spark on a fast machine lived a third as
    long as one on a slow machine and nobody could tell because both looked
    fine on the machine they were written on.
    """
    coarse = particles.Field()
    fine = particles.Field()
    a = coarse.rise("x", (0.0, 0.0), span=2.0, distance=30.0)
    b = fine.rise("x", (0.0, 0.0), span=2.0, distance=30.0)
    coarse.update(0.5)
    for _ in range(50):
        fine.update(0.01)
    assert a.y == pytest.approx(b.y, abs=1e-9)
    assert a.fade == pytest.approx(b.fade, abs=1e-9)


def test_an_orb_flies_to_its_target_and_is_delivered():
    """The pickup arc, which is what connects a reward to the thing that gave it."""
    field = particles.Field()
    made = field.orbs((0.0, 0.0), (60.0, 0.0), count=4, speed=200.0, scatter=0.0)
    assert len(made) == 4
    for _ in range(30):
        field.update(1 / 60)
    assert len(field) == 0


def test_an_orb_never_overshoots_its_target():
    """A step is capped at the distance left, which is what stops it orbiting."""
    one = particles.Particle(x=0.0, y=0.0, target=(5.0, 0.0), speed=10_000.0, span=10.0)
    one.step(1.0)
    assert one.x == pytest.approx(5.0)
    assert one.spent


def test_an_orb_whose_target_is_unreachable_still_dies():
    """The span is the backstop, so nothing lives for ever."""
    field = particles.Field()
    field.orbs((0.0, 0.0), (1e6, 1e6), count=3, speed=1.0, span=0.4, scatter=0.0)
    assert len(field) == 3
    field.update(0.5)
    assert len(field) == 0


def test_a_burst_throws_things_outward_in_every_direction():
    """A spray reads as an impact only if it is actually a spray."""
    field = particles.Field()
    made = field.burst((0.0, 0.0), count=12, speed=50.0, drag=0.0)
    angles = [math.atan2(one.vy, one.vx) for one in made]
    assert max(angles) - min(angles) > 4.0  # spread over most of a turn
    field.update(0.05)
    assert all(math.hypot(one.x, one.y) > 0.0 for one in made)


def test_drag_slows_a_spray_down_and_gravity_pulls_it():
    """Both are what turn a firework into an impact."""
    dragged = particles.Particle(x=0.0, y=0.0, vx=100.0, drag=4.0, span=9.0)
    falling = particles.Particle(x=0.0, y=0.0, gravity=200.0, span=9.0)
    for _ in range(30):
        dragged.step(1 / 60)
        falling.step(1 / 60)
    assert dragged.vx < 100.0
    assert falling.vy > 0.0
    assert falling.y > 0.0


def test_a_full_field_refuses_rather_than_raising():
    """An emitter in a loop must not be the thing that takes down a frame."""
    field = particles.Field(limit=3)
    assert len(field.burst((0.0, 0.0), count=50)) == 3
    assert field.rise("nope", (0.0, 0.0)) is None
    assert len(field) == 3


def test_the_scatter_is_the_same_on_every_run():
    """A replay is a replay, so the flourish cannot be the thing that differs."""
    first = particles.Field(seed=11).burst((0.0, 0.0), count=6)
    second = particles.Field(seed=11).burst((0.0, 0.0), count=6)
    assert [(one.vx, one.vy) for one in first] == [(one.vx, one.vy) for one in second]


class _Batch:
    """A sprite batch that records instead of drawing.

    The real one owns GPU buffers; everything being asserted here is decided
    before the GPU is reached.
    """

    def __init__(self) -> None:
        self.quads: list[dict] = []

    def add(self, **quad) -> None:
        """Record one quad.

        Parameters
        ----------
        **quad
            Whatever :meth:`.Scene.draw` passes through.
        """
        self.quads.append(quad)


def _scene(batch):
    """A scene over a recording batch.

    Returns
    -------
    chisurf.gui.chigame.scene.Scene
        With the default procedural pack and no font.
    """
    from chisurf.gui.chigame.scene import Scene

    return Scene(batch)


def test_particles_draw_through_the_pack_and_fade_as_they_go():
    """A particle names a kind, not a colour, and `alpha` scales what the pack chose."""
    field = particles.Field()
    field.burst((0.0, 0.0), count=4, span=1.0, name="halo")

    batch = _Batch()
    field.draw(_scene(batch))
    fresh = max(quad["color"][3] for quad in batch.quads)
    assert batch.quads, "a burst drew nothing"

    field.update(0.5)
    batch = _Batch()
    field.draw(_scene(batch))
    assert max(quad["color"][3] for quad in batch.quads) < fresh


def test_a_particle_never_names_its_own_colour():
    """The look stays swappable: the pack decides, the particle asks."""
    field = particles.Field()
    field.burst((0.0, 0.0), count=2, kind="photon", name="halo", emission_nm=488.0)
    blue = _Batch()
    field.draw(_scene(blue))

    other = particles.Field()
    other.burst((0.0, 0.0), count=2, kind="photon", name="halo", emission_nm=650.0)
    red = _Batch()
    other.draw(_scene(red))
    assert blue.quads[0]["color"][:3] != red.quads[0]["color"][:3]


def test_text_particles_go_through_the_font_and_not_the_sprite_batch():
    """A number is text; drawing it as a quad would be a coloured blob."""
    field = particles.Field()
    field.rise("+1", (0.0, 0.0))
    batch = _Batch()
    # No font is loaded, so a text draw is a no-op -- and that is the assertion:
    # the particle took the text path, not the sprite path.
    field.draw(_scene(batch))
    assert batch.quads == []
