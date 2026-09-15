"""Frame-level effects: screen transitions and weather.

Ports of the reference's ``transition.gd`` (a full-screen fade with instant and
eased flavours, used around teleports) and the weather half of ``world.gd``
(rain, snow, drifting leaves, clouds and fog, switched per environment). Both
are drawn as ordinary quads through the scene, in screen space, so they cost
nothing when off.
"""

from __future__ import annotations

import numpy as np

from .render import Camera

#: Weather kinds the fx sheet carries art for. The names are the pack's sprite
#: aliases: ``"rain"``, ``"snow"``, ``"leaf"``, ``"cloud"``, ``"fog"``.
RAIN, SNOW, LEAF, CLOUD, FOG = "rain", "snow", "leaf", "cloud", "fog"

_FALLS = {RAIN: 220.0, SNOW: 26.0, LEAF: 20.0}


class Transition:
    """A full-screen fade.

    Parameters
    ----------
    duration : float, optional
        Seconds a fade takes; instant changes ignore it.
    color : tuple of float, optional
        sRGB fade color.
    """

    def __init__(
        self,
        duration: float = 0.3,
        color: tuple[float, float, float, float] = (0.02, 0.02, 0.04, 1.0),
    ) -> None:
        self.duration = duration
        self.color = color
        self.alpha = 0.0
        self._target = 0.0
        self._rate = 0.0
        self.finished = True

    def play(self, cover: bool, instant: bool = False) -> None:
        """Start fading.

        Parameters
        ----------
        cover : bool
            True fades to the cover color, false fades out to the scene.
        instant : bool, optional
            Jump to the end state.
        """
        self._target = 1.0 if cover else 0.0
        self.finished = False
        if instant:
            self.alpha = self._target
            self.finished = True
        else:
            self._rate = 1.0 / self.duration

    @property
    def covered(self) -> bool:
        """Whether the screen is fully covered.

        Returns
        -------
        bool
        """
        return self.alpha >= 0.999

    def update(self, dt: float) -> None:
        """Advance the fade.

        Parameters
        ----------
        dt : float
            Frame step in seconds.
        """
        if self.finished:
            return
        step = self._rate * dt
        if self.alpha < self._target:
            self.alpha = min(self._target, self.alpha + step)
        else:
            self.alpha = max(self._target, self.alpha - step)
        if self.alpha == self._target:
            self.finished = True

    def draw(self, scene, camera: Camera, aspect: float) -> None:
        """Queue the cover quad, in screen space.

        Parameters
        ----------
        scene : chisurf.gui.chigame.scene.Scene
            The frame under construction.
        camera : Camera
            The view whose extents the quad fills.
        aspect : float
            Canvas width over height.
        """
        if self.alpha <= 0.001:
            return
        half = camera.half_extent(aspect)
        color = (self.color[0], self.color[1], self.color[2], self.alpha)
        scene.draw(
            "ui",
            "cover",
            at=(float(camera.center[0]), float(camera.center[1])),
            size=(half[0] * 2.0 + 2.0, half[1] * 2.0 + 2.0),
            color=color,
        )


