"""Test helpers of the burst-FCS window: the pointer driver (with the table-cell helpers) and the layout checks, all shared.

``SatDriver`` is the saturation calculator's driver over the imaging family's ``Driver``; the clipping/overlap checker is the PSF
calculator's. Only the demonstration data and the waiting for the worker are added here.
"""

from __future__ import annotations

import time

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
