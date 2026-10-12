"""The current fit's model editor in the emtk shell's Analysis dock.

The Qt Analysis dock shows each model's own ``view.json`` editor: structure
choices (the FCS *Diffusion* type), the equation, parameter tables labelled with
units (``D [µm²/s]``), component lists with *add* / *del*, read-only outputs.
Here the same editor is drawn natively from what the server resolves of that
spec (``model.editor``, :func:`chisurf.server.services.model_svc.model_editor`):
plain data, never the live model. Every change goes back through the API on the
docks' worker -- a choice through ``model.state.set``, a cell through the
``parameter.*`` calls by the parameter's uid, *add* / *del* through
``model.component.add`` / ``remove`` -- and the editor is re-read when the
server's events say the fit changed.

The resolved sections are turned into an emtk view spec (:func:`native_spec`)
drawn by :func:`emtk.view_form.draw_form`: panels fold as in Qt, a parameter
table is a ``table`` section whose name column draws sub- and superscripts, and
the equation is typeset with :func:`emtk.im.math`.
"""

from __future__ import annotations

import html
import re
from typing import Any

from emtk import im
from emtk.i18n import tr
from emtk.view_form import FormState, draw_form

from chisurf.core.fitting import prior_families

#: Columns of a parameter table, as the Qt editor's ``ParameterGroupTableWidget`` shows them.
PARAMETER_COLUMNS = [
    {
        "key": "label",
        "label": "Name",
        "display": "script",
        "description": "The parameter, with its unit.",
    },
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
    },
    {
        "key": "lo",
        "label": "Lo",
        "editable": True,
        "format": "%.4g",
        "description": "Lower bound, used while Bounds is on.",
    },
    {
        "key": "hi",
        "label": "Hi",
        "editable": True,
        "format": "%.4g",
        "description": "Upper bound, used while Bounds is on.",
    },
    {
        "key": "bounds_on",
        "label": "Bounds",
        "editable": True,
        "description": "Keep the parameter between Lo and Hi while fitting.",
    },
    {
        "key": "error",
        "label": "Error",
        "format": "%.3g",
        "description": "Uncertainty estimate from the last fit.",
    },
    {
        "key": "prior",
        "label": "Prior",
        "editable": True,
        "description": (
            "Box keeps the plain lower/upper bounds; a family (Gaussian, Log-normal, ...) "
            "attaches a smooth prior pulling the fit toward a value. Type a family and its "
            "shape parameters, e.g. Gaussian(4, 0.4); right-click the row for the list."
        ),
    },
]

_SUB = re.compile(r"<sub>(.*?)</sub>", re.IGNORECASE | re.DOTALL)
_SUP = re.compile(r"<sup>(.*?)</sup>", re.IGNORECASE | re.DOTALL)
_TAG = re.compile(r"<[^>]+>")


def label_markup(label: str) -> str:
    """A parameter's HTML label (``w<sub>z</sub>[nm]``) as script markup (``w_{z}[nm]``)."""
    text = _SUB.sub(lambda m: "_{" + _TAG.sub("", m.group(1)) + "}", str(label or ""))
    text = _SUP.sub(lambda m: "^{" + _TAG.sub("", m.group(1)) + "}", text)
    return html.unescape(_TAG.sub("", text))


def plain_label(label: str) -> str:
    """A label as a reader says it: tags stripped, entities decoded (``wz[nm]``)."""
    return html.unescape(_TAG.sub("", str(label or "")))


_WORD = re.compile(r"(?<![\\A-Za-z])([A-Za-z]{2,})")
_SYMBOLS = {
    "·": r" \cdot ",
    "×": r" \times ",
    "−": "-",
    "–": "-",
    "²": "^{2}",
    "³": "^{3}",
    "¹": "^{1}",
    "√": r"\sqrt ",
    "∑": r"\sum ",
    "Σ": r"\Sigma ",
    "≈": r"\approx ",
}


