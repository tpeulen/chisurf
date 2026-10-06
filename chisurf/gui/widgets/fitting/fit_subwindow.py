from __future__ import annotations

import json
import os
import pathlib

from qtpy import QtCore, QtWidgets

import chisurf as cs
import chisurf.core.data
import chisurf.core.fitting
import chisurf.core.settings
import chisurf.core.support.decorators
import chisurf.gui.decorators
import chisurf.gui.widgets
import chisurf.gui.widgets.experiments.widgets
from chisurf.gui import dialogs
from chisurf.gui.widgets.fitting import presentation_fit_members
from chisurf.gui.widgets.fitting.fit_plots_area import FitPlotsArea
from chisurf.gui.widgets.fitting.fitting_client import get_fitting_client
from chisurf.gui.widgets.mdi_custom_titlebar import CustomMdiSubWindow


class FitSubWindow(CustomMdiSubWindow):
    def update(self, *args):
        super().update(*args)
        self.plot_tab_widget.update(*args)
        self.refresh_current_plot()

    def refresh_current_plot(self) -> None:
        """Recompute and redraw every visible plot from the model.

        Repainting the surface does **not** re-pull the model curve; each
        :class:`Plot` does that in its ``update_all``/``update`` hook (the path
        :meth:`on_change_plot` uses). Calling it here makes a parameter edit or
        a finished fit (``fit.updated`` / ``fit.ran``) show without switching
        tabs -- on every page in view, since split regions show several.
        """
        for idx in self.plot_tab_widget.visible_indices():
            plot = self.ensure_plot_created(idx)
            if plot is not None:
                self._update_plot(plot)

    @staticmethod
    def _update_plot(plot) -> None:
        """Re-pull a plot's curves from the model."""
        update_all = getattr(plot, "update_all", None)
        if callable(update_all):
            update_all()
        elif hasattr(plot, "update"):
            plot.update()

    def __init__(
        self,
        fit: cs.core.fitting.fit.FitGroup,
        control_layout: QtWidgets.QLayout,
        fit_widget: object = None,
        *args,
        **kwargs,
    ):
        # Initialize with fit name as title
        title = getattr(fit, "name", "Fit Window")
        super().__init__(title=title, *args, **kwargs)

        self.fit = fit
        self.fit_widget = fit_widget

        # Use the content_layout from CustomMdiSubWindow instead of creating new widget
        # Set the focus policy of the subwindow
        self.setFocusPolicy(QtCore.Qt.ClickFocus)
        self.content_widget.setFocusPolicy(QtCore.Qt.ClickFocus)

        # Use the existing content_layout from CustomMdiSubWindow
        layout = self.content_layout
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # The whole content is one emtk surface (plots, data table, report and
        # the Code face); only the title bar around it is Qt.
        self.plot_tab_widget = FitPlotsArea(self)
        self.flip_to_code_btn = QtWidgets.QToolButton()
        self.flip_to_code_btn.setText("Code")
        self.flip_to_code_btn.setFixedSize(50, 20)
        self.flip_to_code_btn.clicked.connect(self.toggle_code_view)
        self.flip_to_code_btn.setAutoRaise(True)
        self.flip_to_code_btn.setCheckable(True)
        self.flip_to_code_btn.setToolTip("Turn the window over: the model's source and view.json.")
        # Transparent when checked too: the default checked look is a dark
        # sunken box that hid the "Plots" label against the title bar.
        self.flip_to_code_btn.setStyleSheet(
            "QToolButton, QToolButton:checked { background: transparent; border: none;"
            " color: palette(text); font-weight: bold; }"
        )

        # Add Code button directly to CustomTitleBar to save maximum vertical space
        if hasattr(self, "title_bar") and self.title_bar.layout():
            layout = self.title_bar.layout()
            # Insert before minimize, maximize, close
            idx = layout.indexOf(self.title_bar.minimize_btn)
            layout.insertWidget(idx, self.flip_to_code_btn)

        self.content_layout.addWidget(self.plot_tab_widget)
        self.code_face = None

        rect = self.plot_tab_widget.geometry()
        self.setGeometry(rect)

        #: The page whose tab is current; its settings are what the main
        #: window's *Plot settings* dock shows (one emtk surface for all pages).
        self.current_page = None
        self._control_layout = control_layout

        # Lazy plot instantiation: create lightweight tab containers now, build plots on demand
        from chisurf.gui.widgets.models.model_editor import model_plot_specs

        self._plot_specs = model_plot_specs(fit.model)
        self._plots_all = [None] * len(self._plot_specs)  # positional storage
        self._created_plots: list[QtWidgets.QWidget] = []  # actual created plots (shared)
        #: Each page's tab name, in spec order (the persistent layout keys use it).
        self._plot_names: list[str] = []
        for idx, (plot_class, kwargs) in enumerate(self._plot_specs):
            tab_name = getattr(plot_class, "name", None)
            if not isinstance(tab_name, str):
                tab_name = getattr(plot_class, "__name__", str(plot_class))
            self._plot_names.append(tab_name)
            self.plot_tab_widget.add_page(
                tab_name, lambda i=idx: self.ensure_plot_created(i), key=self._plot_key(idx)
            )
        # Share created plot list with FitGroup and its member Fits
        fit.plots = self._created_plots
        for f in presentation_fit_members(fit):
            f.plots = self._created_plots

        # Instantiate the initially visible plot after the event loop returns
        # to avoid re-entrancy issues during fit creation; this may introduce
        # a tiny visual delay but is safer.
        def _ensure_initial_plot():
            idx = self.plot_tab_widget.currentIndex()
            self.ensure_plot_created(idx)
            self._restore_pending_project_plot_state()
            self.on_change_plot()

        self._defer(_ensure_initial_plot)

        self.plot_tab_widget.currentChanged.connect(self.on_change_plot)

        # Use RubberBandResize / RubberBandMove
        self.setOption(
            cs.gui.QtWidgets.QMdiSubWindow.RubberBandResize,
            cs.core.settings.gui["RubberBandResize"],
        )
        self.setOption(
            cs.gui.QtWidgets.QMdiSubWindow.RubberBandMove, cs.core.settings.gui["RubberBandMove"]
        )

        # Set windows icon
        try:
            icon = fit.model.icon
        except AttributeError:
            icon = cs.gui.QtGui.QIcon(":/icons/icons/list-add.png")
        self.setWindowIcon(icon)

        # Set global style sheet
        # window_style = cs.core.settings.gui['fit_window_style']
        # self.setStyleSheet(cs.core.settings.style_sheet)

        self.setAttribute(cs.gui.QtCore.Qt.WA_DeleteOnClose, True)

        # Resize window
        xs, ys = cs.core.settings.gui["fit_windows_size"]
        self.resize(xs, ys)

        self.plot_tab_widget.layoutChanged.connect(self.save_fit_dock_layout_state)
        self.restore_fit_dock_layout_state()

    def get_project_plot_state(self) -> dict:
        """Return project-serializable plot layout and controller state.

        Returns
        -------
        dict
            Fit-window plot state suitable for embedding in ``project.json``.
        """
        plots: list[dict] = []
        for idx, plot in enumerate(getattr(self, "_plots_all", []) or []):
            if plot is None:
                continue
            controller_state = plot.get_settings_state()
            plot_state = {}
            get_plot_state = getattr(plot, "get_state", None)
            if callable(get_plot_state):
                plot_state = get_plot_state()
            rec: dict[str, object] = {
                "index": idx,
                "name": self._plot_names[idx],
            }
            if controller_state:
                rec["controller"] = controller_state
            if plot_state:
                rec["plot"] = plot_state
            plots.append(rec)

        state: dict[str, object] = {
            "version": 1,
            "current_plot_index": int(self.plot_tab_widget.currentIndex()),
            "plots": plots,
        }
        try:
            state["dock_layout"] = self.get_fit_dock_layout_state()
        except Exception:
            pass
        try:
            geom = self.geometry()
            state["geometry"] = [geom.x(), geom.y(), geom.width(), geom.height()]
        except Exception:
            pass
        try:
            state["stack_index"] = 1 if self.plot_tab_widget.code_shown() else 0
        except Exception:
            pass
        return state

    def _restore_pending_project_plot_state(self) -> None:
        """Apply plot state attached to the fit during project loading."""
        state = getattr(self.fit, "_project_plot_state", None)
        if not isinstance(state, dict) or not state:
            return
        try:
            delattr(self.fit, "_project_plot_state")
        except Exception:
            pass
        self.set_project_plot_state(state)

    def set_project_plot_state(self, state: dict) -> bool:
        """Restore project-serialized plot layout and controller state.

        Parameters
        ----------
        state : dict
            State generated by :meth:`get_project_plot_state`.

        Returns
        -------
        bool
            True when at least one state fragment was applied.
        """
        if not isinstance(state, dict):
            return False
        applied = False
        if "plots" in state:
            plot_records = state.get("plots")
            if not isinstance(plot_records, list):
                raise ValueError("saved plots must be a list")
            seen = set()
            for rec in plot_records:
                if not isinstance(rec, dict):
                    raise ValueError("invalid saved plot record")
                idx = rec.get("index")
                if type(idx) is not int or not 0 <= idx < len(self._plot_specs) or idx in seen:
                    raise ValueError(f"invalid saved plot index: {idx}")
                if rec.get("name") != self._plot_names[idx]:
                    raise ValueError(f"saved plot name differs at index {idx}")
                seen.add(idx)
            for rec in plot_records:
                idx = rec["index"]
                plot = self.ensure_plot_created(idx)
                plot_state = rec.get("plot")
                set_plot_state = getattr(plot, "set_state", None)
                if isinstance(plot_state, dict) and callable(set_plot_state):
                    set_plot_state(plot_state)
                    applied = True
                controller_state = rec.get("controller")
                if isinstance(controller_state, dict):
                    plot.set_settings_state(controller_state)
                    applied = True

        dock_state = state.get("dock_layout")
        if isinstance(dock_state, dict):
            try:
                restored = self.plot_tab_widget.set_layout_state(dock_state, emit_change=False)
                applied = bool(restored) or applied
            except Exception:
                pass

        geom = state.get("geometry")
        if isinstance(geom, list) and len(geom) == 4:
            try:
                self.setGeometry(*(int(v) for v in geom))
                applied = True
            except Exception:
                pass

        stack_index = state.get("stack_index")
        if stack_index in (0, 1):
            if stack_index == 1:
                self.show_code_view()
            else:
                self.show_plot_view()
            applied = True

        current_index = state.get("current_plot_index")
        if isinstance(current_index, int):
            try:
                if 0 <= current_index < self.plot_tab_widget.count():
                    self.plot_tab_widget.setCurrentIndex(current_index)
                    applied = True
            except Exception:
                pass
        return applied

    def _fit_model_class_key(self) -> str:
        """Return the persistent layout key for this fit's model class.

        Returns
        -------
        str
            Fully qualified model class name.
        """
        model = getattr(self.fit, "model", None)
        model_cls = model.__class__ if model is not None else self.fit.__class__
        return f"{model_cls.__module__}.{model_cls.__name__}"

    def _plot_key(self, idx: int) -> str:
        """Return the persistent layout key of the page at *idx*.

        Parameters
        ----------
        idx : int
            Page index in spec order.

        Returns
        -------
        str
            Stable plot key, ``"<index>:<tab name>"``.
        """
        return f"{int(idx)}:{self._plot_names[idx]}"

    def _fit_dock_layout_settings(self) -> QtCore.QSettings:
        """Return QSettings for fit-window dock layouts in the user folder.

        Returns
        -------
        QSettings
            Settings object backed by ``~/.chisurf/fit_window_dock_layouts.ini``.
        """
        settings_path = cs.core.settings.get_path("settings") / "fit_window_dock_layouts.ini"
        return QtCore.QSettings(str(settings_path), QtCore.QSettings.IniFormat)

    def get_fit_dock_layout_state(self) -> dict:
        """Return the current dock layout state for this fit's model class.

        Returns
        -------
        dict
            Serialized dock layout.
        """
        return self.plot_tab_widget.get_layout_state()

    def save_fit_dock_layout_state(self) -> None:
        """Persist the current dock layout for this fit's model class."""
        try:
            if self.plot_tab_widget.count() <= 0:
                return
            state = self.get_fit_dock_layout_state()
            settings = self._fit_dock_layout_settings()
            settings.setValue(self._fit_model_class_key(), json.dumps(state, sort_keys=True))
            settings.sync()
        except Exception as exc:
            try:
                cs.logging.warning(f"Failed to save fit dock layout: {exc}")
            except Exception:
                pass

    def restore_fit_dock_layout_state(self) -> None:
        """Restore the saved dock layout for this fit's model class.

        A layout saved for another set of pages (a plot added since, or the
        Qt dock area's format) is ignored by the area: the default tab order
        is used and the next rearrangement saves the new one.
        """
        try:
            settings = self._fit_dock_layout_settings()
            value = settings.value(self._fit_model_class_key())
            if isinstance(value, str):
                state = json.loads(value)
            elif isinstance(value, dict):
                state = value
            else:
                return
            self.plot_tab_widget.set_layout_state(state, emit_change=False)
        except Exception as exc:
            try:
                cs.logging.warning(f"Failed to restore fit dock layout: {exc}")
            except Exception:
                pass

    def ensure_plot_created(self, idx: int):
        # Create plot for given index if not yet created
        if idx < 0 or idx >= len(self._plot_specs):
            return None
        if self._plots_all[idx] is not None:
            return self._plots_all[idx]
        plot_class, kwargs = self._plot_specs[idx]
        plot = plot_class(self.fit, **kwargs)
        # Track in storage lists
        self._plots_all[idx] = plot
        self._created_plots.append(plot)
        # A page first shown in another region than the current one is never
        # "changed to", so it fills itself here.
        self._defer(lambda p=plot: self._update_plot(p))

        # Connect LinePlot region changes to the Fit widget's range selector
        try:
            region_changed = getattr(plot, "regionChanged", None)
            if (
                region_changed is not None
                and hasattr(region_changed, "connect")
                and self.fit_widget is not None
            ):

                def _sync_fit_widget_range(xmin: int, xmax: int, fw=self.fit_widget):
                    # Update only the UI of the fit widget to reflect the plot's region
                    # The underlying fit_range is already updated inside the plot via cs.run
                    try:
                        fw.blockSignals(True)
                        fw.xmin = xmin
                        fw.xmax = xmax
                    finally:
                        fw.blockSignals(False)

                region_changed.connect(_sync_fit_widget_range)
        except Exception:
            pass

        return plot

    def _defer(self, callback) -> None:
        """Run ``callback`` on the next event-loop turn, unless this window is gone.

        ``QTimer.singleShot(0, callback)`` fires even after the window closed:
        a project reload closes the fit windows and the queued plot updates then
        read controller widgets Qt had already deleted. A timer owned by the
        window is deleted with it, and its call with it.
        """
        timer = QtCore.QTimer(self)
        timer.setSingleShot(True)
        timer.timeout.connect(callback)
        timer.timeout.connect(timer.deleteLater)
        timer.start(0)

    def on_change_plot(self):
        idx = self.plot_tab_widget.currentIndex()
        # Ensure the selected tab's plot exists
        plot = self.ensure_plot_created(idx)
        self.current_page = plot
        if plot is None:
            return
        host = self.plot_settings
        if host is not None and (host.owner is self or host.owner_gone()
                                 or self.isActiveWindow()):
            self.show_plot_settings()
        # Ensure the newly visible plot refreshes its content; we defer the
        # heavy update to the next event-loop turn to avoid deep re-entrancy
        # during fit creation.
        try:
            update_all = getattr(plot, "update_all", None)
            if callable(update_all):
                self._defer(update_all)
            elif hasattr(plot, "update"):
                self._defer(plot.update)
        except Exception:
            try:
                plot.update()
            except Exception:
                pass

    def updateStatusBar(self, msg: str):
        """Report code status through the host main window, or the logger."""
        status_bar = getattr(cs.cs, "statusBar", None)
        if callable(status_bar):
            status_bar().showMessage(msg)
        else:
            cs.logging.info(msg)

    @property
    def plot_settings(self):
        """The main window's *Plot settings* host, or ``None`` without a main window."""
        if self._control_layout is None:
            return None
        from chisurf.gui.plots.emtk_settings import host_in

        return host_in(self._control_layout)

    @property
    def current_plot_controller(self):
        """What the options dock shows for this window: the settings host."""
        return self.plot_settings

    def _settings_shows_me(self) -> bool:
        """Whether the settings dock shows one of this window's pages."""
        host = self.plot_settings
        return host is not None and host.owner is self

    def show_plot_settings(self) -> None:
        """Show the current page's settings in the *Plot settings* dock."""
        host = self.plot_settings
        if host is not None:
            host.show_page(self.current_page, owner=self)
            host.show()

    def closeEvent(self, event: QtCore.QEvent):
        self.save_fit_dock_layout_state()
        # Honour a per-window opt-out flag (used by macros/app shutdown) as
        # well as the global confirm_close_fit setting.
        if getattr(self, "close_confirm", True) and cs.core.settings.gui["confirm_close_fit"]:
            reply = dialogs.question(
                self,
                "Message",
                f"Are you sure to close this fit?:\n{self.fit.name}",
                buttons=QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                default=QtWidgets.QMessageBox.No,
            )
            if reply == QtWidgets.QMessageBox.Yes:
                try:
                    fit_idx = getattr(self.fit, "fit_idx", 0)
                    cs.core.actions.dispatch(name="fit.close", payload={"idx": fit_idx})
                except Exception:
                    pass
                cs.gui.widgets.hide_items_in_layout(cs.cs.modelLayout)
                header_layout = getattr(cs.cs, "analysisHeaderLayout", None)
                if header_layout is not None:
                    cs.gui.widgets.hide_items_in_layout(header_layout)
                cs.gui.widgets.hide_items_in_layout(cs.cs.plotOptionsLayout)
            else:
                event.ignore()
        else:
            event.accept()
        if event.isAccepted() and self._settings_shows_me():
            self.plot_settings.show_page(None)

    def ensure_code_created(self):
        """Build the Code face once, when it is first shown."""
        if self.code_face is not None:
            return self.code_face
        from chisurf.gui.widgets.fitting.fit_code_face import FitCodeFace

        self.code_face = FitCodeFace(on_apply=self.save_model_code)
        self.plot_tab_widget.set_code_face(self.code_face)
        return self.code_face

    def toggle_code_view(self):
        """Turn the window over: plots to code, code to plots."""
        if self.plot_tab_widget.code_shown():
            self.show_plot_view()
        else:
            self.show_code_view()

    def show_plot_view(self):
        """Show the plots."""
        self.plot_tab_widget.show_code(False)
        self.flip_to_code_btn.setText("Code")
        self.flip_to_code_btn.setChecked(False)

    def _model_view_spec_path(self):
        """Return the model's user-editable ``view.json`` path, or ``None``.

        Resolves the model's ``view_spec_file`` next to the module that
        defines the model class, so the code view can open it alongside the
        model source.
        """
        try:
            from chisurf.gui.devtools.source_jump import resolve_model_view_spec_path

            target = resolve_model_view_spec_path(self.fit.model)
            return target[0] if target else None
        except Exception:
            return None

    def show_code_view(self):
        """Show the model's source and view.json on the Code face."""
        face = self.ensure_code_created()
        import inspect

        from chisurf.gui.devtools.source_jump import resolve_compute_model_class

        # Resolve the underlying *compute* model class so "Code" opens the pure
        # model source (e.g. core/models/tcspc/lifetime.py) and its co-located
        # view.json — not the GUI widget wrapper that multiply-inherits it.
        model_class = resolve_compute_model_class(self.fit.model) or self.fit.model.__class__
        try:
            source_file = inspect.getsourcefile(model_class)
            if not source_file:
                return
            models_dir = pathlib.Path(source_file).parent
            face.set_files(
                [str(p) for p in sorted(models_dir.glob("*.py"))]
                + [str(p) for p in sorted(models_dir.glob("*.view.json"))]
            )
            # The model's own view.json opens first, as a background tab, then
            # the source, so "Code" shows the computation in front and its
            # editor layout beside it.
            view_json = self._model_view_spec_path()
            if view_json is not None and face.find_document(str(view_json)) < 0:
                try:
                    face.open_file(str(view_json), record=False)
                except Exception as exc:
                    cs.logging.debug(f"Failed to open model view.json: {exc}")
            self.load_code_file(source_file)
            self.original_source_file = source_file
            self.plot_tab_widget.show_code(True)
            self.flip_to_code_btn.setText("Plots")
            self.flip_to_code_btn.setChecked(True)
        except Exception as e:
            dialogs.warning(self, "Error", f"Failed to load model source: {e}")

    def load_code_file(self, file_path, line_number: int = 0):
        """Open *file_path* on the Code face at *line_number* (0-based)."""
        self.ensure_code_created().open_file(str(file_path), int(line_number))

    def save_model_code(self, source_file: str, code: str) -> str:
        """Write *code* to *source_file* and apply it to the open fit.

        A read-only installation gets a timestamped copy in the settings
        folder instead. When the file is the model's source (or a copy of
        it), its module is re-executed and the fit recomputed.

        Returns
        -------
        str
            What happened, for the Code face's status line.
        """
        source_file = str(source_file)
        import inspect

        from chisurf.core.settings.path_utils import get_path
        from chisurf.gui.devtools.source_jump import resolve_compute_model_class

        # Resolve against the *compute* model class so an edit to the pure
        # model source (what "Code" opens) is recognised even when the live
        # instance is a legacy widget that multiply-inherits it.
        instance_class = self.fit.model.__class__
        model_class = resolve_compute_model_class(self.fit.model) or instance_class
        is_model_source = source_file.endswith(".py") and source_file == inspect.getsourcefile(
            model_class
        )

        target_file = source_file
        if not os.access(source_file, os.W_OK):
            import datetime

            models_dir = get_path("settings") / "models"
            models_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            if is_model_source:
                # The name inject_user_models() looks for, so the edit is
                # applied again at the next start.
                name = f"{model_class.__module__}__override__{timestamp}.py"
            else:
                path = pathlib.Path(source_file)
                name = f"{path.stem}_{timestamp}{path.suffix}"
            target_file = str(models_dir / name)

        with open(target_file, "w") as f:
            f.write(code)
        self.updateStatusBar(f"Saved to {target_file}")
        if not is_model_source:
            return f"Saved {target_file}"

        import sys

        module = sys.modules.get(model_class.__module__)
        if module is None:
            return f"Saved {target_file}"
        exec(code, module.__dict__)
        new_class = getattr(module, model_class.__name__, None)
        if new_class:
            # Only swap the instance class when the live object *is* the pure
            # compute model. Replacing a legacy widget's class with the pure
            # model would strip its Qt behaviour; there the redefined module
            # is enough for fresh fits.
            if instance_class is model_class:
                self.fit.model.__class__ = new_class
            fc = get_fitting_client()
            if fc is not None:
                fc.update_fit(fit_index=getattr(self.fit, "fit_idx", None))
        self.updateStatusBar("Model code applied successfully.")
        return f"Saved {target_file}; model code applied."
