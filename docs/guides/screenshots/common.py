"""Constants and helpers shared by the per-guide screenshot modules."""

from __future__ import annotations

import pathlib
import time

from qtpy.QtWidgets import QApplication

#: Where every guide figure lives.
FIG = pathlib.Path(__file__).resolve().parents[1] / "figures"
#: The two-detector BH SPC-132 recording most burst and FCS grabs load.
_SPC_FILE = pathlib.Path("test") / "data" / "tttr" / "BH" / "132" / "BH_SPC132.spc"


def _pump(seconds: float) -> None:
    """Process Qt events for *seconds*, so worker threads and repaints land."""
    end = time.time() + seconds
    while time.time() < end:
        QApplication.instance().processEvents()
        time.sleep(0.02)


def _grab(widget, name: str) -> None:
    """Show *widget*, let it settle, and save a PNG into ``FIG``."""
    widget.show()
    _pump(0.3)
    widget.grab().save(str(FIG / name))
    print("wrote", name)
