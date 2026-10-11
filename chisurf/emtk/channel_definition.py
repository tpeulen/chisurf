"""Reusable native detector setup / channel definition editor: one page, as the Qt page.

The page is what the Qt ``DetectorWizardPage`` is, in one scroll and no tabs:

* the **Setup row** (Setup choice, Save, Rename, Delete, Public, Calibration, ``?``): state and prompts in
  :class:`chisurf.emtk.channel_setup_bar.SetupToolbar`;
* **TTTR Reading routine**: File Type (all container formats of tttrlib, as Qt lists them) with Read, macro and
  micro time resolution, binning and the effective micro time in a two-column label/field grid, and the Plot
  toggle that opens the micro-time decay preview;
* **PIE Windows** (folded at first) and **Detectors** (with the *Polarization resolved* switch in its header):
  real ``data_table`` tables (:class:`emtk.widgets.data_table.TableBinding`) whose cells are typed with Enter or a
  click elsewhere to commit, read with the Qt range-text rules (``20:10``, ``5:5``, ``0:10;20:30``);
* **LUT handling (TAC linearization)**: the gate, the Channel / LUT / Shift table, and Assign LUT..., Configure
  LUTs..., Adjust shifts...;
* **Optical Setup...** at the bottom right.

Fields are drawn at capped widths in label/field grids (see :mod:`chisurf.plugins.emtk_layout`), so the page
works from a 1200 px window down to the 720 px column of a host and below. Floating windows (file chooser, plot,
LUT tools, shift adjuster, optical setup, help, prompts) are drawn by :meth:`ChannelDefinitionWidget.draw_dialogs`;
a host calls it once per frame next to :meth:`ChannelDefinitionWidget.draw`.
"""

import copy
import json
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event

import numpy as np
from emtk.i18n import mark, tr
from emtk.view_form import FormState, draw_form

from chisurf.core.setup_channel_definition import ChannelDefinition
from chisurf.emtk.channel_setup_bar import (
    DELETE,
    LATEST,
    OVERWRITE,
    RENAME,
    SAVE,
    UNSAVED,
    SetupToolbar,
)
from chisurf.plugins.emtk_layout import action_button, action_caption

#: The File Type choices, in the Qt order: Auto, then every container tttrlib reads.
FILE_TYPES = (
    "Auto",
    "PTU",
    "HT3",
    "SPC-130",
    "SPC-600_256",
    "SPC-600_4096",
    "PHOTON-HDF5",
    "CZ-RAW",
    "SM",
    "PHOTONS",
    "SPC-QC",
    "BRIGHTEYES-TTR",
    "FLIMLABS-STT1",
    "FLIMLABS-ITT1",
    "PTO",
)
#: The Microtime binning choices of the Qt combo.
BINNINGS = ("1", "2", "4", "8", "16", "32", "64", "128")
#: The collapsible sections, in drawing order, and whether each starts open (the Qt page folds PIE Windows).
SECTIONS = (
    ("reading", mark("TTTR Reading routine"), True),
    ("windows", mark("PIE Windows"), False),
    ("detectors", mark("Detectors"), True),
    ("lut", mark("LUT handling (TAC linearization)"), True),
)
#: What the Qt page's help button shows.
HELP_TEXT = mark("""You can either load an existing detector Pulsed-Interleaved Excitation (PIE) window definition by choosing a saved setup, or define your own PIE and detector settings by editing the tables. New PIE windows and detectors are added with the Add buttons. Save stores the current configuration as a named setup; the Setup choice restores one.

The TTTR Reading routine section sets the file type and the time resolution used when reading TTTR files; these settings are saved with the setup. Read loads a measurement and takes its timing from the header.

IMPORTANT - micro-time units: PIE windows (Start / End) and detector Micro Time Ranges are given in RAW micro-time channels of the TTTR file (typically 0 to a few thousand), the same units as the loaded data. They are NOT divided by the micro-time binning; binning only changes how the preview decay is displayed. A common mistake is to enter a range like 0-256 that covers only a small fraction of the data and therefore selects almost no photons.

Ranges are typed as start:end, several separated by commas or semicolons (0:10;20:30); a reversed range (20:10) is swapped. Channels are routing channels separated by commas. Double-click a cell of a table, type, and press Enter (or click elsewhere) to commit it.

Use Read, then Plot: the micro-time decay of your data is shown with your PIE windows and detector ranges overlaid, so you can confirm the ranges cover the intended part of the decay before saving the setup.""")

BLUE = (110, 165, 240, 255)
RED_BUTTON = ((170, 40, 40, 220), (210, 60, 60, 255), (240, 80, 80, 255))
#: Column and cell geometry of the label / field grids.
FIELD_W = 170.0
NUMBER_W = 120.0
GRID_GAP = 28.0


# --------------------------------------------------------------------------- #
# Qt's text rules
# --------------------------------------------------------------------------- #
def parse_ranges(text):
    """Micro-time ranges from text, as the Qt table reads them.

    Segments are split at ``,`` or ``;``; a segment is ``a:b``, ``a-b`` or a single ``a`` (the range ``a:a``);
    one that is not two integers is skipped; a reversed range is swapped.

    >>> parse_ranges('20:10')
    [[10, 20]]
    >>> parse_ranges('0:10;20:30')
    [[0, 10], [20, 30]]
    """
    if not isinstance(text, str):
        return []
    ranges = []
    for segment in (item.strip() for item in text.strip().replace(";", ",").split(",")):
        if not segment:
            continue
        if ":" in segment:
            first, second = segment.split(":", 1)
        else:
            position = segment.rfind("-")
            first, second = (
                (segment, segment)
                if position <= 0
                else (segment[:position], segment[position + 1 :])
            )
        try:
            low, high = int(first.strip()), int(second.strip())
        except ValueError:
            continue
        ranges.append([low, high] if low <= high else [high, low])
    return ranges


def format_ranges(ranges):
    """Micro-time ranges as the Qt table shows them: ``0:10, 20:30``."""
    try:
        return ", ".join(f"{int(low)}:{int(high)}" for low, high in ranges or [])
    except (TypeError, ValueError):
        return ""


def parse_channels(text):
    """Routing channels from text, as the Qt table reads them: integers split at ``,`` or ``;``; any other text gives ``[]``."""
    try:
        return [
            int(part.strip()) for part in str(text).replace(";", ",").split(",") if part.strip()
        ]
    except ValueError:
        return []


def parse_gate(text):
    """The G-factor channel range ``start-end`` (``start:end`` too) as ``[start, end]``; ``None`` for anything else."""
    parts = str(text).replace(" ", "").replace(":", "-").split("-")
    if len(parts) != 2:
        return None
    try:
        return [int(parts[0]), int(parts[1])]
    except ValueError:
        return None


def format_gate(gate):
    """The G-factor channel range as the Qt table shows it: ``start-end``."""
    if isinstance(gate, (list, tuple)) and len(gate) == 2:
        return f"{int(gate[0])}-{int(gate[1])}"
    return gate if isinstance(gate, str) else ""


def _signature(value):
    return json.dumps(value, sort_keys=True, default=str)


class _ButtonCells:
    """Buttons inside the cells of a ``data_table`` column (emtk's table has no button column).

    The table draws and hit-tests its cells; this wraps the retained control's ``draw``, ``press`` and
    ``tooltip_at`` so that the cells of the named columns are drawn as buttons over the (empty) cells and a press
    there calls the action with the record. Gap in emtk: a ``data_table`` column cannot be an action.
    """

    def __init__(self, binding, columns):
        self.binding = binding
        self.control = binding.control
        #: ``{column key: (caption, tooltip, action(record))}``
        self.columns = columns
        self.hot = None
        self.control_draw, self.control_press, self.control_tip = (
            self.control.draw,
            self.control.press,
            self.control.tooltip_at,
        )
        self.control.draw, self.control.press, self.control.tooltip_at = (
            self.draw,
            self.press,
            self.tooltip_at,
        )

    def cells(self):
        """``[(position, row index, column key, (x, y, w, h))]`` of the button cells in view."""
        control = self.control
        if control._body_box is None:
            return []
        by = control._body_box[1]
        order = control.order()
        out = []
        for slot in range(control._visible + 1):
            position = control.bar.top + slot
            if position >= len(order):
                break
            y = by + slot * control._row_h
            x = control._header_box[0]
            for column, width in zip(control._shown, control._widths):
                if column.key in self.columns:
                    out.append(
                        (position, order[position], column.key, (x, y, width, control._row_h))
                    )
                x += width
        return out

    def fit_columns(self):
        """Give each button column the room its widest caption needs *in the language in use*.

        The declared widths were measured on the English captions; *Supprimer* or *Löschen* in a fixed
        62 px cell is clipped. The widest caption of the rows in view (else the column's own) sets the
        column's minimum, and the table shares out the rest.
        """
        from dataclasses import replace

        from emtk import im

        for position, column in enumerate(self.control.columns):
            entry = self.columns.get(column.key)
            if entry is None:
                continue
            captions = {
                tr(str(self.control.value(index, column.key) or entry[0]))
                for index in range(self.control.row_count())
            } or {tr(entry[0])}
            need = max(im.calc_text_size(caption)[0] for caption in captions) + 18.0
            if column.min_width != need:
                self.control.columns[position] = replace(column, min_width=need)

    def draw(self, p, x, y, w, h):
        from emtk import style
        from emtk.painter import ALIGN_HCENTER, ALIGN_VCENTER

        self.fit_columns()
        self.control_draw(p, x, y, w, h)
        if self.control._body_box is None:
            return
        bx, by, bw, bh = self.control._body_box
        p.push_clip(bx, by, bw, bh)
        for position, index, key, (cx, cy, cw, ch) in self.cells():
            # the cells hold the source text (the rows are cached); it is translated where it is drawn
            caption = tr(str(self.control.value(index, key) or self.columns[key][0]))
            width = cw - 4.0  # covers the cell's own text, which only reserves the column its width
            bx0, by0, bh0 = cx + (cw - width) / 2.0, cy + 2.0, ch - 4.0
            hot = self.hot == (index, key)
            p.fill_rect(
                bx0, by0, width, bh0, (25, 25, 28, 255)
            )  # opaque: the cell's own text lies under it
            p.stroke_rect(
                bx0,
                by0,
                width,
                bh0,
                style.BORDER,
                (66, 110, 170, 255) if hot else (46, 66, 98, 255),
            )
            p.text(bx0, by0, width, bh0, ALIGN_HCENTER | ALIGN_VCENTER, caption, style.TEXT)
        p.pop_clip()

    def hit(self, x, y):
        """``(row index, column key, rect)`` of the button cell under a point, else ``None``."""
        for position, index, key, rect in self.cells():
            cx, cy, cw, ch = rect
            if (
                cx <= x < cx + cw
                and cy <= y < cy + ch
                and self.control._inside(self.control._body_box, x, y)
            ):
                return index, key, rect
        return None

    def press(self, x, y, *box, **kw):
        hit = self.hit(x, y)
        clicks = int(kw.get("clicks", box[5] if len(box) > 5 else 1) or 1)
        if hit is not None and self.control.editing is None:
            index, key, _ = hit
            record = self.binding.record(index)
            if clicks == 1:
                self.columns[key][2](record)
            return True
        return self.control_press(x, y, *box, **kw)

    def tooltip_at(self, x, y):
        hit = self.hit(x, y)
        if hit is not None:
            index, key, _ = hit
            self.hot = (index, key)
            return self.columns[key][1], ("button", index, key)
        self.hot = None
        return self.control_tip(x, y)


