"""Qt-free model of Settings ▸ Plots: the ``gui.plot`` settings, field by field, applied live.

Every field is a :class:`_Setting` bound to one key of the live ``gui.plot``
dictionary: reading it reads the settings, writing it changes them at once --
the plots read them through :mod:`chisurf.core.plotting.appearance` whenever
they draw, so there is nothing to "apply". Like Settings ▸ Fonts, a change is
also kept for the next start: :meth:`PlotSettingsModel.flush` writes what
differs from the shipped defaults to the user's ``settings_chisurf.yaml``
(the app calls it once a drag is released, not on every frame of it), and
:meth:`PlotSettingsModel.reset_defaults` puts back the shipped look.

:meth:`PlotSettingsModel.preview` is what the preview draws: a simulated
TCSPC measurement and its fit, so every setting has something real to act on.
"""

from __future__ import annotations

import copy
from typing import Any

import numpy as np

from chisurf.core.plotting import appearance
from chisurf.core.support.i18n import tr

#: Node-graph keys under ``gui.plot.node_graph`` and their shipped values (mirrors
#: ``chisurf.emtk.node_editor.style_settings.NODE_GRAPH_DEFAULTS``; a test keeps them equal).
NODE_GRAPH_DEFAULTS = {
    "show_grid": True,
    "grid_line_width": 0.5,
    "grid_opacity": 0.06,
    "grid_spacing": 24.0,
    "node_size": 13.0,
}


def normalise_color(value: Any) -> str:
    """``"#abc"`` / ``"AABBCC"`` as ``"#aabbcc"``; anything else unchanged."""
    text = str(value or "").strip()
    raw = text.lstrip("#").lower()
    if len(raw) == 3:
        raw = "".join(c * 2 for c in raw)
    if len(raw) in (6, 8) and all(c in "0123456789abcdef" for c in raw):
        return "#" + raw[:6]
    return text


def _default(path: tuple[str, ...]) -> Any:
    """The shipped value of a ``gui.plot`` key path."""
    if path[0] == "node_graph":
        return NODE_GRAPH_DEFAULTS[path[1]]
    value: Any = appearance.DEFAULTS
    for key in path:
        value = value[key]
    return value


class _Setting:
    """One ``gui.plot`` key as a model attribute: read and written live.

    Parameters
    ----------
    path : tuple of str
        Key path under ``gui.plot``.
    kind : {"color", "bool", "int", "float"}
        How a written value is coerced.
    bounds : (float, float), optional
        Inclusive range a number is clamped into (the control's range).
    percent : bool
        The control shows ``0..100`` for a stored ``0..1`` fraction.
    """

    def __init__(self, *path: str, kind: str, bounds=None, percent: bool = False) -> None:
        self.path = tuple(path)
        self.kind = kind
        self.bounds = bounds
        self.percent = percent
        self.name = ""

    def __set_name__(self, owner, name: str) -> None:
        self.name = name

    def stored(self, model: PlotSettingsModel) -> Any:
        """The stored value, or the shipped one when the key is missing."""
        block: Any = model.live()
        for key in self.path:
            if not isinstance(block, dict) or key not in block:
                return _default(self.path)
            block = block[key]
        return block

    def coerce(self, value: Any) -> Any:
        """*value* as the control's type, clamped into its range."""
        if self.kind == "color":
            return normalise_color(value)
        if self.kind == "bool":
            return bool(value)
        number = float(value)
        if self.bounds is not None:
            number = min(max(number, self.bounds[0]), self.bounds[1])
        return int(round(number)) if self.kind == "int" else number

    def __get__(self, model, owner=None):
        if model is None:
            return self
        value = self.stored(model)
        try:
            if self.percent:
                return self.coerce(float(value) * 100.0)
            return self.coerce(value)
        except (TypeError, ValueError):
            return self.coerce(_default(self.path) * (100.0 if self.percent else 1.0))

    def __set__(self, model, value) -> None:
        value = self.coerce(value)
        stored = value / 100.0 if self.percent else value
        if self.kind == "int" and not self.percent:
            stored = int(value)
        block = model.live()
        for key in self.path[:-1]:
            child = block.get(key)
            if not isinstance(child, dict):
                child = {}
                block[key] = child
            block = child
        if block.get(self.path[-1]) == stored:
            return
        block[self.path[-1]] = stored
        model.changed(self.name)


