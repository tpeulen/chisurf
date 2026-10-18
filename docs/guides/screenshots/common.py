"""Constants and helpers shared by the per-guide screenshot modules."""

from __future__ import annotations

import pathlib
import time

#: Where every guide figure lives.
FIG = pathlib.Path(__file__).resolve().parents[1] / "figures"
#: The two-detector BH SPC-132 recording most burst and FCS grabs load.
_SPC_FILE = pathlib.Path("test") / "data" / "tttr" / "BH" / "132" / "BH_SPC132.spc"


def _pump(seconds: float) -> None:
    """Wait *seconds*, so worker threads land before the next frame is drawn."""
    time.sleep(seconds)
