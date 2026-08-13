"""What one frame actually cost, and what the machine drawing it is.

Why this exists
---------------
"It feels slow" is not a measurement, and neither is a frame-rate number on its
own. A viewport locked at 30 fps on a vsynced 60 Hz display is telling you
something quite specific -- that the frame is somewhere between 17 and 33 ms,
so it misses one deadline and waits for the next -- but the counter cannot say
*which* 17 ms, and without that the next thing anybody does is guess.

So this collects the numbers that turn the guess into a reading: where the CPU
time went, how much geometry was submitted, which pipelines ran, what the
ambient-occlusion setting is, and what the machine is. It is filled in by the
renderer as it draws and read by the chrome's **nerd mode**.

Deliberately cheap, deliberately honest
--------------------------------------
Every counter here is either a number the renderer already had or an increment
next to work that costs microseconds; nothing is measured by an extra pass, and
nothing is measured by timing the GPU, because timing the GPU properly needs
timestamp queries that not every backend has. Where a number cannot be got, the
field says so rather than showing a plausible one -- a fabricated "GPU load"
would be worse than no line at all, since it is exactly the number somebody
would act on.

The one measurement that *is* subtle: the readout is drawn as chrome, and the
chrome is cached on a fingerprint of what it draws. A block of numbers that
changes every frame therefore invalidates the chrome every frame -- which is
how switching on a frame-rate counter can destroy the frame rate it reports.
:data:`REPORT_INTERVAL` is why this is published a few times a second instead.
"""
from __future__ import annotations

import os
import platform
import time

__all__ = ["FrameStats", "REPORT_INTERVAL", "machine_info", "cpu_load"]

#: How often the numbers are re-published to the chrome, in seconds. Not a
#: cosmetic choice: see the module docstring.
REPORT_INTERVAL = 0.5


def cpu_load() -> tuple[float, str]:
    """Return ``(fraction, source)`` for the machine's current CPU load.

    Returns
    -------
    tuple
        The load as a fraction of all cores (may exceed 1.0 on a load-average
        reading, which is a queue length rather than a utilisation), and where
        the number came from, so the readout can say which it is showing.

    Notes
    -----
    ``psutil`` is used when it happens to be installed, because it measures
    utilisation directly. It is **not** a dependency: the fallback is
    :func:`os.getloadavg`, which is in the standard library and available
    wherever chimol runs natively. A load average is a different quantity from
    a utilisation and is labelled as such rather than quietly presented as one.
    """
    try:
        import psutil  # noqa: PLC0415

        return psutil.cpu_percent(interval=None) / 100.0, "util"
    except Exception:  # noqa: BLE001 - psutil is optional by design
        pass
    try:
        cores = os.cpu_count() or 1
        return os.getloadavg()[0] / cores, "load avg"
    except (OSError, AttributeError):
        return 0.0, "n/a"


def machine_info() -> str:
    """One line naming the machine: processor, cores and memory.

    Returns
    -------
    str
        e.g. ``"arm64 · 10 cores · 32 GB"``. Assembled from the standard
        library, so it works the same in a frozen build and in a checkout.
    """
    parts = [platform.machine() or platform.processor() or "cpu"]
    cores = os.cpu_count()
    if cores:
        parts.append(f"{cores} cores")
    try:
        total = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
        parts.append(f"{total / (1024 ** 3):.0f} GB")
    except (ValueError, OSError, AttributeError):
        pass
    return " · ".join(parts)


