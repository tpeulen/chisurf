"""Breakout physics shared by Qt and EMTK, with no toolkit imports."""

from __future__ import annotations

import math
import random


def wavelength_to_srgb(nanometres: float) -> tuple[float, float, float]:
    """Convert a visible wavelength to an approximate sRGB colour.

    This is the art direction of the default pack: a fluorophore is drawn in the
    colour it actually emits, so the palette is data rather than taste and the
    picture teaches spectra. Wavelengths outside the visible range clamp to the
    nearest visible end rather than fading to black, because an invisible
    creature is a bug, not a feature.

    Parameters
    ----------
    nanometres : float
        Wavelength in nm.

    Returns
    -------
    tuple of float
        sRGB components in 0..1.
    """
    w = float(min(max(nanometres, 380.0), 780.0))
    if w < 440.0:
        r, g, b = -(w - 440.0) / 60.0, 0.0, 1.0
    elif w < 490.0:
        r, g, b = 0.0, (w - 440.0) / 50.0, 1.0
    elif w < 510.0:
        r, g, b = 0.0, 1.0, -(w - 510.0) / 20.0
    elif w < 580.0:
        r, g, b = (w - 510.0) / 70.0, 1.0, 0.0
    elif w < 645.0:
        r, g, b = 1.0, -(w - 645.0) / 65.0, 0.0
    else:
        r, g, b = 1.0, 0.0, 0.0

    # Roll off at the ends of vision, but never all the way to black.
    #
    # The red rolloff starts at 645 rather than 700 deliberately. Above 645 the
    # hue is pure red and stops changing, so without a brightness gradient every
    # wavelength from there to 780 renders *identically* -- which showed up as
    # two adjacent spectral bands that were supposed to differ looking the same.
    # Eye sensitivity really does fall away across that span, so dimming it is
    # both the fix and the more faithful answer. It starts at 620 rather than
    # 645 because two bands only ~40 nm apart still have to be told apart.
    if w < 420.0:
        falloff = 0.3 + 0.7 * (w - 380.0) / 40.0
    elif w > 620.0:
        falloff = 0.28 + 0.72 * (780.0 - w) / 160.0
    else:
        falloff = 1.0
    return r * falloff, g * falloff, b * falloff


#: The visible range the games span, in nanometres. Violet is high-energy and
#: red is low: anything the games rank by difficulty ranks the same way.
VISIBLE_MIN_NM = 405.0
VISIBLE_MAX_NM = 680.0


def spectral_band(fraction: float) -> float:
    """Wavelength at a position across the visible range.

    Used wherever a game needs a series of distinct colours. Taking them from
    the spectrum rather than from a palette means the ordering carries meaning:
    the short-wavelength end is the energetic one, so "harder" and "bluer"
    coincide instead of being two unrelated facts the player must memorise.

    Parameters
    ----------
    fraction : float
        Position in 0..1. ``0`` is violet, ``1`` is deep red.

    Returns
    -------
    float
        Wavelength in nanometres.
    """
    f = min(max(float(fraction), 0.0), 1.0)
    return VISIBLE_MIN_NM + f * (VISIBLE_MAX_NM - VISIBLE_MIN_NM)


def photon_energy_rank(nanometres: float) -> float:
    """How energetic a wavelength is, normalised to 0..1.

    Photon energy goes as the reciprocal of wavelength, so this is not a linear
    ramp -- and using the real relation is what makes "violet is hardest" a
    consequence rather than a decoration.

    Parameters
    ----------
    nanometres : float
        Wavelength in nm.

    Returns
    -------
    float
        ``1`` at the violet end of the visible range, ``0`` at the red end.
    """
    inv = 1.0 / max(nanometres, 1e-6)
    lo = 1.0 / VISIBLE_MAX_NM
    hi = 1.0 / VISIBLE_MIN_NM
    return min(max((inv - lo) / (hi - lo), 0.0), 1.0)


#: Play field in world units, at the original board's pixel dimensions so every
#: speed and size below carries over without rescaling.
W = 800.0
H = 650.0

PADDLE_W = 100.0
PADDLE_H = 16.0
PADDLE_Y = H - 40.0
PADDLE_SPEED = 520.0

BALL_SIZE = 12.0
BASE_BALL_SPEED = 330.0

BRICK_ROWS = 8
BRICK_COLS = 10
BRICK_W = (W - 60.0) / BRICK_COLS
BRICK_H = 22.0
BRICK_TOP = 50.0
BRICK_PAD = 30.0

LIVES = 3

#: The excitation line the detector fires. A real one, and bright on black.
EXCITATION_NM = 488.0

