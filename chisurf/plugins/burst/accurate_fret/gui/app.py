"""Complete native accurate-FRET calibration UI over the scientific view model."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Callable

import numpy as np
from emtk import im, implot
from emtk.app import ImApp
from emtk.docking import DockManager, Region, Split
from emtk.view_form import FormState, draw_sections
from emtk.widgets.view_spec import load_view_spec

from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow, TourTarget

from .controller import AccurateFretController
from .view_model import AccurateFretViewModel

WINDOW_BG = (30, 32, 38, 255)


def _colour(value):
    text = str(value).lstrip("#")
    return (
        tuple(int(text[index : index + 2], 16) for index in (0, 2, 4)) + (255,)
        if len(text) == 6
        else (190, 200, 220, 255)
    )


class AccurateFretGui(TourTarget):
    def __init__(
        self,
        model,
        on_calibrate=None,
        on_export=None,
        on_from_ndx=None,
        on_to_ndx=None,
        on_share=None,
        on_store_setup=None,
        on_guide=None,
        on_help=None,
    ):
        self.model = model
        self.controller = None
        self.on_calibrate, self.on_export = on_calibrate, on_export
        self.on_from_ndx, self.on_to_ndx = on_from_ndx, on_to_ndx
        self.on_share, self.on_store_setup = on_share, on_store_setup
        self.on_guide, self.on_help = on_guide, on_help
        self.item_rects = {}
        self.on_used = None
        self.form_state = FormState()
        specification = load_view_spec(str(Path(__file__).with_name("accurate_fret.view.json")))
        self.sections = copy.deepcopy(specification["sections"][0]["sections"][0]["sections"])
        for section in self.sections:
            if section.get("attr") == "filename":
                section.clear()
                section.update(type="custom", key="accurate_file")
            elif section.get("key") == "setup_selector":
                section["key"] = "accurate_setup"
            elif section.get("type") == "info":
                section["max_height"] = 100
        self.form_state.custom["accurate_file"] = self._file_section
        self.form_state.custom["accurate_setup"] = self._setup_section
        self.help_window = EmTkHelpWindow(
            title="Accurate FRET — Help & Reference",
            resource=Path(__file__).with_name("help.md"),
            owner=model,
            on_start_guide=self.start_guide,
            size=(700.0, 520.0),
        )
        self.tour = EmTkGuidedTour(
            steps=Path(__file__).with_name("guide.json"),
            get_target_rect=lambda key: self.item_rects.get(key),
            owner=model,
            wait_for_controls=True,
            on_step_change=lambda _index, step: self.reveal(self.tour._target_key(step.get("target"))),
        )
        self.on_used = self.tour.notify_used
        self.form_state.on_used = self.tour.notify_used
        #: Collapsed panels a guide step opens on the next frame.
        self._open_once: set[str] = set()
        self.docks = DockManager(
            Split(
                "h", 0.36, Region("settings"), Split("v", 0.42, Region("results"), Region("plots"))
            ),
            name="accurate_fret",
        )
        self.docks.add_window(
            "settings", "Calibration settings", self._render_controls_window, dock="settings"
        )
        self.docks.add_window("channels", "Detector setup", self._draw_channels, dock="settings")
        self.docks.add_window(
            "results",
            "Correction factors and populations",
            self._render_results_window,
            dock="results",
        )
        self.docks.add_window(
            "es",
            "E–S populations",
            lambda box: self._draw_plot(
                "E–S", "Accurate FRET efficiency", "Stoichiometry", self.model.es_series()
            ),
            dock="plots",
        )
        self.docks.add_window(
            "tau",
            "E–lifetime and FRET lines",
            lambda box: self._draw_plot(
                "E–lifetime",
                "Donor lifetime (ns)",
                "Accurate FRET efficiency",
                self.model.e_tau_series(),
            ),
            dock="plots",
        )
        self.docks.add_window(
            "hist",
            "Accurate-E histogram",
            lambda box: self._draw_plot(
                "Efficiency histogram",
                "Accurate FRET efficiency",
                "Bursts",
                self.model.efficiency_histogram(),
            ),
            dock="plots",
        )

    def reveal(self, name):
        """Bring what a guide step points at on screen: its panel, header or dock."""
        if not name:
            return
        for section in self.sections:
            if section.get("type") != "panel":
                continue
            title = str(section.get("title") or "Settings")
            attrs = {s.get("attr") for s in section.get("sections", [])}
            if name == title or name in attrs:
                self._open_once.add(title)
                self.docks.focus("settings")
        if name in ("Share in session", "From ndX", "To ndX"):
            self._open_once.add("Data, session and catalogue actions")
            self.docks.focus("settings")
        if name in ("Correction factors", "Populations", "Report"):
            self.docks.focus("results")
        if name in ("histogram", "E histogram"):
            self.docks.focus("hist")

    def _header(self, title, default_open=False):
        """A collapsing header a guide step can open; its rect is a tour target."""
        if title in self._open_once:
            self._open_once.discard(title)
            opened = im.collapsing_header(title, True)
        else:
            opened = im.collapsing_header(title, im.TreeNodeFlags.DEFAULT_OPEN if default_open else 0)
        self.remember(title)
        return opened

    def track(self, name):
        if callable(self.on_used):
            self.on_used(name)

    def start_guide(self):
        self.tour.start()

    def show_help(self):
        self.help_window.show()

    def _button(self, label, tooltip, callback, key=None):
        if im.button(label):
            if key:
                self.track(key)
            try:
                if callable(callback):
                    callback()
            except Exception as exc:
                if self.controller:
                    self.controller.status = f"Error: {exc}"
                else:
                    self.model.results_text = f"Error: {exc}"
        im.set_item_tooltip(tooltip)
        if key:
            self.remember(key)

    def _file_section(self, section, model, state, width):
        self._button(
            "Open burst table",
            "Choose CSV/TSV/TXT/BUR/NPZ burst data with consistent channel units.",
            lambda: self.controller.browse("load"),
            "filename",
        )
        self._button(
            "MMFDB burst datasets",
            "Resolve a burst table from the database.",
            self.controller.datasets.open,
        )
        im.text_wrapped(self.model.filename or "No burst table loaded.")

    def _setup_section(self, section, model, state, width):
        im.text_wrapped("Detector setup: " + (self.model.setup_name or "none selected"))
        self._button(
            "Select / configure detector setup",
            "Select, edit or save an instrument setup; its channel names and stored calibration seed this run.",
            lambda: self.docks.focus("channels"),
            "setup_selector",
        )

    def _render_controls_window(self, box=None):
        controller = self.controller
        im.begin_disabled(bool(controller and controller.running))
        self._button(
            "Calibrate",
            "Find burst classes and correction factors from all loaded bursts.",
            self.on_calibrate,
            "Calibrate",
        )
        if self.model.can_run():
            im.text_wrapped(self.model.can_run())
        expanded = self._header("Data, session and catalogue actions")
        im.set_item_tooltip(
            "Read or publish ndX data, export/store factors, or refresh optical catalogues."
        )
        if expanded:
            self._button(
                "From ndX",
                "Read the numeric burst columns from the newest registered native ndX source.",
                self.on_from_ndx,
            )
            self._button(
                "To ndX",
                "Apply calibrated factors to the registered ndX sources and refresh their derived columns.",
                self.on_to_ndx,
            )
            self._button(
                "Export per-burst CSV",
                "Export accurate E, S, lifetime and distance with the calibration header.",
                self.on_export,
            )
            self._button(
                "Share calibration in session",
                "Register linkable correction factors for other fits.",
                self.on_share,
                "Share in session",
            )
            self._button(
                "Store calibration on setup",
                "Save measured factors and uncertainties on the selected named detector setup.",
                self.on_store_setup,
            )
            self._button(
                "Refresh dye catalogue",
                "Read dye properties from the configured spectra database.",
                lambda: controller._start("dyes"),
            )
            self._button(
                "Refresh optical priors",
                "List saved light-path simulations that can supply calibration priors.",
                lambda: controller._start("lightpaths"),
            )
            im.text("Spectra database path:")
            changed, path = im.input_text("##accurate_db", self.model.database_path or "")
            im.set_item_tooltip(
                "Optional MMFDB database path for dyes and saved optical priors; empty uses the configured database."
            )
            if changed:
                self.model.database_path = path or None
        im.separator()
        for section in self.sections:
            if section.get("type") == "panel":
                title = str(section.get("title") or "Settings")
                opened = self._header(title, default_open=title == "Channels")
                im.set_item_tooltip(
                    section.get("description") or f"Configure {title.lower()} for this calibration."
                )
                if opened:
                    draw_sections(
                        section.get("sections", []),
                        self.model,
                        self.form_state,
                        n_col=1,
                        titles=False,
                    )
            elif section.get("type") != "info":
                draw_sections([section], self.model, self.form_state, n_col=1, titles=False)
        im.end_disabled()
        self._button(
            "Stop calibration / read",
            "Cancel at the next numerical checkpoint and keep the previous successful result.",
            controller.stop,
        )
        self._button(
            "Guide",
            "Start a step-by-step tour of accurate FRET calibration.",
            self.start_guide,
            "guide",
        )
        im.same_line()
        self._button(
            "Help", "Open the scientific reference and workflow help.", self.show_help, "help"
        )
        if controller.status:
            im.text_wrapped(controller.status)

    def _draw_channels(self, box):
        im.begin_disabled(self.controller.running)
        self.controller.channel_definition.draw()
        im.end_disabled()

    @staticmethod
    def _table(name, rows, columns):
        if not rows:
            return
        if im.begin_table(
            name,
            len(columns),
            im.TableFlags.BORDERS | im.TableFlags.ROW_BG | im.TableFlags.SCROLL_X,
        ):
            for key, label in columns:
                im.table_setup_column(label)
            im.table_headers_row()
            for row in rows:
                im.table_next_row()
                for key, label in columns:
                    im.table_next_column()
                    im.text(str(row.get(key, "")))
            im.end_table()

    def _render_results_window(self, box=None):
        if im.begin_tab_bar("accurate_result_tabs"):
            for label in ("Correction factors", "Populations", "Report"):
                opened = im.begin_tab_item(label)
                self.remember(label)
                im.set_item_tooltip(
                    "Inspect " + label.lower() + " from the actual calibration result."
                )
                if opened:
                    if label == "Correction factors":
                        self._table(
                            "accurate_factors",
                            self.model.factor_rows(),
                            [
                                ("factor", "Factor"),
                                ("value", "Value"),
                                ("uncertainty", "Uncertainty"),
                                ("origin", "Origin"),
                            ],
                        )
                    elif label == "Populations":
                        self._table(
                            "accurate_populations",
                            self.model.population_rows(),
                            [
                                ("population", "Population"),
                                ("n", "Bursts"),
                                ("E", "E"),
                                ("S", "S"),
                                ("tau_f", "Lifetime (ns)"),
                                ("distance", "Distance (Å)"),
                                ("off_line", "FRET-line offset"),
                            ],
                        )
                    else:
                        im.text_wrapped(self.model.results_text)
                    im.end_tab_item()
            im.end_tab_bar()
        if self.model.result is None:
            im.text_wrapped(self.model.results_text)

    def _draw_plot(self, title, xlabel, ylabel, series):
        key = "es_plot" if title == "E–S" else "lifetime_plot" if title == "E–lifetime" else "histogram"
        if implot.begin_plot(title, (-1, -1)):
            implot.setup_axes(xlabel, ylabel)
            # Top right is empty in all three plots; the default top-left legend
            # covered the donor-only cluster (E ≈ 0, S ≈ 1) of the E–S plot.
            implot.setup_legend(implot.LOCATION_NORTH_EAST)
            if title == "E–S":
                implot.setup_axes_limits(-0.1, 1.1, -0.1, 1.1)
            elif title == "E–lifetime":
                implot.setup_axes_limits(0.0, max(self.model.donor_lifetime * 1.1, 1.0), -0.1, 1.1)
            for entry in series:
                x, y = (
                    np.asarray(entry.get("x", []), dtype=float),
                    np.asarray(entry.get("y", []), dtype=float),
                )
                if len(x) != len(y) or not len(x):
                    continue
                colour = _colour(entry.get("color", "#cccccc"))
                if entry.get("no_line") or entry.get("symbol"):
                    implot.set_next_marker_style(
                        implot.MARKER_CIRCLE, float(entry.get("symbol_size", 3)), fill=colour
                    )
                    implot.plot_scatter(entry.get("name", "Bursts"), x, y)
                else:
                    implot.set_next_line_style(
                        colour,
                        float(entry.get("width", 2)),
                        dash=(6.0, 4.0) if entry.get("style") == "dash" else None,
                    )
                    implot.plot_line(entry.get("name", "FRET line"), x, y)
            implot.end_plot()
        self.remember(key)
        if key == "histogram":
            self.remember("E histogram")      # the guide's name for it
        im.set_item_tooltip(
            "Measured burst classes and calibrated FRET lines. Drag to pan; scroll to zoom."
            if series
            else "Load and calibrate bursts to show measured data."
        )

    def draw(self, w, h):
        self.docks.draw((0.0, 0.0, float(w), float(h)))
        self.item_rects.update(self.form_state.rects)
        if self.help_window.open:
            self.help_window.draw((0.0, 0.0, float(w), float(h)))
        if self.tour.active:
            self.tour.draw(float(w), float(h))


class AccurateFretApp(ImApp):
    def __init__(
        self,
        model=None,
        on_calibrate=None,
        on_export=None,
        on_from_ndx=None,
        on_to_ndx=None,
        on_share=None,
        on_store_setup=None,
        on_guide=None,
        on_help=None,
        ndx_source=None,
        setup_model=None,
        db_path=None,
    ):
        self.model = model or AccurateFretViewModel()
        self.controller = AccurateFretController(
            self.model, ndx_source=ndx_source, setup_model=setup_model, db_path=db_path
        )
        self.accurate_gui = AccurateFretGui(
            self.model,
            on_calibrate or self.controller.run,
            on_export or (lambda: self.controller.browse("export")),
            on_from_ndx or self.controller.from_ndx,
            on_to_ndx or self.controller.to_ndx,
            on_share or self.controller.register,
            on_store_setup or self.controller.store_setup,
            on_guide,
            on_help,
        )
        self.accurate_gui.controller = self.controller
        self.gui = self.accurate_gui
        super().__init__(gui=self._render, continuous=True)

    def start_guide(self):
        self.accurate_gui.start_guide()

    def show_help(self):
        self.accurate_gui.show_help()

    def _render(self):
        self.controller.poll()
        width, height = im.get_main_viewport().size
        self.accurate_gui.draw(width, height)
        self.controller.draw_dialogs((0.0, 0.0, float(width), float(height)))

    def on_paths_dropped(self, paths):
        self.controller.on_paths_dropped(paths)

    def export_settings(self):
        fields = (
            "column_i_dd",
            "column_i_da",
            "column_i_aa",
            "column_tau_f",
            "setup_name",
            "donor_dye",
            "acceptor_dye",
            "kappa2",
            "refractive_index",
            "donor_lifetime",
            "forster_radius",
            "linker_sigma",
            "background_dd",
            "background_da",
            "background_aa",
            "gamma_source",
            "use_priors",
            "lightpath_name",
            "quantum_yield_donor",
            "quantum_yield_acceptor",
            "detection_green",
            "detection_red",
            "max_fret_populations",
            "min_population",
            "n_bootstrap",
            "show_dynamic_line",
            "max_points",
            "database_path",
        )
        return {
            "parameters": {field: getattr(self.model, field) for field in fields},
            "channel_definition": self.controller.channel_definition.model.get_settings(),
        }

    def restore_settings(self, settings):
        parameters = settings.get("parameters") or {}
        for field, value in parameters.items():
            if field in self.export_settings()["parameters"]:
                setattr(self.model, field, value)
        if isinstance(settings.get("channel_definition"), dict):
            self.controller.channel_definition.model.data = copy.deepcopy(
                settings["channel_definition"]
            )
            self.controller.apply_setup(settings["channel_definition"])
            if not self.model.setup_name:
                self.model.setup_name = parameters.get("setup_name", "")
            self.controller.channel_definition.model.current_name = self.model.setup_name

    def close(self):
        self.controller.close()


def create_app(**kwargs):
    from chisurf.emtk.i18n import install

    install()
    return AccurateFretApp(**kwargs)
