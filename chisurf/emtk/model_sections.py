"""The model editor's curve pickers and custom sections, drawn natively in the emtk shell.

The server resolves each of these sections into plain data
(:mod:`chisurf.server.services.model_sections`); :class:`SectionViews` draws
that data in the Analysis dock and sends every change back through the API on
the docks' worker:

* ``curve_input`` (IRF, background, linearisation table, a measurement slot): the
  curve's name, ``…`` (a session dataset, ``model.curve.set``), ``✕``
  (``model.curve.unload``) and the IRF's FWHM;
* ``scalar_table``, ``global_parameter_table``: declared ``table`` sections;
* ``rate_matrix``: a table of the row → column rates, with Fixed and the link
  menu on each cell's context menu;
* ``kappa2_controls``: the κ² regime, *show κ²*, *compute κ²* and *calc R0*;
* ``anisotropy_diagnostics``: *VV/VH diag* and the *show r(t)* window;
* ``lcurve``: the L-curve, its sweep window and the corner;
* ``path_list``: the file list of a structure ensemble;
* ``background_run``: start, stop and the progress of a model's own job;
* ``fit_mixer``: the fits a mixture combines and their fractions;
* ``lifetime_amplitude_options``: *Abs.*, *Norm.*, *read* and *link* of a lifetime group.

Every write is ``model.section.call`` / ``model.curve.*`` with the section's
address; the server refuses what the model's ``view.json`` does not declare.
"""

from __future__ import annotations

import csv
import functools
import math
from pathlib import Path
from typing import Any, Callable

from emtk import im, implot
from emtk import style as _style
from emtk.i18n import tr

from chisurf.plugins.emtk_layout import action_button

#: Columns of a ``scalar_table`` (the Qt section's Name / Value).
SCALAR_COLUMNS = [
    {
        "key": "label",
        "label": "Name",
        "display": "script",
        "description": "The setting, with its unit.",
    },
    {
        "key": "value",
        "label": "Value",
        "editable": True,
        "format": "%.6g",
        "description": "Double-click to type a new value; click a check box to toggle it.",
    },
]

#: Columns of the ``global_parameter_table`` (the Qt section's, in its order).
#: Short of width it drops, as the parameter tables do, the bounds first, then
#: the error, then the link columns, then Fixed; owner, parameter and value stay.
GLOBAL_COLUMNS: list[dict[str, Any]] = [
    {
        "key": "row",
        "label": "Row",
        "shade": False,
        "description": "The row number a link names.",
        "collapse_order": 3,
    },
    {
        "key": "owner",
        "label": "Owner",
        "description": "The fit (or tool) the parameter belongs to.",
    },
    {"key": "local", "label": "Local", "description": "The member fit of a fit group."},
    {"key": "label", "label": "Parameter", "display": "script", "description": "The parameter."},
    {
        "key": "value",
        "label": "Value",
        "editable": True,
        "format": "%.5g",
        "description": "The parameter's value; double-click to type a new one.",
    },
    {
        "key": "fixed",
        "label": "Fixed",
        "editable": True,
        "description": "A fixed parameter keeps its value when the fit runs.",
        "collapse_order": 4,
    },
    {
        "key": "lo",
        "label": "Lo",
        "editable": True,
        "format": "%.4g",
        "description": "Lower bound.",
        "collapse_order": 1,
    },
    {
        "key": "hi",
        "label": "Hi",
        "editable": True,
        "format": "%.4g",
        "description": "Upper bound.",
        "collapse_order": 1,
    },
    {
        "key": "bounds_on",
        "label": "Bounds",
        "editable": True,
        "description": "Keep the parameter between Lo and Hi while fitting.",
        "collapse_order": 1,
    },
    {
        "key": "error",
        "label": "Error",
        "format": "%.3g",
        "description": "From the last fit.",
        "collapse_order": 2,
    },
    {
        "key": "link_row",
        "label": "Link row",
        "editable": True,
        "format": "%d",
        "description": "Type another row's number to link this parameter to it; clear it to unlink.",
        "collapse_order": 3,
    },
]

_RT_CURVES = (
    ("data raw", "r_data_unc", "t", (100, 116, 139)),
    ("data corr", "r_data_cor", "t", (22, 163, 74)),
    ("model raw", "r_model_unc", "t_model", (59, 130, 246)),
    ("model corr", "r_model_cor", "t_model", (16, 185, 129)),
)


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


class _Rows(list):
    """Table rows with a ``revision``, so a re-read rebinds the table once."""

    revision = 0


# ── the dialogs a section opens ───────────────────────────────────────────


class _Window:
    """A dialog of the editor drawn over the shell; ``draw(box)`` each frame until it closes."""

    def __init__(self, title: str, size: tuple[float, float], key: str = "") -> None:
        from emtk.dialog_window import DialogWindow

        self.window = DialogWindow(title, size=size, key=key or title)
        self.window.show()
        self.rects: dict[str, tuple] = {}

    @property
    def open(self) -> bool:
        return bool(self.window.open)

    def close(self) -> None:
        self.window.hide()

    def draw(self, box) -> None:
        if not self.window.open:
            return
        pressed = self.window.begin(box)
        try:
            self.body()
        finally:
            self.window.end()
        if pressed == "close":
            self.close()

    def body(self) -> None:  # pragma: no cover - every window draws its own
        raise NotImplementedError

    def rect(self, name: str) -> None:
        self.rects[name] = im.get_item_rect()