def html_to_latex(text: str) -> str:
    """An equation written as HTML (``<sub>``, ``<sup>``, entities) as LaTeX for :func:`emtk.im.math`.

    Words of two letters or more (``exp``, ``MDF``, ``foci``) are set upright,
    single letters stay italic as variables.
    """
    text = re.sub(r"<br\s*/?>", " ", str(text or ""), flags=re.IGNORECASE)
    text = re.sub(r"</?(b|strong|i|em|span|font)[^>]*>", "", text, flags=re.IGNORECASE)
    text = html.unescape(text)
    # Upright words before any command is inserted, so no command is wrapped.
    parts = re.split(r"(<[^>]+>)", text)
    parts = [p if p.startswith("<") else _WORD.sub(r"\\mathrm{\1}", p) for p in parts]
    text = "".join(parts)
    text = _SUB.sub(lambda m: "_{" + _TAG.sub("", m.group(1)) + "}", text)
    text = _SUP.sub(lambda m: "^{" + _TAG.sub("", m.group(1)) + "}", text)
    text = _TAG.sub("", text)
    for symbol, latex in _SYMBOLS.items():
        text = text.replace(symbol, latex)
    return text


#: The per-slot columns of a paired table: (field, spec column id, label, editable, format).
_SLOT_FIELDS = (
    ("value", "value", None, True, "%.5g"),
    ("fixed", "fixed", "Fixed", True, None),
    ("lo", "bounds_lo", "Lo", True, "%.4g"),
    ("hi", "bounds_hi", "Hi", True, "%.4g"),
    ("bounds_on", "bounds_on", "Bounds", True, None),
    ("error", "error", "Error", False, "%.3g"),
)
_SLOT_KEY = re.compile(r"^(value|fixed|lo|hi|bounds_on|error)(\d+)$")


def _group_header(label: str) -> str:
    """A slot's column title: its parameter's label without the component number (``x_{L,1}`` → ``x_{L}``)."""

    def strip(match: re.Match) -> str:
        inner = re.sub(r"[,\s]*\d+\s*$", "", match.group(1)).strip()
        return f"<sub>{inner}</sub>" if inner else ""

    return re.sub(r"<sub>(.*?)</sub>", strip, str(label or ""), flags=re.IGNORECASE)


