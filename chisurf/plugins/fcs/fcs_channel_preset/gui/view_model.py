"""Qt-free view-model for the FCS channel-definition editor.

Holds the editing state (selected detector setup, its logical channels, the
channel-pair list and the *public* flag) and the load/save logic, exposing the
attributes and methods that ``fcs_channel_preset.view.json`` binds to. The
concrete Qt widgets are built by :class:`~chisurf.gui.autoform.auto_form.AutoForm`
from that spec plus the custom ``fcs_channel_pairs`` section
(:mod:`chisurf.plugins.fcs.fcs_channel_preset.gui.sections`).

The channel-pair schema mirrors the on-disk ``fcs_channel_setups.json`` (see the
plugin ``tool`` module docstring): each pair is
``{"name", "channel_a", "channel_b", "n_bins", "n_casc", "make_fine"}``.

GUI-side helpers (``load_detector_setups`` / ``resolve_active_user_id``) are
imported lazily inside methods so importing this module stays cheap and the
class construction cost is paid only when the tool actually opens.
"""

from __future__ import annotations

import json
import pathlib
import typing

from chisurf.core.dataspec import load_view_spec

#: Declarative layout consumed by :meth:`FCSChannelViewModel.view_spec`.
_VIEW_JSON = pathlib.Path(__file__).with_name("fcs_channel_preset.view.json")

#: Editable keys of a channel-pair record.
_PAIR_KEYS = ("name", "channel_a", "channel_b", "n_bins", "n_casc", "make_fine")

#: Observer callback signature: ``(event_name) -> None``.
Observer = typing.Callable[[str], None]