class FrameStats:
    """Counters for the frame being drawn, and the last completed one.

    Two sets, because the frame is still being built when the chrome that
    *reports* it is laid out: reading the live counters would show a frame
    half-drawn, with the chrome's own quads missing because they have not been
    emitted yet. :meth:`begin` moves the live set to the reported one.
    """

    #: Counter names, so the reset and the snapshot cannot drift apart.
    COUNTERS = (
        "draws", "instances", "vertices", "chrome_quads", "chrome_bytes",
        "scene_bytes", "objects",
    )

    def __init__(self) -> None:
        self.enabled = False
        #: Wall-clock milliseconds between the last two frames, and the CPU
        #: milliseconds spent inside the renderer for the last one.
        self.frame_ms = 0.0
        self.cpu_ms = 0.0
        self.chrome_ms = 0.0
        self.scene_ms = 0.0
        #: Set by the renderer as it draws.
        self.ambient_occlusion = ""
        self.pipelines: tuple[str, ...] = ()
        self.adapter = ""
        self.backend = ""
        for name in self.COUNTERS:
            setattr(self, name, 0)
            setattr(self, f"last_{name}", 0)
        self._live_pipelines: set[str] = set()
        self._frame_started = 0.0
        self._cpu_started = 0.0
        self._last_frame_at = 0.0

    # -- collection ----------------------------------------------------- #
    def begin(self) -> None:
        """Start a frame: publish the previous one's counters and reset."""
        now = time.perf_counter()
        if self._last_frame_at:
            self.frame_ms = (now - self._last_frame_at) * 1000.0
        self._last_frame_at = now
        for name in self.COUNTERS:
            setattr(self, f"last_{name}", getattr(self, name))
            setattr(self, name, 0)
        self.pipelines = tuple(sorted(self._live_pipelines))
        self._live_pipelines.clear()
        self._cpu_started = now

    def end(self) -> None:
        """Finish a frame: record the CPU time spent drawing it."""
        if self._cpu_started:
            self.cpu_ms = (time.perf_counter() - self._cpu_started) * 1000.0

    def draw(self, pipeline: str, instances: int = 1, vertices: int = 0) -> None:
        """Record one draw call.

        Parameters
        ----------
        pipeline : str
            Which pipeline it used -- ``"mesh"``, ``"chrome"``, ``"silhouette"``
            and so on. Named rather than counted, because "which passes ran" is
            the question a slow frame raises and a total cannot answer.
        instances : int, optional
            How many instances the call drew.
        vertices : int, optional
            Vertices per instance, so a frame's total is comparable across
            representations that draw the same atoms very differently.
        """
        if not self.enabled:
            return
        self.draws += 1
        self.instances += int(instances)
        self.vertices += int(vertices)
        self._live_pipelines.add(str(pipeline))

    def count(self, name: str, amount: int) -> None:
        """Add *amount* to one of :data:`COUNTERS`."""
        if self.enabled:
            setattr(self, name, getattr(self, name, 0) + int(amount))

    # -- reporting ------------------------------------------------------ #
    def lines(self, fps: float = 0.0) -> tuple[str, ...]:
        """The readout, one string per row.

        Parameters
        ----------
        fps : float, optional
            The measured rate, which the renderer owns rather than this.

        Returns
        -------
        tuple of str
            Ready to draw. Ordered by what a slow frame is asked about first:
            the rate, then where the milliseconds went, then how much was
            submitted, then the machine.
        """
        load, source = cpu_load()
        rate = f"{fps:5.1f} fps" if fps > 0 else "   -- fps"
        budget = ""
        if self.frame_ms > 0.0:
            # The reason a vsynced viewport sits at exactly 30 or exactly 60:
            # a frame that misses the display's deadline waits for the next
            # one. Saying which side of the deadline the frame is on is the
            # whole diagnosis, and it is one comparison.
            budget = " (over 60 Hz budget)" if self.frame_ms > 16.7 else ""
        rows = [
            f"{rate}   frame {self.frame_ms:5.1f} ms{budget}",
            # `wait` is the whole diagnosis of a rate that will not rise: it
            # is the frame minus the work we did, so a large one means the
            # frame is *blocked on presentation* -- vsync, or the scheduler's
            # ceiling -- and a small one means the time is ours and the scene
            # is what to look at. Without it, "33 ms" cannot tell those apart,
            # and they have opposite fixes.
            f"cpu   {self.cpu_ms:5.1f} ms   scene {self.scene_ms:4.1f}   "
            f"chrome {self.chrome_ms:4.1f}   wait {max(self.frame_ms - self.cpu_ms, 0.0):4.1f}",
            f"draws {self.last_draws:5d}   instances {self.last_instances:,}",
            f"chrome {self.last_chrome_quads:,} quads, "
            f"{self.last_chrome_bytes / 1024:.0f} KB",
            f"objects {self.last_objects}   ao {self.ambient_occlusion or 'off'}",
            f"pipelines {', '.join(self.pipelines) or '-'}",
            f"gpu   {self.adapter or '?'} ({self.backend or '?'})",
            f"cpu   {machine_info()}   {load * 100:.0f}% {source}",
        ]
        return tuple(rows)
