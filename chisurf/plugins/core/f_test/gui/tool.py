"""F-test / χ²-max calculator (AutoForm; see okf/subsystems/gui-autoform.md).

Two coupled statistics tools in one declarative form (``ftest.view.json``):

* **F-test** — compare two nested model fits; the confidence that the more
  complex model is justified follows from the F-distribution, and editing the
  confidence instead solves for the χ²(2) threshold.
* **χ²-max** — the largest reduced χ² still compatible with a single fit's χ²
  minimum at a chosen confidence level.

The hand-built ``FTestWidget`` (a QGridLayout with ~25 property accessors and
three per-row "load from fit" menus) is replaced by an :class:`_FTestModel`
whose fields AutoForm binds directly, plus a single compact *From fit ▾* toolbar
button. ``FTestWidget`` is kept as a back-compat alias.

The window is a :class:`~chisurf.gui.widgets.tools.ChisurfDockTool`, so the window-level drag-drop dispatch, the lazy MMFDB accessors, and
the declared-message status bar come from the shared base instead of being
re-forked here.
"""

from __future__ import annotations

import pathlib
from typing import Any

from qtpy import QtWidgets

from chisurf.core.dataspec import load_view_spec
from chisurf.core.math.statistics import chi2_max, f_test_chi2r, f_test_confidence
from chisurf.gui.glyphs import Glyphs
from chisurf.gui.widgets.messages import Msg
from chisurf.gui.widgets.tools import ChisurfDockTool

_GUI_DIR = pathlib.Path(__file__).parent

#: Edited attr -> the recompute method it triggers (mirrors the legacy slots).
_CONF_ATTRS = frozenset({"chi2_2", "n1", "n2"})
_CHI2_2_ATTRS = frozenset({"chi2_1", "conf_level"})
_CHI2_MAX_ATTRS = frozenset({"chi2_min", "npars", "dof", "conf_level_2"})


class _FTestModel:
    """Backing model for the F-test / χ²-max calculator; fields in ftest.view.json."""

    def __init__(self) -> None:
        # F-test: compare two nested models. The defaults describe a plausible
        # pair -- the extra parameters of model 2 buy a 10% lower reduced χ².
        self.chi2_1 = 1.1
        self.n1 = 100
        self.chi2_2 = 1.0
        self.n2 = 98
        self.conf_level = 0.95
        self.recompute_conf()
        # χ²-max: upper χ² limit from a single fit.
        self.chi2_min = 1.0
        self.npars = 1
        self.dof = 100
        self.conf_level_2 = 0.95
        self.chi2_max = 0.0
        self.recompute_chi2_max()

    def view_spec(self):
        return load_view_spec(_GUI_DIR / "ftest.view.json")

    def recompute_conf(self) -> None:
        """Confidence that model 2 is justified: ``F.cdf(χ²₁/χ²₂, n₁, n₂)``."""
        try:
            self.conf_level = f_test_confidence(
                chi2r_1=self.chi2_1, chi2r_2=self.chi2_2, nu_1=self.n1, nu_2=self.n2
            )
        except (ZeroDivisionError, ValueError):
            pass

    def recompute_chi2_2(self) -> None:
        """χ²(2) threshold for the current confidence: ``χ²₁ / F.ppf(conf, n₁, n₂)``."""
        try:
            self.chi2_2 = f_test_chi2r(
                chi2r_1=self.chi2_1, conf_level=self.conf_level, nu_1=self.n1, nu_2=self.n2
            )
        except (ZeroDivisionError, ValueError):
            pass

    def recompute_chi2_max(self) -> None:
        """Upper χ² limit of a fit at ``conf_level_2`` for ``npars`` parameters and ``dof``."""
        self.chi2_max = float(
            chi2_max(
                chi2_value=self.chi2_min,
                number_of_parameters=max(1, int(self.npars)),
                nu=max(1, int(self.dof)),
                conf_level=self.conf_level_2,
            )
        )


