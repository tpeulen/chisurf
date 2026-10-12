"""The Settings ▸ Fonts panel's model: emtk's font configuration, bound field by field.

Each property reads :func:`emtk.fonts.config` and its setter changes one setting with
:func:`emtk.fonts.update` -- which takes effect on the next frame, everywhere -- and
then writes the whole block to ``gui.fonts`` (:mod:`chisurf.core.settings.fonts`), so the
next start applies it too. Qt-free; the form is ``fonts.view.json``.
"""

from __future__ import annotations

from typing import Any

from emtk import fonts
from emtk.i18n import tr

#: Glyph raster scales a user picks from.
OVERSAMPLE_CHOICES = (1.0, 2.0, 3.0, 4.0)

#: What each preview line shows: Latin with accents, Greek, subscripts and a unit --
#: the characters a fallback chain exists for.
PREVIEW_TEXT = {
    "ui": "Fit · Résumé · τ₁ = 2.5 ns · χ²ᵣ = 1.02",
    "code": "def decay(t, τ=2.5):  # 0O 1lI {}[]",
    "prose": "The donor lifetime τ shortens as FRET grows: E = 1 − τ′/τ₀.",
    "heading": "Global analysis of time-resolved data",
    "caption": "Figure 1. Decay of the donor (blue) and the fit (red).",
    "math": r"E = \frac{1}{1 + (R/R_0)^6}",
}


class FontSettingsModel:
    """Backing model of ``fonts.view.json``.

    Parameters
    ----------
    persist : bool
        Write every change to the settings file (off in tests that must not touch it).
    """

    def __init__(self, persist: bool = True) -> None:
        self.persist = bool(persist)
        #: One line saying what the last change did.
        self.status = tr("Changes apply at once and are kept for the next start.")

    # -- plumbing -------------------------------------------------------------------- #
    @staticmethod
    def _cfg() -> fonts.FontConfig:
        return fonts.config()

    def _set(self, **changes: Any) -> None:
        config = fonts.update(**changes)
        if self.persist:
            from chisurf.core.settings.fonts import save

            ok = save(config.to_dict())
            self.status = (
                tr("Applied and saved.")
                if ok
                else tr("Applied; the settings file could not be written.")
            )
        else:
            self.status = tr("Applied.")

    # -- choices --------------------------------------------------------------------- #
    def families(self) -> list:
        """Every installed family, after the generics (``monospace`` = the built-in face)."""
        return list(fonts.system_families())

    def mono_families(self) -> list:
        """Monospaced families only: the editor's columns assume fixed advances."""
        return list(fonts.system_families(monospace=True))

    def math_families(self) -> list:
        """``auto`` (the first installed STIX/Times face) and every installed family."""
        return ["auto", *[f for f in fonts.system_families() if f != "monospace"]]

    def oversample_choices(self) -> list:
        """``(value, label)`` pairs of the glyph raster scale, with what each means."""
        return [(1.0, tr("1× (sharpest)")), (2.0, tr("2× (smoother)")), (3.0, "3×"), (4.0, "4×")]

    # -- interface ------------------------------------------------------------------- #
    @property
    def ui_family(self) -> str:
        return self._cfg().ui.family

    @ui_family.setter
    def ui_family(self, value: str) -> None:
        self._set(ui={"family": str(value)})

    @property
    def ui_size(self) -> float:
        return float(self._cfg().ui.size)

    @ui_size.setter
    def ui_size(self, value: float) -> None:
        self._set(ui={"size": float(value)})

    @property
    def zoom(self) -> float:
        return float(self._cfg().zoom)

    @zoom.setter
    def zoom(self, value: float) -> None:
        self._set(zoom=float(value))

    # -- rendering ------------------------------------------------------------------- #
    @property
    def oversample(self) -> float:
        return float(self._cfg().oversample)

    @oversample.setter
    def oversample(self, value: float) -> None:
        self._set(oversample=float(value))

    @property
    def antialias(self) -> bool:
        return bool(self._cfg().antialias)

    @antialias.setter
    def antialias(self, value: bool) -> None:
        self._set(antialias=bool(value))

    # -- editor and console ------------------------------------------------------------- #
    @property
    def code_family(self) -> str:
        return self._cfg().code.family

    @code_family.setter
    def code_family(self, value: str) -> None:
        self._set(code={"family": str(value)})

    @property
    def code_size(self) -> float:
        return float(self._cfg().code.size)

    @code_size.setter
    def code_size(self, value: float) -> None:
        self._set(code={"size": float(value)})

    # -- documentation ------------------------------------------------------------------ #
    @property
    def prose_family(self) -> str:
        return self._cfg().prose.family

    @prose_family.setter
    def prose_family(self, value: str) -> None:
        self._set(prose={"family": str(value)}, caption={"family": str(value)})

    @property
    def prose_size(self) -> float:
        return float(self._cfg().prose.size)

    @prose_size.setter
    def prose_size(self, value: float) -> None:
        self._set(prose={"size": float(value)})

    @property
    def heading_family(self) -> str:
        return self._cfg().heading.family

    @heading_family.setter
    def heading_family(self, value: str) -> None:
        self._set(heading={"family": str(value)})

    @property
    def heading_step(self) -> float:
        return float(self._cfg().heading_step)

    @heading_step.setter
    def heading_step(self, value: float) -> None:
        self._set(heading_step=float(value))

    @property
    def heading_bold(self) -> bool:
        return bool(self._cfg().heading.bold)

    @heading_bold.setter
    def heading_bold(self, value: bool) -> None:
        self._set(heading={"bold": bool(value)})

    @property
    def caption_size(self) -> float:
        return float(self._cfg().caption.size)

    @caption_size.setter
    def caption_size(self, value: float) -> None:
        self._set(caption={"size": float(value)})

    # -- math and fallbacks ----------------------------------------------------------------- #
    @property
    def math_family(self) -> str:
        return self._cfg().math.family

    @math_family.setter
    def math_family(self, value: str) -> None:
        self._set(math={"family": str(value)})

    @property
    def math_size(self) -> float:
        return float(self._cfg().math.size)

    @math_size.setter
    def math_size(self, value: float) -> None:
        self._set(math={"size": float(value)})

    @property
    def fallbacks(self) -> str:
        return ", ".join(self._cfg().fallbacks)

    @fallbacks.setter
    def fallbacks(self, value: str) -> None:
        self._set(fallbacks=tuple(p.strip() for p in str(value).split(",") if p.strip()))

    # -- actions ------------------------------------------------------------------------- #
    def reset_defaults(self) -> None:
        """Every font setting back to the shipped look, applied and saved."""
        config = fonts.reset()
        if self.persist:
            from chisurf.core.settings.fonts import save

            save(config.to_dict())
        self.status = tr("Fonts reset to the defaults.")

    @staticmethod
    def preview_text(role: str) -> str:
        """The sample line drawn in *role*'s font."""
        return PREVIEW_TEXT[role]


__all__ = ["FontSettingsModel", "OVERSAMPLE_CHOICES", "PREVIEW_TEXT"]
