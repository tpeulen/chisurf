"""Test helpers of the filter calculator window: the pointer driver (with the table-cell helpers) and the layout checks.

Everything is shared: the imaging family's ``Driver`` through the saturation calculator's ``SatDriver`` (table cells) and the
PSF calculator's clipping/overlap checker.
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


class FilterDriver(SatDriver):
    """Operates the window; ``settle`` waits for the worker."""

    def settle(self, timeout=120.0, extra=2):
        end = time.monotonic() + timeout
        self.draw(1)
        while self.app.job.running and time.monotonic() < end:
            time.sleep(0.02)
            self.draw(1)
        assert not self.app.job.running, "the computation did not finish"
        return self.draw(extra)

    def tab(self, name):
        self.click_text(name)
        return self.draw(3)
