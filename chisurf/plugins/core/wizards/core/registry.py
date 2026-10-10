"""Registry of embeddable wizards for the Wizards hub (Qt-free).

The hub is a two-panel tool: a list of wizards on the left, the selected wizard
embedded on the right. Each entry names the native emtk app factory of the wizard by
dotted import path; the hub resolves and builds it lazily on first selection. Keeping
the catalogue here — as plain data — lets it be unit-tested and extended without
importing Qt.
"""

from __future__ import annotations

import dataclasses


@dataclasses.dataclass(frozen=True)
class WizardEntry:
    """One selectable wizard in the hub.

    Parameters
    ----------
    id : str
        Stable identifier (used for selection persistence).
    label : str
        Text shown in the selector list.
    description : str
        One-line summary shown above the embedded wizard.
    emtk : str
        Dotted path ``"pkg.module:factory"`` of the native app factory of the wizard
        (called with no arguments).
    icon : str
        Optional emoji/icon shown next to the label.
    """

    id: str
    label: str
    description: str
    emtk: str
    icon: str = ""


def default_wizards() -> list[WizardEntry]:
    """Return the built-in wizards embedded by the hub."""
    return [
        WizardEntry(
            id="anisotropy",
            label="Anisotropy",
            description="Build a linked VV/VH global time-resolved anisotropy fit.",
            emtk="chisurf.plugins.fluorescence_decay.tr_anisotropy.gui.app:make_app",
            icon="🔬",
        ),
        WizardEntry(
            id="batch_analysis",
            label="Batch analysis",
            description="Apply one template fit to many datasets or files.",
            emtk="chisurf.plugins.core.batch_analysis.gui.app:make_app",
            icon="📋",
        ),
    ]


__all__ = ["WizardEntry", "default_wizards"]
