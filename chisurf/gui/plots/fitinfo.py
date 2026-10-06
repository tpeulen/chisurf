"""The fit window's *Info* page: the fit's report, and its analysis record.

The page shows the fit's report (an emtk read-only text view). Its settings --
what the main window's *Plot settings* dock shows while the page is current --
are the analysis record, in four tabs: *Analysis* (id, type, sample and
conditions), *Metadata* (key / value rows), *External data* (where the raw data
is) and *Export* (the flrCIF preview, copy and save). They are declared in
``fitinfo_settings.view.json`` and drawn by emtk; the rows of the two tables
are the Qt-free models :class:`MetadataRows` and :class:`ExternalRows`.
"""

from __future__ import annotations

import html
import io
import json
import re
import uuid
from pathlib import Path
from typing import Any, Callable

import numpy as np

import chisurf.core.fitting
from chisurf.core.registry.file_formats import FILE_FORMATS as _FILE_FORMATS
from chisurf.gui.glyphs import Glyphs
from chisurf.gui.plots import emtk_notes, plotbase
from chisurf.gui.plots.emtk_text_view import EmtkTextView


def _format_for_path(path: str) -> str:
    """The format column's guess for a dropped or typed path."""
    suffix = Path(path).suffix.lower()
    if suffix in {".ptu", ".bin", ".t3r", ".t3z", ".t3x"}:
        return "ptu"
    if suffix in {".tttr", ".hdf5", ".h5"}:
        return "tttr"
    if suffix in {".csv", ".txt"}:
        return suffix.lstrip(".")
    return ""


def _html_to_text(markup: str) -> str:
    """Flatten a model's ``summary_html`` to the report's plain text."""
    text = re.sub(r"(?i)<\s*(br|/p|/div|/li|/tr|/h[1-6])\s*/?>", "\n", markup)
    text = re.sub(r"<[^>]+>", "", text)
    lines = [" ".join(line.split()) for line in html.unescape(text).splitlines()]
    return "\n".join(line for line in lines if line).strip()


class _Rows:
    """Editable table rows with a picked row: the base of the two tab models."""

    def __init__(self, on_changed: Callable[[], None]) -> None:
        self.rows: list[dict] = []
        self.selected_row = ""
        self._next = 0
        self._on_changed = on_changed

    def _add(self, **fields: str) -> dict:
        self._next += 1
        row = {"_row": str(self._next), **{k: str(v) for k, v in fields.items()}}
        self.rows.append(row)
        return row

    def _selected(self) -> dict | None:
        return next((r for r in self.rows if r["_row"] == self.selected_row), None)

    def select_row(self, record: dict | None) -> None:
        """The table's selection changed."""
        if record is not None:
            self.selected_row = str(record.get("_row", ""))

    def edited(self, record: dict, key: str, value: Any) -> None:
        """A cell was typed into."""
        record[key] = str(value).strip()
        self._on_changed()

    def enabled(self, name: str) -> bool:
        """Removing needs a picked row."""
        if name == "delete_row":
            return self._selected() is not None
        return True

    def delete_row(self) -> None:
        """Remove the picked row."""
        row = self._selected()
        if row is not None:
            self.rows.remove(row)
            self.selected_row = ""
            self._on_changed()