#: Ranges of the numeric controls (the view spec states the same; a test keeps them equal).
RANGES: dict[str, tuple[float, float]] = {
    "line_width": (0.5, 10.0),
    "region_alpha": (0, 255),
    "active_transparency": (0.0, 1.0),
    "inactive_transparency": (0.0, 1.0),
    "font_size": (0, 24),
    "grid_alpha_pct": (0, 100),
    "ng_line_width": (0.0, 4.0),
    "ng_grid_opacity_pct": (0, 100),
    "ng_grid_spacing": (4, 96),
    "ng_node_size": (6.0, 30.0),
}


class PlotSettingsModel:
    """Backing model of ``plot_settings_emtk.view.json``.

    Parameters
    ----------
    persist : bool
        Write changes to the settings file in :meth:`flush` (off in tests that must
        not touch it).
    """

    # -- curves -------------------------------------------------------------------- #
    color_data = _Setting("colors", "data", kind="color")
    color_model = _Setting("colors", "model", kind="color")
    color_irf = _Setting("colors", "irf", kind="color")
    color_residuals = _Setting("colors", "residuals", kind="color")
    color_auto_corr = _Setting("colors", "auto_corr", kind="color")
    line_width = _Setting("line_width", kind="float", bounds=RANGES["line_width"])
    # -- fit range ----------------------------------------------------------------- #
    enable_region_selector = _Setting("enable_region_selector", kind="bool")
    color_region_selector = _Setting("colors", "region_selector", kind="color")
    region_alpha = _Setting(
        "colors", "region_selector_alpha", kind="int", bounds=RANGES["region_alpha"]
    )
    # -- grouped fits -------------------------------------------------------------- #
    active_transparency = _Setting(
        "colors", "active_transparency", kind="float", bounds=RANGES["active_transparency"]
    )
    inactive_transparency = _Setting(
        "colors", "inactive_transparency", kind="float", bounds=RANGES["inactive_transparency"]
    )
    # -- axes and grid ------------------------------------------------------------- #
    label_axis = _Setting("label_axis", kind="bool")
    show_legend = _Setting("show_legend", kind="bool")
    font_size = _Setting("font_size", kind="int", bounds=RANGES["font_size"])
    enable_grid = _Setting("enable_grid", kind="bool")
    grid_alpha_pct = _Setting(
        "grid_alpha", kind="int", bounds=RANGES["grid_alpha_pct"], percent=True
    )
    show_data_grid = _Setting("show_data_grid", kind="bool")
    show_residual_grid = _Setting("show_residual_grid", kind="bool")
    show_acorr_grid = _Setting("show_acorr_grid", kind="bool")
    # -- node graphs --------------------------------------------------------------- #
    ng_show_grid = _Setting("node_graph", "show_grid", kind="bool")
    ng_line_width = _Setting(
        "node_graph", "grid_line_width", kind="float", bounds=RANGES["ng_line_width"]
    )
    ng_grid_opacity_pct = _Setting(
        "node_graph", "grid_opacity", kind="int", bounds=RANGES["ng_grid_opacity_pct"], percent=True
    )
    ng_grid_spacing = _Setting(
        "node_graph", "grid_spacing", kind="float", bounds=RANGES["ng_grid_spacing"]
    )
    ng_node_size = _Setting("node_graph", "node_size", kind="float", bounds=RANGES["ng_node_size"])

    def __init__(self, persist: bool = True) -> None:
        self.persist = bool(persist)
        #: Fields changed since the last :meth:`flush`.
        self.unsaved: set[str] = set()
        #: One line saying what the last change did.
        self.status = tr("Changes apply at once and are kept for the next start.")

    # -- the live settings ---------------------------------------------------------- #
    @staticmethod
    def live() -> dict:
        """The live ``gui.plot`` dictionary (created when missing), the one plots read."""
        import chisurf.core.settings as css

        gui = css.cs_settings.setdefault("gui", {})
        block = gui.get("plot")
        if not isinstance(block, dict):
            block = {}
            gui["plot"] = block
        return block

    @classmethod
    def fields(cls) -> tuple[str, ...]:
        """Every bound attribute, in declaration order."""
        return tuple(name for name, value in vars(cls).items() if isinstance(value, _Setting))

    def values(self) -> dict[str, Any]:
        """Every field and its value."""
        return {name: getattr(self, name) for name in self.fields()}

    def changed(self, name: str) -> None:
        """A field was written: plots drawn from now on use it; :meth:`flush` keeps it."""
        self.unsaved.add(name)
        self.status = tr("Applied. Every open plot is restyled at once.")
        appearance.notify(name)

    # -- persistence ----------------------------------------------------------------- #
    @staticmethod
    def shipped() -> dict:
        """The packaged ``gui.plot`` defaults."""
        from chisurf.core.settings.path_utils import get_path
        from chisurf.core.settings.settings_utils import get_chisurf_settings

        packaged = get_chisurf_settings(
            get_path("settings") / "settings_chisurf.yaml", use_source_folder=True
        )
        return copy.deepcopy((packaged.get("gui") or {}).get("plot") or {})

    def flush(self) -> bool:
        """Keep the changes: write what differs from the shipped defaults; re-style node graphs.

        Returns
        -------
        bool
            True when something was written.
        """
        if not self.unsaved:
            return False
        node_graph = any(name.startswith("ng_") for name in self.unsaved)
        self.unsaved.clear()
        if node_graph:
            # A node graph reads its style when it is built; one that is open catches up here.
            try:
                from chisurf.emtk.node_editor.style_settings import refresh_open_graphs

                refresh_open_graphs()
            except Exception:  # noqa: BLE001 - nothing open to catch up
                pass
        if not self.persist:
            return False
        from chisurf.core.settings.settings_utils import prune_defaults, update_settings_section

        changed = prune_defaults(copy.deepcopy(self.live()), self.shipped())
        ok = update_settings_section("gui", {"plot": changed})
        self.status = (
            tr("Applied and saved. Every open plot is restyled at once.")
            if ok
            else tr("Applied; the settings file could not be written.")
        )
        return ok

    def reset_defaults(self) -> None:
        """Every plot setting back to the shipped look, applied at once and saved."""
        live = self.live()
        live.clear()
        live.update(self.shipped())
        self.unsaved = {"ng_show_grid"}  # also re-styles open node graphs
        self.flush()
        appearance.notify("")
        self.status = tr("Plot settings reset to the defaults.")

    # -- the preview ------------------------------------------------------------------ #
    def preview(self) -> dict[str, Any]:
        """The simulated measurement the preview draws, styled by the current settings.

        Returns
        -------
        dict
            ``curves``: per panel (``acorr``, ``residuals``, ``data``) a list of
            series ``{label, x, y, color, width, opacity}``; ``region``: the fit
            range ``(lo, hi)`` and its fill (``None`` when the selector is off);
            ``grid``: per panel the grid alpha or ``None``; ``legend``, ``labels``
            and ``font_size``.
        """
        sample = preview_sample()
        settings = self.live()
        color = {role: appearance.curve_color(role, settings) for role in appearance.CURVE_ROLES}
        active = appearance.fit_opacity(True, settings)
        other = appearance.fit_opacity(False, settings)
        lo, hi = sample["range"]
        fit_x = sample["t"][lo:hi]

        def series(label, x, y, role, opacity):
            return {
                "label": label,
                "x": x,
                "y": y,
                "color": color[role],
                "width": appearance.line_width(role if role == "data" else "model", settings),
                "opacity": opacity,
            }

        # The other dataset of the global fit goes down first, under the selected one;
        # its curves share one legend entry.
        other_fit = "other fit"
        data = [
            series(other_fit, sample["t"], sample["data_2"], "data", other),
            series(other_fit, fit_x, sample["model_2"], "model", other),
            series("data", sample["t"], sample["data"], "data", active),
            series("model", fit_x, sample["model"], "model", active),
            series("IRF", sample["t"], sample["irf"], "irf", active),
        ]
        residuals = [
            series(other_fit, fit_x, sample["wres_2"] + sample["wres_offset"], "residuals", other),
            series("w.res.", fit_x, sample["wres"], "residuals", active),
        ]
        acorr = [
            series(
                other_fit,
                sample["lag_t"],
                sample["acorr_2"] + sample["acorr_offset"],
                "auto_corr",
                other,
            ),
            series("a.corr.", sample["lag_t"], sample["acorr"], "auto_corr", active),
        ]
        return {
            "curves": {"acorr": acorr, "residuals": residuals, "data": data},
            "region": (
                (float(sample["t"][lo]), float(sample["t"][hi - 1])),
                appearance.region_rgba(settings),
            ),
            "grid": {
                panel: appearance.grid_alpha(panel, settings) for panel in appearance.GRID_PANELS
            },
            "legend": appearance.show_legend(settings),
            "labels": appearance.label_axes(settings),
            "font_size": appearance.font_size(settings),
        }


