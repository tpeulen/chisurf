"""Standalone EMTK staging overview, browser, scrapers and MMFDB import."""

from __future__ import annotations

import json
from pathlib import Path

from emtk import i18n, im, implot
from emtk.app import ImApp
from emtk.docking import DockManager, Region, Split
from emtk.im_core import Col, Style

from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow

from .native import SpectraState
from .translations import LOCALES, TOOLTIPS, install, tr

PANELS = ("Overview", "Browse", "Download", "Add to MMFDB")
SUMMARY = (
    ("Staging DB", "db_path"),
    ("Total components", "total"),
    ("With spectra", "with_spectra"),
    ("Fluorophores", "fluorophores"),
    ("Filters", "filters"),
    ("Dichroics", "dichroics"),
    ("Detectors", "detectors"),
    ("Light sources", "light_sources"),
)


class SpectraApp(ImApp):
    def __init__(self, db=None):
        self.owns_db = db is None
        if db is None:
            from .. import get_db

            db = get_db()
            db.connect()
        install()
        self.model = SpectraState(db)
        self.panel = "Overview"
        self.pending_push = None
        self.message = ""
        self.session = self.model.authorized()
        self.item_rects = {}
        self.navigation_search = ""
        self.tour = EmTkGuidedTour(
            steps=Path(__file__).with_name("guide.json"),
            get_target_rect=lambda key: self.item_rects.get(key),
            owner=self,
        )
        self.help = EmTkHelpWindow(title="Spectra", resource=Path(__file__).with_name("help.md"))
        self.docks = DockManager(Split("h", 0.20, Region("navigation"), Region("content")))
        self.docks.add_window(
            "navigation", tr("Spectra"), self.draw_navigation, dock="navigation", closable=False
        )
        self.docks.add_window(
            "content", tr("Overview"), self.draw_content, dock="content", closable=False
        )
        style = Style(frame_padding=(6, 5), item_spacing=(8, 6), frame_border_size=1)
        im.style_colors_light(style)
        style.colors.update(
            {
                Col.TEXT: (0, 0, 0, 255),
                Col.WINDOW_BG: (239, 239, 239, 255),
                Col.TITLE_BG: (239, 239, 239, 255),
                Col.TITLE_BG_ACTIVE: (239, 239, 239, 255),
                Col.FRAME_BG: (255, 255, 255, 255),
                Col.BORDER: (170, 170, 170, 255),
                Col.BUTTON: (246, 246, 246, 255),
                Col.HEADER: (47, 145, 197, 255),
                Col.HEADER_HOVERED: (190, 220, 240, 255),
                Col.TAB: (232, 232, 232, 255),
                Col.TAB_SELECTED: (255, 255, 255, 255),
            }
        )
        super().__init__(gui=self.render, continuous=True, style=style)

    def tip(self, label):
        # Every interactive control uses its translated purpose as a tooltip.
        im.set_item_tooltip(tr(TOOLTIPS.get(label, label)))
        self.item_rects[label] = im.get_item_rect()

    def button(self, label, action):
        if im.button(tr(label)):
            self.act(action)
        self.tip(label)

    def act(self, action):
        try:
            result = action()
            if result is not None:
                self.message = json.dumps(result, default=str, ensure_ascii=False)
        except Exception as exc:
            self.message = str(exc)

    def draw_navigation(self, box):
        _, self.navigation_search = im.input_text(
            "##navigation_search", self.navigation_search, hint=tr("Filter")
        )
        self.tip("Filter")
        im.spacing()
        for panel in PANELS:
            if self.navigation_search.lower() not in tr(panel).lower():
                continue
            if im.selectable(tr(panel), self.panel == panel):
                self.panel = panel
                self.tour.notify_used(panel)
            self.tip(panel)
        im.separator()
        im.text(tr("Language"))
        locale = i18n.get_locale()
        changed, index = im.combo(
            "##locale", LOCALES.index(locale) if locale in LOCALES else 0, list(LOCALES)
        )
        self.tip("Language")
        if changed:
            i18n.set_locale(LOCALES[index])
        self.button("Guide", self.tour.start)
        self.button("Help", self.help.show)

    def draw_content(self, box):
        if self.panel == "Overview":
            self.draw_overview()
        elif self.panel == "Browse":
            self.draw_browser(box)
        elif self.panel == "Download":
            self.draw_download()
        else:
            self.draw_endpoint()
        if self.message:
            im.separator()
            im.text_wrapped(self.message)

    def draw_overview(self):
        im.heading(tr("Staging database overview"), level=4)
        summary = self.model.overview()
        available = im.get_content_region_avail()[0]
        columns = 4 if available >= 690 else 2
        if im.begin_table("summary", columns, size=(available, 0)):
            for index in range(columns):
                im.table_setup_column(
                    "##column" + str(index), init_width_or_weight=0.32 if index % 2 == 0 else 0.68
                )
            for index, (label, key) in enumerate(SUMMARY):
                if index % (columns // 2) == 0:
                    im.table_next_row()
                im.table_next_column()
                im.text(tr(label))
                im.table_next_column()
                im.set_next_item_width(im.get_content_region_avail()[0])
                im.input_text(
                    "##summary_" + key,
                    str(summary[key]),
                    flags=im.InputTextFlags.READ_ONLY,
                    elide_start=key == "db_path",
                )
                self.tip(label)
            im.end_table()
        self.button("Refresh", self.model.refresh)
        im.spacing()
        im.text(tr("By category / source (JSON)"))
        origin = im.get_cursor_screen_pos()
        size = im.get_content_region_avail()
        draw = im.get_window_draw_list()
        draw.add_rect_filled(
            origin, (origin[0] + size[0], origin[1] + size[1]), (255, 255, 255, 255)
        )
        draw.add_rect(origin, (origin[0] + size[0], origin[1] + size[1]), (170, 170, 170, 255))
        im.begin_child("overview_json", size)
        im.push_font({"family": "monospace", "size": 12})
        im.text_wrapped(json.dumps({k: summary[k] for k in ("by_category", "by_source")}, indent=2))
        im.pop_font()
        im.end_child()

    def choice(self, label, value, values):
        options = [""] + values
        changed, index = im.combo(
            tr(label), options.index(value) if value in options else 0, [tr("All")] + values
        )
        self.tip(label)
        return options[index]

    def draw_browser(self, box):
        m = self.model
        wide = im.get_content_region_avail()[0] >= 680
        if wide:
            im.columns(3)
        _, m.search = im.input_text(tr("Filter"), m.search)
        self.tip("Filter")
        if wide:
            im.next_column()
        m.source = self.choice("Source", m.source, m.sources)
        if wide:
            im.next_column()
        m.category = self.choice("Category", m.category, m.categories)
        if wide:
            im.columns(1)
        self.button("Refresh", m.refresh)
        rows = m.filtered()
        im.same_line()
        im.text(f"{len(rows)} / {len(m.rows)}")
        origin = im.get_cursor_screen_pos()
        width, height = im.get_content_region_avail()
        if wide:
            left = max(530.0, width * 0.65)
            im.begin_child("components_panel", (origin[0], origin[1], left, height))
            self.draw_components(rows)
            im.end_child()
            im.begin_child(
                "detail_panel", (origin[0] + left + 8, origin[1], width - left - 8, height)
            )
            self.draw_detail()
            im.end_child()
        else:
            self.draw_components(rows)
            self.draw_detail()

    def draw_components(self, rows):
        m = self.model
        available = im.get_content_region_avail()[0]
        narrow = available < 470
        im.push_font({"family": "sans-serif", "size": 9 if narrow else 10})
        widths = (28, 24, 110, 88, 66, 76) if narrow else (30, 24, 114, 90, 70, 80)
        if im.begin_table(
            "components_readable",
            6,
            flags=im.TableFlags.BORDERS | im.TableFlags.ROW_BG | im.TableFlags.RESIZABLE,
            size=(available, 0),
        ):
            for label, width in zip((" ", "ID", "Name", "Category", "Source", "Status"), widths):
                im.table_setup_column(
                    tr(label), flags=im.TableColumnFlags.WIDTH_FIXED, init_width_or_weight=width
                )
            im.table_headers_row()
            for row in rows:
                im.table_next_row()
                im.table_set_column_index(0)
                pid = row["probe_id"]
                changed, enabled = im.checkbox(f"##probe{pid}", pid in m.selected)
                self.tip("Select components to inspect their metadata and spectra.")
                self.item_rects[f"probe:{pid}"] = im.get_item_rect()
                if changed:
                    m.select(pid, enabled)
                for j, key in enumerate(
                    ("probe_id", "chromophore_name", "category", "source", "verification_status"), 1
                ):
                    im.table_set_column_index(j)
                    value = str(row.get(key) or "")
                    shown = value
                    room = im.get_content_region_avail()[0]
                    while shown and im.calc_text_size(shown)[0] > room:
                        shown = shown[:-1]
                    if shown != value:
                        shown = shown[:-1] + "…"
                    im.text(shown)
                    im.set_item_tooltip(value)
            im.end_table()
        im.pop_font()
        self.button("Push selected", lambda: setattr(self, "pending_push", True))
        self.button("Push all", lambda: setattr(self, "pending_push", False))

    def draw_detail(self):
        m = self.model
        if not m.detail:
            im.text_wrapped(tr("Select components to inspect their metadata and spectra."))
            return
        im.separator()
        probe = m.detail["probe"]
        im.heading(str(probe.get("chromophore_name") or ""), level=4)
        for label, key in (
            ("Category", "category"),
            ("Source", "source"),
            ("Status", "verification_status"),
        ):
            im.text_wrapped(f"{tr(label)}: {probe.get(key) or ''}")
        if im.begin_tab_bar("details"):
            if im.begin_tab_item(tr("Properties")):
                self.tip("Properties")
                for prop in m.detail["optical_properties"]:
                    im.text_wrapped(f"{prop['property_name']}: {prop['property_value']}")
                im.end_tab_item()
            if im.begin_tab_item(tr("Metadata (JSON)")):
                self.tip("Metadata (JSON)")
                meta = {
                    "probe": m.detail["probe"],
                    "optical_properties": {
                        p["property_name"]: p["property_value"]
                        for p in m.detail["optical_properties"]
                    },
                    "spectra": [
                        {"type": s["spectrum_type"], "points": len(s["wavelengths"])}
                        for s in m.detail["spectra"]
                    ],
                }
                im.text_wrapped(json.dumps(meta, indent=2, default=str))
                im.end_tab_item()
            im.end_tab_bar()
        if implot.begin_plot("##spectra", (-1, 220)):
            implot.setup_axes(tr("Wavelength (nm)"), tr("Intensity"))
            for s in m.detail["spectra"]:
                colors = {
                    "emission": (200, 0, 0, 255),
                    "absorption": (0, 100, 200, 255),
                    "transmission": (0, 150, 0, 255),
                }
                implot.plot_line(
                    s["spectrum_type"],
                    s["wavelengths"],
                    s["intensity"],
                    spec=implot.PlotSpec(
                        line_color=colors.get(s["spectrum_type"], (0, 100, 200, 255)), line_weight=2
                    ),
                )
            implot.end_plot()

    def draw_download(self):
        from ..download._base import SCRAPERS

        specs = sorted(SCRAPERS, key=lambda s: s.label)
        index = next((i for i, s in enumerate(specs) if s.module == self.model.module), 0)
        _, index = im.combo(tr("Available sources"), index, [s.label for s in specs])
        self.tip("Available sources")
        self.model.module = specs[index].module
        im.begin_disabled(self.model.process is not None)
        self.button("Run selected script", self.model.run_script)
        im.end_disabled()
        im.text_wrapped(
            f"{tr('Already scraped')} ({self.model.source_slug()}): {json.dumps(self.model.source_counts())}"
        )
        self.button("Browse this source", self.browse_source)
        im.separator()
        im.text_wrapped(self.model.log)

    def browse_source(self):
        self.model.refresh()
        self.model.source = self.model.source_slug()
        self.panel = "Browse"

    def draw_endpoint(self):
        m = self.model.endpoint
        _, index = im.combo(
            tr("Endpoint"), int(m.mode == "server"), [tr("Local file"), tr("Server (ZMQ)")]
        )
        self.tip("Endpoint")
        m.mode = ("local", "server")[index]
        _, m.db_path = im.input_text(tr("Local MMFDB"), m.db_path)
        self.tip("Local MMFDB")
        _, m.replace = im.checkbox(tr("Replace existing reference set"), m.replace)
        self.tip("Replace existing reference set")
        _, m.mark_verified = im.checkbox(tr("Mark imported as approved"), m.mark_verified)
        self.tip("Mark imported as approved")
        opened = im.collapsing_header(tr("Advanced — connection & authentication"))
        self.tip("Advanced — connection & authentication")
        if opened:
            for attr, label in (("host", "Host"), ("user", "User"), ("password", "Password")):
                _, value = im.input_text(
                    tr(label),
                    getattr(m, attr),
                    flags=im.InputTextFlags.PASSWORD if attr == "password" else 0,
                )
                setattr(m, attr, value)
                self.tip(label)
            for attr, label in (("cmd_port", "Command port"), ("pub_port", "Publish port")):
                _, value = im.input_int(tr(label), getattr(m, attr))
                setattr(m, attr, max(1, min(65535, value)))
                self.tip(label)
        self.button("Check session", self.check_session)
        if self.session is not None:
            ok, note = self.session
            im.text_wrapped(f"{m.user}: {tr('Administrator' if ok else 'Not authorized')} ({note})")
        self.button("Add all to MMFDB", self.model.add_all)

    def check_session(self):
        self.session = self.model.authorized()

    def render(self):
        self.model.poll()
        vp = im.get_main_viewport()
        frame = (0.0, 0.0, *vp.size)
        im.push_font({"family": "sans-serif", "size": 12})
        self.docks.layout.ratio = min(200.0, max(145.0, vp.size[0] * 0.20)) / max(1.0, vp.size[0])
        self.docks.windows["navigation"].title = tr("Spectra")
        self.docks.windows["content"].title = tr(self.panel)
        self.docks.draw(frame)
        if self.tour.active:
            self.tour.draw(*vp.size)
        if self.help.open:
            self.help.draw(frame)
        if self.pending_push is not None:
            if im.begin(tr("Confirm import"), box=(40, 100, min(500, vp.size[0] - 80), 180)):
                im.text_wrapped(tr("Import these staging components into the connected MMFDB?"))

                def push():
                    selected = self.pending_push
                    self.pending_push = None
                    return self.model.push(selected=selected)

                self.button("Confirm import", push)
                im.same_line()
                self.button("Cancel", lambda: setattr(self, "pending_push", None))
            im.end()
        im.pop_font()

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
                self.model.select(pid)

    def close(self):
        self.model.close()
        if self.owns_db:
            self.model.db.close()


def create_app(db=None):
    return SpectraApp(db)
