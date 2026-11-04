"""The wizard's laser inventory: which heads are installed, as verified.

The companion module :mod:`chisurf.plugins.core.acq.live.power_calibration`
owns everything about a power calibration itself -- the key (laser, conditions),
the verified configuration and emission states, the 3-calendar-month expiry and
the bounded conversion. This module owns the piece that module deliberately
does not: the pool of heads the wizard may offer for selection. Available is
NOT installed: only heads the hardware configuration showed connected -- and
the user verified from its readback -- are selectable, an exchange is manual
(disconnect/reconnect by hand, then verify), and nothing is auto-switched.
"""

from __future__ import annotations

import datetime
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from ..power_calibration import LASER_WAVELENGTHS_NM

__all__ = [
    "AVAILABLE_LASERS_NM",
    "InstallationRecord",
    "LaserInventory",
    "NotInstalled",
]

#: Laser models the instrument line offers, as the wizard lists them. Availability
#: is NOT installation: only heads verified from the hardware configuration may
#: be calibrated or selected.
AVAILABLE_LASERS_NM = tuple(int(w) for w in LASER_WAVELENGTHS_NM)


class NotInstalled(LookupError):
    """A laser was selected that the inventory does not record as verified installed."""


def _now_iso() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


@dataclass
class InstallationRecord:
    """One laser head the user verified from the hardware configuration."""

    wavelength_nm: int
    evidence: str
    verified_at: str
    note: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, doc: dict) -> "InstallationRecord":
        return cls(**doc)


class LaserInventory:
    """Which lasers are installed -- as verified, never as assumed.

    The wizard calibrates ONLY lasers recorded here. An exchange is manual:
    the user disconnects and reconnects cables by hand, then verifies the new
    head; nothing is auto-switched and nothing is inferred from an inactive
    head being present in a settings file. An unverifiable readback is simply
    never recorded -- there is no state a stale record could lie about.
    """

    def __init__(self) -> None:
        self._installed: dict[int, InstallationRecord] = {}
        #: the manual exchanges, for the record
        self.exchange_log: list[dict] = []

    # -- inspection
    def installed(self) -> tuple[int, ...]:
        return tuple(sorted(self._installed))

    def is_verified(self, wavelength_nm: int) -> bool:
        return int(wavelength_nm) in self._installed

    def record(self, wavelength_nm: int) -> InstallationRecord:
        try:
            return self._installed[int(wavelength_nm)]
        except KeyError:
            raise NotInstalled(
                f"{wavelength_nm} nm is not verified installed"
            ) from None

    def select(self, wavelength_nm: int) -> int:
        """The wizard's selection: refused unless the head is verified installed."""
        if not self.is_verified(wavelength_nm):
            raise NotInstalled(
                f"{wavelength_nm} nm is not verified installed -- verify it from the "
                "hardware configuration first; never assume an inactive head is installed"
            )
        return int(wavelength_nm)

    # -- the user's verification acts
    def verify_installed(self, wavelength_nm: int, *, evidence: str, note: str = "") -> InstallationRecord:
        nm = int(wavelength_nm)
        if nm not in AVAILABLE_LASERS_NM:
            raise ValueError(f"{nm} nm is not one of the available lasers {AVAILABLE_LASERS_NM}")
        if not str(evidence).strip():
            raise ValueError(
                "verification needs the hardware-configuration readback as evidence"
            )
        rec = InstallationRecord(
            wavelength_nm=nm, evidence=str(evidence), verified_at=_now_iso(), note=note
        )
        self._installed[nm] = rec
        return rec

    def unverify_installed(self, wavelength_nm: int, *, note: str = "") -> None:
        nm = int(wavelength_nm)
        if nm not in self._installed:
            raise NotInstalled(f"{nm} nm is not installed")
        del self._installed[nm]
        self.exchange_log.append(
            {"wavelength_nm": nm, "note": note, "at": _now_iso()}
        )

    # -- persistence (the wizard's host owns the file)
    def save(self, path: str | Path) -> None:
        doc = {
            "format": "chisurf-laser-inventory",
            "installed": [r.to_dict() for r in self._installed.values()],
            "exchange_log": list(self.exchange_log),
        }
        Path(path).write_text(json.dumps(doc, indent=2))

    @classmethod
    def load(cls, path: str | Path) -> "LaserInventory":
        doc = json.loads(Path(path).read_text())
        inv = cls()
        for rec in doc.get("installed", []):
            parsed = InstallationRecord.from_dict(rec)
            inv._installed[parsed.wavelength_nm] = parsed
        inv.exchange_log = list(doc.get("exchange_log", []))
        return inv