class FCSChannelViewModel:
    """State + logic behind the FCS channel-definition editor (Qt-free)."""

    def __init__(self, db_path: str | None = None) -> None:
        self._db_path = db_path
        self._detector_setups: dict[str, typing.Any] = {}
        self._fcs_cfg: dict[str, typing.Any] = {}
        self._current_setup: str | None = None
        self._channel_names: list[str] = []
        self._pairs: list[dict[str, typing.Any]] = []
        self._is_public = False
        self._can_edit_public = False
        self._observers: list[Observer] = []
        self._load_initial()

    # ── observer plumbing ────────────────────────────────────────────
    def add_observer(self, callback: Observer) -> None:
        """Register a callback invoked with an event name on every state change."""
        self._observers.append(callback)

    def notify(self, event: str) -> None:
        """Emit *event* to every registered observer (exceptions swallowed)."""
        for callback in list(self._observers):
            try:
                callback(event)
            except Exception:  # noqa: BLE001 - an observer must never break the model
                pass

    # ── initial load ─────────────────────────────────────────────────
    def _load_initial(self) -> None:
        from chisurf.core.fluorescence.fcs.channel_setups import load_fcs_channel_setups

        self._reload_detector_setups_data()
        self._fcs_cfg = load_fcs_channel_setups(db_path=self._db_path, skip_migration=True)
        names = self.setup_names()
        last = self._fcs_cfg.get("last_used_setup") if isinstance(self._fcs_cfg, dict) else None
        if isinstance(last, str) and last in names:
            self.current_setup = last
        elif names:
            self.current_setup = names[0]

    def _reload_detector_setups_data(self) -> None:
        from chisurf.gui.widgets.wizard.tttr_channeldefinition import load_detector_setups

        data = load_detector_setups(db_path=self._db_path, skip_migration=True)
        self._detector_setups = data.get("setups", {}) if isinstance(data, dict) else {}

    # ── detector-setup selection (bound: choice attr ``current_setup``) ──
    def setup_names(self) -> list[str]:
        """Return the sorted detector-setup names (choice ``options_source``)."""
        return sorted(self._detector_setups.keys())

    @property
    def current_setup(self) -> str:
        """Name of the selected detector setup (bound choice value)."""
        return self._current_setup or ""

    @current_setup.setter
    def current_setup(self, value: str) -> None:
        self._current_setup = (value or "").strip() or None
        self._refresh_for_setup()
        self.notify("setup_changed")

    def _refresh_for_setup(self) -> None:
        """Recompute channels, pairs and the public flag for the current setup."""
        self._channel_names = []
        setup = self._detector_setups.get(self._current_setup) if self._current_setup else None
        if isinstance(setup, dict):
            from chisurf.core.fluorescence.fcs.channel_setups import build_channels_from_setup

            channels = build_channels_from_setup(
                setup.get("windows", {}) or {}, setup.get("detectors", {}) or {}
            )
            self._channel_names = sorted(channels.keys())

        cfg_all = self._fcs_cfg.get("setups", {}) if isinstance(self._fcs_cfg, dict) else {}
        cfg = cfg_all.get(self._current_setup, {}) if self._current_setup else {}
        raw_pairs = cfg.get("pairs", []) if isinstance(cfg, dict) else []
        self._pairs = [self._normalize_pair(p) for p in raw_pairs if isinstance(p, dict)]

        self._is_public = bool(cfg.get("_is_public", False)) if isinstance(cfg, dict) else False
        owner = cfg.get("_owner") if isinstance(cfg, dict) else None
        try:
            from chisurf.gui.widgets.wizard.tttr_channeldefinition.tttr_setup_utils import (
                resolve_active_user_id,
            )

            active = resolve_active_user_id()
        except Exception:  # noqa: BLE001
            active = None
        self._can_edit_public = owner is None or owner == active

    @staticmethod
    def _normalize_pair(pair: typing.Mapping[str, typing.Any]) -> dict[str, typing.Any]:
        return {
            "name": str(pair.get("name", "")),
            "channel_a": str(pair.get("channel_a", "")),
            "channel_b": str(pair.get("channel_b", "")),
            "n_bins": pair.get("n_bins"),
            "n_casc": pair.get("n_casc"),
            "make_fine": pair.get("make_fine"),
        }

    # ── channels + pairs (consumed by the custom section) ────────────
    @property
    def channel_names(self) -> list[str]:
        """Logical channel keys available for the current detector setup."""
        return list(self._channel_names)

    @property
    def pairs(self) -> list[dict[str, typing.Any]]:
        """Live, mutable list of channel-pair records (custom-section target)."""
        return self._pairs

    def _correlator_defaults(self) -> tuple[int, int, bool]:
        from chisurf.core.settings import cs_settings

        def _int(key: str, default: int) -> int:
            try:
                return int(cs_settings["correlator"][key])
            except Exception:  # noqa: BLE001
                return default

        try:
            fine = bool(cs_settings["correlator"]["fine"])
        except Exception:  # noqa: BLE001
            fine = True
        return _int("B", 2), _int("number_of_cascades", 25), fine

    def add_pair(self, channel_a: str, channel_b: str, name: str = "") -> None:
        """Append a channel pair seeded with the default correlator settings."""
        a = (channel_a or "").strip()
        b = (channel_b or "").strip()
        if not a or not b:
            return
        name = (name or "").strip() or (f"{a}×{b}" if a != b else f"{a}_ACF")
        n_bins, n_casc, fine = self._correlator_defaults()
        self._pairs.append(
            {"name": name, "channel_a": a, "channel_b": b,
             "n_bins": n_bins, "n_casc": n_casc, "make_fine": fine}
        )
        self.notify("pairs_changed")

    def remove_pair(self, index: int) -> None:
        """Remove the pair at *index* (no-op if out of range)."""
        if 0 <= index < len(self._pairs):
            self._pairs.pop(index)
            self.notify("pairs_changed")

    def update_pair(self, index: int, key: str, value: typing.Any) -> None:
        """Write a single field of an existing pair (called on cell edits)."""
        if 0 <= index < len(self._pairs) and key in _PAIR_KEYS:
            self._pairs[index][key] = value

    # ── public flag (bound: toggle attr ``is_public``) ───────────────
    @property
    def is_public(self) -> bool:
        """Whether this setup is shared with all MMFDB users (bound toggle)."""
        return self._is_public

    @is_public.setter
    def is_public(self, value: bool) -> None:
        self._is_public = bool(value)

    @property
    def can_edit_public(self) -> bool:
        """Whether the active user owns this setup (may flip the public flag)."""
        return self._can_edit_public

    # ── actions (bound: button_row actions) ──────────────────────────
    def reload_setups(self) -> None:
        """Re-read detector setups from disk, preserving the selection if valid."""
        self._reload_detector_setups_data()
        names = self.setup_names()
        if self._current_setup not in names:
            self.current_setup = names[0] if names else ""
        self.notify("setups_reloaded")

    def save(self) -> bool:
        """Persist the current setup's channel pairs and public flag."""
        if not self._current_setup:
            self.notify("no_setup")
            return False
        from chisurf.core.fluorescence.fcs.channel_setups import (
            load_fcs_channel_setups,
            save_fcs_channel_setups,
        )

        cfg_all = load_fcs_channel_setups()
        setups = cfg_all.get("setups")
        if not isinstance(setups, dict):
            setups = {}
            cfg_all["setups"] = setups
        setups[self._current_setup] = self._collect_setup_data()
        cfg_all["last_used_setup"] = self._current_setup
        ok = bool(save_fcs_channel_setups(cfg_all, is_public=self._is_public))
        self._fcs_cfg = cfg_all
        self.notify("saved" if ok else "save_failed")
        return ok

    def _collect_setup_data(self) -> dict[str, typing.Any]:
        pairs: list[dict[str, typing.Any]] = []
        for pair in self._pairs:
            a = str(pair.get("channel_a", "")).strip()
            b = str(pair.get("channel_b", "")).strip()
            if not a or not b:
                continue
            name = str(pair.get("name", "")).strip() or (f"{a}×{b}" if a != b else f"{a}_ACF")
            record: dict[str, typing.Any] = {
                "name": name,
                "channel_a": a,
                "channel_b": b,
                "kind": "ACF" if a == b else "CCF",
            }
            for key in ("n_bins", "n_casc"):
                value = pair.get(key)
                if value not in (None, ""):
                    try:
                        record[key] = int(value)
                    except (TypeError, ValueError):
                        pass
            fine = pair.get("make_fine")
            if fine is not None:
                record["make_fine"] = bool(fine)
            pairs.append(record)
        return {"pairs": pairs, "_is_public": self._is_public}

    def request_close(self) -> None:
        """Ask the hosting tool to close (dispatched via the ``close`` event)."""
        self.notify("close")

    # ── view spec ────────────────────────────────────────────────────
    def view_spec(self):
        """Parse the bundled ``view.json`` into a :class:`ModelView`."""
        spec = json.loads(_VIEW_JSON.read_text(encoding="utf-8"))
        return load_view_spec(spec)