#: The wall is an emission spectrum: one row per band, violet at the top and
#: deep red at the bottom.
ROW_NM = [spectral_band(row / (BRICK_ROWS - 1)) for row in range(BRICK_ROWS)]

#: How many hits a band takes. This is not a difficulty curve someone chose --
#: it follows photon energy, which goes as 1/lambda, so the short-wavelength
#: rows are the hard ones and "bluer" and "tougher" are the same fact rather
#: than two the player has to memorise separately.
ROW_HARDNESS = [1 + int(photon_energy_rank(nm) > 0.5) for nm in ROW_NM]


class Brick:
    """One brick.

    Parameters
    ----------
    x, y : float
        Centre in world units.
    w, h : float
        Size in world units.
    nm : float
        Emission wavelength of this band, in nanometres.
    hp : int
        Hits remaining.
    """

    def __init__(self, x, y, w, h, nm, hp) -> None:
        self.x = x
        self.y = y
        self.w = w
        self.h = h
        self.nm = nm
        self.hp = hp
        self.max_hp = hp

    @property
    def alive(self) -> bool:
        """Whether the brick is still standing.

        Returns
        -------
        bool
            True while it has hits left.
        """
        return self.hp > 0

    def hit(self) -> bool:
        """Take one hit.

        Returns
        -------
        bool
            True when this hit destroyed the brick.
        """
        self.hp -= 1
        return self.hp <= 0


class Particle:
    """A brick fragment.

    Parameters
    ----------
    x, y : float
        Starting position.
    vx, vy : float
        Velocity in world units per second.
    nm : float
        Emission wavelength, in nanometres.
    life : float, optional
        Lifetime in seconds.
    """

    def __init__(self, x, y, vx, vy, nm, life: float = 0.45) -> None:
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy
        self.nm = nm
        self.life = life
        self.max_life = life

    def update(self, dt: float) -> None:
        """Advance the fragment.

        Parameters
        ----------
        dt : float
            Seconds elapsed.
        """
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.vy += 700.0 * dt
        self.life -= dt