class MetadataRows(_Rows):
    """The *Metadata* tab: key / value rows, keys from the mmCIF catalogue."""

    def __init__(self, on_changed: Callable[[], None]) -> None:
        super().__init__(on_changed)
        self._catalogue: list[str] | None = None

    # -- the data (the vocabulary the page speaks) ----------------------------
    def set_data(self, data: list[dict[str, str]]) -> None:
        """Replace every row with *data* (``{"key", "value"}`` dicts).

        Rows that already say the same are kept as they are -- with the picked
        row and any row still being filled in -- because every edit writes the
        metadata and the page then reloads it.
        """
        wanted = {
            str(d.get("key", "")).strip(): str(d.get("value", "")).strip()
            for d in data
            if str(d.get("key", "")).strip()
        }
        if wanted == self.as_dict():
            return
        self.rows, self.selected_row = [], ""
        for item in data:
            self._add(key=item.get("key", ""), value=item.get("value", ""))

    def get_data(self) -> list[dict[str, str]]:
        """The rows with a key, as ``{"key", "value"}`` dicts."""
        return [
            {"key": r["key"].strip(), "value": r["value"].strip()}
            for r in self.rows
            if r["key"].strip()
        ]

    def as_dict(self) -> dict[str, str]:
        """The metadata as a flat key -> value dict."""
        return {d["key"]: d["value"] for d in self.get_data()}

    def metadata_rows(self) -> list[dict]:
        """The table's source."""
        return self.rows

    # -- the key catalogue ----------------------------------------------------
    def catalogue(self) -> list[str]:
        """Every key offered: the rows' own keys first, then the mmCIF catalogue."""
        if self._catalogue is None:
            from chisurf.core.fio.mmcif.metadata_keys import all_metadata_keys

            self._catalogue = list(all_metadata_keys())
        extra = [r["key"] for r in self.rows if r["key"] and r["key"] not in self._catalogue]
        return [""] + list(dict.fromkeys(extra)) + self._catalogue

    def key_options(self) -> list[tuple[str, str]]:
        """The *Key* choice's options."""
        return [(k, k or "(pick a key from the catalogue)") for k in self.catalogue()]

    @property
    def detail_key(self) -> str:
        """The picked row's key."""
        row = self._selected()
        return row["key"] if row is not None else ""

    @detail_key.setter
    def detail_key(self, key: str) -> None:
        row = self._selected()
        if row is None:
            row = self._add(key="", value="")
            self.selected_row = row["_row"]
        row["key"] = str(key or "").strip()
        self._on_changed()

    def key_help(self) -> str:
        """What the picked key means."""
        from chisurf.core.fio.mmcif.metadata_keys import key_description

        key = self.detail_key
        if not key:
            return "Pick a row, then its key from the mmCIF catalogue (type to filter)."
        return f"{key}: {key_description(key) or 'no description in the dictionary.'}"

    def add_row(self) -> None:
        """Add an empty row and pick it."""
        row = self._add(key="", value="")
        self.selected_row = row["_row"]


class ExternalRows(_Rows):
    """The *External data* tab: file path / URL and format of each raw data file."""

    def set_streams(self, streams: list[dict]) -> None:
        """Replace every row with the analysis's photon streams (unless they say the same)."""
        wanted = [
            (str(s.get("file_path") or "").strip(), str(s.get("file_format") or "").strip())
            for s in streams
            if str(s.get("file_path") or "").strip()
        ]
        if wanted == self.streams():
            return
        self.rows, self.selected_row = [], ""
        for stream in streams:
            self._add(
                file_path=stream.get("file_path") or "",
                file_format=stream.get("file_format") or "",
            )

    def external_rows(self) -> list[dict]:
        """The table's source."""
        return self.rows

    def streams(self) -> list[tuple[str, str]]:
        """``(path, format)`` of every row with a path."""
        return [
            (r["file_path"].strip(), r["file_format"].strip())
            for r in self.rows
            if r["file_path"].strip()
        ]

    def add_paths(self, paths: list[str]) -> int:
        """Add a row per path (a drop); return how many were added."""
        added = 0
        for path in paths:
            path = str(path or "").strip()
            if path:
                self._add(file_path=path, file_format=_format_for_path(path))
                added += 1
        if added:
            self._on_changed()
        return added

    def add_row(self) -> None:
        """Add an empty row to type a path into, and pick it."""
        row = self._add(file_path="", file_format="")
        self.selected_row = row["_row"]

    def drop_hint(self) -> str:
        """How rows get here."""
        return (
            "Drag & drop files onto this panel to add external data references "
            "(PTU/TTTR/CSV). Detector / channel info goes in the Metadata tab."
        )


class _ReadOnlyBridge:
    """The analysis-id line: ``setText`` fills the emtk field, ``text`` reads it."""

    def __init__(self, form, attribute: str) -> None:
        self._form = form
        self._attribute = attribute

    def setText(self, text: str) -> None:  # noqa: N802 - Qt's spelling
        getattr(self._form, f"set_{self._attribute}")(str(text))

    def text(self) -> str:
        return getattr(self._form, self._attribute).text


class _LineBridge:
    """A one-line field: the Qt ``text``/``setText`` surface on the emtk form."""

    def __init__(self, form, attribute: str, reader: Callable[[], str]) -> None:
        self._form = form
        self._attribute = attribute
        self._reader = reader

    def setText(self, text: str) -> None:  # noqa: N802 - Qt's spelling
        getattr(self._form, f"set_{self._attribute}")(str(text))

    def text(self) -> str:
        return self._reader()


