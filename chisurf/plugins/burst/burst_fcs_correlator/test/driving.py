"""Test helpers of the burst-FCS window: the pointer driver (with the table-cell helpers) and the layout checks, all shared.

``SatDriver`` is the saturation calculator's driver over the imaging family's ``Driver``; the clipping/overlap checker is the PSF
calculator's. Only the demonstration data and the waiting for the worker are added here.
"""

from __future__ import annotations

import time
from pathlib import Path

from chisurf.plugins.calculator.fcs_saturation_calc.tests.driving import (  # noqa: F401
    BIG,
    SMALL,
    SatDriver,
    clipped_texts,
    draw_clip,
    hermetic_env,
    layout_problems,
)


class BurstDriver(SatDriver):
    def settle(self, timeout=60.0, extra=2):
        """Draw until the correlation has finished and its curves are shown."""
        end = time.monotonic() + timeout
        self.draw(1)
        while (
            self.app.controller.running or self.app.controller._future is not None
        ) and time.monotonic() < end:
            time.sleep(0.02)
            self.draw(1)
        assert not self.app.controller.running, "the correlation did not finish"
        return self.draw(extra)

    def tab(self, name):
        self.click_text(name)
        return self.draw(3)


def make_input_container(folder, ranges, name="measurement"):
    """A measurement ``.pto`` with one burst-search run of *ranges* — the tool's sanctioned input.

    Legacy ``.bst``/``.bur`` layouts are no longer inputs; tests build what the
    GUI accepts: a stream (the BH SPC-132 sample) packed into a container with
    one run whose burst table carries *ranges* (``first, last`` photon indices).
    Returns ``(raw_stream, container)``.
    """
    import shutil

    from chisurf.plugins.burst.burst_fcs_correlator import demo as _demo
    from chisurf.plugins.burst.burst_selection.api.io import write_container

    source = Path(__file__).resolve().parents[5] / "test/data/tttr/BH/132/BH_SPC132.spc"
    raw = Path(folder) / f"{name}.spc"
    shutil.copyfile(source, raw)
    write_container(
        raw, _demo.demo_burst_table(list(ranges)), parameters={"test": True}, run="run1#1"
    )
    return raw, raw.with_suffix(".pto")