class BreakoutModel:
    def __init__(self, host=None):
        self.host = host
        self.restart()

    def restart(self) -> None:
        """Reset score, level and lives, and build the first level."""
        self.score = 0
        self.level = 1
        self.lives = LIVES
        self.paused = False
        self.muted = False
        self.message: str | None = None
        self.init_level()

    def init_level(self) -> None:
        """Lay out the brick grid and re-serve."""
        self.bricks: list[Brick] = []
        self.particles: list[Particle] = []
        for row in range(BRICK_ROWS):
            nm = ROW_NM[row % len(ROW_NM)]
            hp = ROW_HARDNESS[row % len(ROW_HARDNESS)]
            for col in range(BRICK_COLS):
                x = BRICK_PAD + col * BRICK_W + BRICK_W * 0.5
                y = BRICK_TOP + row * (BRICK_H + 4.0) + BRICK_H * 0.5
                self.bricks.append(Brick(x, y, BRICK_W - 8.0, BRICK_H, nm, hp))
        self.paddle_x = W * 0.5
        self.serve()

    def serve(self) -> None:
        """Stick the ball to the paddle and wait for a launch."""
        self.stuck = True
        self.ball_x = self.paddle_x
        self.ball_y = PADDLE_Y - PADDLE_H * 0.5 - BALL_SIZE * 0.5
        self.ball_vx = 0.0
        self.ball_vy = 0.0
        # A freshly served photon carries the excitation line until it
        # interacts. 488 is a real laser line and, unlike the violet end,
        # it is bright enough to follow against a dark field.
        self.ball_nm = EXCITATION_NM

    def launch(self) -> None:
        """Send the ball upward at a random angle."""
        angle = random.uniform(-math.pi / 4, math.pi / 4)
        direction = random.choice((-1.0, 1.0))
        self.ball_vx = math.cos(angle) * BASE_BALL_SPEED * direction
        self.ball_vy = -abs(math.sin(angle) * BASE_BALL_SPEED) - BASE_BALL_SPEED * 0.6
        self.stuck = False
        self._sfx("launch", 540.0)

    def _sfx(self, name: str, frequency: float) -> None:
        """Play a sound effect unless muted.

        Parameters
        ----------
        name : str
            Effect name.
        frequency : float
            Pitch in Hz.
        """
        if not self.muted:
            self.host.audio.sfx(name, frequency)

    def spawn_particles(self, x, y, nm, count: int = 15) -> None:
        """Emit brick fragments.

        Parameters
        ----------
        x, y : float
            Impact point.
        nm : float
            Emission wavelength of the band that released them.
        count : int, optional
            Number of fragments.
        """
        for _ in range(count):
            angle = random.uniform(0, math.tau)
            speed = random.uniform(60.0, 280.0)
            self.particles.append(
                Particle(x, y, math.cos(angle) * speed, math.sin(angle) * speed, nm)
            )

    def update(self, dt: float, keys) -> None:
        """Advance one frame.

        Parameters
        ----------
        dt : float
            Seconds elapsed.
        keys : chisurf.gui.chigame.input.InputMap
            Controller state.
        """
        if keys.just_pressed("menu"):
            self.paused = not self.paused
        if keys.just_pressed("cancel"):
            self.restart()
            return
        if keys.just_pressed("shoulder_r"):
            self.muted = not self.muted
        if self.message is not None:
            if keys.just_pressed("confirm"):
                self.restart()
            return
        if self.paused:
            return

        half = PADDLE_W * 0.5
        self.paddle_x = min(max(self.paddle_x + keys.axis()[0] * PADDLE_SPEED * dt, half), W - half)

        if self.stuck:
            self.ball_x = self.paddle_x
            if keys.just_pressed("confirm"):
                self.launch()
        else:
            self._move_ball(dt)

        for particle in self.particles:
            particle.update(dt)
        self.particles = [p for p in self.particles if p.life > 0.0]

    def _move_ball(self, dt: float) -> None:
        """Advance the ball and resolve every collision.

        Parameters
        ----------
        dt : float
            Seconds elapsed.
        """
        self.ball_x += self.ball_vx * dt
        self.ball_y += self.ball_vy * dt
        radius = BALL_SIZE * 0.5

        if self.ball_x - radius <= 0.0:
            self.ball_x = radius
            self.ball_vx = abs(self.ball_vx)
            self._sfx("wall", 420.0)
        elif self.ball_x + radius >= W:
            self.ball_x = W - radius
            self.ball_vx = -abs(self.ball_vx)
            self._sfx("wall", 420.0)
        if self.ball_y - radius <= 0.0:
            self.ball_y = radius
            self.ball_vy = abs(self.ball_vy)
            self._sfx("wall", 420.0)

        # Paddle: the strike point steers the bounce, as in the original.
        if (
            self.ball_vy > 0.0
            and abs(self.ball_y - PADDLE_Y) <= (PADDLE_H + BALL_SIZE) * 0.5
            and abs(self.ball_x - self.paddle_x) <= (PADDLE_W + BALL_SIZE) * 0.5
        ):
            offset = (self.ball_x - self.paddle_x) / (PADDLE_W * 0.5)
            speed = math.hypot(self.ball_vx, self.ball_vy)
            angle = offset * 1.0
            self.ball_vx = math.sin(angle) * speed
            self.ball_vy = -abs(math.cos(angle) * speed)
            self.ball_y = PADDLE_Y - (PADDLE_H + BALL_SIZE) * 0.5
            self._sfx("paddle", 660.0)

        self._hit_bricks()

        if self.ball_y - radius > H:
            self.lives -= 1
            self._sfx("lost", 180.0)
            if self.lives <= 0:
                self.message = "Sample bleached"
            else:
                self.serve()

    def _hit_bricks(self) -> None:
        """Break the first band the photon overlaps and re-emit off it."""
        radius = BALL_SIZE * 0.5
        for brick in self.bricks:
            if not brick.alive:
                continue
            if (
                abs(self.ball_x - brick.x) > brick.w * 0.5 + radius
                or abs(self.ball_y - brick.y) > brick.h * 0.5 + radius
            ):
                continue
            # Bounce off whichever face was actually crossed: comparing the
            # overlap depths is what stops the photon tunnelling along a row.
            overlap_x = brick.w * 0.5 + radius - abs(self.ball_x - brick.x)
            overlap_y = brick.h * 0.5 + radius - abs(self.ball_y - brick.y)
            if overlap_x < overlap_y:
                self.ball_vx = -self.ball_vx
            else:
                self.ball_vy = -self.ball_vy
            # The photon leaves carrying the band's wavelength, so its colour is
            # a running record of what it last interacted with.
            self.ball_nm = brick.nm
            if brick.hit():
                self.score += 10 * brick.max_hp
                self.spawn_particles(brick.x, brick.y, brick.nm)
                self._sfx("break", 780.0)
            else:
                self._sfx("crack", 520.0)
            break

        if all(not brick.alive for brick in self.bricks):
            self.level += 1
            self.init_level()
