"""The Spectra tool: staging overview, component browser, scraper runner and MMFDB import, drawn by emtk.

Four panels as in the Qt tool (Overview, Browse, Download, Add to MMFDB) behind a navigation list. Every form is a
spec drawn by ``emtk.view_form`` with this app (or a small model) as the model: the Overview fields and the endpoint
form are the Qt tool's own ``overview.view.json`` / ``endpoint_auth.view.json``, the component detail is the
mmfdb-admin ``fluorophore.view.json``, and the rest is ``spectra_emtk.view.json``. Tables are ``data_table`` sections.
The scrapers run as the Qt tool ran them (a subprocess streamed into the log), an import into the MMFDB is asked for
and logged; nothing here touches the network except what the user starts.
"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from emtk import i18n, im, implot
from emtk.app import ImApp
from emtk.view_form import FormState, draw_form

from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow, TourTarget
from chisurf.plugins.emtk_layout import LabelColumn, button_row, labelled, layout_spec

from .native import SpectraState
from .translations import LOCALES, TOOLTIPS, install, tr

HERE = Path(__file__).parent
PANELS = ("Overview", "Browse", "Download", "Add to MMFDB")
_TEXT_KEYS = ("title", "label", "description", "tooltip", "hint", "placeholder")
SPECTRUM_COLOURS = {"emission": (200, 0, 0, 255), "absorption": (0, 100, 200, 255), "transmission": (0, 150, 0, 255)}
ERROR_COLOUR = (235, 100, 90, 255)
HEADER = 0.0


def _optical_view():
    """The mmfdb-admin component detail spec (found by path: importing its package would import Qt)."""
    return Path(__file__).resolve().parents[2] / "core" / "mmfdb_admin" / "gui" / "optical_components" / "fluorophore.view.json"


def translated(node):
    """A copy of a spec with the texts a user reads put through ``tr``."""
    if isinstance(node, dict):
        out = {}
        for key, value in node.items():
            if key in _TEXT_KEYS and isinstance(value, str):
                out[key] = tr(value) if value else value
            elif key == "labels" and isinstance(value, list):
                out[key] = [tr(v) for v in value]
            else:
                out[key] = translated(value)
        return out
    if isinstance(node, list):
        return [translated(item) for item in node]
    return node


class Fields:
    """A read-only attribute bag for a form (the Overview counts, the component detail)."""

    def __init__(self, **values):
        self.__dict__.update(values)

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        return ""


class SpectraApp(TourTarget, ImApp):
    def __init__(self, db=None):
        self.owns_db = db is None
        if db is None:
            from .. import get_db

            db = get_db()
            db.connect()
        install()
        self.model = SpectraState(db)
        self.panel = "Overview"
        self.status = "Ready"
        self.message, self.message_is_error = "", False
        self.dialog = None
        self.session = None
        self.item_rects = {}
        self.navigation_search = ""
        self.detail_tab = "Properties"
        self.current = None
        self.forms = {key: FormState(on_used=self.used) for key in ("overview", "browse", "detail", "download", "mmfdb", "mmfdb_top")}
        for key in ("properties", "metadata"):
            self.forms[key] = FormState(on_used=self.used)
        self.forms["endpoint"] = FormState(on_used=self.used)
        self.sources_json = json.loads((HERE / "spectra_emtk.view.json").read_text(encoding="utf-8"))
        self.specs, self.spec_locale = {}, None
        self.help = EmTkHelpWindow(title="Spectra", resource=HERE / "help.md", on_start_guide=self.start_guide)
        self.tour = EmTkGuidedTour(
            steps=HERE / "guide.json",
            get_target_rect=self._target_rect,
            owner=self,
            wait_for_controls=True,
        )
        self.labels = None
        self.overview = Fields()
        self.refresh_overview()
        self.refresh_session()
        super().__init__(gui=self.render, continuous=False)

    # -- the specs ------------------------------------------------------------------------------------------------- #
    def build_specs(self):
        """Load, translate and lay out every panel's spec once per locale; one caption column per window."""
        src = self.sources_json
        overview_fields = json.loads((HERE / "overview.view.json").read_text(encoding="utf-8"))["sections"]
        endpoint = json.loads((HERE / "endpoint_auth.view.json").read_text(encoding="utf-8"))
        for section in endpoint["sections"]:
            self._spin_ports(section)
        detail = json.loads(_optical_view().read_text(encoding="utf-8"))
        specs = {
            "overview": {"sections": [{"type": "panel", "title": "Staging database overview", "n_col": 2,
                                       "sections": overview_fields}] + src["overview"]["sections"]},
            "browse": src["browse"],
            "detail": {"sections": [{"type": "panel", "title": "", "n_col": 2, "sections": detail["sections"]}]},
            "properties": src["properties"],
            "metadata": src["metadata"],
            "download": src["download"],
            "mmfdb_top": src["mmfdb_top"],
            "mmfdb": src["mmfdb"],
            "endpoint": {"sections": endpoint["sections"]},
        }
        out = {}
        for key, spec in specs.items():
            out[key] = layout_spec(translated(deepcopy(spec)))
        labels = LabelColumn()
        labels.measure([f["label"] for key in ("endpoint", "download", "browse") for f in labelled(out[key]["sections"])])
        for key in ("endpoint", "download", "browse"):
            labels.pad(out[key]["sections"])
        return out

    @staticmethod
    def _spin_ports(section):
        if section.get("type") == "value" and section.get("kind") == "int" and not section.get("read_only"):
            section["style"] = "spin"
        for child in section.get("sections", []):
            SpectraApp._spin_ports(child)

    # -- form models --------------------------------------------------------------------------------------------------- #
    def used(self, name):
        self.tour.notify_used(name)

    @property
    def search(self):
        return self.model.search

    @search.setter
    def search(self, value):
        self.model.search = str(value)

    def source_options(self):
        return ["All"] + self.model.sources

    def category_options(self):
        return ["All"] + self.model.categories

    @property
    def source_filter(self):
        return self.model.source or "All"

    @source_filter.setter
    def source_filter(self, value):
        self.model.source = "" if value == "All" else value

    @property
    def category_filter(self):
        return self.model.category or "All"

    @category_filter.setter
    def category_filter(self, value):
        self.model.category = "" if value == "All" else value

    def scraper_labels(self):
        from ..download._base import SCRAPERS

        return [s.label for s in sorted(SCRAPERS, key=lambda s: s.label)]

    @property
    def scraper_label(self):
        from ..download._base import get_scraper

        spec = get_scraper(self.model.module)
        return spec.label if spec else ""

    @scraper_label.setter
    def scraper_label(self, value):
        from ..download._base import SCRAPERS

        spec = next((s for s in SCRAPERS if s.label == value), None)
        if spec is not None:
            self.model.module = spec.module

    @property
    def log(self):
        return self.model.log

    @property
    def mmfdb_log(self):
        return self.model.mmfdb_log

    @property
    def metadata_json(self):
        d = self.model.detail
        if not d or self.current is None:
            return ""
        return json.dumps(
            {
                "probe": d["probe"],
                "optical_properties": {p["property_name"]: p["property_value"] for p in d["optical_properties"]},
                "spectra": [{"type": s["spectrum_type"], "points": len(s["wavelengths"])} for s in d["spectra"]],
            },
            indent=2,
            default=str,
        )

    def enabled(self, name):
        m = self.model
        if name == "run_script":
            return m.process is None
        if name in ("push_selected",):
            return True
        if name == "add_all":
            return not self.busy
        return True

    @property
    def busy(self):
        return False

    def bounds(self, name):
        return (1, 65535) if name in ("cmd_port", "pub_port") else (None, None)

    # -- data for the tables -------------------------------------------------------------------------------------------- #
    def category_rows(self):
        return [{"name": k or "(none)", "count": v} for k, v in sorted(self.overview_data["by_category"].items())]

    def source_rows(self):
        return [{"name": k or "(none)", "count": v} for k, v in self.overview_data["by_source"].items()]

    def component_rows(self):
        m = self.model
        return [
            {
                "pick": r["probe_id"] in m.selected,
                "probe_id": r["probe_id"],
                "name": str(r.get("chromophore_name") or ""),
                "category": str(r.get("category") or ""),
                "source": str(r.get("source") or ""),
                "status": str(r.get("verification_status") or ""),
            }
            for r in m.filtered()
        ]

    def property_rows(self):
        d = self.model.detail
        return [{"property": p["property_name"], "value": str(p["property_value"])} for p in (d["optical_properties"] if d else [])]

    def select_row(self, record):
        if isinstance(record, dict) and record.get("probe_id") is not None:
            self.current = int(record["probe_id"])
            self.model.show(self.current)
        self.used("select_row")

    def pick_row(self, record, key, value):
        if key == "pick" and isinstance(record, dict):
            self.model.pick(int(record["probe_id"]), bool(value))
            self.used("pick_row")

    # -- actions ---------------------------------------------------------------------------------------------------------- #
    def notice(self, text, error=False):
        self.message, self.message_is_error = text, error

    def refresh_overview(self):
        self.model.refresh()
        self.overview_data = self.model.overview()
        self.overview = Fields(**{k: str(v) for k, v in self.overview_data.items() if not isinstance(v, dict)})

    def refresh_browse(self):
        self.model.refresh()
        self.notice(tr("Ready"))

    def refresh_session(self):
        self.session = self.model.session_text()

    def check_session(self):
        self.refresh_session()

    def run_script(self):
        try:
            if self.model.run_script():
                self.notice("")
        except Exception as exc:  # noqa: BLE001
            self.notice(str(exc), True)

    def browse_source(self):
        self.model.refresh()
        self.model.source = self.model.source_slug()
        self.panel = "Browse"

    def push_selected(self):
        if not self.model.selected:
            self.ask("Push selected", tr("No components selected."), [("OK", None)])
            return
        self.ask("Push to MMFDB", tr("Push {} selected component(s) from this staging database into the connected MMFDB?").format(len(self.model.selected)),
                 [("Yes", lambda: self.do_push(True)), ("No", None)])

    def push_all(self):
        self.ask("Push to MMFDB", tr("Push all {} component(s) from this staging database into the connected MMFDB?").format(len(self.model.rows)),
                 [("Yes", lambda: self.do_push(False)), ("No", None)])

    def do_push(self, selected):
        try:
            summary = self.model.push(selected=selected)
        except Exception as exc:  # noqa: BLE001
            self.ask("Push failed", str(exc), [("OK", None)])
            return
        summary = summary if isinstance(summary, dict) else {}
        self.ask("Push complete", tr("Pushed {} component(s) into the MMFDB.").format(summary.get("merged", 0))
                 + "\n" + tr("Consolidated: {}").format(summary.get("consolidated")), [("OK", None)])

    def add_all(self):
        self.model.add_all_logged()

    def ask(self, title, text, buttons):
        self.dialog = {"title": title, "text": text, "buttons": buttons}

    def answer(self, callback):
        self.dialog = None
        if callback is not None:
            callback()

    # -- the window ---------------------------------------------------------------------------------------------------------- #
    def _target_rect(self, key):
        if key in self.item_rects:
            return self.item_rects[key]
        panel = next((p for p in PANELS if key and key.casefold() in p.casefold()), None)
        return self.item_rects.get("nav." + panel) if panel else None

    def start_guide(self):
        self.tour.start()

    def show_help(self):
        self.help.show()

    def step(self, delta):
        index = PANELS.index(self.panel) + delta
        if 0 <= index < len(PANELS):
            self.select_panel(PANELS[index])

    def select_panel(self, panel):
        self.panel = panel
        self.status = "Ready"
        self.tour.notify_used(panel)

    def draw_navigation(self, width):
        _, self.navigation_search = im.input_text("##navigation_search", self.navigation_search, hint=tr("Filter"))
        im.set_item_tooltip(tr(TOOLTIPS.get("Filter", "Filter")))
        self.item_rects["search"] = im.get_item_rect()
        im.spacing()
        for panel in PANELS:
            if self.navigation_search.lower() not in tr(panel).lower():
                continue
            if im.selectable(tr(panel) + "##nav." + panel, self.panel == panel, size=(width - 8, 24)):
                self.select_panel(panel)
            im.set_item_tooltip(tr(TOOLTIPS.get(panel, panel)))
            self.item_rects["nav." + panel] = im.get_item_rect()
        im.separator()
        im.text(tr("Language"))
        locale = i18n.get_locale()
        changed, index = im.combo("##locale", LOCALES.index(locale) if locale in LOCALES else 0, list(LOCALES))
        im.set_item_tooltip(tr(TOOLTIPS.get("Language", "Language")))
        self.item_rects["language"] = im.get_item_rect()
        if changed:
            i18n.set_locale(LOCALES[index])
        pressed = button_row(
            [
                {"label": tr("Guide"), "key": "guide", "tip": tr(TOOLTIPS.get("Guide", "Guide"))},
                {"label": tr("Help"), "key": "help", "tip": tr(TOOLTIPS.get("Help", "Help"))},
            ],
            width - 8,
            remember=lambda name: self.item_rects.__setitem__(name, im.get_item_rect()),
        )
        if pressed == "guide":
            self.start_guide()
        elif pressed == "help":
            self.show_help()

    def draw_form(self, key, model=None):
        state = self.forms[key]
        state.rects.clear()
        state.custom.update({"count": self.draw_count, "scraped": self.draw_scraped, "session": self.draw_session})
        draw_form(self.specs[key], model if model is not None else self, state, titles=True)
        self.item_rects.update(state.rects)

    def draw_count(self, section, model, state, width):
        im.text_disabled(f"{len(self.model.filtered())} / {len(self.model.rows)}")

    def draw_scraped(self, section, model, state, width):
        counts = json.dumps(self.model.source_counts()) if self.model.source_counts() else tr("none yet")
        im.text_wrapped(f"{tr('Already scraped')} ({self.model.source_slug()}): {counts}")

    def draw_session(self, section, model, state, width):
        ok, text = self.session or (True, "")
        if not ok:
            im.push_style_color(im.Col.TEXT, ERROR_COLOUR)
        im.text_wrapped(tr(text) if text in TOOLTIPS else text)
        if not ok:
            im.pop_style_color(1)

    def draw_overview(self):
        self.draw_form("overview", self.overview_model())

    def overview_model(self):
        outer = self

        class Model:
            def __getattr__(self, name):
                if name in ("refresh_overview", "category_rows", "source_rows"):
                    return getattr(outer, name)
                return getattr(outer.overview, name)

            def enabled(self, name):
                return True

        return Model()

    def draw_browse(self, width, height):
        wide = width >= 900
        x, y = im.get_cursor_screen_pos()
        left = min(max(520.0, width * 0.52), width - 360.0) if wide else width
        im.begin_child((x, y, left, height if wide else max(260.0, height * 0.5)), child_id="spectra-list")
        self.draw_form("browse")
        im.end_child()
        if wide:
            im.begin_child((x + left + 8.0, y, width - left - 8.0, height), child_id="spectra-detail")
        self.draw_detail()
        if wide:
            im.end_child()

    def draw_detail(self):
        m = self.model
        if not m.detail:
            im.text_wrapped(tr("Select components to inspect their metadata and spectra."))
            return
        probe = m.detail["probe"]
        data = dict(probe)
        for p in m.detail["optical_properties"]:
            data.setdefault(p["property_name"], p["property_value"])
        fields = Fields(**{k: ("" if v is None else str(v)) for k, v in data.items()})
        self.draw_form("detail", fields)
        if im.begin_tab_bar("details"):
            for tab, key in (("Properties", "properties"), ("Metadata (JSON)", "metadata")):
                opened = im.begin_tab_item(tr(tab))
                im.set_item_tooltip(tr(TOOLTIPS.get(tab, tab)))
                self.item_rects["tab." + key] = im.get_item_rect()
                if opened:
                    x, y = im.get_cursor_screen_pos()
                    w = im.get_content_region_avail()[0]
                    im.begin_child((x, y, w, 160.0), child_id="spectra-tab-" + key)
                    self.draw_form(key)
                    im.end_child()
                    im.dummy(w, 160.0)
                    im.end_tab_item()
            im.end_tab_bar()
        origin, room = im.get_cursor_screen_pos(), im.get_content_region_avail()
        self.item_rects["plot"] = (origin[0], origin[1], room[0], max(room[1], 180.0))
        if implot.begin_plot("##spectra", (-1, max(room[1], 180.0))):
            implot.setup_axes(tr("Wavelength (nm)"), tr("Intensity"))
            for s in m.detail["spectra"]:
                implot.plot_line(
                    s["spectrum_type"], s["wavelengths"], s["intensity"],
                    spec=implot.PlotSpec(line_color=SPECTRUM_COLOURS.get(s["spectrum_type"], (0, 100, 200, 255)), line_weight=2),
                )
            implot.end_plot()

    def draw_content(self, width, height):
        self.model.poll()
        if self.panel == "Overview":
            self.draw_overview()
        elif self.panel == "Browse":
            self.draw_browse(width, height)
        elif self.panel == "Download":
            self.draw_form("download")
        else:
            im.heading(tr("Add staging components to the MMFDB"), level=4)
            self.draw_form("mmfdb_top")
            self.draw_form("endpoint", self.model.endpoint)
            self.draw_form("mmfdb")
        if self.message:
            im.separator()
            if self.message_is_error:
                im.push_style_color(im.Col.TEXT, ERROR_COLOUR)
            im.text_wrapped(self.message)
            if self.message_is_error:
                im.pop_style_color(1)

    def render(self):
        if self.specs == {} or self.spec_locale != i18n.get_locale():
            self.specs, self.spec_locale = self.build_specs(), i18n.get_locale()
        self.model.poll()
        if self.model.process is not None or self.tour.active:
            from emtk.im_core import get_current_context

            ctx = get_current_context()
            ctx.request_frame_at(ctx.io.now + 0.1)
        vp = im.get_main_viewport()
        width, height = float(vp.size[0]), float(vp.size[1])
        left, bar = min(200.0, max(150.0, width * 0.20)), 30.0
        im.set_next_window_pos((0.0, 0.0), im.Cond.ALWAYS)
        im.set_next_window_size((left, height), im.Cond.ALWAYS)
        if im.begin(tr("Spectra")):
            self.draw_navigation(left)
        im.end()
        im.set_next_window_pos((left + 4.0, 0.0), im.Cond.ALWAYS)
        im.set_next_window_size((width - left - 4.0, height - bar), im.Cond.ALWAYS)
        if im.begin(tr(self.panel) + "##content"):
            avail = im.get_content_region_avail()
            self.draw_content(avail[0], avail[1])
        im.end()
        im.set_next_window_pos((left + 4.0, height - bar), im.Cond.ALWAYS)
        im.set_next_window_size((width - left - 4.0, bar), im.Cond.ALWAYS)
        if im.begin("##spectra-status", flags=im.WindowFlags.NO_TITLE_BAR):
            index = PANELS.index(self.panel)
            im.text_unformatted(tr(self.status))
            im.same_line(max(120.0, width - left - 200.0))
            im.begin_disabled(index <= 0)
            if im.button(tr("Back")):
                self.step(-1)
            self.item_rects["back"] = im.get_item_rect()
            im.set_item_tooltip(tr("Go to the previous panel."))
            im.end_disabled()
            im.same_line()
            im.begin_disabled(index >= len(PANELS) - 1)
            if im.button(tr("Next")):
                self.step(1)
            self.item_rects["next"] = im.get_item_rect()
            im.set_item_tooltip(tr("Go to the next panel."))
            im.end_disabled()
        im.end()
        if self.dialog:
            d = self.dialog
            w = min(460.0, width - 60.0)
            im.set_next_window_pos(((width - w) / 2, max(40.0, height / 3.0)), im.Cond.ALWAYS)
            im.set_next_window_size((w, 150.0), im.Cond.ALWAYS)
            if im.begin(tr(d["title"]) + "##spectra-dialog"):
                im.text_wrapped(d["text"])
                im.spacing()
                for i, (label, callback) in enumerate(d["buttons"]):
                    if i:
                        im.same_line()
                    if im.button(tr(label)):
                        self.answer(callback)
                    im.set_item_tooltip(tr(label))
                    self.item_rects["dialog." + label] = im.get_item_rect()
            im.end()
        if self.tour.active:
            if self.tour.awaiting:
                self.tour.draw(width, height)  # the highlighted control must stay clickable
            else:
                # A window of its own over the others, so the card's buttons are hovered (a button answers only when no
                # other window is under the pointer).
                flags = (im.WindowFlags.NO_DECORATION | im.WindowFlags.NO_BACKGROUND | im.WindowFlags.NO_SAVED_SETTINGS
                         | im.WindowFlags.NO_MOVE | im.WindowFlags.NO_NAV)
                im.begin("##spectra_tour", (0.0, 0.0, width, height), flags)
                self.tour.draw(width, height)
                im.end()
        if self.help.open:
            self.help.draw((0.0, 0.0, width, height))
        self.io.mouse_wheel = self.io.mouse_wheel_h = 0.0

    # -- state ---------------------------------------------------------------------------------------------------------------- #
    def export_state(self):
        # Credentials deliberately remain session-only.
        return {
            "panel": self.panel,
            "search": self.model.search,
            "category": self.model.category,
            "source": self.model.source,
            "module": self.model.module,
            "selected": sorted(self.model.selected),
            "endpoint": {k: v for k, v in vars(self.model.endpoint).items() if k != "password"},
        }

    export_settings = export_state

    def restore_state(self, state):
        if state.get("panel") in PANELS:
            self.panel = state["panel"]
        for key in ("search", "category", "source"):
            setattr(self.model, key, str(state.get(key, "")))
        from ..download._base import get_scraper

        if get_scraper(state.get("module", "")):
            self.model.module = state["module"]
        for key, value in state.get("endpoint", {}).items():
            if hasattr(self.model.endpoint, key) and key != "password":
                setattr(self.model.endpoint, key, value)
        valid = {r["probe_id"] for r in self.model.rows}
        for pid in state.get("selected", []):
            if pid in valid:
                self.model.pick(pid)

    restore_settings = restore_state

    def close(self):
        self.model.close()
        if self.owns_db:
            self.model.db.close()


def create_app(db=None):
    return SpectraApp(db)