def _paired(entries: list, width: int, section: dict) -> tuple[list, list]:
    """Rows and columns of a paired table: ``width`` parameters a row, a column block per slot."""
    wanted = list(section.get("columns") or [])
    fields = [f for f in _SLOT_FIELDS if not wanted or f[1] in wanted or f[0] == "value"]
    slot_labels = list(section.get("slot_labels") or [])
    row_labels = list(section.get("row_labels") or [])
    target = str(section.get("key", ""))
    rows = []
    for r in range(len(entries) // width):
        params = [_row(e) for e in entries[r * width : (r + 1) * width]]
        row = {
            "uid": f"{target}#{r}",
            "index": row_labels[r] if r < len(row_labels) else str(r + 1),
            "_component": r,
            "_target": target,
            "_params": params,
            "muted": all(p["muted"] for p in params),
        }
        for j, p in enumerate(params):
            for field, _sid, _label, _edit, _fmt in fields:
                row[f"{field}{j}"] = p[field]
        rows.append(row)
    columns = [
        {
            "key": "index",
            "label": "" if row_labels else "#",
            "description": "The component (or the quantity) of the row.",
        }
    ]
    for j in range(width):
        if j < len(slot_labels):
            title = slot_labels[j]
        elif j < len(entries):
            title = plain_label(
                _group_header(entries[j].get("label") or entries[j].get("name", ""))
            )
        else:
            title = str(j + 1)
        for field, _sid, label, editable, fmt in fields:
            column = {
                "key": f"{field}{j}",
                "label": title if field == "value" else label,
                "editable": editable,
            }
            if fmt:
                column["format"] = fmt
            columns.append(column)
    return rows, columns


def _slot_parameter(record: Any, key: str) -> dict | None:
    match = _SLOT_KEY.match(str(key or ""))
    params = (record or {}).get("_params") or []
    if match is None or int(match.group(2)) >= len(params):
        return None
    return params[int(match.group(2))]


def _slot_field(key: str) -> str:
    match = _SLOT_KEY.match(str(key or ""))
    return match.group(1) if match else ""


class _Rows(list):
    """Table rows with a ``revision``, so a re-read rebinds the table once."""

    revision = 0


def _number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _row(entry: dict) -> dict:
    """One table row from a resolved parameter entry.

    An output (a derived quantity such as ``s`` or ``ε``) is computed, never fitted: it has no
    *Fixed* or *Bounds* to set, so those cells are empty (``None``) rather than a check box —
    the Qt editor shows none either. The entry still says ``fixed`` (nothing may move it).
    """
    output = bool(entry.get("is_output"))
    linked = bool(entry.get("is_linked") or entry.get("linked_to"))
    fit_control = None if output else True
    return {
        "uid": str(entry.get("uid") or entry.get("name")),
        "name": str(entry.get("name", "")),
        "label": label_markup(entry.get("label") or entry.get("name", "")),
        "value": _number(entry.get("value")),
        "fixed": fit_control and bool(entry.get("fixed")),
        "lo": fit_control and _number(entry.get("lo")),
        "hi": fit_control and _number(entry.get("hi")),
        "bounds_on": fit_control and bool(entry.get("bounds_on")),
        "prior": None if output else prior_families.describe(entry.get("prior")),
        "prior_state": entry.get("prior"),
        "error": _number(entry.get("error_estimate")),
        "output": output,
        "linked": linked,
        #: The master a follower borrows its value from: drawn in the linked ink, named in its tooltip.
        "master": str(entry.get("linked_to") or (tr("another parameter") if linked else "")),
        "muted": bool(entry.get("fixed")) or output or linked,
    }


class ModelEditor:
    """The model editor of the current fit, drawn from the server's resolved ``view.json``.

    Parameters
    ----------
    docks : chisurf.emtk.fit_docks.DataDocks
        Runs the editor's changes as API calls on its worker.
    """

    def __init__(self, docks: Any) -> None:
        object.__setattr__(self, "_controls", {})
        self.docks = docks
        self.uid = ""
        self.editor: dict | None = None
        self.spec: dict = {"sections": []}
        self.form = FormState()
        self.form.custom["model_info"] = self._draw_info
        from chisurf.emtk.model_sections import SectionViews

        #: The curve pickers and custom sections (``chisurf.emtk.model_sections``).
        self.sections = SectionViews(self)
        self.sections.install(self.form)
        self._sources: dict[str, _Rows] = {}
        self._values: dict[str, Any] = {}
        self._actions: dict[str, Any] = {}
        #: Row uid -> (component target, position in its table, row width).
        self._positions: dict[str, tuple[str, int, int]] = {}
        self._selected: dict[str, int] = {}
        #: Editor section key (a group's target) -> the table source drawing it.
        self._keyed: dict[str, str] = {}

    # -- what the server sent ------------------------------------------------ #
    def set_editor(self, uid: str, editor: dict | None) -> None:
        """Adopt the resolved editor of fit *uid* (``None``: the model has no editor)."""
        if uid != self.uid:
            self._selected.clear()
        self.uid = uid
        self.editor = editor if isinstance(editor, dict) else None
        controls: dict[str, dict] = {}
        self._actions = {}
        self._positions = {}
        self._values = {}
        self._keyed = {}
        old = self._sources
        self._sources = {}
        self.sections.reset()
        self.sections._sources = {
            k: v for k, v in old.items() if k.startswith(("section_rows_", "mixer_rows_"))
        }
        counter = iter(range(1_000_000))

        def rows_for(name: str, entries: list) -> _Rows:
            rows = _Rows(_row(e) for e in entries)
            rows.revision = getattr(old.get(name), "revision", 0) + 1
            self._sources[name] = rows
            return rows

        def convert(section: dict) -> dict | list | None:
            kind = section.get("type")
            n = next(counter)
            common = {"description": section.get("description", "")}
            if section.get("hidden"):
                common["visible"] = False
            if kind == "panel":
                children = []
                for child in section.get("sections", []):
                    made = convert(child)
                    if isinstance(made, list):
                        children.extend(made)
                    elif made is not None:
                        children.append(made)
                return {
                    "type": "panel",
                    "title": section.get("title", ""),
                    "collapsible": bool(section.get("collapsible", True)),
                    "collapsed": bool(section.get("collapsed", False)),
                    "n_col": int(section.get("n_col") or 1),
                    "sections": children,
                    **common,
                }
            if kind in ("choice", "toggle", "value"):
                attr = f"control_{n}"
                controls[attr] = section
                self._values[attr] = section.get("value")
                out = {
                    "type": kind,
                    "attr": attr,
                    "label": section.get("label", ""),
                    **common,
                }
                if kind == "choice":
                    options = section.get("options") or []
                    out.update(
                        options=[o[0] for o in options],
                        labels=[str(o[1]) for o in options],
                        style=section.get("style", "combo"),
                    )
                    if section.get("descriptions"):
                        out["descriptions"] = list(section["descriptions"])
                if kind == "value":
                    out.update(
                        kind=section.get("kind", "str"),
                        decimals=section.get("decimals", 3),
                        suffix=section.get("suffix", ""),
                        read_only=bool(section.get("read_only")),
                    )
                    for bound in ("minimum", "maximum"):
                        if section.get(bound) is not None:
                            out[bound] = section[bound]
                return out
            if kind == "info":
                return {
                    "type": "custom",
                    "key": "model_info",
                    "options": {
                        "text": section.get("text", ""),
                        "is_markdown": section.get("is_markdown"),
                    },
                    **common,
                }
            if kind in ("parameters", "components"):
                source = f"rows_{n}"
                entries = section.get("rows") or []
                rows_for(source, entries)
                self._keyed[str(section.get("key", ""))] = source
                table = {
                    "type": "table",
                    "source": source,
                    "row_key": "uid",
                    "edited_call": "edit_cell",
                    "editable_call": "cell_editable",
                    "muted_key": "muted",
                    "link_key": "master",
                    "fit_rows": True,
                    "fit_columns": True,
                    "context_call": "section_context",
                    "columns": PARAMETER_COLUMNS,
                    "description": section.get("description")
                    or tr(
                        "Double-click a value or bound to type it; click Fixed or Bounds "
                        "to toggle. Outputs and linked parameters are dimmed and read only."
                    ),
                }
                width = max(1, int(section.get("row_width") or 1))
                if width > 1 and (kind == "parameters" or section.get("style") == "table"):
                    # Paired, as the Qt editor's tables: one component (row_width parameters)
                    # a row, each slot's columns side by side under the slot's name.
                    rows, columns = _paired(entries, width, section)
                    paired_rows = _Rows(rows)
                    paired_rows.revision = self._sources[source].revision
                    self._sources[source] = paired_rows
                    table.update(
                        columns=columns, edited_call="edit_paired", editable_call="paired_editable"
                    )
                if kind == "parameters":
                    # A group with no parameters draws nothing, as in the Qt editor.
                    return {**table, **common} if entries else None
                target = str(section.get("key", ""))
                for position, entry in enumerate(entries):
                    uid = str(entry.get("uid") or entry.get("name"))
                    self._positions[uid] = (target, position, width)
                add, remove = f"add_{n}", f"remove_{n}"
                self._actions[add] = ("add", target, section)
                self._actions[remove] = ("remove", target, section)
                buttons = {
                    "type": "button_row",
                    "buttons": [
                        {
                            "label": section.get("add_label") or "add",
                            "action": add,
                            "description": tr("Add a component."),
                        },
                        {
                            "label": section.get("remove_label") or "del",
                            "action": remove,
                            "description": tr("Remove the selected component, or the last one."),
                        },
                    ],
                    **common,
                }
                table["selected_call"] = "row_selected"
                parts = [buttons]
                for header in section.get("header") or []:
                    made = self.sections.convert(header, common, next(counter))
                    parts.extend(made if isinstance(made, list) else [made])
                if entries:
                    parts.append({**table, **common})
                return parts
            if kind == "toggle_row":
                items = []
                for i, item in enumerate(section.get("items") or []):
                    attr = f"control_{n}_{i}"
                    controls[attr] = item
                    self._values[attr] = bool(item.get("value"))
                    items.append(
                        {
                            "attr": attr,
                            "label": item.get("label", ""),
                            "description": item.get("description", ""),
                        }
                    )
                return {"type": "toggle_row", "items": items, **common}
            if kind == "buttons":
                buttons = []
                for i, button in enumerate(section.get("buttons") or []):
                    name = f"press_{n}_{i}"
                    self._actions[name] = ("press", str(button.get("action", "")), section)
                    buttons.append(
                        {
                            "label": button.get("label", ""),
                            "action": name,
                            "description": button.get("description", ""),
                        }
                    )
                return {"type": "button_row", "buttons": buttons, **common}
            if kind == "records":
                source = f"records_{n}"
                rows = _Rows(dict(r) for r in section.get("rows") or [])
                rows.revision = getattr(old.get(source), "revision", 0) + 1
                self._sources[source] = rows
                table = {
                    "type": "table",
                    "source": source,
                    "columns": list(section.get("columns") or []),
                    "height": int(section.get("height") or 0) or 140,
                    **common,
                }
                if section.get("selected_key"):
                    select = f"select_{n}"
                    self._actions[select] = ("select", str(section["selected_key"]), section)
                    table["selected_call"] = select
                return table
            if kind in ("curve_input", "custom"):
                made = self.sections.convert(section, common, n)
                if section.get("key") == "fit_mixer":
                    fractions = (section.get("data") or {}).get("fractions") or []
                    if fractions:
                        source = f"rows_{n}_fractions"
                        rows_for(source, fractions)
                        parts = made if isinstance(made, list) else [made]
                        return parts + [
                            {
                                "type": "table",
                                "source": source,
                                "row_key": "uid",
                                "edited_call": "edit_cell",
                                "editable_call": "cell_editable",
                                "context_call": "section_context",
                                "muted_key": "muted",
                                "link_key": "master",
                                "fit_rows": True,
                                "fit_columns": True,
                                "columns": PARAMETER_COLUMNS,
                                **common,
                            }
                        ]
                return made
            return {
                "type": "info",
                "text": tr("{kind}: not drawn in this window yet.").format(
                    kind=section.get("title") or str(section.get("kind") or "?").replace("_", " ")
                ),
                **common,
            }

        sections: list = []
        for section in (self.editor or {}).get("sections", []):
            made = convert(section)
            if isinstance(made, list):
                sections.extend(made)
            elif made is not None:
                sections.append(made)
        object.__setattr__(self, "_controls", controls)
        self.spec = {"sections": sections}

    # -- what the form binds ------------------------------------------------- #
    def __getattr__(self, name: str) -> Any:
        if name.startswith(("rows_", "records_", "section_rows_")):
            rows = self.__dict__.get("_sources", {}).get(name)
            if rows is not None:
                return lambda: rows
        if name.startswith("control_"):
            values = self.__dict__.get("_values", {})
            if name in values:
                return values[name]
        sections = self.__dict__.get("sections")
        forwarded = {
            "section_edit_scalar": "edit_scalar",
            "section_edit_rate": "edit_rate",
            "section_edit_global": "edit_global",
            "section_editable": "editable",
            "section_context": "context",
        }
        if sections is not None and name in forwarded:
            return getattr(sections, forwarded[name])
        if sections is not None and name == "section_shading":
            return sections.shading
        actions = self.__dict__.get("_actions", {})
        if name in actions:
            kind, target, _section = actions[name]
            if kind == "press":
                return lambda: self.docks.model_action(target)
            if kind == "select":
                return lambda record: self.docks.set_model_state(target, dict(record or {}))
            return lambda: self.change_components(kind, target)
        raise AttributeError(name)

    def __setattr__(self, name: str, value: Any) -> None:
        controls = self.__dict__.get("_controls", {})
        if name in controls:
            section = controls[name]
            if section.get("read_only"):
                return
            self._values[name] = value
            self.docks.set_model_state(
                str(section.get("key", "")), value, str(section.get("label") or "")
            )
            return
        object.__setattr__(self, name, value)

    def enabled(self, name: str) -> bool:
        """Controls are live while no call is under way; *add* / *del* only where the group allows it."""
        if self.docks.busy:
            return False
        if name in self._actions:
            kind, _target, section = self._actions[name]
            if kind in ("press", "select"):
                return True
            if kind == "add":
                return bool(section.get("can_add", True))
            return bool(section.get("can_remove", True)) and int(section.get("count", 0)) > int(
                section.get("min_rows", 0)
            )
        control = self._controls.get(name)
        if control is not None:
            return not control.get("read_only")
        return True

    def cell_editable(self, record: Any, key: str) -> bool:
        record = record or {}
        return not self.docks.busy and not record.get("output") and not record.get("linked")

    def edit_cell(self, record: Any, key: str, value: Any) -> None:
        """A cell of a parameter table was changed: send it to the server by the parameter's uid."""
        if isinstance(record, dict) and record.get("uid"):
            self.docks.edit_model_parameter(record, key, value)

    def paired_editable(self, record: Any, key: str) -> bool:
        parameter = _slot_parameter(record, key)
        return parameter is not None and self.cell_editable(parameter, key)

    def edit_paired(self, record: Any, key: str, value: Any) -> None:
        """A cell of a paired table: the parameter of its slot, edited as in a one-per-row table."""
        parameter = _slot_parameter(record, key)
        if parameter is not None:
            self.edit_cell(parameter, _slot_field(key), value)

    def row_selected(self, record: Any) -> None:
        """Remember which component a component table's selection is in (for *del*)."""
        if isinstance(record, dict) and "_component" in record:
            self._selected[str(record.get("_target", ""))] = int(record["_component"])
            return
        where = self._positions.get(str((record or {}).get("uid", "")))
        if where is not None:
            target, position, width = where
            self._selected[target] = position // width

    def change_components(self, kind: str, target: str) -> None:
        """*add* or *del* of a component group: the selected component, else the last one."""
        if kind == "add":
            self.docks.change_components(target, add=True)
        else:
            self.docks.change_components(target, add=False, index=self._selected.pop(target, -1))

    # -- drawing --------------------------------------------------------------- #
    def _draw_info(self, section: dict, model: Any, state: FormState, width: float) -> None:
        options = section.get("options") or {}
        text = str(options.get("text") or "")
        if not text:
            return
        if "<sub>" in text or "<sup>" in text or "&" in text:
            im.math(html_to_latex(text), font_size=15.0, max_width=max(40.0, width))
        else:
            im.text_wrapped(plain_label(text))

    def draw(self, item_rects: dict | None = None) -> None:
        """Draw the editor into the current window (the Analysis dock, below the controller)."""
        if item_rects is not None:
            # Only what is drawn now: another fit's editor left rectangles of controls this one lacks.
            for key in [k for k in item_rects if k.startswith("editor.")]:
                del item_rects[key]
        if self.editor is None:
            return
        self.form.rects.clear()
        draw_form(self.spec, self, self.form, titles=True)
        if item_rects is not None:
            for key, rect in self.form.rects.items():
                item_rects[f"editor.{key}"] = rect

    # -- lookups (for tests, tours and the parity check) --------------------------- #
    def control_for(self, key: str) -> str:
        """The form attribute of the editor control bound to state *key* (``""`` if none)."""
        return next((attr for attr, c in self._controls.items() if c.get("key") == key), "")

    def action_for(self, kind: str, target: str) -> str:
        """The button action of *kind* (``add``, ``remove``, ``press``) on *target* (``""`` if none)."""
        return next(
            (name for name, (k, t, _s) in self._actions.items() if k == kind and t == target), ""
        )

    def table_for(self, key: str) -> str:
        """The table source drawing the editor section *key* (a group's target)."""
        return self._keyed.get(key, "")

    def rows(self, key: str) -> list:
        """The rows the editor shows for section *key* (a parameter group's target)."""
        source = self.table_for(key)
        rows = list(self._sources.get(source, [])) if source else []
        # A paired table holds a component a row; its parameters are the rows asked for.
        return (
            [p for row in rows for p in row["_params"]] if rows and "_params" in rows[0] else rows
        )

    def visible_titles(self) -> list[str]:
        """Titles of the panels drawn now (hidden ones left out)."""
        titles: list[str] = []

        def walk(sections: list) -> None:
            for section in sections:
                if section.get("visible") is False:
                    continue
                if section.get("type") == "panel" and section.get("title"):
                    titles.append(section["title"])
                walk(section.get("sections") or [])

        walk(self.spec.get("sections", []))
        return titles

    label_markup = staticmethod(label_markup)
    plain_label = staticmethod(plain_label)

    def modal_open(self) -> bool:
        """Whether a dialog or menu of a section is open over the shell."""
        return self.sections.modal_open()

    def draw_dialogs(self, box) -> None:
        """The sections' dialogs and menus (drawn last, on top)."""
        self.sections.draw_dialogs(box)

    # -- for parity checks ------------------------------------------------------ #
    def inventory(self) -> set[str]:
        """Every label, title and option of the editor, hidden sections included (as plain text)."""
        found: set[str] = set()

        def walk(section: dict) -> None:
            for key in ("title", "label", "add_label", "remove_label"):
                if section.get(key):
                    found.add(plain_label(section[key]))
            options = section.get("options") if section.get("type") == "choice" else None
            for value, label in options or []:
                found.add(plain_label(label))
            for row in section.get("rows") or []:
                found.add(plain_label(row.get("label") or row.get("name", "")))
            for button in section.get("buttons") or []:
                found.add(plain_label(button.get("label", "")))
            for item in section.get("items") or []:
                found.add(plain_label(item.get("label", "")))
            for child in section.get("sections") or []:
                walk(child)

        for section in (self.editor or {}).get("sections", []):
            walk(section)

        def columns(section: dict) -> None:
            for column in section.get("columns") or []:
                if isinstance(column, dict) and column.get("label"):
                    found.add(plain_label(str(column["label"])))
            for child in section.get("sections") or []:
                columns(child)

        for section in self.spec.get("sections", []):
            columns(section)
        return found | {plain_label(t) for t in self.sections.inventory()}


__all__ = ["ModelEditor", "PARAMETER_COLUMNS", "html_to_latex", "label_markup", "plain_label"]