class Weather:
    """Falling and drifting weather over a view.

    Each active kind keeps its own population of particles, respawned at the
    view edge as they leave it, exactly the feel of the reference's GPU
    emitters with a fraction of the machinery. Fog is not particles: it is two
    large drifting copies of the fog sheet, alpha-tweened in and out.

    Parameters
    ----------
    view : tuple of float, optional
        World width and height the weather covers (a bit more than a room).
    """

    def __init__(self, view: tuple[float, float] = (352.0, 192.0)) -> None:
        self.view = np.asarray(view, dtype=np.float64)
        self.active: set[str] = set()
        self.fog_alpha = 0.0
        self.fog_target = 0.0
        self._drops: dict[str, np.ndarray] = {}
        self._clouds: np.ndarray | None = None
        self._fog_scroll = 0.0

    def set(self, kinds) -> None:
        """Switch the active weather.

        Parameters
        ----------
        kinds : iterable of str
            Active kinds; anything absent fades out (fog) or despawns.
        """
        wanted = set(kinds)
        self.active = wanted
        self.fog_target = 1.0 if FOG in wanted else 0.0
        for kind in wanted:
            if kind in _FALLS and kind not in self._drops:
                count = {"rain": 90, "snow": 40, "leaf": 14}[kind]
                self._drops[kind] = self._spawn(count)
        for kind in list(self._drops):
            if kind not in wanted:
                del self._drops[kind]
        if CLOUD in wanted and self._clouds is None:
            self._clouds = self._spawn(6)
        if CLOUD not in wanted:
            self._clouds = None

    def _spawn(self, count: int) -> np.ndarray:
        """Random particle states inside the view.

        Parameters
        ----------
        count : int
            How many.

        Returns
        -------
        numpy.ndarray
            ``(count, 4)`` — x, y, speed scale, sway phase.
        """
        states = np.zeros((count, 4), dtype=np.float64)
        states[:, 0] = np.random.random(count) * self.view[0]
        states[:, 1] = np.random.random(count) * self.view[1]
        states[:, 2] = 0.7 + np.random.random(count) * 0.6
        states[:, 3] = np.random.random(count) * np.pi * 2.0
        return states

    def update(self, dt: float) -> None:
        """Advance every active kind.

        Parameters
        ----------
        dt : float
            Frame step in seconds.
        """
        for kind, states in self._drops.items():
            fall = _FALLS[kind]
            states[:, 1] += fall * states[:, 2] * dt
            states[:, 3] += dt * (2.0 if kind == LEAF else 0.6)
            states[:, 0] += np.sin(states[:, 3]) * (14.0 if kind == LEAF else 4.0) * dt
            left = states[:, 1] > self.view[1]
            states[left, 1] -= self.view[1]
            states[left, 0] = np.random.random(int(left.sum())) * self.view[0]
            # Sway can walk a particle past the side of a box that shrank
            # under it (a zoom in), and a falling kind has no horizontal
            # wrap of its own -- without this it would hang off-screen until
            # its next bottom wrap, which for a leaf is most of a minute.
            wide = states[:, 0] > self.view[0]
            states[wide, 0] -= self.view[0]
        if self._clouds is not None:
            self._clouds[:, 0] += 12.0 * self._clouds[:, 2] * dt
            # Wrap each cloud outside its *own* width: the sprite is roughly
            # 80 source pixels times the cloud's scale, and a fixed ±60-unit
            # margin pops a zoomed cloud into existence fully on-screen --
            # at a close zoom the art is hundreds of world units wide.
            width = 80.0 * self._clouds[:, 2]
            gone = self._clouds[:, 0] - width > self.view[0]
            self._clouds[gone, 0] = -width[gone]
        if self.fog_alpha != self.fog_target:
            step = dt / 2.0
            if self.fog_alpha < self.fog_target:
                self.fog_alpha = min(self.fog_target, self.fog_alpha + step)
            else:
                self.fog_alpha = max(self.fog_target, self.fog_alpha - step)
        self._fog_scroll += dt * 6.0

    def particles(self, kind: str):
        """Yield one falling kind's particle states, view-relative.

        For a game that draws weather through its own sprite names rather
        than the pack vocabulary: this exposes the same simulation the
        :meth:`draw` path renders, position and all, without reaching into
        the arrays.

        Parameters
        ----------
        kind : str
            One of :data:`RAIN`, :data:`SNOW`, :data:`LEAF`.

        Yields
        ------
        tuple of float
            ``(x, y, scale, phase)`` in view coordinates, top-left origin.
        """
        states = self._drops.get(kind)
        if states is None:
            return
        for x, y, scale, phase in states:
            yield float(x), float(y), float(scale), float(phase)

    def clouds(self):
        """Yield the drifting cloud states, view-relative.

        Clouds are not a falling kind: they live in their own population and
        drift sideways rather than fall, so a game drawing weather through
        its own sprite names gets them through this rather than
        :meth:`particles`.

        Yields
        ------
        tuple of float
            ``(x, y, scale, phase)`` in view coordinates, top-left origin.
        """
        states = self._clouds
        if states is None:
            return
        for x, y, scale, phase in states:
            yield float(x), float(y), float(scale), float(phase)

    def draw(self, scene, camera: Camera) -> None:
        """Queue the weather around the view centre.

        Weather is positioned relative to the *camera*, not the world — rain
        follows the player the way the reference's emitters, parented to the
        world node around the camera, do.

        Parameters
        ----------
        scene : chisurf.gui.chigame.scene.Scene
            The frame under construction.
        camera : Camera
            The view.
        """
        cx, cy = float(camera.center[0]), float(camera.center[1])
        left, top = cx - self.view[0] * 0.5, cy - self.view[1] * 0.5
        for kind, states in self._drops.items():
            for index, (x, y, _scale, _phase) in enumerate(states):
                if kind == RAIN:
                    scene.draw("sprite", "rain", at=(left + x, top + y),
                               size=(2.0, 5.0), alpha=0.55)
                elif kind == SNOW:
                    scene.draw("tile", "snowflake", at=(left + x, top + y),
                               size=(8.0, 8.0), state=f"0,{index % 7}", alpha=0.7)
                else:
                    scene.draw("tile", "leaflet", at=(left + x, top + y),
                               size=(12.0, 7.0), state=f"0,{index % 6}", alpha=0.85)
        if self._clouds is not None:
            for x, y, scale, _phase in self._clouds:
                scene.draw("sprite", "cloud",
                           at=(x - 30.0, top + y * 0.3),
                           size=(80.0 * scale, 36.0 * scale), alpha=0.5)
        if self.fog_alpha > 0.01:
            # The reference's fog is a slow-breathing veil over the scene, not
            # a wall: one drifting sheet at low alpha, with the second layer
            # half as strong again for depth. Two full-view sheets at 0.8
            # washed every tile into paste — the reference's own fog shader
            # peaks around a quarter.
            drift = (self._fog_scroll % self.view[0])
            for layer, strength in ((0.0, 0.30), (0.5, 0.15)):
                x = cx - self.view[0] * (0.5 - layer) + drift * 0.2
                scene.draw("sprite", "fog", at=(x, cy),
                           size=(self.view[0], self.view[1]),
                           alpha=self.fog_alpha * strength)