class _SampleComboBridge:
    """The editable sample combo: Qt's surface over the emtk EditableComboBox."""

    def __init__(self, page) -> None:
        self._page = page

    @property
    def _combo(self):
        return self._page.analysis_form.sample

    def setEditText(self, text: str) -> None:  # noqa: N802 - Qt's spelling
        self._combo.set_text(str(text))
        self._page._update_sample_uuid_display()
        self._page._on_changed()

    def currentText(self) -> str:  # noqa: N802 - Qt's spelling
        return self._combo.text



class _UuidLabelBridge:
    """The sample-UUID line: Qt's ``setText``/``text`` on the form's caption."""

    def __init__(self, form) -> None:
        self._form = form

    def setText(self, text: str) -> None:  # noqa: N802 - Qt's spelling
        self._form.set_uuid(str(text))

    def text(self) -> str:
        return self._form.uuid_text


class _DetailBridge:
    """A detail editor: the QPlainTextEdit surface on an emtk detail editor."""

    def __init__(self, detail) -> None:
        self._detail = detail

    def setPlainText(self, text: str) -> None:  # noqa: N802 - Qt's spelling
        self._detail.set_text(str(text))

    def toPlainText(self) -> str:  # noqa: N802 - Qt's spelling
        return self._detail.text


class FitInfo(plotbase.Plot):
    """The *Info* page: the fit's report; its settings are the analysis record."""

    name = "Info"
    settings_view = "fitinfo_settings.view.json"
    #: The four tabs of the settings, in order (panel titles of the spec).
    TABS = ("Analysis", "Metadata", "External data", "Export")

    def __init__(self, fit: chisurf.core.fitting.fit.FitGroup, parent=None, **kwargs):
        super().__init__(fit, parent=parent, **kwargs)
        self.analysis_id = getattr(fit, "name", None) or str(getattr(fit, "fit_idx", "analysis_1"))
        self.db = self._find_flr_database()
        self._memory_metadata = getattr(fit, "flr_metadata", {})
        self._memory_streams = getattr(fit, "flr_photon_streams", [])

        #: The report, the page's body.
        self.textedit = EmtkTextView()
        #: The Export tab's mmCIF preview.
        self.cif_preview = EmtkTextView()
        self.tabs = emtk_notes.Tabs(self.TABS)
        self._shown_tab: int | None = None
        self._save_dialog = None
        self._suppress_change = True
        self.metadata_editor = MetadataRows(on_changed=self._on_changed)
        self.external = ExternalRows(on_changed=self._on_external_table_changed)
        self._build_analysis_tab()
        self._populate_sample_combo()
        self._suppress_change = False
        self._reload_record()
        self._update_cif_preview(full=False)

    # -- body and settings --------------------------------------------------
    def emtk_body(self):
        """The report fills the page."""
        return self.textedit.editor

    def refreshables(self) -> list:
        """The report repaints when its text changes."""
        return [self.textedit]

    def set_settings_refresh(self, callback: Callable[[], None] | None) -> None:
        """What redraws the *Plot settings* dock; the mmCIF preview redraws it too."""
        super().set_settings_refresh(callback)
        self.cif_preview.set_refresh_target(callback)

    def register_settings_sections(self, form) -> None:
        """The analysis form and the mmCIF preview are drawn by the page."""
        form.custom["analysis_form"] = self._draw_analysis_form
        form.custom["cif_preview"] = self._draw_cif_preview

    def draw_settings(self) -> None:
        """The four tabs of the analysis record."""
        from emtk.view_form import draw_form, find_section

        spec = self.settings_spec()
        models = (self, self.metadata_editor, self.external, self)

        def body(index: int) -> None:
            if index != self._shown_tab:
                self._shown_tab = index
                if self.TABS[index] == "Export":
                    self._update_cif_preview(full=False)
            panel = find_section(spec, self.TABS[index])
            draw_form(panel, models[index], self.settings_form, titles=False)

        self.tabs.draw("fitinfo-tabs", body)

    def get_settings_state(self) -> dict:
        """The tab shown in the settings."""
        return {"tab": self.TABS[self.tabs.current]}

    def set_settings_state(self, state: dict) -> None:
        """Show the tab :meth:`get_settings_state` saved."""
        tab = (state or {}).get("tab")
        if tab in self.TABS:
            self.tabs.select(self.TABS.index(tab))

    def on_paths_dropped(self, paths: list[str]) -> None:
        """Files dropped on the settings become external data references."""
        self.tabs.select(self.TABS.index("External data"))
        self.external.add_paths(list(paths))

    def _draw_analysis_form(self, section, model, state, width: float) -> None:
        from emtk import im

        im.host_control("##fitinfo-analysis", self.analysis_form, (width, 0.0))
        if section.get("description"):
            im.set_item_tooltip(str(section["description"]))

    def _draw_cif_preview(self, section, model, state, width: float) -> None:
        from emtk import im

        dialog = self._save_dialog
        if dialog is not None:
            result = dialog.draw()
            if result:
                self._write_cif(result[0])
                self._save_dialog = None
            elif result is False:
                self._save_dialog = None
            return
        im.host_control("##fitinfo-cif", self.cif_preview.editor, (width, 0.0))

    def _find_flr_database(self):
        for obj in (self.fit, getattr(self.fit, "model", None)):
            for attr in ("fluorophore_database", "db", "mmcif_db"):
                value = getattr(obj, attr, None)
                if value is not None:
                    return value
        return None

    def _get_metadata(self):
        if self.db is not None:
            return self.db.get_analysis_metadata(self.analysis_id)
        return dict(getattr(self.fit, "flr_metadata", self._memory_metadata))

    def _set_metadata(self, metadata):
        if self.db is not None:
            self.db.set_analysis_metadata(self.analysis_id, metadata)
        else:
            self._memory_metadata = dict(metadata)
            self.fit.flr_metadata = self._memory_metadata

    @staticmethod
    def _is_tttr_stream(stream: dict) -> bool:
        """Check if a photon stream originates from a TTTR file format.

        Uses the FILE_FORMATS registry (``chisurf/core/file_formats.json``).
        A format is considered TTTR if its entry has a non-null
        ``tttrlib_container`` or ``reading_routine``.
        """
        fp = stream.get("file_path") or ""
        fmt = stream.get("file_format") or ""
        if not fp and not fmt:
            return False
        # Try matching by file_format name first (e.g. "PicoQuant PTU").
        if fmt:
            fmt_lower = fmt.lower().strip()
            for info in _FILE_FORMATS.values():
                name = (info.get("name") or "").lower()
                routine = info.get("reading_routine")
                container = info.get("tttrlib_container")
                if fmt_lower in (name, routine or "", container or ""):
                    if routine or container:
                        return True
        # Fallback: look up by file extension.
        info = _FILE_FORMATS.get(Path(fp).suffix.lower())
        if info is not None:
            return bool(info.get("tttrlib_container") or info.get("reading_routine"))
        return False

    def _photon_streams_for_display(self) -> list[dict]:
        """Return photon streams that should be shown in the fitinfo plot.

        Only streams originating from TTTR files are included. Non-TTTR
        entries (e.g. TCSPC CSV or text files) are excluded.
        """
        raw = (
            self.db.get_photon_streams(self.analysis_id)
            if self.db is not None
            else getattr(self.fit, "flr_photon_streams", self._memory_streams)
        )
        return [s for s in raw if self._is_tttr_stream(s)]

    # ── Analysis tab ───────────────────────────────────────────────

    def _build_analysis_tab(self):
        from .emtk_analysis_form import EmtkAnalysisForm

        # The emtk fields report changes as they are filled, so the
        # construction prefill must not persist anything (_suppress_change).
        self.analysis_form = EmtkAnalysisForm(
            on_generate_uuid=self._generate_sample_uuid,
            on_changed=self._on_changed,
        )
        # Bridges: every existing reader/writer keeps its vocabulary.
        self.analysis_id_edit = _ReadOnlyBridge(self.analysis_form, "analysis_id")
        self.method_edit = _LineBridge(self.analysis_form, "method", self.analysis_form.method_value)
        self.sample_combo = _SampleComboBridge(self)
        self.sample_uuid_label = _UuidLabelBridge(self.analysis_form)
        self.sample_details_edit = _DetailBridge(self.analysis_form.sample_details)
        self.condition_details_edit = _DetailBridge(self.analysis_form.condition_details)
        # The model hint prefills the analysis type.
        model = getattr(self.fit, "model", None)
        if model is not None:
            hint = type(model).__name__
            if hint and hint != "object":
                self.analysis_form.set_method(hint)

    def _populate_sample_combo(self):
        """Offer the database's samples in the *Sample* combo."""
        ids = []
        if self.db is not None:
            ids = [str(s["sample_id"]) for s in self.db.list_samples() if s.get("sample_id")]
        self.analysis_form.set_samples(ids)

    def _generate_sample_uuid(self):
        new_uuid = str(uuid.uuid4())
        self.sample_uuid_label.setText(new_uuid)
        self._on_changed()

    # -- the Analysis tab's typed-input surface (tests and helpers) ----- #
    def sample_type(self, text: str) -> None:
        """Type a sample id into the emtk combo, as a user would."""
        self.sample_combo.setEditText(text)

    def method_type(self, text: str) -> None:
        self.method_edit.setText(text)

    def sample_details_type(self, text: str) -> None:
        self.sample_details_edit.setPlainText(text)

    def condition_details_type(self, text: str) -> None:
        self.condition_details_edit.setPlainText(text)

    def method_value(self) -> str:
        return self.method_edit.text()

    def sample_value(self) -> str:
        return self.sample_combo.currentText()

    def sample_details_value(self) -> str:
        return self.sample_details_edit.toPlainText()

    def condition_details_value(self) -> str:
        return self.condition_details_edit.toPlainText()

    def sample_count(self) -> int:
        return len(self.analysis_form.sample.options)

    def sample_pick(self, index: int) -> None:
        from emtk.keys import KEY_ENTER

        self.analysis_form.sample.select(index)
        self.analysis_form.sample.key(KEY_ENTER, "", 0)
        self._update_sample_uuid_display()
        self._on_changed()

    def _update_sample_uuid_display(self):
        sid = self.sample_combo.currentText().strip()
        if not sid:
            self.sample_uuid_label.setText("")
            return
        if self.db is not None:
            row = self.db.get_sample(sid)
            if row and row.get("sample_uuid"):
                self.sample_uuid_label.setText(row["sample_uuid"])
                return
        # New sample: auto-generate UUID
        self.sample_uuid_label.setText(str(uuid.uuid4()))

    def _iter_fit_members(self) -> list[Any]:
        """Return grouped fits or the current fit as a one-item list."""
        grouped_fits = getattr(self.fit, "grouped_fits", None)
        if isinstance(grouped_fits, (list, tuple)) and grouped_fits:
            return list(grouped_fits)
        return [self.fit]

    def _analysis_data_type_for_curve(self, fit: Any, curve_key: str) -> str:
        """Return the small-data type for a named fit curve."""
        if curve_key == "data":
            model_name = str(type(getattr(fit, "model", None)).__name__).lower()
            fit_name = str(type(fit).__name__).lower()
            if "spectrum" in model_name or "spectrum" in fit_name:
                return "spectrum"
            if "fcs" in model_name or "fcs" in fit_name or "correlation" in model_name:
                return "correlation"
            return "decay"
        if curve_key == "model":
            return "model"
        if curve_key == "weighted residuals":
            return "residual"
        if curve_key == "autocorrelation":
            return "correlation"
        return "fit_curve"

    def _analysis_data_name(self, fit: Any, curve_key: str) -> str:
        """Return a stable data name for a named fit curve."""
        fit_name = str(getattr(fit, "name", "") or getattr(fit, "fit_idx", "") or "fit").strip()
        fit_name = "".join(
            ch if ch.isalnum() or ch in {"-", "_", "."} else "_" for ch in fit_name
        ).strip("._")
        curve_name = str(curve_key).strip()
        curve_name = "".join(
            ch if ch.isalnum() or ch in {"-", "_", "."} else "_" for ch in curve_name
        ).strip("._")
        if not fit_name:
            return curve_name or "data"
        if not curve_name:
            return fit_name
        return f"{fit_name}.{curve_name}"

    def _collect_embedded_analysis_data(self) -> list[dict[str, Any]]:
        """Collect small x/y curves from the current fit for mmCIF embedding."""
        records: list[dict[str, Any]] = []
        for fit in self._iter_fit_members():
            try:
                curves = fit.get_curves(copy_curves=False, full_length=True)
            except Exception:
                curves = {}
            if not curves:
                data = getattr(fit, "data", None)
                if data is not None:
                    curves = {"data": data}
            for curve_key, curve in getattr(curves, "items", lambda: [])():
                try:
                    x = np.asarray(getattr(curve, "x", []), dtype=np.float64).ravel()
                    y = np.asarray(getattr(curve, "y", []), dtype=np.float64).ravel()
                except Exception:
                    continue
                if x.size == 0 or y.size == 0:
                    continue
                n = min(x.size, y.size)
                x = x[:n]
                y = y[:n]
                finite = np.isfinite(x) & np.isfinite(y)
                if not np.all(finite):
                    x = x[finite]
                    y = y[finite]
                if x.size == 0:
                    continue
                data_type = self._analysis_data_type_for_curve(fit, str(curve_key))
                records.append(
                    {
                        "data_type": data_type,
                        "data_name": self._analysis_data_name(fit, str(curve_key)),
                        "x_values": x,
                        "y_values": y,
                        "x_unit": None,
                        "y_unit": None,
                        "details": "Embedded from FitInfo current fit curves",
                    }
                )
        return records

    def _sync_embedded_analysis_data(self) -> None:
        """Store current fit curves in the FLR database analysis_data table."""
        if self.db is None:
            return
        for record in self._collect_embedded_analysis_data():
            self.db.add_analysis_data(
                self.analysis_id,
                record["data_type"],
                record["x_values"],
                record["y_values"],
                data_name=record["data_name"],
                x_unit=record["x_unit"],
                y_unit=record["y_unit"],
                details=record["details"],
            )

    @staticmethod
    def _array_to_text(values: Any) -> str:
        """Convert numeric values to a CIF-compatible space-separated string."""
        arr = np.asarray(values, dtype=np.float64).ravel()
        return " ".join(f"{float(v):.8g}" for v in arr)

    # ── External data tab ─────────────────────────────────────

    def _on_external_table_changed(self):
        if self._suppress_change:
            return
        streams = self.external.streams()
        if self.db is not None:
            # Clear existing photon streams for this analysis, then re-add from table.
            self.db.conn.execute(
                "DELETE FROM flr_photon_stream WHERE analysis_id = ?", (self.analysis_id,)
            )
            for row, (path, file_format) in enumerate(streams):
                self.db.add_photon_stream(
                    self.analysis_id,
                    path,
                    stream_id=f"stream_{row + 1}",
                    file_format=file_format or None,
                )
        else:
            self._memory_streams = [
                {"stream_id": f"stream_{row + 1}", "file_path": path, "file_format": file_format}
                for row, (path, file_format) in enumerate(streams)
            ]
            self.fit.flr_photon_streams = self._memory_streams
        self._update_cif_preview(full=False)

    def add_external_data(self, path: str, file_format: str | None = None) -> None:
        """Add an external data reference to the external data table."""
        self.external._add(file_path=str(path), file_format=file_format or "")
        self._on_external_table_changed()

    # ── Export tab ────────────────────────────────────────────────

    def export_full_preview(self) -> None:
        """Compute the full mmCIF, with the fit's curves embedded."""
        self._update_cif_preview(full=True)

    def export_copy(self) -> None:
        """Copy the preview to the clipboard."""
        from emtk import clipboard

        clipboard.copy(self.cif_preview.toPlainText())

    def export_save(self) -> None:
        """Ask where to save the preview (an emtk file dialog in the Export tab)."""
        from emtk.file_dialog import FileDialog

        self._save_dialog = FileDialog(
            "Save mmCIF",
            mode="save",
            filters="mmCIF files (*.cif *.mmcif);;All files (*)",
            filename=f"{self.analysis_id}.cif",
        )

    def _write_cif(self, path: str) -> None:
        try:
            Path(path).write_text(self.cif_preview.toPlainText())
        except Exception as exc:
            self.cif_preview.setPlainText(f"(save failed: {exc})")

    def _get_tttr_entries_from_data_curve(self) -> dict[str, str]:
        """Parse TTTR header JSON from the first TTTR-sourced data curve.

        Returns a flat dict of ``{name: value}`` pairs from the PTU/TTTR
        header tags, or an empty dict if no TTTR data is available.
        """
        if not hasattr(self.fit, "grouped_fits"):
            return {}
        for grouped in getattr(self.fit, "grouped_fits", []):
            dc = getattr(grouped, "data", None)
            if dc is None:
                continue
            meta = getattr(dc, "meta_data", None) or {}
            hdr = meta.get("tttr_header_json", "")
            if not hdr:
                continue
            try:
                raw = json.loads(hdr) if isinstance(hdr, str) else hdr
            except Exception:
                continue
            tags = raw.get("tags", [])
            result: dict[str, str] = {}
            for tag in tags:
                name = tag.get("name", "")
                value = tag.get("value", "")
                idx = tag.get("idx", 0)
                if value is None or value == "":
                    continue
                key = name
                if idx and idx > 0:
                    key = f"{name}[{idx}]"
                result[str(key)] = str(value)
            if result:
                return result
        return {}

    def _update_cif_preview(self, full: bool = False):
        tttr_data = self._get_tttr_entries_from_data_curve()
        has_analysis_meta = bool(self._memory_metadata or self._get_metadata())
        if self.db is None and not has_analysis_meta and not tttr_data:
            self.cif_preview.setPlainText("(no data to export)")
            return
        if not full:
            lines = ["mmCIF preview (metadata only)", ""]
            if self.db is not None:
                meta = self._get_metadata()
                if meta:
                    lines.append("--- Analysis metadata ---")
                    lines.extend(f"{k}: {v}" for k, v in sorted(meta.items()))
            else:
                if self._memory_metadata:
                    lines.append("--- Analysis metadata ---")
                    lines.extend(f"{k}: {v}" for k, v in sorted(self._memory_metadata.items()))
            if tttr_data:
                lines.append("")
                lines.append("--- Instrument info (TTTR header) ---")
                lines.extend(f"{k}: {v}" for k, v in sorted(tttr_data.items()))
            if not has_analysis_meta and not tttr_data:
                lines.append("(no metadata)")
            lines.append("")
            lines.append(f"Click {Glyphs.REFRESH} to compute full mmCIF with embedded small data.")
            self.cif_preview.setPlainText("\n".join(lines))
            return
        try:
            buf = io.StringIO()
            if self.db is not None:
                self._sync_embedded_analysis_data()
                self.db.export_flr_cif(buf, analysis_id=self.analysis_id)
            else:
                # Minimal in-memory CIF with separate TTTR header section
                import ihm.format

                writer = ihm.format.CifWriter(buf)
                writer.start_block("chisurf_flr_export")
                # General analysis metadata
                if self._memory_metadata:
                    with writer.loop(
                        "_chisurf_analysis_metadata", ["analysis_id", "key", "value"]
                    ) as loop:
                        for key, value in sorted(self._memory_metadata.items()):
                            loop.write(
                                analysis_id=self.analysis_id or "analysis_1", key=key, value=value
                            )
                # TTTR instrument header in its own category
                if tttr_data:
                    with writer.loop(
                        "_chisurf_tttr_header", ["analysis_id", "name", "value"]
                    ) as loop:
                        for key, value in sorted(tttr_data.items()):
                            loop.write(
                                analysis_id=self.analysis_id or "analysis_1", name=key, value=value
                            )
                analysis_data = self._collect_embedded_analysis_data()
                if analysis_data:
                    with writer.loop(
                        "_chisurf_analysis_data",
                        [
                            "analysis_id",
                            "data_type",
                            "data_name",
                            "x_values",
                            "y_values",
                            "x_unit",
                            "y_unit",
                            "details",
                        ],
                    ) as loop:
                        for data in analysis_data:
                            loop.write(
                                analysis_id=self.analysis_id or "analysis_1",
                                data_type=data.get("data_type"),
                                data_name=data.get("data_name"),
                                x_values=self._array_to_text(data.get("x_values")),
                                y_values=self._array_to_text(data.get("y_values")),
                                x_unit=data.get("x_unit"),
                                y_unit=data.get("y_unit"),
                                details=data.get("details"),
                            )
            text = buf.getvalue()
            if not text.strip():
                self.cif_preview.setPlainText("(empty — no data to export)")
                return
            # Validate with ihm CifTokenReader
            try:
                import ihm.format

                reader = ihm.format.CifTokenReader(io.StringIO(text))
                tokens = list(reader.read_file())
                from ihm.format import CifParserError

                errors = [t for t in tokens if isinstance(t, CifParserError)]
                if errors:
                    valid = False
                    val_msg = "; ".join(str(e) for e in errors)
                else:
                    valid = True
            except Exception as val_err:
                valid = False
                val_msg = str(val_err)
            if valid:
                self.cif_preview.setPlainText(text + "\n# ✅ mmCIF validates OK")
            else:
                self.cif_preview.setPlainText(text + f"\n# ⚠️ Validation: {val_msg}")
        except Exception as exc:
            self.cif_preview.setPlainText(f"(preview failed: {exc})")

    # ── Refresh ──────────────────────────────────────────────────

    def _reload_record(self):
        self._suppress_change = True
        self.analysis_id_edit.setText(self.analysis_id)
        if self.db is not None:
            row = self.db.conn.execute(
                "SELECT * FROM flr_fret_analysis WHERE analysis_id = ?", (self.analysis_id,)
            ).fetchone()
            if row:
                self.method_edit.setText(row["type"] or row["method"] or self.method_edit.text())
                self.sample_combo.setEditText(row["sample_id"] or self.analysis_id)
                self.sample_details_edit.setPlainText(row["details"] or "")
            condition = self.db.conn.execute(
                "SELECT * FROM flr_sample_condition WHERE condition_id = ?",
                (f"condition_{self.analysis_id}",),
            ).fetchone()
            if condition:
                self.condition_details_edit.setPlainText(condition["details"] or "")
        self._update_sample_uuid_display()
        # Metadata table
        metadata = self._get_metadata()
        self.metadata_editor.set_data(
            [{"key": str(k), "value": str(v)} for k, v in sorted(metadata.items())]
        )
        # External table
        if self.db is not None:
            self.external.set_streams(self.db.get_photon_streams(self.analysis_id))
        else:
            self.external.set_streams(getattr(self.fit, "flr_photon_streams", self._memory_streams))
        self._suppress_change = False

    def _on_changed(self):
        if not hasattr(self, "_suppress_change") or self._suppress_change:
            return
        if self.db is not None:
            sample_id = self.sample_combo.currentText().strip() or None
            # Ensure sample exists in DB
            if sample_id and self.db.get_sample(sample_id) is None:
                suuid = self.sample_uuid_label.text().strip() or None
                self.db.add_sample(sample_id, uuid=suuid)
                self._populate_sample_combo()
            self.db.update_analysis_record(
                self.analysis_id,
                type=self.method_edit.text().strip() or None,
                method=self.method_edit.text().strip() or None,
                sample_id=sample_id,
                details=self.sample_details_edit.toPlainText().strip() or None,
            )
            self.db.conn.execute(
                "INSERT OR REPLACE INTO flr_sample_condition (condition_id, details) VALUES (?, ?)",
                (
                    f"condition_{self.analysis_id}",
                    self.condition_details_edit.toPlainText().strip(),
                ),
            )
            self.db.set_analysis_metadata(self.analysis_id, self.metadata_editor.as_dict())
        else:
            self._memory_metadata = self.metadata_editor.as_dict()
            self.fit.flr_metadata = self._memory_metadata
        self.update()

    def _model_summary(self) -> str:
        """Return the model's own account of what it is fitting, as plain text.

        A model may publish how many bursts survived a cut, which estimator is
        in use, why an uncertainty is not to be trusted. That belongs *here*,
        with the rest of the fit's provenance -- and **in** this report rather
        than in a widget of its own above it, which arrives with its own
        scrollbar and its own idea of how tall it should be and reads as
        something bolted on.

        ``summary_text()`` is the hook; ``summary_html()`` is accepted and
        flattened so a model written for an AutoForm ``info`` section needs no
        second implementation.
        """
        model = getattr(self.fit, "model", None)
        source = getattr(model, "summary_text", None)
        if callable(source):
            try:
                return str(source() or "")
            except Exception as exc:
                return f"(summary unavailable: {exc})"
        source = getattr(model, "summary_html", None)
        if callable(source):
            try:
                return _html_to_text(str(source() or ""))
            except Exception as exc:
                return f"(summary unavailable: {exc})"
        return ""

    def update(self, *args, **kwargs) -> None:
        """Rebuild every panel from the fit's current state."""
        super().update(*args, **kwargs)
        fit = self.fit
        meta = self._get_metadata()
        lines = [str(fit)]
        summary = self._model_summary()
        if summary:
            lines.append(f"\n--- Model ---\n{summary}")
        lines.append(f"\n--- Analysis: {self.analysis_id} ---")
        if self.db is not None:
            lines.append("DB-backed metadata")
        else:
            lines.append("In-memory metadata")
        lines.append(f"  type: {self.method_edit.text().strip() or '?'}")
        sample_id = self.sample_combo.currentText().strip() or self.analysis_id
        lines.append(f"  sample: {sample_id}")
        suuid = self.sample_uuid_label.text().strip()
        if suuid:
            lines.append(f"  uuid: {suuid}")
        sd = self.sample_details_edit.toPlainText().strip()
        if sd:
            lines.append(f"  details: {sd}")
        cd = self.condition_details_edit.toPlainText().strip()
        if cd:
            lines.append(f"  condition: {cd}")
        if meta:
            lines.append("")
            for k, v in sorted(meta.items()):
                lines.append(f"  {k}: {v}")
        else:
            lines.append("  (no metadata)")
        streams = self._photon_streams_for_display()
        if streams:
            lines.append(f"\n--- Photon streams ({len(streams)}) ---")
            for s in streams:
                fp = s.get("file_path") or ""
                lines.append(f"  path={fp}")
        self.textedit.setPlainText("\n".join(lines))
        self._reload_record()
        self._update_cif_preview(full=False)
