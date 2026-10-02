"""Native EMTK HYDROPRO / HYDRO++ app.

Mirrors the Qt AutoForm (``hydropro.view.json``) onto the immediate-mode API.
The settings live in the Qt-free :class:`~..core.settings.HydroProSettings`
dataclass and the compute in :func:`~..core.runner.run_hydro`, exactly as the
Qt tool drives them; this module never imports Qt.
"""

from __future__ import annotations

from emtk import im
from emtk.app import ImApp

from .core import HydroProSettings, run_hydro
from .strings import install_translations, tr

install_translations()

_LABEL_COL = 150.0

_INDMODES = ("1", "2", "4")


def _label_col() -> float:
    width, _ = im.get_main_viewport().size
    return min(_LABEL_COL, max(90.0, width * 0.34))


def _row_input_width(fixed: float | None = None) -> float:
    avail = im.get_content_region_avail()[0]
    if fixed is None:
        return max(90.0, min(240.0, avail - 8))
    return max(60.0, min(fixed, avail - 8))


class HydroProApp(ImApp):
    """Run HYDROPRO / HYDRO++ over structural files."""

    def __init__(self, settings: HydroProSettings | None = None):
        self.exe_path = ""
        self.struct_files = ""
        #: INDMODE held as string for the combo, like the Qt model.
        self.indmode = "1"
        self.settings = settings or HydroProSettings()
        self.status = ""
        self._running = False
        self._log_lines: list[str] = []
        super().__init__(self.render)

    # ── settings conversion (parity with the Qt _HydroModel) ────────────
    def to_settings(self) -> HydroProSettings:
        s = self.settings
        s.indmode = int(self.indmode)
        s.idif = 1 if s.idif else 0
        return s

    # ── render ──────────────────────────────────────────────────────────
    def render(self):
        width, height = im.get_main_viewport().size
        im.begin(tr("HydroPro"), (0, 0, width, height))
        im.heading(tr("HYDROPRO / HYDRO++"), level=2)

        self._render_inputs()
        im.separator()
        self._render_primary_model()
        im.separator()
        self._render_solvent()
        im.separator()
        self._render_optional()
        im.separator()
        self._render_run()
        if self.status:
            im.text_wrapped(self.status)
        im.separator()
        im.heading(tr("Log"), level=2)
        for line in self._log_lines:
            im.text(line)
        im.end()

    def _render_field(self, label, tip, draw_control):
        im.text(label)
        im.same_line(_label_col())
        draw_control()
        im.set_item_tooltip(tip)

    def _render_inputs(self):
        self._render_field(
            tr("Executable"), tr("Path to the HYDROPRO or HYDRO++ executable. The flavour is auto-detected from the filename."),
            lambda: self._text("##exe_path", "exe_path", "hydropro10.exe / hydro++10.exe"),
        )
        self._render_field(
            tr("Structures"), tr("Comma-separated structural files (PDB or bead coordinate files)."),
            lambda: self._text("##struct_files", "struct_files", "use 'Select files…'"),
        )

    def _text(self, widget_id, attr, hint):
        im.set_next_item_width(-1)
        changed, value = im.input_text(widget_id, str(getattr(self, attr)), hint=hint)
        if changed:
            setattr(self, attr, value)
        return value

    def _render_primary_model(self):
        self._render_field(
            tr("INDMODE"), tr("1 = atomic/shell; 2 = residue/shell; 4 = residue/bead."),
            lambda: self._combo_setting("##indmode", "indmode", _INDMODES),
        )
        self._render_field(
            "AER", tr("Hydrodynamic radius of primary elements. Typical: 2.9 (mode 1), 4.8 (2), 6.1 (4)."),
            lambda: self._float_setting("##aer", "aer", 0.1),
        )
        self._render_field(
            tr("NSIG"), tr("Number of minibead radii (>2, typically 5–8). Use -1 for automatic SIGMIN/SIGMAX."),
            lambda: self._int_setting("##nsig", "nsig"),
        )
        self._render_field(
            tr("SIGMIN"), tr("Minimum minibead radius (shell modes 1/2 when NSIG ≠ -1)."),
            lambda: self._float_setting("##sigmin", "sigmin", 0.1),
        )
        self._render_field(
            tr("SIGMAX"), tr("Maximum minibead radius (shell modes 1/2 when NSIG ≠ -1)."),
            lambda: self._float_setting("##sigmax", "sigmax", 0.1),
        )

    def _render_solvent(self):
        self._render_field("T", tr("Temperature in centigrade."),
                           lambda: self._float_setting("##t", "t", 1.0))
        self._render_field("ETA", tr("Solvent viscosity in poises (water at 20 °C ≈ 0.01 P)."),
                           lambda: self._float_setting("##eta", "eta", 0.001))
        self._render_field("RM", tr("Molecular weight in daltons."),
                           lambda: self._float_setting("##rm", "rm", 1000.0))
        self._render_field("VBAR", tr("Partial specific volume (proteins ≈ 0.73–0.75 cm³/g)."),
                           lambda: self._float_setting("##vbar", "vbar", 0.01))
        self._render_field("RHO", tr("Solution (≈ solvent) density in g/cm³."),
                           lambda: self._float_setting("##rho", "rho", 0.01))

    def _render_optional(self):
        self._render_field(
            tr("NQ"), tr("Scattering q values: 0 omit, -1 automatic, >0 specify QMAX."),
            lambda: self._int_setting("##nq", "nq"),
        )
        self._render_field(
            tr("QMAX"), tr("Upper limit of scattering variable q (only when NQ > 0)."),
            lambda: self._float_setting("##qmax", "qmax", 0.0),
        )
        self._render_field(
            tr("NS"), tr("Intervals for the distance distribution p(r): 0 omit, -1 automatic, >0 specify RMAX."),
            lambda: self._int_setting("##ns", "ns"),
        )
        self._render_field(
            tr("RMAX"), tr("Maximum distance for p(r) (only when NS > 0)."),
            lambda: self._float_setting("##rmax", "rmax", 0.0),
        )
        self._render_field(
            tr("NTRIALS"), tr("Monte-Carlo trials for the covolume calculation (0 to omit; very time-consuming)."),
            lambda: self._int_setting("##ntrials", "ntrials"),
        )
        changed, value = im.checkbox(tr("Full diffusion tensor"), bool(self.settings.idif))
        im.set_item_tooltip(tr("IDIF=1: output the full 6×6 diffusion tensor and diffusion centre."))
        if changed:
            self.settings.idif = 1 if value else 0

    def _render_run(self):
        if im.button(f"{tr('Run')}##run_hydro") and not self._running:
            self._run()
        im.set_item_tooltip(tr("Run HYDROPRO over the listed structures"))
        if self._running:
            im.same_line()
            im.text_wrapped(tr("Running…"))

    def _combo_setting(self, widget_id, attr, options):
        current = options.index(str(getattr(self, attr))) if str(getattr(self, attr)) in options else 0
        im.set_next_item_width(_row_input_width(120))
        changed, index = im.combo(widget_id, current, list(options))
        if changed:
            setattr(self, attr, options[index])

    def _float_setting(self, widget_id, attr, step):
        im.set_next_item_width(_row_input_width(160))
        changed, value = im.input_float(widget_id, float(getattr(self.settings, attr)), step=step, step_fast=step * 10.0 or 1.0)
        if changed:
            setattr(self.settings, attr, float(value))

    def _int_setting(self, widget_id, attr):
        im.set_next_item_width(_row_input_width(160))
        changed, value = im.input_int(widget_id, int(getattr(self.settings, attr)))
        if changed:
            setattr(self.settings, attr, int(value))

    # ── actions ─────────────────────────────────────────────────────────
    def _struct_list(self) -> list:
        import pathlib

        return [pathlib.Path(p.strip()) for p in self.struct_files.split(",") if p.strip()]

    def _run(self) -> None:
        import pathlib

        files = self._struct_list()
        if not files:
            self.status = tr("Select at least one structural file.")
            return
        if not self.exe_path:
            self.status = tr("Select the HYDRO executable.")
            return
        self._running = True
        self.status = tr("Running…")
        self._log_lines = []
        try:
            results = run_hydro(
                files,
                self.to_settings(),
                pathlib.Path(self.exe_path),
                on_log=self._log_lines.append,
            )
            self.status = tr("Finished: {} file(s).").format(len(results))
        except Exception as exc:  # noqa: BLE001 - surface run errors inline
            self.status = f"{tr('Error')}: {exc}"
        finally:
            self._running = False

    # ── persistence ─────────────────────────────────────────────────────
    def export_settings(self) -> dict:
        return {
            "exe_path": self.exe_path,
            "struct_files": self.struct_files,
            # Sync the combo into the settings first, like the Qt save path.
            **self.to_settings().to_dict(),
            "indmode": self.indmode,
        }

    def restore_settings(self, settings: dict) -> None:
        if "exe_path" in settings:
            self.exe_path = str(settings["exe_path"])
        if "struct_files" in settings:
            self.struct_files = str(settings["struct_files"])
        if "indmode" in settings:
            self.indmode = str(settings["indmode"])
        self.settings = HydroProSettings.from_dict(settings)


def make_app() -> HydroProApp:
    return HydroProApp()