_SAMPLE: dict[str, Any] = {}


def _convolve(decay: np.ndarray, irf: np.ndarray) -> np.ndarray:
    """The decay convolved with the instrument response, on the decay's channels."""
    return np.convolve(irf, decay)[: decay.size]


def _autocorrelation(values: np.ndarray, lags: int) -> np.ndarray:
    """Normalised autocorrelation of *values* for lags ``1..lags`` (``0`` for white noise)."""
    v = np.asarray(values, dtype=float)
    n = v.size
    mean_sq = float(np.mean(v * v)) or 1.0
    return np.array([float(np.mean(v[k:] * v[: n - k])) / mean_sq for k in range(1, lags + 1)])


def preview_sample() -> dict[str, np.ndarray]:
    """A simulated TCSPC measurement: IRF ⊛ two-exponential decay + background, Poisson noise.

    The model is the noise-free decay of a *fit* that is close but not exact (a
    slightly shorter long lifetime), so model and data can be told apart and
    the weighted residuals show the structure a misfit leaves. A second
    dataset of a global fit is simulated the same way, at another brightness,
    to show the other fits of a group. Deterministic: a fixed seed.
    """
    if _SAMPLE:
        return _SAMPLE
    rng = np.random.default_rng(20261012)
    dt = 0.05  # ns per channel
    t = np.arange(256) * dt
    # A Gaussian prompt with the short exponential shoulder of a real detector.
    irf = np.exp(-0.5 * ((t - 1.2) / 0.09) ** 2) + 0.01 * np.exp(-(t - 1.2) / 0.25) * (t > 1.2)
    irf /= irf.sum()

    def measured(total, amplitudes, lifetimes, background):
        decay = sum(a * np.exp(-t / tau) for a, tau in zip(amplitudes, lifetimes))
        decay = _convolve(decay / decay.sum(), irf)
        return total * decay / decay.sum() + background

    expected = measured(4.0e5, (0.55, 0.45), (0.8, 3.6), 3.0)
    expected_2 = measured(1.6e5, (0.3, 0.7), (0.6, 2.8), 2.0)
    data = rng.poisson(expected).astype(float)
    data_2 = rng.poisson(expected_2).astype(float)
    lo, hi = int(np.argmax(t >= 0.9)), 236
    model = measured(4.0e5, (0.57, 0.43), (0.84, 3.35), 3.0)[lo:hi]
    model *= data[lo:hi].sum() / model.sum()
    model_2 = measured(1.6e5, (0.32, 0.68), (0.62, 2.7), 2.0)[lo:hi]
    model_2 *= data_2[lo:hi].sum() / model_2.sum()
    wres = (data[lo:hi] - model) / np.sqrt(np.maximum(data[lo:hi], 1.0))
    wres_2 = (data_2[lo:hi] - model_2) / np.sqrt(np.maximum(data_2[lo:hi], 1.0))
    lags = (hi - lo) // 2
    acorr = _autocorrelation(wres, lags)
    _SAMPLE.update(
        {
            "t": t,
            "irf": irf * expected.max() / irf.max() * 0.6 + 1.0,
            "data": data,
            "data_2": data_2,
            "model": model,
            "model_2": model_2,
            "range": (lo, hi),
            "wres": wres,
            "wres_2": wres_2,
            # A group's other fits sit above the selected one, as the fit window stacks them.
            "wres_offset": float(np.ceil(2.5 * np.percentile(np.abs(wres), 95))),
            "acorr": acorr,
            "acorr_2": _autocorrelation(wres_2, lags),
            "acorr_offset": float(2.5 * np.percentile(np.abs(acorr), 95)),
            "lag_t": t[lo : lo + lags],
        }
    )
    return _SAMPLE


__all__ = [
    "NODE_GRAPH_DEFAULTS",
    "PlotSettingsModel",
    "RANGES",
    "normalise_color",
    "preview_sample",
]
