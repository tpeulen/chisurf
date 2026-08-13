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
from collections import deque

__all__ = ["FrameStats", "REPORT_INTERVAL", "machine_info", "cpu_load"]

#: How often the numbers are re-published to the chrome, in seconds. Not a
#: cosmetic choice: see the module docstring.
REPORT_INTERVAL = 0.5

#: Whether :func:`cpu_load` has taken its first ``psutil`` sample.
_CPU_PRIMED = False

#: Frames of history the graphs keep. At a smooth 60 Hz that is two seconds,
#: which is the window in which a stutter is still felt as one -- longer and a
#: single bad frame is one pixel wide and invisible.
HISTORY = 120

#: The series the graphs draw, as ``(key, label, unit)``. Data, because the
#: collector, the publisher and the painter all enumerate them and three
#: hand-written lists is three chances for one to be forgotten.
SERIES: tuple[tuple[str, str, str], ...] = (
    ("fps", "frame rate", "fps"),
    ("frame_ms", "frame time", "ms"),
    ("cpu_load", "cpu", "%"),
    ("instances", "gpu submitted", "inst"),
)

#: The parts a frame's time is split into, drawn stacked. Ordered as they
#: happen, so the bar reads left-to-right in time as well as bottom-to-top.
BREAKDOWN: tuple[tuple[str, str, tuple], ...] = (
    ("scene_ms", "scene", (120, 170, 240)),
    ("chrome_ms", "chrome", (245, 200, 110)),
    ("wait_ms", "wait", (150, 150, 165)),
)


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

        # Primed on the first call: `cpu_percent(interval=None)` measures
        # *since the previous call*, so the very first one has nothing to
        # compare against and returns 0.0. Reported as-is that reads as an idle
        # machine, which is a wrong answer rather than a missing one.
        global _CPU_PRIMED
        if not _CPU_PRIMED:
            psutil.cpu_percent(interval=None)
            _CPU_PRIMED = True
            return 0.0, "priming"
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
        #: Per-frame history for the graphs. Appended on every frame -- which
        #: is cheap, a deque append of a float -- and *published* to the chrome
        #: only on :data:`REPORT_INTERVAL`, because the chrome is cached on
        #: what it draws and a graph that advanced every frame would rebuild it
        #: every frame. The graph still shows per-frame detail; it is the
        #: *snapshot* that is taken twice a second, not the sampling.
        self.history: dict[str, deque] = {
            name: deque(maxlen=HISTORY)
            for name in [key for key, _l, _u in SERIES]
            + [key for key, _l, _c in BREAKDOWN]
        }

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
        if self.enabled and self.frame_ms > 0.0:
            self._record()

    def end(self) -> None:
        """Finish a frame: record the CPU time spent drawing it."""
        if self._cpu_started:
            self.cpu_ms = (time.perf_counter() - self._cpu_started) * 1000.0

    def _record(self) -> None:
        """Append the frame just finished to the graph history.

        The load is read here rather than in :meth:`lines`, so the graph and
        the printed figure are the same sample rather than two readings taken
        a moment apart -- which, on a number that moves as fast as CPU load,
        looks like one of them being wrong.
        """
        history = self.history
        history["fps"].append(1000.0 / self.frame_ms if self.frame_ms > 0 else 0.0)
        history["frame_ms"].append(self.frame_ms)
        history["cpu_load"].append(cpu_load()[0] * 100.0)
        history["instances"].append(float(self.last_instances))
        history["scene_ms"].append(self.scene_ms)
        history["chrome_ms"].append(self.chrome_ms)
        # What the frame spent *not* working: the presentation wait. Clamped at
        # zero because the two clocks are read at slightly different points and
        # a hair of negative wait is noise, not a discovery.
        history["wait_ms"].append(max(self.frame_ms - self.cpu_ms, 0.0))

    def graphs(self) -> tuple:
        """A snapshot of the history, in the form the chrome compares and draws.

        Tuples rather than the live deques: the chrome caches on a fingerprint
        of what it draws, and a mutable sequence would compare equal to itself
        after changing, which is the silent half of a stale-picture bug.

        Returns
        -------
        tuple
            ``((key, label, unit, samples), ...)`` for :data:`SERIES`, then one
            extra entry, ``("breakdown", ...)``, carrying the stacked series.
        """
        rows = [
            (key, label, unit, tuple(self.history[key]))
            for key, label, unit in SERIES
        ]
        rows.append((
            "breakdown", "frame time, in detail", "ms",
            tuple(
                (key, label, colour, tuple(self.history[key]))
                for key, label, colour in BREAKDOWN
            ),
        ))
        return tuple(rows)

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
