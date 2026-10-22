"""Toolkit-free view model behind the Burstwise → PTO converter."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable

from chisurf.core.fio.fluorescence.burstwise_import import (
    BurstwiseImportError,
    ImportReport,
    convert_folder,
    parse_mti,
    scan_folder,
)
from chisurf.plugins.burst.burstwise_import import create_beside_resolver, create_mti_resolver

logger = logging.getLogger(__name__)


class BurstwiseImportViewModel:
    """State and business logic for the Burstwise → PTO conversion tool."""

    def __init__(self) -> None:
        self.folder: str = ""
        self.inventory: dict[str, Any] | None = None
        self.mti_entries: dict[str, float] = {}
        self.resolver_mode: str = "mti"  # "mti" | "beside"
        self.old_prefix: str = "N:\\"
        self.new_prefix: str = ""
        self.dry_run: bool = False
        self.raw_data: str = "sidecar"  # "embed" | "sidecar"
        self.report_unmapped: bool = True
        self.out_dir: str = ""

        self.report: ImportReport | None = None
        self.status_text: str = ""
        self.messages: list[str] = []
        self.is_running: bool = False

        self._observers: list[Callable[[str], None]] = []

    def add_observer(self, callback: Callable[[str], None]) -> None:
        """Register an event observer."""
        if callback not in self._observers:
            self._observers.append(callback)

    def remove_observer(self, callback: Callable[[str], None]) -> None:
        """Unregister an event observer."""
        if callback in self._observers:
            self._observers.remove(callback)

    def notify(self, event: str = "change") -> None:
        """Notify all observers of an event."""
        for obs in list(self._observers):
            try:
                obs(event)
            except Exception:
                logger.warning("BurstwiseImportViewModel observer failed", exc_info=True)

    def load_example(self) -> None:
        """The demo affordance: the shipped legacy sample folder, inventoried."""
        from chisurf.plugins.burst.burstwise_import.demo import load_into

        load_into(self)

    def set_folder(self, folder: str | Path) -> None:
        """Set active burstwise folder."""
        self.folder = str(folder).strip()
        self.notify("folder")

    def scan(self, folder: str | Path | None = None) -> dict[str, Any]:
        """Inventory the target burstwise folder."""
        if folder is not None:
            self.folder = str(folder).strip()
        if not self.folder:
            raise BurstwiseImportError("No folder path specified")

        inv = scan_folder(self.folder)
        self.inventory = inv

        if inv.get("mti"):
            self.mti_entries = parse_mti(inv["mti"])
            if self.mti_entries and self.old_prefix == "N:\\":
                first_key = next(iter(self.mti_entries))
                if len(first_key) >= 3 and first_key[1:3] == ":\\":
                    self.old_prefix = first_key[:3]
        else:
            self.mti_entries = {}

        stem_count = len(inv.get("tables", {}))
        self.status_text = f"Scanned: {stem_count} measurement stem(s) found."
        self.messages.append(f"Scanned {self.folder}: {stem_count} stem(s).")
        self.notify("scan")
        return inv

    def build_resolver(self) -> Callable[[str, dict[str, float]], Path | None]:
        """Construct the source TTTR resolver callback based on current mode."""
        if self.resolver_mode == "mti":
            return create_mti_resolver(self.old_prefix, self.new_prefix)
        return create_beside_resolver(self.folder)

    def convert(
        self,
        folder: str | Path | None = None,
        out_dir: str | Path | None = None,
        dry_run: bool | None = None,
    ) -> ImportReport:
        """Execute conversion on current or provided folder."""
        target_folder = folder if folder is not None else self.folder
        if not target_folder:
            raise BurstwiseImportError("No folder path specified for conversion")

        resolver = self.build_resolver()
        effective_out = out_dir if out_dir is not None else (self.out_dir or None)
        effective_dry = dry_run if dry_run is not None else self.dry_run

        rep = convert_folder(
            target_folder,
            source_resolver=resolver,
            out_dir=effective_out,
            dry_run=effective_dry,
            raw_data=self.raw_data,
        )
        self.report = rep
        self.status_text = rep.summary()
        self.messages.append(rep.summary())
        self.notify("convert")
        return rep

    def clear(self) -> None:
        """Clear queued scan, results, and messages."""
        self.inventory = None
        self.mti_entries.clear()
        self.report = None
        self.status_text = ""
        self.messages.clear()
        self.notify("clear")

    def export_settings(self) -> dict[str, Any]:
        """Export current settings dictionary."""
        return {
            "folder": self.folder,
            "resolver_mode": self.resolver_mode,
            "old_prefix": self.old_prefix,
            "new_prefix": self.new_prefix,
            "dry_run": self.dry_run,
            "report_unmapped": self.report_unmapped,
            "out_dir": self.out_dir,
        }

    def restore_settings(self, settings: dict[str, Any]) -> None:
        """Restore configuration from settings dictionary."""
        if not isinstance(settings, dict):
            return
        for key in (
            "folder",
            "resolver_mode",
            "old_prefix",
            "new_prefix",
            "dry_run",
            "report_unmapped",
            "out_dir",
        ):
            if key in settings:
                setattr(self, key, settings[key])
        self.notify("restore")
