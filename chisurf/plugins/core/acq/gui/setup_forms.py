"""The Device Setup cards as AutoForm forms: ``bh_setup``, ``picoquant_setup`` and ``brickmic_setup.view.json``.

Each card is declared in its ``view.json`` and drawn by :func:`emtk.view_form.draw_sections` over one of the
form objects below. A form is the binding layer between the declaration and the Qt-free contract of
:mod:`.setup_models`: a ``value`` or ``choice`` section's ``attr`` reads and writes one setting, a ``button_row``
action is a method, an ``info`` section's ``source`` returns its text, the BH module list is a ``data_table`` whose
rows come from :meth:`BHSetupForm.card_rows`. Nothing here draws; the acquisition window
(:mod:`.app`) owns the card's dialog window and its file chooser.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .setup_models import (
    BH_PARAMETERS,
    BHSetupModel,
    BrickMicSetupModel,
    PicoQuantSetupModel,
)

#: The ``view.json`` of each card, beside this module.
SPECS = {
    BHSetupModel: "bh_setup.view.json",
    PicoQuantSetupModel: "picoquant_setup.view.json",
    BrickMicSetupModel: "brickmic_setup.view.json",
}


class _CardForm:
    """What every card's form shares: the status line and the OK / close and Cancel buttons."""

    def __init__(self, setup: Any, on_close: Callable[[], Any]) -> None:
        self.setup = setup
        self._on_close = on_close

    def status_text(self) -> str:
        """The card's status line: what the last action did, or why it did not."""
        return str(self.setup.status)

    def ok(self) -> None:
        """*OK / close*: close the card; only what Apply wrote affects the device or acquisition."""
        self._on_close()

    def cancel(self) -> None:
        """*Cancel*: close the card without applying pending edits."""
        self._on_close()


class BHSetupForm(_CardForm):
    """The BH SPC card: detection, module selection, the five parameter tabs and the file actions.

    Every retained BH parameter (``BH_PARAMETERS``) is an attribute of its own name (``CFD_LIMIT_LOW``, ...) that
    reads and writes ``setup.values``, so ``bh_setup.view.json`` binds them as ordinary fields.
    """

    def __init__(
        self,
        setup: BHSetupModel,
        on_close: Callable[[], Any],
        request_file: Callable[[str], Any],
        on_applied: Callable[[bool], Any],
    ) -> None:
        super().__init__(setup, on_close)
        self._request_file = request_file
        self._on_applied = on_applied

    @property
    def simulation_mode(self) -> bool:
        return bool(self.setup.simulation_mode)

    @simulation_mode.setter
    def simulation_mode(self, value: bool) -> None:
        self.setup.simulation_mode = bool(value)

    # -- the module list (data_table) ---------------------------------------------------------- #
    def card_rows(self) -> list[dict]:
        """One row per detected module: its tick (in the active-card selection), number and status."""
        return [
            {
                "module": int(card["module_number"]),
                "use": int(card["module_number"]) in self.setup.active_cards,
                "label": f"Module {int(card['module_number'])}",
                "status": str(card.get("status", "Unknown")),
            }
            for card in self.setup.cards
        ]

    def set_card_use(self, record: dict, key: str, value: Any) -> None:
        """A tick in the *Use* column adds the module to, or removes it from, the active-card selection."""
        if key != "use":
            return
        module = int(record["module"])
        cards = [item for item in self.setup.active_cards if item != module]
        if value:
            cards.append(module)
        self.setup.active_cards = cards

    # -- actions ------------------------------------------------------------------------------ #
    def detect_cards(self) -> None:
        self.setup.detect_cards()

    def read_values(self) -> None:
        self.setup.read_parameters()

    def save_json(self) -> None:
        self._request_file("bh_save")

    def load_json(self) -> None:
        self._request_file("bh_load")

    def apply(self) -> None:
        self._on_applied(self.setup.apply())


def _bh_value(name: str, integer: bool) -> property:
    def get(self: BHSetupForm) -> int | float:
        value = self.setup.values[name]
        return int(value) if integer else float(value)

    def put(self: BHSetupForm, value: Any) -> None:
        self.setup.values[name] = int(round(float(value))) if integer else float(value)

    return property(get, put, doc=f"The BH parameter ``{name}``.")


for _spec in BH_PARAMETERS:
    setattr(BHSetupForm, _spec.name, _bh_value(_spec.name, _spec.integer))


class PicoQuantSetupForm(_CardForm):
    """The PicoQuant card: the firmware's modes (read only), the maximum-photon stop and the device status."""

    def __init__(
        self, setup: PicoQuantSetupModel, on_close: Callable[[], Any], acquisition: Any
    ) -> None:
        super().__init__(setup, on_close)
        self._acquisition = acquisition

    @property
    def max_photons(self) -> int:
        return int(self.setup.max_photons)

    @max_photons.setter
    def max_photons(self, value: Any) -> None:
        self.setup.max_photons = int(round(float(value)))

    def modes_text(self) -> str:
        """The two settings the firmware and INI files own, as the Qt dialog showed them."""
        return (
            f"Measurement mode (firmware): {self.setup.measurement_mode}\n"
            f"Reference source (firmware): {self.setup.reference_source}"
        )

    def refresh_status(self) -> None:
        self.setup.detect_status()

    def apply(self) -> None:
        self.setup.apply(self._acquisition)


class BrickMicSetupForm(_CardForm):
    """The BrickMic card: the five hardware and SPC-output settings and the derived channel count."""

    def channels_text(self) -> str:
        """Channels follow the counter window (end - start + 1); Apply writes them with the rest."""
        return f"Channels (derived): {int(self.setup.values['channels'])}"

    def apply(self) -> None:
        self.setup.apply()


def _brick_value(name: str) -> property:
    def get(self: BrickMicSetupForm) -> int:
        return int(self.setup.values[name])

    def put(self: BrickMicSetupForm, value: Any) -> None:
        self.setup.values[name] = int(round(float(value)))

    return property(get, put, doc=f"The BrickMic setting ``{name}``.")


for _key, *_ in BrickMicSetupModel.FIELDS:
    setattr(BrickMicSetupForm, _key, _brick_value(_key))


__all__ = ["SPECS", "BHSetupForm", "BrickMicSetupForm", "PicoQuantSetupForm"]