class RtWindow(_Window):
    """*show r(t)*: r(t) of data and model, uncorrected and corrected, with live correction factors."""

    FACTORS = (
        ("g", "g:"),
        ("l1", "l1:"),
        ("l2", "l2:"),
        ("bg_vv", "BgVV:"),
        ("bg_vh", "BgVH:"),
        ("shift", "dVH-VV:"),
    )

    def __init__(self, views: SectionViews, section: str) -> None:
        super().__init__(
            tr("Anisotropy decays (corrected vs uncorrected)"), (640.0, 520.0), key=f"rt-{section}"
        )
        self.views = views
        self.section = section
        self.data: dict = {}
        self.factors: dict[str, float] = {}
        self.defaults: dict[str, float] = {}
        self.link_l = True
        self.pending = True
        self.error = ""

    def received(self, result: Any) -> None:
        data = (result or {}).get("result") or {}
        self.data = data
        self.defaults = dict(data.get("defaults") or {})
        if not self.factors:
            self.factors = dict(data.get("factors") or self.defaults)

    def failed(self, error: str) -> None:
        self.error = error

    def _request(self) -> None:
        if self.views.docks.busy:
            return
        self.pending = False
        factors = dict(self.factors)
        if self.link_l and "l1" in factors:
            factors["l2"] = factors["l1"]
        self.views.call(
            self.section,
            "rt",
            {"factors": factors},
            tr("Computing r(t)…"),
            after=self.received,
            update=False,
            failed=self.failed,
        )

    def body(self) -> None:
        if self.pending:
            self._request()
        if self.error:
            im.text_wrapped(self.error)
        for i, (key, label) in enumerate(self.FACTORS):
            if i % 3:
                im.same_line()
            im.align_text_to_frame_padding()
            im.text(tr(label))
            im.same_line()
            im.set_next_item_width(110.0)
            disabled = key == "l2" and self.link_l
            im.begin_disabled(disabled)
            value = float(self.factors.get(key, self.defaults.get(key, 0.0)) or 0.0)
            changed, value = im.input_double(f"##rt-{key}", value, 0.0, 0.0, "%.6g")
            self.rect(key)
            im.end_disabled()
            if changed:
                self.factors[key] = float(value)
                self.pending = True
        changed, self.link_l = im.checkbox(tr("link l1/l2") + "##rt-link", self.link_l)
        self.rect("link_l")
        im.set_item_tooltip(tr("Keep l2 equal to l1 (the usual case for one detector pair)"))
        if changed:
            self.pending = True
        im.same_line()
        if action_button(
            "reset", id="rt-reset", tooltip=tr("Restore the factors the fit is currently using")
        ):
            self.factors = dict(self.defaults)
            self.link_l = True
            self.pending = True
        self.rect("reset")
        w, h = im.get_content_region_avail()
        if implot.begin_plot("##rt-plot", (w, max(120.0, h - 40.0))):
            implot.setup_axes(tr("Time"), tr("r(t)"))
            implot.setup_axis_limits(implot.AXIS_Y1, 0.0, 0.5, implot.COND_ONCE)
            implot.setup_legend(implot.LOCATION_NORTH_EAST)
            drawn = False
            for name, key, axis, colour in _RT_CURVES:
                x, y = self.data.get(axis), self.data.get(key)
                if x and y:
                    implot.set_next_line_style(colour, 2.0)
                    implot.plot_line(
                        tr(name),
                        [float(v) for v in x],
                        [float("nan") if v is None else float(v) for v in y],
                    )
                    drawn = True
            if not drawn:
                implot.plot_dummy(tr("no anisotropy decay yet"))
            implot.end_plot()
        self.rect("plot")
        if im.button(tr("Save CSV") + "##rt-save"):
            self.views.docks.open_file_dialog(
                tr("Save anisotropy decay"), mode="save", done=self.save_csv
            )
        im.set_item_tooltip(tr("Save the anisotropy decay r(t) as a CSV file."))
        self.rect("save")
        im.same_line()
        if action_button("close", id="rt-close"):
            self.close()
        self.rect("close")

    def save_csv(self, path: str) -> None:
        """Write the drawn curves: data and model on their own time axes (padded, not resampled)."""
        d = self.data
        t, du, dc = d.get("t") or [], d.get("r_data_unc") or [], d.get("r_data_cor") or []
        tm, mu, mc = d.get("t_model") or [], d.get("r_model_unc") or [], d.get("r_model_cor") or []
        if not t:
            self.views.docks.status = tr("No anisotropy decay data to save.")
            return
        header = ["time_data", "r_data_uncorrected", "r_data_corrected"]
        columns = [t, du, dc]
        if tm:
            header += ["time_model", "r_model_uncorrected", "r_model_corrected"]
            columns += [tm, mu, mc]
        n = max(len(c) for c in columns)
        with open(path, "w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(header)
            for i in range(n):
                writer.writerow(["" if i >= len(c) or c[i] is None else c[i] for c in columns])
        self.views.docks.status = tr("Saved to {name}").format(name=Path(path).name)


class Kappa2ShowWindow(_Window):
    """*show κ²*: ρ(κ²), ρ(R_app/R_DA) and, for a model with distances, ρ(R_DA) against ρ(R_app)."""

    def __init__(self, views: SectionViews, section: str, use_fast: bool) -> None:
        super().__init__(tr("κ² & R_app/R_DA distributions"), (560.0, 640.0), key=f"k2-{section}")
        self.views = views
        self.data: dict = {}
        self.error = ""
        views.call(
            section,
            "distribution",
            {"use_fast": bool(use_fast)},
            tr("Reading the κ² distribution…"),
            after=self._received,
            update=False,
            failed=self._failed,
        )

    def _received(self, result: Any) -> None:
        self.data = (result or {}).get("result") or {}

    def _failed(self, error: str) -> None:
        self.error = error

    def _plot(self, ident: str, x_label: str, y_label: str, curves: list, height: float) -> None:
        w = im.get_content_region_avail()[0]
        if implot.begin_plot(ident, (w, height)):
            implot.setup_axes(x_label, y_label)
            implot.setup_legend(implot.LOCATION_NORTH_EAST)
            for name, x, y, colour, vertical in curves:
                if vertical is not None:
                    implot.set_next_line_style(colour, 2.0)
                    implot.plot_inf_lines(name, [float(vertical)])
                elif x and y:
                    implot.set_next_line_style(colour, 2.0)
                    implot.plot_line(name, [float(v) for v in x], [float(v) for v in y])
            implot.end_plot()

    def body(self) -> None:
        d = self.data
        if self.error:
            im.text_wrapped(self.error)
        elif not d:
            im.text_disabled(tr("Reading…"))
        else:
            mean = float(d.get("k2_mean") or 0.0)
            im.text_wrapped(
                tr("Transformation: R_app/R_DA = (⟨κ²⟩/κ²)^(1/6) | ⟨κ²⟩ = {mean:.3f}").format(
                    mean=mean
                )
            )
            im.text_disabled(
                tr("Current orientation mode: {mode} | dynamic κ² = {k2:.3f}").format(
                    mode=d.get("mode", "fast"), k2=float(d.get("kappa2") or 0.0)
                )
            )
            rows = 3 if d.get("r_da") else 2
            height = max(110.0, (im.get_content_region_avail()[1] - 40.0) / rows)
            self._plot(
                "##k2-dist",
                tr("κ²"),
                tr("Probability"),
                [
                    (tr("ρ(κ²)"), d.get("k2"), d.get("p_k2"), (255, 100, 100), None),
                    (tr("⟨κ²⟩ = {mean:.3f}").format(mean=mean), None, None, (255, 160, 80), mean),
                ],
                height,
            )
            self.rect("k2_plot")
            self._plot(
                "##k2-ratio",
                tr("R_app/R_DA"),
                tr("Probability Density"),
                [
                    (tr("ρ(R_app/R_DA)"), d.get("ratio"), d.get("p_ratio"), (80, 160, 255), None),
                    (tr("mean (1.0)"), None, None, (255, 160, 80), 1.0),
                ],
                height,
            )
            self.rect("ratio_plot")
            if d.get("r_da"):
                self._plot(
                    "##k2-distance",
                    tr("Distance (Å)"),
                    tr("Normalized Intensity"),
                    [
                        (tr("ρ(R_DA)"), d.get("r_da"), d.get("p_r_da"), (80, 255, 160), None),
                        (tr("ρ(R_app)"), d.get("r_app"), d.get("p_r_app"), (255, 80, 160), None),
                    ],
                    height,
                )
                self.rect("distance_plot")
        if im.button(tr("OK") + "##k2-show-ok"):
            self.close()
        im.set_item_tooltip(tr("Close the kappa-squared window."))
        self.rect("ok")


class Kappa2ComputeDialog(_Window):
    """*compute κ²*: the κ² distribution calculator; OK hands its distribution to the model."""

    def __init__(self, views: SectionViews, section: str, kappa2: float) -> None:
        import json

        from emtk.view_form import FormState

        from chisurf.plugins.calculator.kappa2_dist.gui.app import _SPEC_PATH
        from chisurf.plugins.calculator.kappa2_dist.gui.client import Kappa2DistClient
        from chisurf.plugins.calculator.kappa2_dist.gui.model import _Kappa2DistModel

        super().__init__(
            tr("Experimental k2 (orientation factor distribution)"),
            (620.0, 700.0),
            key=f"k2c-{section}",
        )
        self.views = views
        self.section = section
        self.model = _Kappa2DistModel()
        self.model.kappa2_true = float(kappa2)
        self.client = Kappa2DistClient()
        spec = json.loads(Path(_SPEC_PATH).read_text(encoding="utf-8"))
        # The inputs, as the calculator's own window shows them (its Results panel is a line here).
        self.spec = {
            "sections": [
                s
                for s in spec["sections"]
                if s.get("type") == "panel" and s.get("title") != "Results"
            ]
        }
        self.form = FormState()
        self.error = ""
        self.compute()

    def compute(self) -> None:
        try:
            self.model.compute(self.client)
            self.error = (
                ""
                if self.model._k2hist is not None
                else tr("No kappa2 distribution computed in plugin.")
            )
        except Exception as exc:  # noqa: BLE001 - said in the dialog
            self.error = str(exc)

    def accept(self) -> None:
        m = self.model
        if m._k2hist is None or m._k2scale is None:
            self.error = tr("No kappa2 distribution computed in plugin.")
            return
        self.views.call(
            self.section,
            "apply_distribution",
            {
                "k2": [float(v) for v in m._k2scale],
                "p_k2": [float(v) for v in m._k2hist],
                "k2_mean": float(m.k2_mean),
            },
            tr("Applying the κ² distribution…"),
        )
        self.close()

    def body(self) -> None:
        from emtk.view_form import draw_form

        draw_form(self.spec, self.model, self.form, titles=True)
        self.rects.update({f"form.{k}": v for k, v in self.form.rects.items()})
        if im.button(tr("Compute") + "##k2c-compute", role="primary"):
            self.compute()
        im.set_item_tooltip(tr("Compute the kappa-squared distribution for these settings."))
        self.rect("compute")
        im.same_line()
        im.text_disabled(
            tr("⟨κ²⟩ = {mean:.3f} ± {sd:.3f}").format(
                mean=float(self.model.k2_mean or 0.0), sd=float(self.model.k2_sd or 0.0)
            )
        )
        if self.error:
            im.text_wrapped(self.error)
        series = self.model.kappa2_plot_series()
        w, h = im.get_content_region_avail()
        if implot.begin_plot("##k2c-plot", (w, max(120.0, h - 40.0))):
            implot.setup_axes(tr("κ²"), tr("p(κ²)"))
            for s in series:
                implot.plot_line(tr("p(κ²)"), s["x"], s["y"])
            if not series:
                implot.plot_dummy(tr("press Compute to draw the distribution"))
            implot.end_plot()
        self.rect("plot")
        if im.button(tr("OK") + "##k2c-ok"):
            self.accept()
        im.set_item_tooltip(tr("Use the computed kappa-squared distribution in the model."))
        self.rect("ok")
        im.same_line()
        if action_button(
            "cancel", id="k2c-cancel", tooltip=tr("Close without changing the model's κ².")
        ):
            self.close()
        self.rect("cancel")


class LinkMenu:
    """The link menu of a parameter: *Link {name} to* → a fit → its parameters, and *Unlink*."""

    def __init__(self, views: SectionViews, record: dict, fits: list, anchor) -> None:
        from emtk.widgets.menus import Menu, MenuItem, Popup

        self.views = views
        self.record = dict(record)
        # Menu actions; what one returns (link/unlink report success) is not used.
        self.calls: dict[int, Callable[[], object]] = {}
        source = str(record.get("uid", ""))
        name = str(record.get("name", ""))
        fit_menus = []
        for fit in fits:
            entries = []
            members = fit.get("members") or []
            groups = (
                [(m.get("name", ""), m.get("parameters_all") or []) for m in members]
                if len(members) > 1
                else [
                    (
                        "",
                        (
                            members[0].get("parameters_all")
                            if members
                            else (fit.get("model") or {}).get("parameters_all")
                        )
                        or [],
                    )
                ]
            )
            for member_name, parameters in groups:
                items = []
                for p in parameters:
                    uid = str(p.get("uid", ""))
                    # Only the equation the fit shows: a catalogue model keeps its other ports as
                    # parameters too (``active_in_structure`` false), and offering all 100+ drowns
                    # the few it fits with. A server that does not say lists everything.
                    if not uid or uid == source or not p.get("active_in_structure", True):
                        continue
                    item = MenuItem(str(p.get("name", "")))
                    self.calls[id(item)] = functools.partial(views.link, self.record, uid)
                    items.append(item)
                if member_name:
                    entries.append(Menu(str(member_name), items))
                else:
                    entries += items
            fit_menus.append(Menu(str(fit.get("name", "") or tr("Fit")), entries))
        unlink = MenuItem(tr("Unlink"), enabled=bool(record.get("linked")))
        self.calls[id(unlink)] = lambda: views.unlink(self.record)
        self.unlink_item = unlink
        menus: list = [Menu(tr("🔗 Link {name} to").format(name=name), fit_menus), unlink]
        if "prior" in record and not record.get("output"):
            menus.insert(1, self._prior_menu(record))
        self.panel = Popup(menus, title=name)
        if anchor is not None:
            self.panel.open_at(float(anchor[0]), float(anchor[1]))
        else:
            self.panel.open_at()

    def _prior_menu(self, record: dict):
        """The *Prior* submenu: Box (the plain bounds) and the smooth families, the current one ticked."""
        from emtk.widgets.menus import Menu, MenuItem

        from chisurf.core.fitting import prior_families

        current = prior_families.family_label(record.get("prior_state"))
        items = []
        for label in [prior_families.BOX_LABEL] + [s[0] for s in prior_families.PRIOR_FAMILY_SPECS]:
            item = MenuItem(tr(label), checked=label == current, checkable=True)
            typed = "Box" if label == prior_families.BOX_LABEL else label
            self.calls[id(item)] = functools.partial(
                self.views.docks.edit_model_parameter, self.record, "prior", typed
            )
            items.append(item)
        return Menu(tr("Prior"), items)

    @property
    def open(self) -> bool:
        return bool(self.panel.open)

    def pick(self, item: Any) -> None:
        call = self.calls.get(id(item))
        self.panel.open = False
        if call is not None:
            call()

    def draw(self, box) -> None:
        from emtk import overlays

        overlays.popup(
            ("model-editor-link", id(self)),
            self.panel,
            on_close=lambda: setattr(self.panel, "open", False),
            on_pick=self.pick,
        )


class _PathAdapter:
    """What :class:`~chisurf.plugins.microscopy.imaging_emtk.path_list.PathListView` reads, from resolved data."""

    def __init__(self, target: str, paths: list[str], busy: bool) -> None:
        setattr(self, target, list(paths))
        self.busy = busy


# ── the sections ───────────────────────────────────────────────────────────


class SectionViews:
    """Draws the resolved curve and custom sections of :class:`chisurf.emtk.model_editor.ModelEditor`.

    Parameters
    ----------
    editor : ModelEditor
        Owns the form; its ``docks`` run the API calls.
    """

    def __init__(self, editor: Any) -> None:
        self.editor = editor
        #: Resolved section data by its address (``id`` of a custom, ``key`` of a curve).
        self.data: dict[str, dict] = {}
        #: The dialogs and menus open over the shell.
        self.dialogs: list[Any] = []
        self.k2_fast = True
        self.diag_shown: set[str] = set()
        self.sweep: dict[str, list[float]] = {}
        self.mixer: dict[str, dict] = {}
        self.path_views: dict[str, Any] = {}
        #: How the global parameter table shades its numbers (``None`` or ``"column"``).
        self.shading: str | None = None
        self._sources: dict[str, _Rows] = {}

    @property
    def docks(self):
        return self.editor.docks

    @property
    def item_rects(self) -> dict:
        """Where a file list records its rows and buttons: the editor's form rectangles."""
        return self.editor.form.rects

    def install(self, form) -> None:
        """Register the drawers on the editor's form."""
        for key, draw in (
            ("curve_input", self._draw_curve),
            ("kappa2_controls", self._draw_kappa2),
            ("anisotropy_diagnostics", self._draw_diagnostics),
            ("lcurve", self._draw_lcurve),
            ("path_list", self._draw_paths),
            ("background_run", self._draw_run),
            ("fit_mixer", self._draw_mixer),
            ("lifetime_amplitude_options", self._draw_amplitude_options),
            ("section_error", self._draw_error),
            ("table_tools", self._draw_table_tools),
        ):
            form.custom[key] = draw

    # -- what the server sent ------------------------------------------------ #
    def reset(self) -> None:
        self.data = {}

    def convert(self, section: dict, common: dict, n: int) -> dict | list | None:
        """The emtk spec section(s) drawing one resolved ``curve_input`` or ``custom`` section."""
        if section.get("type") == "curve_input":
            key = str(section.get("key", ""))
            self.data[key] = section
            return {"type": "custom", "key": "curve_input", "options": {"id": key}, **common}
        key = str(section.get("key", ""))
        ident = str(section.get("id", key))
        self.data[ident] = section
        if section.get("error"):
            return {"type": "custom", "key": "section_error", "options": {"id": ident}, **common}
        data = section.get("data") or {}
        if key == "scalar_table":
            # The Name column draws script markup: an HTML label (``x<sub>min</sub>``) is
            # converted, as the parameter and global tables do, or its tags are drawn as text.
            rows = [
                dict(r, label=self.editor.label_markup(r.get("label") or r.get("name", "")))
                for r in data.get("rows") or []
            ]
            return self._table(
                ident,
                n,
                "scalar",
                rows,
                SCALAR_COLUMNS,
                section,
                common,
                title=(section.get("options") or {}).get("title"),
            )
        if key == "global_parameter_table":
            rows = [
                dict(r, label=self.editor.label_markup(r.get("label") or r.get("name", "")))
                for r in data.get("rows") or []
            ]
            return self._table(
                ident, n, "global", rows, GLOBAL_COLUMNS, section, common, context=True
            )
        if key == "rate_matrix":
            return self._rate_table(ident, n, section, common)
        return {"type": "custom", "key": key, "options": {"id": ident}, **common}

    def _rows(self, name: str, rows: list) -> _Rows:
        made = _Rows(rows)
        made.revision = getattr(self._sources.get(name), "revision", 0) + 1
        self._sources[name] = made
        return made

    def _table(self, ident, n, kind, rows, columns, section, common, title=None, context=False):
        source = f"section_rows_{n}"
        self.editor._sources[source] = self._rows(source, [dict(r, _section=ident) for r in rows])
        table = {
            "type": "table",
            "source": source,
            "row_key": "attr" if kind == "scalar" else "uid",
            "edited_call": f"section_edit_{kind}",
            "editable_call": "section_editable",
            "fit_rows": True,
            "fit_columns": True,
            "columns": columns,
            **common,
        }
        if kind == "global":
            table["muted_key"] = "muted"
            table["height"] = 320
            table.pop("fit_rows")
            table.update(
                filter=True, column_picker=True, status=True, colour_source="section_shading"
            )
            tools = {
                "type": "custom",
                "key": "table_tools",
                "options": {"id": ident, "source": source},
                **common,
            }
            return [table, tools]
        if context:
            table["context_call"] = "section_context"
        if title:
            return [{"type": "info", "text": str(title), **common}, table]
        return table

    def _rate_table(self, ident, n, section, common):
        data = section.get("data") or {}
        options = section.get("options") or {}
        size = int(data.get("n") or 0)
        labels = list(data.get("labels") or [str(i + 1) for i in range(size)])
        values = list(data.get("values") or [])
        cells = dict(data.get("cells") or {})
        rows = []
        for i in range(size):
            row = {"uid": f"{ident}#{i}", "state": labels[i], "_section": ident, "_i": i}
            for j in range(size):
                value = values[i * size + j] if i * size + j < len(values) else None
                cell = cells.get(f"{i},{j}") or {}
                row[f"c{j}"] = _number(value)
                row[f"fixed{j}"] = bool(cell.get("fixed"))
                row[f"cell{j}"] = cell
            rows.append(row)
        columns = [{"key": "state", "label": "", "description": tr("The source state of a row.")}]
        for j in range(size):
            columns.append(
                {
                    "key": f"c{j}",
                    "label": labels[j],
                    "editable": True,
                    "format": "%." + str(int(options.get("decimals", 4))) + "g",
                    "description": tr(
                        "Rate from the row's state to {state}; right-click "
                        "for Fixed and the link menu."
                    ).format(state=labels[j]),
                }
            )
        source = f"section_rows_{n}"
        self.editor._sources[source] = self._rows(source, rows)
        title = str(options.get("title", "") or "")
        unit = str(data.get("unit") or "")
        caption = (
            tr("row → column rate ({unit})").format(unit=unit) if unit else tr("row → column rate")
        )
        header = "  ·  ".join(([title] if title else []) + [caption])
        return [
            {"type": "info", "text": header, **common},
            {
                "type": "table",
                "source": source,
                "row_key": "uid",
                "edited_call": "section_edit_rate",
                "editable_call": "section_editable",
                "context_call": "section_context",
                "fit_rows": True,
                "fit_columns": True,
                "columns": columns,
                **common,
            },
        ]

    # -- the table callbacks (the editor forwards them) ------------------------ #
    def editable(self, record: Any, key: str) -> bool:
        record = record or {}
        if self.docks.busy:
            return False
        section = self.data.get(str(record.get("_section", ""))) or {}
        if section.get("key") == "rate_matrix" and key.startswith("c"):
            i, j = int(record.get("_i", -1)), int(key[1:])
            options = section.get("options") or {}
            if i == j and not options.get("diagonal", False):
                return False
            if i == 0 and options.get("disable_row0"):
                return False
            cell = record.get(f"cell{j}") or {}
            return not cell.get("is_linked") and not cell.get("linked_to")
        if section.get("key") == "global_parameter_table" and key != "link_row":
            return not record.get("is_output") and not record.get("linked")
        return True

    def edit_scalar(self, record: Any, key: str, value: Any) -> None:
        record = record or {}
        self.call(
            str(record.get("_section", "")),
            "set",
            {"attr": str(record.get("attr", "")), "value": value},
            tr("Setting {name}…").format(name=record.get("label", "")),
        )

    def edit_rate(self, record: Any, key: str, value: Any) -> None:
        record = record or {}
        number = _number(value)
        if number is None or not key.startswith("c"):
            return
        self.call(
            str(record.get("_section", "")),
            "set_cell",
            {"source": int(record.get("_i", 0)), "target": int(key[1:]), "value": number},
            tr("Setting a rate…"),
        )

    def edit_global(self, record: Any, key: str, value: Any) -> None:
        record = dict(record or {})
        if key == "link_row":
            rows = list(self._sources.get(self._source_of(record), []))
            target = int(value) if _number(value) is not None else 0
            if 1 <= target <= len(rows):
                self.link(record, str(rows[target - 1].get("uid", "")))
            else:
                self.unlink(record)
            return
        self.docks.edit_model_parameter(
            record, key, value, owner_uid=record.get("owner_uid") or record.get("fit_uid")
        )

    def _source_of(self, record: dict) -> str:
        ident = str(record.get("_section", ""))
        for name, rows in self._sources.items():
            if rows and rows[0].get("_section") == ident:
                return name
        return ""

    def context(self, record: Any, key: Any, at: Any) -> None:
        """Right click on a parameter or a rate cell: Fixed (a rate), the link menu."""
        record = dict(record or {})
        section = self.data.get(str(record.get("_section", ""))) or {}
        if section.get("key") == "rate_matrix":
            if not str(key or "").startswith("c"):
                return
            cell = record.get(f"cell{str(key)[1:]}") or {}
            if not cell.get("uid"):
                return
            self.open_link_menu(dict(cell), at, fixed_toggle=True)
            return
        if record.get("_params"):
            from chisurf.emtk.model_editor import _slot_parameter

            record = _slot_parameter(record, str(key or "")) or {}
        if record.get("uid"):
            self.open_link_menu(record, at)

    # -- writes ---------------------------------------------------------------- #
    def call(
        self, section: str, op: str, args: dict, label: str, after=None, update=True, failed=None
    ) -> bool:
        return self.docks.section_call(
            section, op, args, label, after=after, update=update, failed=failed
        )

    def link(self, record: dict, target_uid: str) -> bool:
        return self.docks.link_model_parameter(record, target_uid)

    def unlink(self, record: dict) -> bool:
        return self.docks.unlink_model_parameter(record)

    def open_link_menu(self, record: dict, at: Any, fixed_toggle: bool = False) -> None:
        """Read the session's fits, then open the link menu at *at*."""

        def opened(fits: Any) -> None:
            menu = LinkMenu(self, record, list(fits or []), at)
            if fixed_toggle:
                from emtk.widgets.menus import MenuItem

                fixed = MenuItem(tr("Fixed"), checked=bool(record.get("fixed")), checkable=True)
                menu.calls[id(fixed)] = lambda: self.docks.edit_model_parameter(
                    record, "fixed", not bool(record.get("fixed"))
                )
                menu.panel.entries.insert(0, fixed)
            self.dialogs.append(menu)

        self.docks.read_fits_for_links(opened)

    # -- drawing helpers ---------------------------------------------------------- #
    def _rect(self, state, name: str) -> None:
        state.rects[name] = im.get_item_rect()

    def _section(self, section: dict) -> dict:
        return self.data.get(str((section.get("options") or {}).get("id", ""))) or {}

    def _draw_table_tools(self, section, model, state, width) -> None:
        """Under the global parameter table: re-read, export and shading, as the Qt table's toolbar."""
        options = section.get("options") or {}
        ident = str(options.get("id", ""))
        if im.button(f"🔄##tools-refresh-{ident}"):
            self.docks.reread_current()
        self._rect(state, "table.refresh")
        im.set_item_tooltip(tr("Read the parameters of every fit again."))
        im.same_line()
        if im.button(f"📤##tools-export-{ident}"):
            rows = list(self._sources.get(str(options.get("source", "")), []))
            self.docks.open_file_dialog(
                tr("Export the parameters"),
                mode="save",
                done=lambda path: self.export_rows(path, rows),
            )
        self._rect(state, "table.export")
        im.set_item_tooltip(tr("Write the table to a CSV file."))
        im.same_line()
        changed, shaded = im.toggle_button(f"🎨##tools-shade-{ident}", self.shading is not None)
        self._rect(state, "table.shade")
        im.set_item_tooltip(tr("Shade each numeric column by value."))
        if changed:
            self.shading = "column" if shaded else None

    def export_rows(self, path: str, rows: list) -> None:
        """The global parameter table as CSV, in its column order."""
        keys = [c["key"] for c in GLOBAL_COLUMNS]
        with open(path, "w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow([c["label"] for c in GLOBAL_COLUMNS])
            for row in rows:
                writer.writerow(
                    [
                        self.editor.plain_label(str(row.get(k, "")))
                        if k == "label"
                        else ("" if row.get(k) is None else row.get(k))
                        for k in keys
                    ]
                )
        self.docks.status = tr("Saved to {name}").format(name=Path(path).name)

    def _draw_error(self, section, model, state, width) -> None:
        d = self._section(section)
        im.text_colored(
            _style.TEXT_DANGER,
            tr("{kind}: {error}").format(
                kind=d.get("title") or d.get("key", ""), error=d.get("error", "")
            ),
        )

    def _draw_curve(self, section, model, state, width) -> None:
        d = self._section(section)
        key = str(d.get("key", ""))
        label = str(d.get("label", ""))
        busy = self.docks.busy
        im.align_text_to_frame_padding()
        im.text(tr(label))
        im.same_line()
        buttons = 2 * (im.get_frame_height() + 6.0)
        fwhm_w = (im.calc_text_size(tr("FWHM"))[0] + 80.0) if d.get("shows_fwhm") else 0.0
        im.set_next_item_width(max(60.0, im.get_content_region_avail()[0] - buttons - fwhm_w))
        im.input_text(
            f"##curve-{key}",
            str(d.get("curve_name") or ""),
            tr("load {label} →").format(label=tr(label)),
            im.InputTextFlags.READ_ONLY,
            elide_start=True,
        )
        self._rect(state, f"curve.{key}.name")
        im.set_item_tooltip(str(d.get("curve_name") or "") or tr("No curve loaded."))
        im.same_line()
        im.begin_disabled(busy)
        if im.button(f"…##curve-pick-{key}"):
            self.docks.pick_curve(key, im.get_item_rect())
        self._rect(state, f"curve.{key}.pick")
        im.set_item_tooltip(tr("Select {label}").format(label=tr(label)))
        if d.get("can_unload"):
            im.same_line()
            im.begin_disabled(not d.get("loaded"))
            if im.button(f"✕##curve-unload-{key}"):
                self.docks.unload_curve(key, label)
            self._rect(state, f"curve.{key}.unload")
            im.set_item_tooltip(tr("Unload {label}").format(label=tr(label)))
            im.end_disabled()
        im.end_disabled()
        if d.get("shows_fwhm"):
            im.same_line()
            im.text(tr("FWHM"))
            im.same_line()
            fwhm = _number(d.get("fwhm"))
            im.text("" if fwhm is None else f"{fwhm:.3f}")
            self._rect(state, f"curve.{key}.fwhm")

    def _draw_kappa2(self, section, model, state, width) -> None:
        d = self._section(section)
        ident = str(d.get("id", ""))
        data = d.get("data") or {}
        busy = self.docks.busy
        mode = str(data.get("mode", "fast"))
        im.begin_disabled(busy or not data.get("available"))
        if (
            im.radio_button(tr("dynamic κ²") + f"##k2-dyn-{ident}", mode == "fast")
            and mode != "fast"
        ):
            self.call(ident, "set_mode", {"mode": "fast"}, tr("Setting the κ² regime…"))
        self._rect(state, "kappa2.dynamic")
        im.set_item_tooltip(tr("One κ² for every donor-acceptor pair (fast reorientation)."))
        im.same_line()
        if (
            im.radio_button(tr("static κ²") + f"##k2-stat-{ident}", mode == "slow")
            and mode != "slow"
        ):
            self.call(ident, "set_mode", {"mode": "slow"}, tr("Setting the κ² regime…"))
        self._rect(state, "kappa2.static")
        im.set_item_tooltip(tr("Average over a static κ² distribution (slow reorientation)."))
        im.end_disabled()
        im.same_line()
        _changed, self.k2_fast = im.checkbox(tr("Fast") + f"##k2-fast-{ident}", self.k2_fast)
        self._rect(state, "kappa2.fast")
        im.set_item_tooltip(
            tr(
                "Use fast loop-based convolution for static κ² distributions.\n"
                "Provides speedup for large κ² distributions by looping over\n"
                "ratio values and accumulating shifted distance histograms.\n"
                "Disable for exact outer product."
            )
        )
        im.begin_disabled(busy)
        if im.button(tr("show κ²") + f"##k2-show-{ident}"):
            self.dialogs.append(Kappa2ShowWindow(self, ident, self.k2_fast))
        self._rect(state, "kappa2.show")
        im.set_item_tooltip(tr("The κ² distribution and what it does to the apparent distance."))
        im.same_line()
        if im.button(tr("compute κ²") + f"##k2-compute-{ident}"):
            self.dialogs.append(
                Kappa2ComputeDialog(self, ident, float(data.get("kappa2") or 2 / 3))
            )
        self._rect(state, "kappa2.compute")
        im.set_item_tooltip(tr("Compute a κ² distribution from the dyes' anisotropies and use it."))
        im.same_line()
        im.begin_disabled(not data.get("can_set_r0"))
        if im.button(tr("calc R0") + f"##k2-r0-{ident}"):
            self.open_forster(ident)
        self._rect(state, "kappa2.r0")
        im.set_item_tooltip(
            tr("Open the Förster radius calculator to compute R₀ from MMFDB spectra")
        )
        im.end_disabled()
        im.end_disabled()

    def open_forster(self, ident: str) -> None:
        """*calc R0*: the Förster radius calculator; its R0 goes to the model."""
        from chisurf.emtk.forster_calculator import ForsterCalculatorDialog

        def closed(r0: Any) -> None:
            if _number(r0) is not None:
                self.call(
                    ident,
                    "set_forster_radius",
                    {"r0": float(r0)},
                    tr("Setting the Förster radius…"),
                )

        self.dialogs.append(ForsterCalculatorDialog(on_close=closed))

    def _draw_diagnostics(self, section, model, state, width) -> None:
        d = self._section(section)
        ident = str(d.get("id", ""))
        data = d.get("data") or {}
        shown = ident in self.diag_shown
        changed, shown = im.toggle_button(tr("VV/VH diag") + f"##diag-{ident}", shown)
        self._rect(state, "anisotropy.diag")
        im.set_item_tooltip(
            tr("Show the background-corrected VV and VH integrals (computed outputs)")
        )
        if changed:
            (self.diag_shown.add if shown else self.diag_shown.discard)(ident)
        im.same_line()
        im.begin_disabled(self.docks.busy or not data.get("has_rt"))
        if im.button(tr("show r(t)") + f"##rt-{ident}"):
            self.dialogs.append(RtWindow(self, ident))
        self._rect(state, "anisotropy.rt")
        im.set_item_tooltip(
            tr(
                "Open the anisotropy decay of data and model, uncorrected and corrected,\n"
                "with g / l1 / l2 / backgrounds / VH-VV shift as live controls"
            )
        )
        im.end_disabled()
        if shown:
            outputs = data.get("outputs") or []
            if not outputs:
                im.text_disabled(tr("This model reports no corrected VV/VH integrals."))
            for row in outputs:
                value = _number(row.get("value"))
                im.text(
                    f"{self.editor.plain_label(row.get('label') or row.get('name', ''))}  "
                    f"{'' if value is None else f'{value:.3g}'}"
                )

    def _draw_lcurve(self, section, model, state, width) -> None:
        d = self._section(section)
        ident = str(d.get("id", ""))
        data = d.get("data") or {}
        options = d.get("options") or {}
        rho = [float(v) for v in data.get("residual_norm") or [] if v is not None]
        eta = [float(v) for v in data.get("solution_norm") or [] if v is not None]
        height = float(options.get("max_height", 260))
        w = im.get_content_region_avail()[0]
        if implot.begin_plot(
            f"##lcurve-{ident}", (w, max(float(options.get("min_height", 160)), min(height, 220.0)))
        ):
            implot.setup_axes(
                tr(options.get("x_label", "residual norm")),
                tr(options.get("y_label", "solution norm")),
            )
            implot.setup_axis_scale(implot.AXIS_X1, implot.SCALE_LOG10)
            implot.setup_axis_scale(implot.AXIS_Y1, implot.SCALE_LOG10)
            implot.setup_legend(implot.LOCATION_NORTH_EAST)
            if rho and len(rho) == len(eta):
                implot.set_next_line_style((0, 200, 200), 2.0)
                implot.plot_line(tr("L-curve"), rho, eta)
                corner = data.get("corner_index")
                if corner is not None and 0 <= int(corner) < len(rho):
                    implot.set_next_marker_style(implot.MARKER_CIRCLE, 6.0, (220, 50, 50))
                    implot.plot_scatter(tr("chosen"), [rho[int(corner)]], [eta[int(corner)]])
                if (
                    options.get("select_action")
                    and implot.is_plot_hovered()
                    and im.is_mouse_clicked(0)
                    and not self.docks.busy
                ):
                    pos = implot.get_plot_mouse_pos()
                    index = self._nearest(rho, eta, float(pos.x), float(pos.y))
                    if index is not None:
                        self.call(ident, "select", {"index": index}, tr("Picking the weight…"))
            else:
                implot.plot_dummy(tr("no L-curve yet"))
            implot.end_plot()
        self._rect(state, f"lcurve.{ident}.plot")
        if not (options.get("compute_action") or options.get("select_action")):
            return
        window = self.sweep.setdefault(
            ident,
            [
                float(options.get("log10_min", -3.0)),
                float(options.get("log10_max", 0.0)),
                float(options.get("n_points", 32)),
            ],
        )
        for i, (label, fmt) in enumerate(
            ((tr("min"), "%.2f"), (tr("max"), "%.2f"), (tr("N"), "%.0f"))
        ):
            if i:
                im.same_line()
            im.align_text_to_frame_padding()
            im.text(label)
            im.same_line()
            im.set_next_item_width(70.0)
            changed, value = im.input_double(f"##sweep-{ident}-{i}", window[i], 0.0, 0.0, fmt)
            self._rect(state, f"lcurve.{ident}.{('min', 'max', 'n')[i]}")
            if changed:
                window[i] = float(value)
        busy = self.docks.busy
        im.begin_disabled(busy)
        if options.get("compute_action"):
            im.same_line()
            if im.button(tr("⟳ sweep") + f"##sweep-{ident}"):
                lo, hi = sorted((window[0], window[1]))
                n = int(min(256, max(2, round(window[2]))))
                self.call(
                    ident,
                    "compute",
                    {"n_points": n, "log10_min": lo, "log10_max": hi},
                    tr("Sampling the L-curve…"),
                )
            self._rect(state, f"lcurve.{ident}.sweep")
            im.set_item_tooltip(
                tr(
                    "Sample the regularization weight over the range above and redraw "
                    "the L-curve. The corner is the weight balancing misfit against "
                    "smoothness."
                )
            )
            im.same_line()
            corner = data.get("corner_index")
            im.begin_disabled(corner is None or not options.get("select_action"))
            if im.button(tr("⌾ corner") + f"##corner-{ident}") and corner is not None:
                self.call(ident, "select", {"index": int(corner)}, tr("Picking the weight…"))
            self._rect(state, f"lcurve.{ident}.corner")
            im.set_item_tooltip(tr("Adopt the weight at the detected corner."))
            im.end_disabled()
        im.end_disabled()

    @staticmethod
    def _nearest(rho: list, eta: list, x: float, y: float) -> int | None:
        """The swept point nearest (x, y) in decades: the axes are logarithmic."""
        if x <= 0 or y <= 0:
            return None
        best, index = math.inf, None
        for i, (r, e) in enumerate(zip(rho, eta)):
            if r > 0 and e > 0:
                d = (math.log10(r) - math.log10(x)) ** 2 + (math.log10(e) - math.log10(y)) ** 2
                if d < best:
                    best, index = d, i
        return index

    def _draw_paths(self, section, model, state, width) -> None:
        from chisurf.plugins.microscopy.imaging_emtk.path_list import PathListView

        d = self._section(section)
        ident = str(d.get("id", ""))
        options = d.get("options") or {}
        target = str(d.get("target", "")) or "paths"
        view = self.path_views.get(ident)
        if view is None:
            view = PathListView(
                self,
                actions={
                    "add": lambda: self._choose_paths(ident, options, folder=False),
                    "folder": lambda: self._choose_paths(ident, options, folder=True),
                    "database": lambda: self._database_paths(ident, options),
                    "remove": lambda path: self._remove_path(ident, path),
                    "clear": lambda: self.call(ident, "clear", {}, tr("Clearing the list…")),
                },
            )
            self.path_views[ident] = view
        adapter = _PathAdapter(target, (d.get("data") or {}).get("paths") or [], self.docks.busy)
        spec = {
            "title": options.get("title") or d.get("title") or target,
            "description": d.get("description", ""),
            "options": {"target": target, "empty": tr("No file. Add or drop one.")},
        }
        view.draw(spec, adapter, state)

    def _choose_paths(self, ident: str, options: dict, folder: bool) -> None:
        self.docks.open_file_dialog(
            tr("Add folder") if folder else tr("Add files"),
            mode="folder" if folder else "open",
            done=lambda path: self.call(ident, "add", {"paths": [path]}, tr("Adding files…")),
        )

    def _database_paths(self, ident: str, options: dict) -> None:
        """MMFDB's datasets of the kinds the list takes, picked like any other dataset."""
        self.docks.pick_database_paths(
            options.get("mmfdb_kinds") or [],
            lambda paths: self.call(ident, "add", {"paths": list(paths)}, tr("Adding files…")),
        )

    def _remove_path(self, ident: str, path: str) -> None:
        paths = ((self.data.get(ident) or {}).get("data") or {}).get("paths") or []
        if path in paths:
            self.call(ident, "remove", {"index": paths.index(path)}, tr("Removing a file…"))

    def _draw_run(self, section, model, state, width) -> None:
        d = self._section(section)
        ident = str(d.get("id", ""))
        data = d.get("data") or {}
        options = d.get("options") or {}
        running = bool(data.get("running"))
        if running:
            self.docks.poll_model_job(int(options.get("interval_ms", 500)))
        im.begin_disabled(self.docks.busy or running)
        if im.button(tr(options.get("start_label", "Start")) + f"##run-start-{ident}"):
            self.call(ident, "start", {}, tr("Starting…"))
        self._rect(state, f"run.{ident}.start")
        im.set_item_tooltip(tr(options.get("start_description", "Start the job.")))
        im.end_disabled()
        if options.get("stop_action"):
            im.same_line()
            im.begin_disabled(self.docks.busy or not running)
            if im.button(tr(options.get("stop_label", "Stop")) + f"##run-stop-{ident}"):
                self.call(ident, "stop", {}, tr("Stopping…"))
            self._rect(state, f"run.{ident}.stop")
            im.set_item_tooltip(tr(options.get("stop_description", "Stop the job.")))
            im.end_disabled()
        progress = _number(data.get("progress"))
        if progress is not None:
            im.progress_bar(max(0.0, min(1.0, progress)), None, f"{100.0 * progress:.0f}%")
            self._rect(state, f"run.{ident}.progress")
        if data.get("status"):
            im.text_disabled(str(data["status"]))

    def _draw_mixer(self, section, model, state, width) -> None:
        d = self._section(section)
        ident = str(d.get("id", ""))
        data = d.get("data") or {}
        mine = self.mixer.setdefault(ident, {"pick": "", "name": "", "all": False})
        candidates = data.get("candidates") or []
        uids = [c["uid"] for c in candidates]
        if mine["pick"] not in uids:
            mine["pick"] = uids[0] if uids else ""
        names = [c["name"] for c in candidates]
        busy = self.docks.busy
        im.set_next_item_width(
            max(80.0, im.get_content_region_avail()[0] - im.get_frame_height() - 8.0)
        )
        index = uids.index(mine["pick"]) if mine["pick"] in uids else -1
        if im.begin_combo(
            f"##mixer-fit-{ident}", names[index] if index >= 0 else tr("no lifetime fit")
        ):
            for i, name in enumerate(names):
                if im.selectable(f"{name}##mixer-{i}", i == index):
                    mine["pick"] = uids[i]
                im.set_item_tooltip(tr("Add this lifetime fit to the mixture."))
            im.end_combo()
        self._rect(state, f"mixer.{ident}.fit")
        im.set_item_tooltip(tr("Select a lifetime fit to add to the mixture."))
        im.same_line()
        if im.button(f"🔄##mixer-refresh-{ident}"):
            self.docks.reread_current()
        self._rect(state, f"mixer.{ident}.refresh")
        im.set_item_tooltip(tr("Refresh the list of available lifetime fits."))
        im.align_text_to_frame_padding()
        im.text(tr("Name"))
        im.same_line()
        im.set_next_item_width(90.0)
        _c, mine["name"] = im.input_text(
            f"##mixer-name-{ident}", mine["name"], tr("fraction name…")
        )
        self._rect(state, f"mixer.{ident}.name")
        im.set_item_tooltip(tr("Name for the fraction parameter (default: x_N)."))
        im.same_line()
        _c, mine["all"] = im.checkbox(tr("all") + f"##mixer-all-{ident}", mine["all"])
        self._rect(state, f"mixer.{ident}.all")
        im.set_item_tooltip(tr("Add all listed fits at once."))
        im.same_line()
        im.begin_disabled(busy or not uids)
        if im.button(tr("add") + f"##mixer-add-{ident}"):
            picked = list(uids) if mine["all"] else [mine["pick"]]
            self.call(
                ident,
                "add",
                {"fit_uids": picked, "name": mine["name"]},
                tr("Adding to the mixture…"),
            )
        self._rect(state, f"mixer.{ident}.add")
        im.set_item_tooltip(tr("Add the selected fit to the mixture."))
        im.end_disabled()
        components = data.get("components") or []
        if not components:
            im.text_disabled(tr("No fit is mixed yet."))
        for i, name in enumerate(components):
            im.align_text_to_frame_padding()
            im.text(f"{i + 1}: {name}")
            im.same_line()
            im.begin_disabled(busy)
            if im.small_button(tr("remove") + f"##mixer-del-{ident}-{i}"):
                self.call(ident, "remove", {"index": i}, tr("Removing from the mixture…"))
            self._rect(state, f"mixer.{ident}.remove.{i}")
            im.set_item_tooltip(tr("Remove this fit from the mixture."))
            im.end_disabled()
        if data.get("fractions"):
            im.text(tr("Fraction"))

    def _draw_amplitude_options(self, section, model, state, width) -> None:
        d = self._section(section)
        ident = str(d.get("id", ""))
        data = d.get("data") or {}
        busy = self.docks.busy
        im.begin_disabled(busy)
        changed, absolute = im.checkbox(
            tr("Abs.") + f"##abs-{ident}", bool(data.get("absolute", True))
        )
        self._rect(state, f"amplitudes.{ident}.abs")
        im.set_item_tooltip(tr("Take absolute value of amplitudes (no negative amplitudes)."))
        if changed:
            self.call(ident, "set", {"absolute": absolute}, tr("Setting the amplitudes…"))
        im.same_line()
        changed, normalize = im.checkbox(
            tr("Norm.") + f"##norm-{ident}", bool(data.get("normalize", True))
        )
        self._rect(state, f"amplitudes.{ident}.norm")
        im.set_item_tooltip(tr("Normalize amplitudes so they sum to one."))
        if changed:
            self.call(ident, "set", {"normalize": normalize}, tr("Setting the amplitudes…"))
        targets = data.get("targets") or []
        for op, label, tip in (
            ("read", tr("read"), tr("Copy parameter values from another lifetime group.")),
            ("link", tr("link"), tr("Link this lifetime group to another (shared spectrum).")),
        ):
            im.same_line()
            if im.button(f"{label} ▾##{op}-{ident}"):
                self._target_menu(ident, op, targets, im.get_item_rect())
            self._rect(state, f"amplitudes.{ident}.{op}")
            im.set_item_tooltip(tip)
        im.end_disabled()

    def _target_menu(self, ident: str, op: str, targets: list, anchor) -> None:
        from emtk.widgets.menus import MenuItem, Popup

        class _Menu:
            def __init__(menu) -> None:
                menu.calls = {}
                items = []
                for target in targets:
                    item = MenuItem(str(target.get("label", "")))
                    args = {k: target[k] for k in ("fit_uid", "member", "group")}
                    menu.calls[id(item)] = lambda a=args: self.call(
                        ident,
                        op,
                        a,
                        tr("Reading the lifetimes…")
                        if op == "read"
                        else tr("Linking the lifetimes…"),
                    )
                    items.append(item)
                if not items:
                    items = [MenuItem(tr("No other lifetime group"), enabled=False)]
                menu.panel = Popup(items)
                x, y, _w, h = anchor
                menu.panel.open_at(float(x), float(y) + float(h))

            @property
            def open(menu) -> bool:
                return bool(menu.panel.open)

            def draw(menu, box) -> None:
                from emtk import overlays

                def picked(item):
                    menu.panel.open = False
                    call = menu.calls.get(id(item))
                    if call is not None:
                        call()

                overlays.popup(
                    ("model-editor-targets", id(menu)),
                    menu.panel,
                    on_close=lambda: setattr(menu.panel, "open", False),
                    on_pick=picked,
                )

        self.dialogs.append(_Menu())

    # -- dialogs ----------------------------------------------------------------- #
    @staticmethod
    def _is_open(dialog: Any) -> bool:
        if hasattr(dialog, "open"):
            return bool(dialog.open)
        return bool(getattr(getattr(dialog, "window", None), "open", False))

    def modal_open(self) -> bool:
        self.dialogs = [d for d in self.dialogs if self._is_open(d)]
        return bool(self.dialogs)

    def draw_dialogs(self, box) -> None:
        for dialog in list(self.dialogs):
            dialog.draw(box)
        self.dialogs = [d for d in self.dialogs if self._is_open(d)]

    # -- for parity checks ---------------------------------------------------------- #
    def inventory(self) -> set[str]:
        """Every label the drawn sections offer, the ones behind their buttons included."""
        found: set[str] = set()
        for d in self.data.values():
            key = d.get("key", "")
            if d.get("type") == "curve_input":
                found |= {str(d.get("label", "")), "…", "✕"} | (
                    {"FWHM"} if d.get("shows_fwhm") else set()
                )
                continue
            data = d.get("data") or {}
            options = d.get("options") or {}
            if key == "kappa2_controls":
                found |= {"dynamic κ²", "static κ²", "Fast", "show κ²", "compute κ²", "calc R0"}
            elif key == "anisotropy_diagnostics":
                found |= {"VV/VH diag", "show r(t)"}
            elif key == "lcurve":
                found |= {"L-curve"}
                if options.get("compute_action"):
                    found |= {"min", "max", "N", "⟳ sweep", "⌾ corner"}
            elif key == "fit_mixer":
                found |= {"Name", "all", "add", "🔄", "Fraction"} | {
                    c["name"] for c in data.get("candidates") or []
                }
            elif key == "lifetime_amplitude_options":
                found |= {"Abs.", "Norm.", "read", "link"}
            elif key == "path_list":
                found |= {
                    str(options.get("title", "")),
                    "Add files",
                    "Folder",
                    "Database",
                    "Remove",
                    "Clear",
                }
            elif key == "background_run":
                found |= {str(options.get("start_label", "")), str(options.get("stop_label", ""))}
            elif key == "scalar_table":
                found |= {"Name", "Value"} | {
                    str(r.get("label", "")) for r in data.get("rows") or []
                }
                if options.get("title"):
                    found.add(str(options["title"]))
            elif key == "rate_matrix":
                found |= set(data.get("labels") or [])
                title = str(options.get("title", "") or "")
                unit = str(data.get("unit") or "")
                caption = f"row → column rate ({unit})" if unit else "row → column rate"
                found.add("  ·  ".join(([title] if title else []) + [caption]))
            elif key == "global_parameter_table":
                found |= {c["label"] for c in GLOBAL_COLUMNS} | {"🔄", "📤", "🎨"}
        return {f for f in found if f}


__all__ = ["GLOBAL_COLUMNS", "SCALAR_COLUMNS", "SectionViews"]