class ChannelDefinitionWidget:
    """The detector setup editor: setup row, reading routine, PIE windows, detectors, LUT handling, optical setup.

    Parameters
    ----------
    settings : dict, optional
        The working definition to start from.
    model : ChannelDefinition, optional
        The definition and its stores (default: built from *settings*).
    on_changed : callable, optional
        Called with the settings after every change.
    read_only : bool, optional
        Disable working-definition edits, including JSON application.
    """

    def __init__(
        self,
        settings=None,
        model=None,
        on_changed=None,
        read_only=False,
        host_app=None,
        visibility=None,
        on_definition_saved=None,
    ):
        from emtk.dialog_window import DialogWindow

        self.model = model or ChannelDefinition(settings)
        self.model.on_changed = on_changed
        self.hosted = False
        self.on_edit_setup = None
        self._own_on_changed = None
        self._hosted_pending = None
        self._hosted_can_apply = None
        self._hosted_form = FormState(on_used=self._item_used)
        self._hosted_spec = json.loads(
            Path(__file__).with_name("channel_definition_hosted.view.json").read_text()
        )
        self.status = ""
        self.read_only = bool(read_only)
        self.host_app = host_app
        self.visibility = dict(visibility or {})
        self.on_definition_saved = on_definition_saved
        self._io_view = json.loads(
            Path(__file__).with_name("channel_definition_io.view.json").read_text()
        )
        self._io_state = FormState()
        self.reference_app = None
        self.reference_info = ""
        self._reference_future = None
        self._reference_cancel = Event()
        self._reference_context = {}
        self._reference_drop_hooks = {}
        self._reference_model = None
        self._reference_temp = None
        self._reference_focus = False
        self._reference_capture = False
        self._reference_discard = False
        self._reference_apply_requested = False
        self._closing = False
        self.setup_name = self.model.current_name
        self.public = bool(self.model.data.get("_is_public"))
        self.calibrations = []
        self.calibration = LATEST
        self.toolbar = SetupToolbar(self)
        #: ``on_used(name)`` is called when the user used a named control (a guided tour waits for it).
        self.on_used = None
        self.item_rects = {}
        self.open_sections = {key: opened for key, _title, opened in SECTIONS}
        self.lut_start, self.lut_stop = 0, 32768
        self.selected_channel = None
        self._preview_detector = None
        self.dialog = None
        self.json_window = DialogWindow(
            tr("Edit JSON definition"), size=(820.0, 560.0), key="channel_json"
        )
        self.json_text = ""
        self.json_error = ""
        self._json_view = json.loads(
            Path(__file__).with_name("channel_definition_json.view.json").read_text()
        )["panels"]
        for section in self._json_view["toolbar"]["sections"]:
            for button in section.get("buttons", []):
                if button["action"] == "edit_json":
                    button["visible"] = self.is_visible("edit_json")
                elif button["action"] == "preview_g":
                    button["visible"] = self.is_visible("tables")
        self._json_toolbar_state = FormState()
        self._json_state = FormState()
        self._json_toolbar_state.on_used = self._used
        self._json_state.on_used = self._used
        self.reference_window = DialogWindow(
            tr("Reference G-factor calibration"), size=(1100.0, 780.0), key="channel_reference"
        )
        self.reference_prompt = DialogWindow(
            tr("Use the saved calibration tail?"),
            size=(720.0, 180.0),
            key="channel_reference_prompt",
            fit_height=True,
        )
        self._reference_view = json.loads(
            Path(__file__).with_name("channel_definition_calibration.view.json").read_text()
        )["panels"]
        self._reference_state = FormState()
        self.action = "measurement"
        self._future = None
        self._cancel = Event()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="channel-definition")
        self.optical = None
        self._text = {}
        self._seen = {}
        #: A narrow host (under 520 px): the buttons of the Detectors table are 'G' and 'Del'.
        self._compact = False
        self._detector_rows, self._detector_sig = [], None
        self._window_rows, self._window_sig = [], None
        self._lut_rows, self._lut_sig = [], None
        self._shift_draft = {}
        self.question = ""
        self.prompt_window = DialogWindow(
            mark("Setup"), size=(460.0, 130.0), key="channel_setup", fit_height=True
        )
        self.question_window = DialogWindow(
            mark("Missing LUTs"), size=(480.0, 150.0), key="channel_missing_luts", fit_height=True
        )
        self.help_window = DialogWindow(
            mark("Help - Detector Setup"), size=(620.0, 420.0), key="channel_help"
        )
        self.preview_window = DialogWindow(
            mark("Micro-time Decay Preview"), size=(700.0, 450.0), key="channel_preview"
        )
        self.lut_window = DialogWindow(
            mark("TTTR LUT Tools"), size=(560.0, 330.0), key="channel_lut_tools"
        )
        self.shift_window = DialogWindow(
            mark("Adjust micro-time shifts"), size=(760.0, 480.0), key="channel_shifts"
        )
        self.optical_window = DialogWindow(
            mark("Optical Setup"), size=(820.0, 600.0), key="channel_optical"
        )
        self._detector_table = self._binding(
            "detector_rows",
            "edit_detector",
            "select_detector",
            (
                (
                    "name",
                    mark("Detector Name"),
                    120,
                    True,
                    mark("Name of the detector. Double-click, type and press Enter to rename it."),
                ),
                (
                    "chs",
                    mark("Channels"),
                    90,
                    True,
                    mark("Routing channels of the detector, separated by commas (0, 1)."),
                ),
                (
                    "ranges",
                    mark("Micro Time Ranges"),
                    150,
                    True,
                    mark("Micro-time gates as start:end in raw TAC channels; several with , or ; (0:10;20:30). A reversed range is swapped."),
                ),
                (
                    "g",
                    mark("G-Factor"),
                    70,
                    True,
                    mark("Polarization sensitivity correction of the detector; an empty cell means 1.0."),
                ),
                ("l1", "l1", 60, True, mark("Polarization mixing correction l1.")),
                ("l2", "l2", 60, True, mark("Polarization mixing correction l2.")),
                (
                    "gch",
                    mark("G-Factor Channels"),
                    120,
                    True,
                    mark("TAC range start-end used to calculate the G factor from the loaded decays."),
                ),
                ("calc", "", 62, False, mark("Calculate the G factor of this detector.")),
                ("delete", "", 62, False, mark("Remove this detector.")),
            ),
        )
        self._detector_buttons = _ButtonCells(
            self._detector_table,
            {
                "calc": (
                    mark("Calc G"),
                    mark("Choose an independent TTTR reference and open full native G-factor calibration, including background, mixing and archived provenance."),
                    self._calc_g,
                ),
                "delete": (
                    mark("Delete"),
                    mark("Remove this detector from the working definition."),
                    self._remove_detector,
                ),
            },
        )
        self._window_table = self._binding(
            "window_rows",
            "edit_window",
            "select_window",
            (
                (
                    "name",
                    mark("Window Name"),
                    160,
                    True,
                    mark("Name of the PIE window. Double-click, type and press Enter to rename it."),
                ),
                ("start", mark("Start"), 90, True, mark("First TAC channel of the window.")),
                ("end", mark("End"), 90, True, mark("Exclusive upper TAC channel of the window.")),
                ("delete", "", 62, False, mark("Remove this window.")),
            ),
        )
        self._window_buttons = _ButtonCells(
            self._window_table,
            {
                "delete": (mark("Delete"), mark("Remove this PIE window."), self._remove_window),
            },
        )
        self._lut_table = self._binding(
            "lut_rows",
            "edit_lut",
            "select_lut",
            (
                ("channel", mark("Channel"), 80, False, mark("Routing channel.")),
                (
                    "lut",
                    "LUT",
                    0,
                    False,
                    mark("The TAC linearization table assigned to the channel, or none (raw reading)."),
                ),
                (
                    "shift",
                    mark("Shift"),
                    110,
                    True,
                    mark("Micro-time shift in bins applied after linearization. Double-click, type and press Enter."),
                ),
            ),
        )

    # ------------------------------------------------------------------ plumbing
    def _binding(self, source, edited, selected, columns):
        from emtk.widgets.data_table import TableBinding

        spec = {
            "type": "custom",
            "key": "data_table",
            "options": {
                "source": source,
                "row_key": "id",
                "edited_call": edited,
                "selected_call": selected,
                "editable": True,
                "min_column_width": 36,
                "height": 120,
                "fit_columns": True,
                "columns": [
                    {
                        "key": k,
                        "title": t or " ",
                        "width": w,
                        "editable": e,
                        "description": d,
                        "align": "left",
                    }
                    for k, t, w, e, d in columns
                ],
            },
        }
        return TableBinding(spec, self)

    def _call(self, function, *args, **kwargs):
        try:
            value = function(*args, **kwargs)
            self.status = tr("Settings updated.")
            return value
        except Exception as exc:
            self.status = tr("Error: {error}").format(error=exc)
            return None

    def _used(self, name):
        if callable(self.on_used):
            self.on_used(name)

    def _item(self, name, tip):
        """Tooltip and rectangle (for tests and guided tours) of the control just drawn."""
        from emtk import im

        im.set_item_tooltip(tip)
        self.item_rects[name] = im.get_item_rect()

    def refresh(self):
        self.toolbar.reload()

    def select_setup(self, name):
        self.model.select_setup(name)
        self.setup_name = name
        self.public = bool(self.model.data.get("_is_public"))
        self.calibrations = self.model.calibration_dates()
        self.calibration = LATEST
        self.reset_views()
        self.status = tr("Selected setup: {name}").format(name=name)

    def reset_views(self):
        """Forget what the tables, text fields and the optical editor show; they are read from the model again."""
        self.optical = None
        self._text, self._seen = {}, {}
        self._detector_sig = self._window_sig = self._lut_sig = None

    def load_definition(self, data):
        """Replace the working definition by *data*, keeping the setups, the stores and the change callback."""
        callback, setups, last_used = self.model.on_changed, self.model.setups, self.model.last_used
        loaded = ChannelDefinition(data, file_path=self.model.file_path, db=self.model.db)
        loaded.get_settings()
        self.model.__dict__.update(loaded.__dict__)
        self.model.setups, self.model.on_changed, self.model.last_used = setups, callback, last_used
        self.setup_name = self.model.current_name
        self.public = bool(self.model.data.get("_is_public"))
        self.reset_views()
        self.model.changed()

    def enabled(self, name):
        """JSON editing is unavailable for a read-only page or during calibration reading."""
        if name in {"edit_json", "json_text", "apply_json"}:
            return (
                not self.read_only
                and self._future is None
                and self._reference_future is None
                and self.reference_app is None
            )
        if name == "preview_g":
            return (
                not self.read_only
                and self._future is None
                and self._reference_future is None
                and self.reference_app is None
                and bool(self.model.preview)
            )
        if name in {"calibration_headless", "calibration_interactive"}:
            return not self.read_only and self._reference_model is not None
        if name == "calibration_apply":
            return not self.read_only and self.reference_app is not None
        return True

    def is_visible(self, name):
        """Existing native controls follow the embedding page's declared visibility."""
        default = name not in {"save_definition", "setups_file"}
        return bool(self.visibility.get(name, default))

    @property
    def show_save_definition(self):
        """Whether the declared full-definition export action is shown."""
        return self.is_visible("save_definition")

    @property
    def show_setups_file(self):
        """Whether the declared named-library import/export actions are shown."""
        return self.is_visible("setups_file")

    def save_definition(self):
        """Choose where to export the complete current working definition."""
        self.browse("save_definition")

    def import_setups(self):
        """Choose a named-setup library through the existing native picker."""
        self.browse("import_setups")

    def export_setups(self):
        """Choose where to export the current named-setup library."""
        self.browse("export_setups")

    def edit_json(self):
        """Open a fresh draft of the complete current portable definition."""
        if not self.enabled("edit_json"):
            return
        self.json_text = json.dumps(self.model.get_settings(), indent=2)
        self.json_error = ""
        self._json_state = FormState()
        self._json_state.on_used = self._used
        self.json_window.show()

    def apply_json(self):
        """Validate and apply a raw draft without writing a named setup."""
        if not self.json_window.open or not self.enabled("apply_json"):
            return
        try:
            data = json.loads(self.json_text)
            if not isinstance(data, dict):
                raise ValueError(tr("The definition must be a JSON object."))
            candidate = ChannelDefinition(data)
            for key in ("windows", "detectors", "tttr_reading", "channel_luts", "channel_shifts"):
                if not isinstance(candidate.data[key], dict):
                    raise ValueError(tr("'{field}' must be an object.").format(field=key))
            candidate.get_settings()
            for bounds in candidate.data["windows"].values():
                if not isinstance(bounds, list) or len(bounds) != 2:
                    raise ValueError(tr("Each PIE window must contain two channel bounds."))
                float(bounds[0]), float(bounds[1])
            for detector in candidate.data["detectors"].values():
                if not isinstance(detector.get("chs", []), list):
                    raise ValueError(tr("Detector routing channels must be a list."))
                for bounds in detector.get("micro_time_ranges", []):
                    if not isinstance(bounds, list) or len(bounds) != 2:
                        raise ValueError(tr("Each detector gate must contain two channel bounds."))
                    float(bounds[0]), float(bounds[1])
        except (ValueError, TypeError, AttributeError, IndexError, OverflowError) as exc:
            self.json_error = tr("Invalid definition: {error}").format(error=exc)
            return
        self.load_definition(data)
        self.json_error = ""
        self.json_window.hide()
        self.status = tr("Working definition updated; save the named setup separately.")

    def cancel_json(self):
        """Close the raw draft without changing the working definition."""
        self.json_window.hide()
        self.json_error = ""

    def _json_body(self):
        """Render the existing AutoForm code editor and declared Apply/Cancel controls."""
        draw_form(self._json_view["dialog"], self, self._json_state)
        self.item_rects.update(self._json_state.rects)

    def export_state(self):
        """What is worth remembering of the page itself: which sections are open and whether the plot is."""
        return {"sections": dict(self.open_sections), "plot": bool(self.preview_window.open)}

    def restore_state(self, state):
        """Restore :meth:`export_state`; unknown keys and wrong types are ignored."""
        state = state if isinstance(state, dict) else {}
        for key, value in (state.get("sections") or {}).items():
            if key in self.open_sections:
                self.open_sections[key] = bool(value)
        if state.get("plot"):
            self.preview_window.show()

    # ------------------------------------------------------------------ small widgets
    @staticmethod
    def _width(label):
        from emtk import im

        return im.calc_text_size(label)[0] + 18.0

    def _section(self, key, title, tip, right=0.0):
        """A section header (a clickable band with a triangle); whether the section is open. *right* leaves room beside it."""
        from emtk import im
        from emtk.im_core import Col

        opened = self.open_sections[key]
        width = max(
            im.get_content_region_avail()[0]
            - right
            - (im.get_style().item_spacing[0] if right else 0.0),
            40.0,
        )
        im.push_style_color(Col.TEXT, BLUE)
        clicked = im.selectable(
            f"{'▼' if opened else '▶'} {tr(title)}##section_{key}", True, (width, 0.0)
        )
        im.pop_style_color()
        self._item("section_" + key, tip)
        if clicked:
            self.open_sections[key] = opened = not opened
            self._used("section_" + key)
        return opened

    def _grid(self, rows):
        """Rows of label/field cells: ``rows = [[(label, draw_field, field_width), ...], ...]`` (one or two cells per row).

        Two cells sit side by side while the page is wide enough (each label column is as wide as the widest label of
        its side, every field a capped width, so the labels and fields of the rows line up), else one under the other.
        """
        from emtk import im

        left = max((self._width(r[0][0]) for r in rows), default=0.0)
        right = max((self._width(r[1][0]) for r in rows if len(r) > 1), default=0.0)
        field = max((cell[2] for r in rows for cell in r[:1]), default=FIELD_W)
        second = left + field + GRID_GAP
        wide = (
            im.get_content_region_avail()[0]
            >= second + right + max((cell[2] for r in rows for cell in r[1:]), default=0.0) + 8.0
        )
        for row in rows:
            for group in [row] if wide else [[cell] for cell in row]:
                for n, (label, draw_field, width) in enumerate(group):
                    label_x, field_x = (0.0, left) if n == 0 else (second, second + right)
                    if n:
                        im.same_line(label_x)
                    im.align_text_to_frame_padding()
                    im.text(label)
                    im.same_line(field_x)
                    im.set_next_item_width(width)
                    draw_field()

    def _text_field(self, key, value):
        """The text a number field shows: what the user typed while it is a valid number or being typed, else the value."""
        if key not in self._text or self._seen.get(key) != value:
            self._text[key] = f"{value}"
            self._seen[key] = value
        return self._text[key]

    def _number_input(self, key, value, tip, kind=float, name=None):
        """A typed number field (a text field: Enter or a click elsewhere keeps it; a typo keeps the last valid value).

        Returns the new value when the user typed a valid one this frame, else ``None``.
        """
        from emtk import im

        text = self._text_field(key, value)
        changed, text = im.input_text("##" + key, text)
        self._item(name or key, tip)
        if not changed:
            return None
        self._text[key] = text
        try:
            parsed = kind(text)
        except ValueError:
            return None
        self._seen[key] = parsed
        return parsed

    # ------------------------------------------------------------------ setup row
    def _setup_row(self):
        from emtk import im
        from emtk.im_core import Col

        if not self.is_visible("setup_selection"):
            return

        bar = self.toolbar
        total = im.get_content_region_avail()[0]
        spacing = 8.0
        used = [0.0]

        def place(width):
            if used[0] > 0.0 and used[0] + spacing + width > total:
                used[0] = 0.0
            elif used[0] > 0.0:
                im.same_line()
            used[0] += width + (spacing if used[0] > 0.0 else 0.0)

        im.begin_disabled(self._future is not None or bool(bar.dialog))
        names = [UNSAVED] + bar.names
        index = names.index(bar.selected) if bar.selected in names else 0
        place(self._width(tr("Setup:")) + 230.0)
        im.align_text_to_frame_padding()
        im.text(tr("Setup:"))
        im.same_line()
        im.set_next_item_width(220.0)
        changed, picked = im.combo("##setup_choice", index, [tr(names[0]), *names[1:]])
        self._item(
            "setup_choice",
            tr("Choose a saved detector setup; its detectors, PIE windows, reading routine, LUTs and optical setup replace the working definition."),
        )
        if changed:
            bar.select("" if picked == 0 else names[picked])
            self._used("setup_choice")
        place(self._width(action_caption("save")))
        tip = tr("Ask for a name and store the working definition as a saved setup.")
        if action_button("save", tooltip=tip):
            bar.request_save()
            self._used("save")
        self.item_rects["save"] = im.get_item_rect()
        for name, label, tip, action in (
            ("rename", tr("Rename"), tr("Give the selected saved setup another name."), bar.request_rename),
            (
                "delete",
                tr("Delete"),
                tr("Delete the selected saved setup after asking."),
                bar.request_delete,
            ),
        ):
            place(self._width(label))
            if im.button(label):
                action()
                self._used(name)
            self._item(name, tip)
        place(self._width(tr("Public")) + 24.0)
        im.begin_disabled(not bar.can_public())
        changed, value = im.checkbox(tr("Public"), bool(self.public))
        self._item(
            "public",
            tr("When checked, the setup is visible to all users in the MMFDB; it takes effect with Save. Only the owner of a saved setup can change this."),
        )
        im.end_disabled()
        if changed:
            bar.select_public(value)
        items = bar.calibration_items()
        picked_index = items.index(self.calibration) if self.calibration in items else 0
        place(self._width(tr("Calibration:")) + 200.0)
        im.align_text_to_frame_padding()
        im.text(tr("Calibration:"))
        im.same_line()
        im.set_next_item_width(190.0)
        shown_items = [tr("Latest") if item == LATEST else item for item in items]
        changed, picked = im.combo("##calibration_choice", picked_index, shown_items)
        self._item(
            "calibration",
            tr("Pick a stored calibration snapshot of the selected setup: its G factor, l1 and l2 are applied to the detectors. Latest leaves the factors as they are."),
        )
        if changed:
            bar.select_calibration(items[picked])
            self._used("calibration")
        im.end_disabled()
        if not self.is_visible("help"):
            return
        place(self._width("?") + 8.0)
        for col, rgba in zip((Col.BUTTON, Col.BUTTON_HOVERED, Col.BUTTON_ACTIVE), RED_BUTTON):
            im.push_style_color(col, rgba)
        if im.button(tr("?") + "##page_help"):
            self.help_window.show()
            self._used("page_help")
        im.pop_style_color(3)
        self._item(
            "page_help",
            tr("Explain the page: setups, reading routine, PIE windows, detectors and the units of micro-time ranges."),
        )

    # ------------------------------------------------------------------ TTTR reading
    def _reading_section(self):
        from emtk import im, style

        reading = self.model.data["tttr_reading"]
        im.text(tr("TTTR Reading Routine:"))
        current = str(reading.get("file_type") or "Auto")
        shown = "Auto" if current.lower() == "auto" else current
        options = list(FILE_TYPES) + ([shown] if shown not in FILE_TYPES else [])

        def file_type():
            changed, index = im.combo("##tttr_format", options.index(shown), options)
            self._item(
                "file_type",
                tr("The TTTR container format used to read measurements; Auto detects it from the file."),
            )
            if changed:
                reading["file_type"] = options[index]
                self.model.changed()
                self._used("file_type")
            im.same_line()
            if im.button(tr("Read")):
                self.browse("measurement")
                self._used("read")
            self._item(
                "read",
                tr("Read a measurement or BH SET calibration: macro and micro time resolution from the header, and the decay of every routing channel."),
            )

        def number(key, label, tip):
            def draw():
                parsed = self._number_input(key, float(reading.get(key, 0) or 0), tip)
                if parsed is not None:
                    reading[key] = parsed
                    reading["override_timing"] = True
                    self.model.changed()

            return draw

        binning = str(int(reading.get("micro_time_binning", 1) or 1))
        bins = list(BINNINGS) + ([binning] if binning not in BINNINGS else [])

        def binning_field():
            changed, index = im.combo("##binning", bins.index(binning), bins)
            self._item("binning", tr("Number of original TAC channels per analysis bin."))
            if changed:
                reading["micro_time_binning"] = int(bins[index])
                self.model.changed()

        effective = float(reading.get("micro_time_resolution", 0) or 0) * max(
            1, int(reading.get("micro_time_binning", 1) or 1)
        )

        def effective_field():
            im.input_text("##effective", f"{effective:.6f}", "", im.InputTextFlags.READ_ONLY)
            self._item("effective", tr("Microtime resolution times the binning (read-only)."))

        left = max(
            self._width(label)
            for label in (tr("File Type:"), tr("Macrotime res. (ns):"), tr("Microtime binning:"))
        )
        # the Read button sits beside the combo: in a narrow host the combo gives way to it
        file_width = max(
            90.0,
            min(
                FIELD_W + 40.0, im.get_content_region_avail()[0] - left - self._width(tr("Read")) - 16.0
            ),
        )
        self._grid(
            [
                [(tr("File Type:"), file_type, file_width)],
                [
                    (
                        tr("Macrotime res. (ns):"),
                        number(
                            "macro_time_resolution",
                            tr("Macrotime"),
                            tr("Macro-time tick (the excitation period) in nanoseconds."),
                        ),
                        NUMBER_W,
                    ),
                    (
                        tr("Microtime res. (ps):"),
                        number(
                            "micro_time_resolution",
                            tr("Microtime"),
                            tr("Micro-time channel width in picoseconds."),
                        ),
                        NUMBER_W,
                    ),
                ],
                [
                    (tr("Microtime binning:"), binning_field, NUMBER_W),
                    (tr("Eff. microtime (ps):"), effective_field, NUMBER_W),
                ],
            ]
        )
        plotting = self.preview_window.open
        if plotting:
            im.push_style_color(im.Col.BUTTON, style.BUTTON_ACTIVE)
        if im.button(tr("Plot")):
            self.preview_window.toggle()
            self._used("plot")
        if plotting:
            im.pop_style_color()
        self._item(
            "plot",
            tr("Show or hide the micro-time decay preview with the PIE windows and detector gates overlaid."),
        )

    # ------------------------------------------------------------------ tables
    def detector_rows(self):
        """Records of the Detectors table, rebuilt from the definition when it changed elsewhere."""
        detectors = self.model.data["detectors"]
        signature = _signature([detectors, self._compact])
        if signature != self._detector_sig:
            self._detector_sig = signature
            self._detector_rows = [
                {
                    "id": name,
                    "name": name,
                    "chs": ", ".join(map(str, info.get("chs", []))),
                    "ranges": format_ranges(info.get("micro_time_ranges", [])),
                    "g": str(info.get("g_factor", 1.0)),
                    "l1": str(info.get("l1", 0.0)),
                    "l2": str(info.get("l2", 0.0)),
                    "gch": format_gate(info.get("g_factor_channels")),
                    "calc": "G" if self._compact else mark("Calc G"),
                    "delete": mark("Del") if self._compact else mark("Delete"),
                }
                for name, info in detectors.items()
            ]
        return self._detector_rows

    def window_rows(self):
        """Records of the PIE Windows table."""
        windows = self.model.data["windows"]
        signature = _signature(windows)
        if signature != self._window_sig:
            self._window_sig = signature
            self._window_rows = [
                {
                    "id": name,
                    "name": name,
                    "start": str(bounds[0]),
                    "end": str(bounds[1]),
                    "delete": mark("Delete"),
                }
                for name, bounds in windows.items()
            ]
        return self._window_rows

    def used_channels(self):
        """The routing channels of every detector, and those that already carry a LUT or a shift (sorted)."""
        channels = {
            int(ch) for info in self.model.data["detectors"].values() for ch in info.get("chs", [])
        }
        channels.update(int(k) for k in self.model.data.get("channel_luts", {}))
        channels.update(int(k) for k in self.model.data.get("channel_shifts", {}))
        return sorted(channels)

    def lut_rows(self):
        """Records of the Channel / LUT / Shift table."""
        data = self.model.data
        signature = _signature(
            [
                self.used_channels(),
                {k: bool(v) for k, v in data.get("channel_luts", {}).items()},
                data.get("channel_shifts", {}),
                data.get("channel_lut_sources", {}),
            ]
        )
        if signature != self._lut_sig:
            self._lut_sig = signature
            rows = []
            for channel in self.used_channels():
                lut = data.get("channel_luts", {}).get(str(channel))
                source = data.get("channel_lut_sources", {}).get(str(channel))
                label = (source or "assigned") if lut else tr("— none —")
                rows.append(
                    {
                        "id": str(channel),
                        "channel": str(channel),
                        "lut": label,
                        "shift": int(data.get("channel_shifts", {}).get(str(channel), 0)),
                    }
                )
            self._lut_rows = rows
        return self._lut_rows

    def _refresh_rows(self):
        self._detector_sig = self._window_sig = self._lut_sig = None

    def _keep_rows(self):
        """After an edit made in a table: the rows already show what was typed, so they are not rebuilt."""
        self._detector_sig = _signature([self.model.data["detectors"], self._compact])
        self._window_sig = _signature(self.model.data["windows"])

    def edit_detector(self, record, key, value):
        """A Detectors cell was committed: apply it with the Qt rules; a value Qt refuses keeps the old one."""
        name = record["id"]
        detectors = self.model.data["detectors"]
        info = detectors.get(name)
        if info is None:
            return
        text = str(value).strip()
        if key == "name":
            if not text or (text != name and text in detectors):
                record["name"] = name
                self.status = tr("Error: Choose an unused detector name.")
                return
            if text != name:
                self.model.rename_detector(name, text)
                record["id"] = text
                self.status = tr("Settings updated.")
            record["name"] = text
            self._keep_rows()
            return
        if key == "chs":
            info["chs"] = parse_channels(text)
        elif key == "ranges":
            info["micro_time_ranges"] = parse_ranges(text)
        elif key == "g":
            try:
                number = float(text) if text else 1.0
            except ValueError:
                record["g"] = str(info.get("g_factor", 1.0))
                self.status = tr("Error: The G factor must be a number.")
                return
            info["g_factor"] = number
            record["g"] = f"{number:.3f}"
        elif key in ("l1", "l2"):
            try:
                info[key] = float(text)
            except ValueError:
                record[key] = str(info.get(key, 0.0))
                self.status = tr("Error: {name} must be a number.").format(name=key)
                return
        elif key == "gch":
            gate = parse_gate(text)
            if gate is None:
                info.pop("g_factor_channels", None)
            else:
                info["g_factor_channels"] = gate
        self.status = tr("Settings updated.")
        self.model.changed()
        self._keep_rows()

    def edit_window(self, record, key, value):
        """A PIE Windows cell was committed."""
        name = record["id"]
        windows = self.model.data["windows"]
        if name not in windows:
            return
        text = str(value).strip()
        if key == "name":
            if not text or (text != name and text in windows):
                record["name"] = name
                self.status = tr("Error: Choose an unused PIE window name.")
                return
            if text != name:
                self.model.rename_window(name, text)
                record["id"] = text
            record["name"] = text
        else:
            try:
                number = int(text)
            except ValueError:
                record[key] = str(windows[name][0 if key == "start" else 1])
                self.status = tr("Error: {name} must be a whole number.").format(
                    name=tr(key.capitalize())
                )
                return
            bounds = list(windows[name])
            bounds[0 if key == "start" else 1] = number
            windows[name] = bounds
            self.model.changed()
        self.status = tr("Settings updated.")
        self._keep_rows()

    def edit_lut(self, record, key, value):
        """A shift was committed (the only editable column of the LUT table)."""
        if key != "shift":
            return
        try:
            shift = max(-100000, min(100000, int(value)))
        except (TypeError, ValueError):
            return
        record["shift"] = shift
        self.model.data.setdefault("channel_shifts", {})[record["id"]] = shift
        self.model.changed()
        self._lut_sig = None
        self.refresh_preview()

    def select_detector(self, record):
        """Remember the Preview G target; calculator and delete buttons retain their row."""
        self._preview_detector = record["id"]

    select_window = select_detector

    def select_lut(self, record):
        """Remember the channel Assign LUT and the LUT tools act on."""
        self.selected_channel = int(record["id"]) if isinstance(record, dict) else None

    def add_detector(self):
        """Add a detector with the Qt defaults (channels 0, 1; range 0:2048) under an unused name."""
        detectors = self.model.data["detectors"]
        name, count = "New Detector", 1
        while name in detectors:
            name, count = f"New Detector {count}", count + 1
        detectors[name] = {
            "chs": [0, 1],
            "micro_time_ranges": [[0, 2048]],
            "g_factor": 1.0,
            "l1": 0.0,
            "l2": 0.0,
        }
        self.optical = None
        self.model.changed()
        self._refresh_rows()

    def add_window(self):
        """Add a PIE window 0:2048 under an unused name, as Qt does."""
        windows = self.model.data["windows"]
        name, count = "New Window", 1
        while name in windows:
            name, count = f"New Window {count}", count + 1
        windows[name] = [0, 2048]
        self.model.changed()
        self._refresh_rows()

    def _remove_detector(self, record):
        self.model.data["detectors"].pop(record["id"], None)
        self.optical = None
        self.model.changed()
        self._refresh_rows()

    def _remove_window(self, record):
        self.model.data["windows"].pop(record["id"], None)
        self.model.changed()
        self._refresh_rows()

    def _calc_g(self, record):
        if self.read_only or self._future is not None or self._reference_future is not None:
            return
        if self.host_app is None:
            self.status = tr("Reference calibration requires a native application host.")
            return
        name = record["id"]
        detector = self.model.data["detectors"][name]
        if len(detector.get("chs", [])) < 2:
            self.status = tr(
                "Reference calibration needs parallel and perpendicular routing channels."
            )
            return
        self._reference_context = {
            "name": name,
            "channels": list(detector["chs"]),
            "definition": self.model.data,
            "setup_name": self.model.current_name,
        }
        self._capture_reference_drops()
        self.browse("reference_calibration")

    def preview_g(self):
        """Keep the previous loaded-decay ratio as an explicit, unarchived quick operation."""
        if not self.enabled("preview_g"):
            return
        detectors = self.model.data["detectors"]
        name = (
            self._preview_detector
            if self._preview_detector in detectors
            else next(iter(detectors), None)
        )
        if name is not None and self._call(self.model.calculate_g, name) is not None:
            self._refresh_rows()

    def _read_reference(self, path):
        """Prepare independent reference histograms without replacing the active definition."""
        if self.read_only or self._reference_future is not None:
            return
        snapshot = ChannelDefinition(self.model.get_settings())
        self._reference_cancel = Event()
        cancelled = self._reference_cancel
        name = self._reference_context["name"]
        self.status = tr("Reading independent calibration reference ...")
        self._reference_future = self._executor.submit(
            self._prepare_reference, snapshot, path, name, cancelled
        )

        def completed(future):
            if self._closing or cancelled.is_set():
                self._discard_prepared_reference(future)
            else:
                self.host_app.request_frame()

        self._reference_future.add_done_callback(completed)

    def _prepare_reference(self, snapshot, path, name, cancelled=None):
        """Reuse portable TTTR reading and native G-factor arithmetic for one reference."""
        from chisurf.core.fio import write_vv_vh
        from chisurf.plugins.vv_vh_g_factor.gui.model import GFactorModel

        cancelled = self._reference_cancel if cancelled is None else cancelled
        if Path(path).suffix.lower() == ".set":
            raise ValueError(
                tr(
                    "Choose a TTTR measurement, not a timing-only SET header, for reference calibration."
                )
            )
        snapshot.preview, snapshot.raw_preview, snapshot.preview_path = {}, {}, ""
        snapshot.data.pop("_microtime_per_channel_decay", None)
        snapshot.data.pop("_raw_microtime_per_channel_decay", None)
        snapshot.read_tttr(path, cancel_cb=cancelled.is_set)
        if cancelled.is_set():
            raise InterruptedError(tr("Reference calibration cancelled."))
        channels = snapshot.data["detectors"][name]["chs"]
        if not snapshot.preview or snapshot.preview_path != str(path):
            raise ValueError(tr("The reference contains no newly read detector histograms."))
        shape = next(iter(snapshot.preview.values()))
        parallel = sum(
            (snapshot.preview[ch] for ch in channels[::2] if ch in snapshot.preview),
            start=np.zeros_like(shape),
        )
        perpendicular = sum(
            (snapshot.preview[ch] for ch in channels[1::2] if ch in snapshot.preview),
            start=np.zeros_like(shape),
        )
        binning = max(1, int(snapshot.data["tttr_reading"].get("micro_time_binning", 1)))
        if binning > 1:
            indices = np.arange(0, len(parallel), binning)
            parallel, perpendicular = (
                np.add.reduceat(parallel, indices),
                np.add.reduceat(perpendicular, indices),
            )
        temporary = tempfile.TemporaryDirectory(prefix="chisurf-reference-calibration-")
        try:
            filename = Path(temporary.name) / "reference_vv_vh.dat"
            write_vv_vh(str(filename), vv=parallel, vh=perpendicular)
            reference = GFactorModel()
            timing = snapshot.get_settings()["tttr_reading"]["effective_micro_time_resolution"]
            reference.fp_dt_ns = float(timing) * 1e-3
            reference.load(filename)
            gate = snapshot.data["detectors"][name].get("g_factor_channels")
            if isinstance(gate, str):
                gate = parse_gate(gate)
            saved_tail = isinstance(gate, (list, tuple)) and len(gate) == 2 and gate[1] > gate[0]
            if saved_tail:
                reference.region = [float(bound) / binning for bound in gate]
            reference.compute()
            if cancelled.is_set():
                raise InterruptedError(tr("Reference calibration cancelled."))
            return (
                reference,
                temporary,
                {
                    "path": str(path),
                    "binning": binning,
                    "timing": timing,
                    "saved_tail": saved_tail,
                    "prepared_file": str(filename),
                },
            )
        except Exception:
            temporary.cleanup()
            raise

    def _poll_reference(self):
        future = self._reference_future
        if future is None or not future.done():
            return
        self._reference_future = None
        try:
            reference, temporary, context = future.result()
            self._reference_model, self._reference_temp = reference, temporary
            self._reference_context.update(context)
            if self._reference_cancel.is_set() or self.read_only or self._closing:
                self.calibration_cancel()
                return
            self.reference_info = tr(
                "Reference: {path}\nDetector: {name}. Use the stored tail headlessly, or inspect the full calculator."
            ).format(path=context["path"], name=self._reference_context["name"])
            if context["saved_tail"]:
                self.reference_prompt.show()
            else:
                self.calibration_interactive()
        except Exception as exc:
            self.status = tr("Reference calibration failed: {error}").format(error=exc)
            self.calibration_cancel()

    def calibration_interactive(self):
        """Open the existing native calculator as a toolkit-neutral hosted child."""
        if not self.enabled("calibration_interactive"):
            return
        from chisurf.plugins.vv_vh_g_factor.gui.app import create_app

        self.reference_prompt.hide()
        self._reference_discard = False
        self._reference_apply_requested = False
        self.reference_app = create_app(on_close=self._publish_reference)
        self.reference_app.model = self._reference_model
        self.reference_app.settings_signature = self.reference_app.fingerprint()
        self.reference_window.show()

    def calibration_headless(self):
        """Archive the same prepared model and stored-tail result without a calculator window."""
        if not self.enabled("calibration_headless"):
            return
        self.reference_prompt.hide()
        self._reference_discard = False
        self._publish_reference(self._reference_model)
        self._cleanup_reference()

    def _publish_reference(self, reference):
        """Publish exactly one valid completed result in the captured detector context."""
        if reference is None or self._reference_discard or self.read_only or self._closing:
            return
        name = self._reference_context["name"]
        try:
            if (
                self.model.data is not self._reference_context["definition"]
                or self.model.current_name != self._reference_context["setup_name"]
            ):
                raise ValueError(
                    tr(
                        "The active definition changed during calibration; start a new Calc G reference."
                    )
                )
            if reference.fast_file != self._reference_context["prepared_file"]:
                raise ValueError(
                    tr(
                        "The fast reference changed. Start a new Calc G TTTR workflow to establish its raw-channel and timing provenance."
                    )
                )
            if self.model.data["detectors"][name].get("chs") != self._reference_context["channels"]:
                raise ValueError(tr("Detector routing channels changed during calibration."))
            self.model.archive_reference_g(
                name,
                reference,
                micro_time_resolution=self._reference_context["timing"],
                binning=self._reference_context["binning"],
                source_measurement=self._reference_context["path"],
                save_named=bool(
                    self.model.current_name in self.model.setups and self.toolbar.is_owner()
                ),
            )
            self._refresh_rows()
            self.status = tr("Reference calibration archived and detector updated.")
        except Exception as exc:
            self.status = tr("Reference calibration failed: {error}").format(error=exc)

    def calibration_apply(self):
        """Close after pending field edits and their native computation have finished."""
        self._reference_apply_requested = True

    def calibration_cancel(self):
        """Discard a reference or calculator without changing its parent definition."""
        self._reference_discard = True
        self._reference_cancel.set()
        future, self._reference_future = self._reference_future, None
        if future is not None:
            future.add_done_callback(self._discard_prepared_reference)
        if self.reference_app is not None:
            self.reference_app.close()
            self.reference_app = None
        self.reference_prompt.hide()
        self.reference_window.hide()
        self._cleanup_reference()

    def _cleanup_reference(self):
        """Release prepared reference files and restore the captured host drop endpoints."""
        if self._reference_temp is not None:
            self._reference_temp.cleanup()
            self._reference_temp = None
        self._reference_model = None
        self._reference_apply_requested = False
        self._release_reference_drops()

    @staticmethod
    def _discard_prepared_reference(future):
        """Dispose a late successful preparation even after its parent has closed."""
        try:
            _model, temporary, _context = future.result()
        except Exception:
            return
        temporary.cleanup()

    def _capture_reference_drops(self):
        """Capture existing native host drop endpoints for this modal's lifetime."""
        if self._reference_drop_hooks:
            return
        for name in ("files_dropped", "on_files_dropped", "on_paths_dropped"):
            self._reference_drop_hooks[name] = (
                name in self.host_app.__dict__,
                self.host_app.__dict__.get(name),
            )
            setattr(self.host_app, name, self._reference_drop)

    def _release_reference_drops(self):
        """Restore exactly the host endpoints present before reference capture."""
        if self.host_app is None:
            return
        for name, (was_instance_attribute, value) in self._reference_drop_hooks.items():
            if was_instance_attribute:
                setattr(self.host_app, name, value)
            else:
                self.host_app.__dict__.pop(name, None)
        self._reference_drop_hooks.clear()

    def _reference_drop(self, paths):
        """A reference modal cannot replace the active parent dataset/definition."""
        if self.reference_app is not None and not self.read_only:
            return self.reference_app.files_dropped(paths) is not False
        return True

    def _reference_events(self, box):
        """Forward the host's current native input through the existing child APIs."""
        from emtk import im
        from emtk.events import ALT_MODIFIER, CONTROL_MODIFIER, META_MODIFIER, SHIFT_MODIFIER

        child, io = self.reference_app, im.get_io()
        assert child is not None
        x, y, width, height = box
        px, py = io.mouse_pos
        inside = x <= px < x + width and y <= py < y + height
        modifiers = (
            (SHIFT_MODIFIER if io.key_shift else 0)
            | (CONTROL_MODIFIER if io.key_ctrl else 0)
            | (ALT_MODIFIER if io.key_alt else 0)
            | (META_MODIFIER if io.key_super else 0)
        )
        buttons = sum((1 << index) for index, down in enumerate(io.mouse_down) if down)
        child.pointer_move(px - x, py - y, buttons, modifiers)
        for index in range(3):
            if io.mouse_clicked[index]:
                self._reference_focus = inside
                self._reference_capture = inside
                child.pointer_press(
                    px - x,
                    py - y,
                    1 << index,
                    modifiers,
                    2 if io.mouse_double_clicked[index] else 1,
                )
            if io.mouse_released[index]:
                child.pointer_release(px - x, py - y, 1 << index, modifiers)
                self._reference_capture = False
        if inside and io.mouse_wheel:
            child.wheel(px - x, py - y, io.mouse_wheel, modifiers)
        if self._reference_focus:
            for key, text, mask in io.key_events:
                child.key(key, text, mask)
        self._reference_focus = self._reference_focus and not child.close_requested

    def _draw_reference_dialogs(self, frame):
        """Render prompts and the existing native calculator with clipped child input."""
        from emtk import im

        if self.reference_prompt.open:
            pressed = self.reference_prompt.begin(frame)
            draw_form(self._reference_view["reference_prompt"], self, self._reference_state)
            self.item_rects.update(self._reference_state.rects)
            self.reference_prompt.end()
            if pressed == "close":
                self.calibration_cancel()
        child = self.reference_app
        if child is None:
            return
        self.reference_window.escape_closes = not (
            child.dialog is not None
            or child.help.open
            or child.guide.active
            or child.dataset_picker.is_open
        )
        pressed = self.reference_window.begin(frame)
        draw_form(self._reference_view["calibration_footer"], self, self._reference_state)
        self.item_rects.update(self._reference_state.rects)
        if self.reference_app is not child:
            self.reference_window.end()
            return
        assert child is not None
        x, y = im.get_cursor_screen_pos()
        width, height = im.get_content_region_avail()
        box = (x, y, max(40, width), max(40, height))
        self._reference_events(box)
        self.host_app.draw_child(im.get_current_context().p, child, *box, local_coordinates=True)
        for key, rectangle in child.item_rects.items():
            if rectangle:
                self.item_rects["reference." + key] = (
                    rectangle[0] + x,
                    rectangle[1] + y,
                    *rectangle[2:],
                )
        for state in child.forms.values():
            for key, rectangle in state.rects.items():
                self.item_rects["reference." + key] = (
                    rectangle[0] + x,
                    rectangle[1] + y,
                    *rectangle[2:],
                )
        self.reference_window.end()
        if (
            pressed == "close"
            or child.close_requested
            or (self._reference_apply_requested and not child.job.running)
        ):
            child.close()
            self.reference_app = None
            self.reference_window.hide()
            self._cleanup_reference()
        elif child.animating() or self._reference_future is not None:
            self.host_app.request_frame()

    def _draw_table(self, binding, name, rows):
        from emtk import im
        from emtk.widgets.data_table import draw_table

        line = im.get_text_line_height()
        binding.height = line * 1.35 + min(max(rows, 3), 8) * line * 1.45 + 6.0
        draw_table(binding, name)

    # ------------------------------------------------------------------ detectors / windows sections
    def _windows_section(self):
        from emtk import im

        if self.is_visible("add_inputs"):
            im.align_text_to_frame_padding()
            im.text(tr("PIE Windows"))
            im.same_line(self._width(tr("PIE Windows")))
            width = max(im.get_content_region_avail()[0], 40.0)
            if im.button(tr("Add") + "##add_window", (width, 0.0)):
                self.add_window()
                self._used("add_window")
            self._item(
                "add_window",
                tr("Add a PIE window (0:2048) with a free name; rename and edit it in the table."),
            )
        self._draw_table(self._window_table, "windows", len(self.model.data["windows"]))

    #: Columns the Detectors table drops, in this order, when the page is too narrow for the others (they stay in the model).
    NARROW_COLUMNS = ("gch", "l1", "l2")

    def _narrow_detector_columns(self, width):
        """The Detectors table's columns to hide at *width*, measured in the language in use.

        A column cannot be narrower than its translated header or, for a button column, its translated
        caption, so what fits is a matter of the text, not of a fixed pixel limit (``Löschen`` and
        ``Supprimer`` need more than ``Delete``). Columns go in :attr:`NARROW_COLUMNS` order until the
        rest fits.
        """
        from emtk import im

        self._detector_buttons.fit_columns()
        least = {}
        for column in self._detector_table.control.columns:
            title = tr(column.title) if column.title.strip() else ""
            text = im.calc_text_size(title)[0] + 16.0 if title else 0.0
            least[column.key] = max(36.0, text, column.min_width)
        total = sum(least.values()) + 24.0  # the vertical scroll bar and the table's frame
        hidden = set()
        for key in self.NARROW_COLUMNS:
            if total <= width:
                break
            hidden.add(key)
            total -= least.get(key, 0.0)
        return hidden

    def _detectors_section(self):
        from emtk import im

        if self.is_visible("add_inputs"):
            im.align_text_to_frame_padding()
            im.text(tr("Detectors"))
            im.same_line(self._width(tr("PIE Windows")))
            width = max(im.get_content_region_avail()[0], 40.0)
            if im.button(tr("Add") + "##add_detector", (width, 0.0)):
                self.add_detector()
                self._used("add_detector")
            self._item(
                "add_detector",
                tr("Add a detector (channels 0, 1; range 0:2048) with a free name; rename and edit it in the table."),
            )
        width = im.get_content_region_avail()[0]
        self._compact = width < 520.0
        hidden = self._narrow_detector_columns(width)
        for key in self.NARROW_COLUMNS:
            self._detector_table.control.set_column_hidden(key, key in hidden)
        self._draw_table(self._detector_table, "detectors", len(self.model.data["detectors"]))

    # ------------------------------------------------------------------ LUT handling
    def _toggle_apply_lut(self, checked):
        self.model.data["apply_lut"] = bool(checked)
        self.model.changed()
        self.refresh_preview()
        if checked:
            missing = [
                c
                for c in self.used_channels()
                if not self.model.data.get("channel_luts", {}).get(str(c))
            ]
            if missing:
                self.question = tr(
                    "Channels without a LUT will be read raw: {channels}.\n\nOpen the LUT calculator to compute one now?"
                ).format(channels=", ".join(map(str, missing)))
                self.question_window.show()

    def _lut_section(self):
        from emtk import im

        from chisurf.plugins.emtk_layout import button_row

        changed, value = im.checkbox(
            tr("Apply TAC linearization (LUT) when reading"), bool(self.model.data.get("apply_lut"))
        )
        self._item(
            "apply_lut",
            tr("When checked, each routing channel's assigned LUT linearizes the raw micro-times at read time (needed for e.g. SPC-130). If a used channel has no LUT, you are offered the LUT calculator."),
        )
        if changed:
            self._toggle_apply_lut(value)
            self._used("apply_lut")
        self._draw_table(self._lut_table, "luts", len(self.used_channels()))
        pressed = button_row(
            [
                {
                    "label": tr("Assign LUT..."),
                    "key": "assign",
                    "tip": tr("Assign a LUT file (.npy / .npz / .txt) to the selected channel row."),
                },
                {
                    "label": tr("Configure LUTs..."),
                    "key": "configure",
                    "tip": tr("Open the LUT tools: compute a LUT from the loaded calibration decay (linear region or automatic), assign, export or remove it."),
                },
                {
                    "label": tr("Adjust shifts..."),
                    "key": "shifts",
                    "tip": tr("Visually align the per-channel micro-time shifts on the (LUT-corrected) calibration decay; read a calibration file first."),
                },
            ],
            remember=lambda key: None,
        )
        if pressed == "assign":
            self.assign_lut_dialog()
        elif pressed == "configure":
            self.lut_window.show()
        elif pressed == "shifts":
            self.open_shift_adjuster()
        if pressed:
            self._used(pressed)

    def assign_lut_dialog(self):
        """Choose a LUT file for the selected channel row (Qt: 'Select a channel row first')."""
        if self.selected_channel is None:
            self.status = tr("Assign LUT: select a channel row first.")
            return
        self.browse("lut")

    def open_shift_adjuster(self):
        """Open the shift adjuster, or say that a calibration has to be read first."""
        if not self.model.preview:
            self.status = tr("Adjust shifts: read a calibration TTTR file first (Read in the TTTR Reading routine) so the per-channel decays can be shown.")
            return
        self._shift_draft = {
            int(k): int(v) for k, v in self.model.data.get("channel_shifts", {}).items()
        }
        for key in [k for k in self._text if k.startswith("shift_")]:
            del self._text[key], self._seen[key]
        self.shift_window.show()

    # ------------------------------------------------------------------ page
    def host(self, model, on_edit_setup=None, can_apply=None):
        """Use the hub's authoritative definition while retaining this child's callback."""
        if self.model is not model:
            self._own_on_changed = self.model.on_changed
            self.cancel_read()
            self.calibration_cancel()
            self.model = model
        self.hosted = True
        self.on_edit_setup = on_edit_setup
        self._hosted_can_apply = can_apply
        self.item_rects.clear()

    def hosted_changed(self, settings):
        """Deliver a private copy, or defer it while this child is read-only."""
        self._hosted_pending = copy.deepcopy(settings)
        self._poll_hosted()

    def _poll_hosted(self):
        """Apply the latest shared definition once the child can accept edits."""
        if self.read_only or self._hosted_pending is None:
            return
        if callable(self._hosted_can_apply) and not self._hosted_can_apply():
            return
        pending = self._hosted_pending
        if callable(self._own_on_changed):
            self._own_on_changed(copy.deepcopy(pending))
        self._hosted_pending = None

    def _hosted_setup_name(self):
        """Describe the definition whose full editor lives at the hub's setup step."""
        return str(tr("Setup: {name}")).format(name=self.model.current_name or tr("Unsaved"))

    def edit_setup(self):
        """Return the user to the hub's shared setup editor."""
        if callable(self.on_edit_setup):
            self.on_edit_setup()

    def _item_used(self, name):
        """Forward declared hosted-control use to the child's existing guide callback."""
        if callable(self.on_used):
            self.on_used(name)

    def _draw_hosted(self):
        """Render only the declared setup summary and Edit setup action."""
        self._poll_hosted()
        draw_form(self._hosted_spec, self, self._hosted_form)
        self.item_rects.update(self._hosted_form.rects)

    def draw(self):
        if self.hosted:
            return self._draw_hosted()
        from emtk import im

        self.poll()
        im.begin_disabled(
            self._future is not None
            or self._reference_future is not None
            or self.reference_app is not None
            or self.reference_prompt.open
            or self.read_only
            or self.json_window.open
        )
        self._setup_row()
        for key, title, _opened in SECTIONS:
            if key == "reading" and not self.is_visible("tttr_reading"):
                continue
            if key in ("windows", "detectors") and not self.is_visible("tables"):
                continue
            tip = {
                "reading": tr("File type, timing and binning used to read TTTR files."),
                "windows": tr("PIE excitation windows (start and end TAC channel)."),
                "detectors": tr("Detectors: routing channels, micro-time gates and polarization factors."),
                "lut": tr("TAC linearization tables and micro-time shifts per routing channel."),
            }[key]
            if key == "detectors":
                right = self._width(tr("Polarization resolved")) + 28.0
                opened = self._section(key, title, tip, right=right)
                im.same_line()
                changed, value = im.checkbox(
                    tr("Polarization resolved"),
                    bool(self.model.data.get("polarization_resolved", True)),
                )
                self._item(
                    "polarization",
                    tr("ON: each detector's routing channels are interleaved parallel/perpendicular (VV/VH) for anisotropy. OFF: one unpolarized stream per detector."),
                )
                if changed:
                    self.model.data["polarization_resolved"] = value
                    self.model.changed()
            else:
                opened = self._section(key, title, tip)
            if opened:
                {
                    "reading": self._reading_section,
                    "windows": self._windows_section,
                    "detectors": self._detectors_section,
                    "lut": self._lut_section,
                }[key]()
        draw_form(self._json_view["toolbar"], self, self._json_toolbar_state)
        self.item_rects.update(self._json_toolbar_state.rects)
        if self.show_save_definition or self.show_setups_file:
            draw_form(self._io_view, self, self._io_state)
            self.item_rects.update(self._io_state.rects)
        im.same_line()
        optical = tr("Optical Setup...")  # measured as drawn: the translation is longer than the source
        width = self._width(optical)
        im.dummy(
            max(im.get_content_region_avail()[0] - width - im.get_style().item_spacing[0], 0.0), 1.0
        )
        im.same_line()
        if im.button(optical):
            self.optical_window.show()
            self._used("optical")
        self._item(
            "optical",
            tr("Open the light-path editor: configure filters, dyes and detectors, and compute Foerster radii and cross-talk."),
        )
        im.end_disabled()
        if self._future is not None or self._reference_future is not None:
            if im.button(tr("Cancel calibration read")):
                self.cancel_read()
            im.set_item_tooltip(tr("Cancel staged reading and keep previous calibration values."))
        if self.status:
            im.text_wrapped(self.status)

    # ------------------------------------------------------------------ plots and windows
    def refresh_preview(self):
        if self.model.preview_path:
            self.read(self.model.preview_path, preserve_timing=True)

    def _plot_decays(self, size, shifts=None, gates=True):
        """The per-routing-channel decays (log counts) with the PIE windows and detector gates as draggable lines."""
        from emtk import implot

        if not self.model.preview:
            from emtk import im

            im.text_wrapped(
                tr("Read a measurement to see the micro-time decay of every routing channel.")
            )
            return
        if implot.begin_plot(tr("Micro-time decay") + "##plot", size):
            implot.setup_axes(tr("Micro-time channel"), tr("Counts"))
            implot.setup_axis_scale(implot.AXIS_Y1, implot.SCALE_LOG10)
            length = float(max(len(counts) for counts in self.model.preview.values()))
            implot.setup_axis_limits(implot.AXIS_X1, 0.0, length)
            for channel, counts in self.model.preview.items():
                counts = np.asarray(counts, dtype=float)
                if shifts:
                    counts = np.roll(counts, int(shifts.get(channel, 0)) % max(len(counts), 1))
                implot.plot_line(
                    tr("Routing {channel}").format(channel=channel),
                    np.arange(len(counts), dtype=float),
                    np.where(counts > 0, counts, np.nan),
                )
            if gates:
                self._plot_gates(implot)
            implot.end_plot()

    def _plot_gates(self, implot):
        for i, (name, bounds) in enumerate(self.model.data["windows"].items()):
            low = implot.drag_line_x(1000 + i * 2, float(bounds[0]))
            high = implot.drag_line_x(1001 + i * 2, float(bounds[1]))
            if low.modified or high.modified:
                lo, hi = sorted([int(low.value), int(high.value)])
                if 0 <= lo < hi:
                    self.model.data["windows"][name] = [lo, hi]
                    self.model.changed()
                    self._refresh_rows()
        gate_id = 2000
        for info in self.model.data["detectors"].values():
            for index, bounds in enumerate(info.get("micro_time_ranges", [])):
                low = implot.drag_line_x(gate_id, float(bounds[0]))
                high = implot.drag_line_x(gate_id + 1, float(bounds[1]))
                gate_id += 2
                if low.modified or high.modified:
                    lo, hi = sorted([int(low.value), int(high.value)])
                    if 0 <= lo < hi:
                        info["micro_time_ranges"][index] = [lo, hi]
                        self.model.changed()
                        self._refresh_rows()

    def _optical_controls(self):
        if self.optical is None:
            from chisurf.emtk.optical_configuration import OpticalConfigurationWidget

            self.optical = OpticalConfigurationWidget(
                self.model.data.get("optical_config"),
                list(self.model.data["detectors"]),
                on_changed=self._optical_changed,
                auto_recalculate=False,
            )
        self.optical.draw()

    def _optical_changed(self, config):
        self.model.data["optical_config"] = copy.deepcopy(config)
        self.model.changed()

    def _draw_window(self, window, frame, body):
        """A floating window: draw *body* in it; True when its close button was pressed."""
        if not window.open:
            return False
        pressed = window.begin(frame)
        body()
        window.end()
        if pressed == "close":
            window.hide()
        return pressed == "close"

    def draw_prompt(self, frame):
        """The name prompt (Save, Rename) and the confirmations (Delete, overwrite) of the Setup row."""
        from emtk import im

        bar = self.toolbar
        window = self.prompt_window
        if bar.dialog and not window.open:
            window.show()
        if not bar.dialog and window.open:
            window.hide()
        if not window.open:
            return
        titles = {
            SAVE: tr("Save setup"),
            RENAME: tr("Rename setup"),
            DELETE: tr("Confirm deletion"),
            OVERWRITE: tr("Setup exists"),
        }
        window.title = titles.get(bar.dialog, tr("Setup"))
        pressed = window.begin(frame)
        kind = bar.dialog
        if kind in (SAVE, RENAME):
            im.text(
                tr("Enter a name for this setup:")
                if kind == SAVE
                else tr("Enter a new name for this setup:")
            )
            im.set_next_item_width(-1.0)
            changed, value = im.input_text("##setup_name_prompt", bar.name_text)
            im.set_item_tooltip(tr("The name the setup is stored under."))
            self.item_rects["name_prompt"] = im.get_item_rect()
            if changed:
                bar.name_text = value
            ok, ok_tip, keep = (
                (tr("Save") if kind == SAVE else tr("Rename")),
                (
                    tr("Store the setup under this name.")
                    if kind == SAVE
                    else tr("Rename the selected setup.")
                ),
                tr("Cancel"),
            )
        elif kind == DELETE:
            im.text_wrapped(
                tr("Are you sure you want to delete the setup '{name}'?").format(name=bar.selected)
            )
            ok, ok_tip, keep = tr("Delete"), tr("Delete this saved setup from its store."), tr("Keep setup")
        else:
            im.text_wrapped(
                tr("A setup named '{name}' already exists. Do you want to overwrite it?").format(
                    name=bar._pending_name
                )
            )
            ok, ok_tip, keep = (
                tr("Overwrite"),
                tr("Replace the existing setup by the renamed one."),
                tr("Cancel"),
            )
        if im.button(ok):
            bar.confirm()
            self._used("confirm")
        self._item("confirm", ok_tip)
        im.same_line()
        if im.button(keep):
            bar.cancel()
        im.set_item_tooltip(tr("Close this prompt; nothing changes."))
        window.end()
        if pressed == "close":
            bar.cancel()

    def _draw_question(self, frame):
        from emtk import im

        if not self.question_window.open:
            return
        pressed = self.question_window.begin(frame)
        im.text_wrapped(self.question)
        if im.button(tr("Yes")):
            self.question_window.hide()
            self.lut_window.show()
        im.set_item_tooltip(tr("Open the LUT tools to compute a LUT now."))
        im.same_line()
        if im.button(tr("No")):
            self.question_window.hide()
        im.set_item_tooltip(tr("Keep reading the channels without a LUT raw."))
        self.question_window.end()
        if pressed == "close":
            self.question_window.hide()

    def _help_body(self):
        from emtk import im

        im.text_wrapped(HELP_TEXT)
        im.text_wrapped(
            tr(
                "Edit JSON opens the complete working definition, including calibration identifiers and metadata not shown in the tables. Apply validates the draft and refreshes the page; Cancel keeps the previous definition. Derived channel and timing fields are regenerated. Save the named setup separately."
            )
        )

    def _lut_tools_body(self):
        from emtk import im

        from chisurf.plugins.emtk_layout import button_row

        channels = self.used_channels()
        if not channels:
            im.text_wrapped(
                tr("Define detectors or read a measurement to discover routing channels.")
            )
            return
        self.lut_channel()
        im.text(tr("Routing channel:"))
        im.same_line()
        im.set_next_item_width(NUMBER_W)
        changed, index = im.combo(
            "##lut_channel", channels.index(self.selected_channel), [str(c) for c in channels]
        )
        im.set_item_tooltip(
            tr("Routing channel whose LUT is computed, assigned, exported or removed.")
        )
        if changed:
            self.selected_channel = channels[index]
        key = str(self.selected_channel)
        im.text(
            tr("LUT: {count} entries").format(
                count=len(self.model.data.get("channel_luts", {}).get(key, []))
            )
        )
        for attribute, label, tip in (
            (
                "lut_start",
                tr("Linear region start"),
                tr("First channel of the uniform-illumination linear calibration region."),
            ),
            (
                "lut_stop",
                tr("Linear region stop"),
                tr("Last channel of the linear calibration region; Auto-detect infers it."),
            ),
        ):
            im.set_next_item_width(NUMBER_W)
            value = self._number_input(attribute, getattr(self, attribute), tip, int, attribute)
            im.same_line()
            im.text(label)
            if value is not None:
                setattr(self, attribute, value)
        pressed = button_row(
            [
                {
                    "label": tr("Compute TAC LUT"),
                    "key": "compute",
                    "tip": tr("Build a TAC table from the selected channel histogram and the entered linear region."),
                },
                {
                    "label": tr("Auto-detect TAC LUT"),
                    "key": "auto",
                    "tip": tr("Infer a populated linear region and calculate its TAC correction."),
                },
                {
                    "label": tr("Assign LUT file"),
                    "key": "assign",
                    "tip": tr("Load a TAC linearization table for the selected routing channel."),
                },
                {
                    "label": tr("Export channel LUT"),
                    "key": "export",
                    "tip": tr("Save this channel correction as a reusable TAC table."),
                },
                {
                    "label": tr("Remove channel LUT"),
                    "key": "remove",
                    "tip": tr("Remove the correction table from this channel."),
                },
            ]
        )
        if pressed == "compute":
            self._compute_lut(self.lut_start, self.lut_stop)
        elif pressed == "auto":
            self._compute_lut()
        elif pressed == "assign":
            self.browse("lut")
        elif pressed == "export":
            self.browse("export_lut")
        elif pressed == "remove":
            self._remove_lut()

    def lut_channel(self):
        """The routing channel the LUT tools act on: the selected row, else the first channel in use."""
        channels = self.used_channels()
        if self.selected_channel not in channels:
            self.selected_channel = channels[0] if channels else None
        return self.selected_channel

    def _compute_lut(self, start=None, stop=None):
        channel = self.lut_channel()
        if channel is None:
            self.status = (
                tr("Error: Define a detector or read a measurement to discover routing channels.")
            )
            return
        if self._call(self.model.compute_lut, channel, start, stop) is not None:
            self._lut_sig = None
            self.refresh_preview()

    def _remove_lut(self):
        channel = self.lut_channel()
        self.model.data.get("channel_luts", {}).pop(str(channel), None)
        self.model.data.get("channel_lut_sources", {}).pop(str(channel), None)
        self.model.changed()
        self._lut_sig = None
        self.refresh_preview()

    def _shift_body(self):
        from emtk import im

        im.text_wrapped(
            tr(
                "Align each routing channel's micro-time histogram. Shifts wrap and are applied on the LUT-linearized axis."
            )
            if self.model.data.get("apply_lut")
            else tr("Align each routing channel's micro-time histogram. Shifts wrap.")
        )
        self._plot_decays((-1.0, 260.0), shifts=self._shift_draft, gates=False)
        for channel in sorted(self.model.preview):
            im.text(tr("ch {channel}").format(channel=channel))
            im.same_line()
            im.set_next_item_width(NUMBER_W)
            value = self._number_input(
                f"shift_{channel}",
                int(self._shift_draft.get(channel, 0)),
                tr("Micro-time shift of routing channel {channel}, in bins (the histogram wraps).").format(
                    channel=channel
                ),
                int,
                f"shift_{channel}",
            )
            if value is not None:
                self._shift_draft[channel] = value
        if im.button(tr("OK") + "##shift_ok"):
            self.model.data["channel_shifts"] = {
                str(c): int(s) for c, s in self._shift_draft.items() if int(s)
            }
            self.model.changed()
            self._lut_sig = None
            self.refresh_preview()
            self.shift_window.hide()
        im.set_item_tooltip(tr("Keep the shifts shown."))
        im.same_line()
        if action_button(
            "cancel", tooltip=tr("Close without changing the shifts."), id="shift_cancel"
        ):
            self.shift_window.hide()

    def _preview_body(self):
        from emtk import im

        self._plot_decays((-1.0, max(im.get_content_region_avail()[1] - 6.0, 120.0)))

    def draw_dialogs(self, frame):
        """Draw the floating windows: prompts, file chooser, plot, LUT tools, shift adjuster, optical setup, help."""
        if self.hosted:
            return self._poll_hosted()
        from emtk import im

        self.draw_prompt(frame)
        if self._draw_window(self.json_window, frame, self._json_body):
            self.cancel_json()
        self._draw_reference_dialogs(frame)
        self._draw_question(frame)
        self._draw_window(self.help_window, frame, self._help_body)
        self._draw_window(self.preview_window, frame, self._preview_body)
        self._draw_window(self.lut_window, frame, self._lut_tools_body)
        self._draw_window(self.shift_window, frame, self._shift_body)
        self._draw_window(self.optical_window, frame, self._optical_controls)
        if self.optical is not None:
            self.optical.draw_dialogs(frame)
        if self.dialog is None:
            return
        if im.begin(tr("Channel definition file chooser")):
            result = self.dialog.draw()
            if result:
                try:
                    if self.action == "reference_calibration":
                        self._read_reference(result[0])
                    elif self.action == "measurement":
                        self.read(result[0])
                    elif self.action == "lut":
                        self._assign_lut(result[0])
                    elif self.action == "export_lut":
                        self.model.export_lut(self.selected_channel, result[0])
                    elif self.action == "save_definition":
                        self.model.export_definition(
                            result[0],
                            update_named=bool(
                                self.model.current_name in self.model.setups
                                and self.toolbar.is_owner()
                            ),
                        )
                        self.status = tr("Complete detector definition saved.")
                        if callable(self.on_definition_saved):
                            self.on_definition_saved(result[0])
                    elif self.action == "import_setups":
                        self.files_dropped([result[0]])
                    else:
                        from chisurf.core.data_io.detector_setups import save_detector_setups

                        save_detector_setups(
                            {"setups": self.model.setups, "last_used": self.model.current_name},
                            result[0],
                        )
                    self.dialog = None
                except Exception as exc:
                    self.status = tr("Error: {error}").format(error=tr(str(exc)))
                    self.dialog = None
            elif result is False:
                self.dialog = None
                if self.action == "reference_calibration":
                    self.calibration_cancel()
        im.end()

    # ------------------------------------------------------------------ reading
    def read(self, path, preserve_timing=False):
        if self._future is not None:
            self.status = tr("A calibration read is already running.")
            return
        self._cancel.clear()
        snapshot = ChannelDefinition(self.model.get_settings())
        self.status = tr("Reading calibration header and microtime histograms ...")
        self._future = self._executor.submit(self._read, snapshot, path, preserve_timing)

    def _read(self, snapshot, path, preserve_timing=False):
        reading = copy.deepcopy(snapshot.data["tttr_reading"])
        snapshot.read_tttr(path, cancel_cb=self._cancel.is_set)
        if preserve_timing:
            snapshot.data["tttr_reading"] = reading
        if self._cancel.is_set():
            raise InterruptedError(tr("Calibration read cancelled"))
        return snapshot

    def poll(self):
        if self.hosted:
            return self._poll_hosted()
        self._poll_reference()
        if self._future is None or not self._future.done():
            return
        future, self._future = self._future, None
        try:
            snapshot = future.result()
            if self._cancel.is_set():
                raise InterruptedError(tr("Calibration read cancelled"))
            self.model.data, self.model.preview, self.model.preview_path, self.model.raw_preview = (
                snapshot.data,
                snapshot.preview,
                snapshot.preview_path,
                snapshot.raw_preview,
            )
            self.model.changed()
            if self.model.raw_preview:
                self.lut_stop = len(next(iter(self.model.raw_preview.values()))) - 1
            self.status = tr("Header timing and per-routing-channel decay histograms loaded.")
        except Exception as exc:
            self.status = str(exc) if self._cancel.is_set() else tr("Error: {error}").format(error=exc)

    def cancel_read(self):
        self._cancel.set()
        self._reference_cancel.set()

    def files_dropped(self, paths):
        """Files dropped on the window: a ``.json`` library becomes the setups file, a LUT table is assigned to the
        selected channel, anything else is read as a measurement. Returns whether it did something."""
        if self.hosted:
            return False
        for path in (str(p) for p in paths):
            suffix = path.lower().rsplit(".", 1)[-1] if "." in path else ""
            if suffix == "json":
                self.model.file_path = path
                self.toolbar.reload()
            elif suffix in ("npy", "npz", "lut"):
                if self.selected_channel is None:
                    self.status = tr("Assign LUT: select a channel row first.")
                    return True
                self._call(self._assign_lut, path)
            else:
                self.read(path)
            return True
        return False

    def _assign_lut(self, path):
        self.model.assign_lut(self.selected_channel, path)
        self.model.data.setdefault("channel_lut_sources", {})[str(self.selected_channel)] = (
            str(path).replace("\\", "/").rsplit("/", 1)[-1]
        )
        self._lut_sig = None
        self.refresh_preview()

    def browse(self, action):
        from emtk.file_dialog import FileDialog

        self.action = action
        mode = "save" if action in ("save_definition", "export_setups", "export_lut") else "open"
        patterns = [
            "*.json",
            "*.ptu",
            "*.pto",
            "*.spc",
            "*.set",
            "*.ht3",
            "*.pt3",
            "*.h5",
            "*.txt",
            "*.csv",
            "*.lut",
            "*.npy",
            "*.npz",
        ]
        self.dialog = FileDialog(
            tr("Detector setup / calibration file"),
            mode=mode,
            filters=[(tr("All supported files"), patterns)],
            filename=(
                "tac_lut.json"
                if action == "export_lut"
                else "detector_definition.json"
                if action == "save_definition"
                else "detector_setups.json"
            )
            if mode == "save"
            else None,
        )

    def close(self):
        self._closing = True
        self.toolbar.wait()  # a background read of the setup store must not outlive the window
        self.calibration_cancel()
        self.cancel_read()
        self._executor.shutdown(wait=False, cancel_futures=True)
        if self.optical is not None:
            self.optical.close()
