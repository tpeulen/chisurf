"""Figures of a fit window and its *Plot settings* dock, both drawn by the emtk shell.

Starts the shell on a private session, loads the IBH sample decay with its measured prompt
(``test/data/tcspc/ibh_sample``), adds a lifetime fit, picks the prompt as IRF, scores it over the
decay and fits. Each figure brings a fit page forward, sets what it shows and raises the *Plot
settings* dock, so the whole window shows the page and its settings side by side, as a user sees it.

    pixi run -e test python docs/guides/screenshots/fit_window_emtk.py

Writes into ``docs/manual/figures/``.
"""

from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from manual_shell import ManualShell  # noqa: E402


def _scan(shell: ManualShell, page) -> None:
    """Scan the first free parameter over its scan range (default +-5 %) in 30 steps."""
    page.parameter_name = page.parameter_names()[0]
    page.scan_steps = 30
    page.scan_parameter()
    end = time.monotonic() + 300
    while getattr(page, "_job", None) is not None and time.monotonic() < end:
        shell.driver.frame(1)
        time.sleep(0.05)


def _raw_log_x(shell: ManualShell, page) -> None:
    """Draw the curves raw on a logarithmic time axis."""
    model = page.settings_model()
    model.reference_mode = "raw"
    model.log_x = True
    page.update()


#: ``(file, tab title, change)``: the page to show and what to do with it first.
SHOTS = (
    ("fit_window_plot_settings.png", "Fit", None),
    ("fit_window_reference_settings.png", "Fit", _raw_log_x),
    ("fit_window_info_settings.png", "Info", None),
    ("fit_window_parameter_scan.png", "Parameter scan", _scan),
)


def main() -> None:
    """Write every figure of :data:`SHOTS`."""
    shell = ManualShell(size=(1500, 900))
    shell.ibh_fit()
    for name, title, change in SHOTS:
        page = shell.page(title)
        if change is not None:
            change(shell, page)
            shell.driver.frame(6)
        shell.settings()
        shell.save(name)
    os._exit(0)


if __name__ == "__main__":
    main()