class FTestTool(ChisurfDockTool):
    """F-test / χ²-max calculator; constructs with no required arguments (hub-embeddable).

    A calculator has no file inputs, so the base's window-level drop is answered
    with a standing message instead of being silently swallowed.
    """

    name = "F-Test"

    #: QSettings key for the base's geometry helpers.
    tool_settings_name: str = "FTestTool"

    class Information(ChisurfDockTool.Information):
        """Conditions this tool can report."""

        no_file_input = Msg("The F-test calculator takes no dropped files.")

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.setWindowTitle("F-Calculator")

        from chisurf.gui.autoform import AutoForm

        self._model = _FTestModel()
        self._form = AutoForm(self._model, self)
        self.setCentralWidget(self._form)
        self._build_toolbar()
        self._wire_fields()
        self._form.sync_fields()

        # Geometry is owned by the manifest-declared window statefulness; wire it
        # here too so it applies however the plugin is launched (the helper is
        # idempotent). The base's save/restore_window_geometry are deliberately
        # left uncalled so the two mechanisms do not both write a geometry key.
        try:
            from chisurf.core.plugin import load_manifest
            from chisurf.core.plugin.registry import apply_manifest_statefulness

            manifest = load_manifest(pathlib.Path(__file__).parents[1] / "manifest.json")
            if manifest is not None:
                apply_manifest_statefulness(self, manifest)
        except Exception:
            pass

    def on_paths_dropped(self, paths: list[pathlib.Path]) -> None:
        """Report that the calculator has no file input.

        The base enables window-level path drag-drop for every dock tool. This
        tool computes from typed-in numbers, so a dropped path has nowhere to go;
        say so in the status bar rather than accepting the drop and doing nothing.
        """
        if paths:
            self.Information.no_file_input()

    # ── toolbar: load values from an open fit ─────────────────────────
    def _build_toolbar(self) -> None:
        toolbar = self.addToolBar("F-test")
        toolbar.setObjectName("fTestToolbar")
        toolbar.setMovable(False)
        self._from_fit_btn = QtWidgets.QToolButton()
        self._from_fit_btn.setText(f"{Glyphs.CHART} From fit")
        self._from_fit_btn.setToolTip("Load n_points / n_free / χ²r from an open fit.")
        self._from_fit_btn.setPopupMode(QtWidgets.QToolButton.InstantPopup)
        self._from_fit_btn.setMenu(self._build_fit_menu())
        toolbar.addWidget(self._from_fit_btn)
        self.ensure_help_toolbar(toolbar=toolbar, title="F-test — help")

    def _build_fit_menu(self) -> QtWidgets.QMenu:
        """One submenu per open fit, each with the three load targets."""
        menu = QtWidgets.QMenu(self)
        menu.aboutToShow.connect(self._rebuild_fit_menu)
        return menu

    def _rebuild_fit_menu(self) -> None:
        menu = self._from_fit_btn.menu()
        menu.clear()
        try:
            from chisurf.gui.widgets.fitting.fitting_client import get_fitting_client

            fits = [fs for group in get_fitting_client().get_fit_objects() for fs in group]
        except Exception:
            fits = []
        if not fits:
            menu.addAction("(no open fits)").setEnabled(False)
            return
        for fit in fits:
            sub = menu.addMenu(getattr(fit, "name", "fit"))
            sub.addAction("→ F-test model 1 (χ²₁, n₁)").triggered.connect(
                lambda _=False, f=fit: self._load_fit(f, "model1")
            )
            sub.addAction("→ F-test model 2 (χ²₂, n₂)").triggered.connect(
                lambda _=False, f=fit: self._load_fit(f, "model2")
            )
            sub.addAction("→ χ²-max (χ²min, params, ν)").triggered.connect(
                lambda _=False, f=fit: self._load_fit(f, "chi2max")
            )

    def _load_fit(self, fit: Any, target: str) -> None:
        """Copy a fit's statistics into the selected target section, then recompute."""
        n_points = int(fit.model.n_points)
        n_free = int(fit.model.n_free)
        chi2r = float(fit.chi2r)
        m = self._model
        if target == "model1":
            m.chi2_1, m.n1 = chi2r, max(1, n_points - n_free)
            m.recompute_chi2_2()
        elif target == "model2":
            m.chi2_2, m.n2 = chi2r, max(1, n_points - n_free)
            m.recompute_conf()
        else:  # chi2max
            m.chi2_min, m.npars, m.dof = chi2r, n_free, max(1, n_points - n_free)
            m.recompute_chi2_max()
        self._form.sync_fields()

    # ── field wiring: recompute on edit (dispatch by attr) ────────────
    def _wire_fields(self) -> None:
        from chisurf.gui.autoform.sections.builtin import ValueWidget

        for vw in self._form.findChildren(ValueWidget):
            attr = getattr(getattr(vw, "_section", None), "attr", None)
            editor = getattr(vw, "editor", None)
            if attr is None or editor is None:
                continue
            signal = getattr(editor, "editingFinished", None) or getattr(
                editor, "valueChanged", None
            )
            if signal is not None:
                signal.connect(lambda *_a, a=attr: self._on_field_edited(a))

    def _on_field_edited(self, attr: str) -> None:
        m = self._model
        if attr in _CONF_ATTRS:
            m.recompute_conf()
        elif attr in _CHI2_2_ATTRS:
            m.recompute_chi2_2()
        if attr in _CHI2_MAX_ATTRS:
            m.recompute_chi2_max()
        self._form.sync_fields()


# Back-compat alias (nothing external imports it, but keep the old name stable).
FTestWidget = FTestTool


if __name__ == "__main__":
    import sys

    app = QtWidgets.QApplication(sys.argv)
    win = FTestTool()
    win.show()
    sys.exit(app.exec_())
