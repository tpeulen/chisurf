"""The lab bench: dyes are cultured, not only caught.

Part of the farm layer: a collected creature can be planted as a culture, and
the culture matures on a **real-world clock** — because fluorescent-protein
maturation genuinely takes tens of minutes to hours, the growth timer is a
physical property wearing a game mechanic, not an invented wait. Harvesting a
mature culture yields a fresh, unbleached copy of the creature; the original
is a template and is never consumed.

The other half of the farm — the docs as a shared garden — lives in the world
itself: a page whose content moved under its sign-off comes back **withered**
(see :mod:`.world`), visibly rotten from across the map until somebody
re-tends it.

Qt-free and clock-injected: every method takes ``now`` so tests never sleep.
"""

from __future__ import annotations

import dataclasses

#: How many cultures can grow at once. Small: the bench is a rhythm between
#: sessions, not a factory.
PLOTS = 3

#: Maturation bounds, in seconds. Real FP maturation spans roughly this range
#: (fast folders come up in ~15 minutes; slow reds take hours); each creature
#: gets a stable time inside it, seeded by identity.
MATURE_MIN = 15.0 * 60.0
MATURE_MAX = 90.0 * 60.0


def maturation_seconds(probe_id: int) -> float:
    """How long a creature's culture takes to come up.

    Parameters
    ----------
    probe_id : int
        The creature's identity.

    Returns
    -------
    float
        Seconds, stable per creature, inside the real-FP band.
    """
    span = MATURE_MAX - MATURE_MIN
    return MATURE_MIN + (probe_id * 2654435761 % 1000) / 1000.0 * span


@dataclasses.dataclass
class Plot:
    """One growing culture.

    Attributes
    ----------
    probe_id : int
        What is growing.
    planted_at : float
        Wall-clock seconds when it went in.
    duration : float
        Seconds until mature.
    """

    probe_id: int
    planted_at: float
    duration: float

    def progress(self, now: float) -> float:
        """How far along the culture is.

        Parameters
        ----------
        now : float
            Wall-clock seconds.

        Returns
        -------
        float
            0..1, clamped.
        """
        if self.duration <= 0:
            return 1.0
        return max(0.0, min((now - self.planted_at) / self.duration, 1.0))

    def ready(self, now: float) -> bool:
        """Whether the culture can be harvested.

        Parameters
        ----------
        now : float
            Wall-clock seconds.

        Returns
        -------
        bool
            True when mature.
        """
        return self.progress(now) >= 1.0


class Lab:
    """The bench: a handful of plots and the rules between them.

    Parameters
    ----------
    plots : list of Plot, optional
        Restored cultures from a save.
    """

    def __init__(self, plots: list[Plot] | None = None) -> None:
        self.plots: list[Plot] = list(plots or [])

    def can_plant(self) -> bool:
        """Whether the bench has a free plot.

        Returns
        -------
        bool
            True below :data:`PLOTS` cultures.
        """
        return len(self.plots) < PLOTS

    def plant(self, probe_id: int, now: float) -> Plot | None:
        """Start a culture from a collected creature.

        The creature is a template, not an ingredient — planting never
        consumes it, and the same creature can grow on two plots at once.

        Parameters
        ----------
        probe_id : int
            What to culture.
        now : float
            Wall-clock seconds.

        Returns
        -------
        Plot or None
            The new culture, or ``None`` when the bench is full.
        """
        if not self.can_plant():
            return None
        plot = Plot(probe_id=probe_id, planted_at=now,
                    duration=maturation_seconds(probe_id))
        self.plots.append(plot)
        return plot

    def harvest(self, index: int, now: float) -> int | None:
        """Take a mature culture off the bench.

        Parameters
        ----------
        index : int
            Which plot.
        now : float
            Wall-clock seconds.

        Returns
        -------
        int or None
            The harvested creature's probe id, or ``None`` when the plot does
            not exist or is not ready — an immature culture stays put rather
            than being lost to an early click.
        """
        if not 0 <= index < len(self.plots):
            return None
        if not self.plots[index].ready(now):
            return None
        return self.plots.pop(index).probe_id

    def as_rows(self) -> list[list[float]]:
        """Serialise for the save file.

        Returns
        -------
        list
            ``[probe_id, planted_at, duration]`` per plot.
        """
        return [[plot.probe_id, plot.planted_at, plot.duration] for plot in self.plots]

    @classmethod
    def from_rows(cls, rows) -> Lab:
        """Rebuild the bench from a save.

        Parameters
        ----------
        rows : list
            What :meth:`as_rows` produced. Malformed rows are dropped rather
            than refusing the whole save.

        Returns
        -------
        Lab
            The restored bench.
        """
        plots: list[Plot] = []
        for row in rows or []:
            try:
                probe_id, planted_at, duration = row
                plots.append(Plot(int(probe_id), float(planted_at), float(duration)))
            except (TypeError, ValueError):
                continue
        return cls(plots[:PLOTS])
