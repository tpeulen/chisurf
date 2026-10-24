"""The one metadata editor: typed, schema-driven, shared by every plugin that has metadata.

Hosts (burst selection's flrCIF metadata, the Zenodo deposit, ...) used to grow
their own little key/value forms -- one entry at a time, no types, no checks.
This module is the single editor behind all of them: a *schema* of typed fields
plus free-form extras, validated, rendered by one EMTK widget and applied back
through the host's own setters.

Qt-free: plugins, the CLI and tests use :class:`EditorModel` directly; the
drawing lives in ``gui/widget.py``.
"""

from __future__ import annotations

import dataclasses
from typing import Any, Iterable

__all__ = [
    "EditorModel",
    "Field",
    "Schema",
    "flrcif_schema",
    "freeform_schema",
    "zenodo_schema",
]


@dataclasses.dataclass(frozen=True)
class Field:
    """One typed metadata entry.

    ``kind`` is a view-form value kind (``str``, ``text``, ``int``, ``float``,
    ``date``) or ``"choice"`` with *options*; ``text`` is multi-line.
    """

    key: str
    label: str = ""
    kind: str = "str"
    options: tuple[str, ...] = ()
    required: bool = False
    placeholder: str = ""
    help: str = ""

    def __post_init__(self) -> None:
        if self.kind == "choice" and not self.options:
            raise ValueError(f"field {self.key!r}: a choice needs options")
        if not self.key:
            raise ValueError("a field needs a key")

    @property
    def display_label(self) -> str:
        return self.label or self.key.replace("_", " ").strip().capitalize()


class Schema(tuple):
    """An ordered set of :class:`Field` -- tuple, so it is immutable and iterable."""

    __slots__ = ()

    def __new__(cls, fields: Iterable[Field]) -> "Schema":
        items = [f if isinstance(f, Field) else Field(**f) for f in fields]
        keys = [f.key for f in items]
        if len(set(keys)) != len(keys):
            dupes = sorted({k for k in keys if keys.count(k) > 1})
            raise ValueError(f"duplicate field keys: {', '.join(dupes)}")
        return super().__new__(cls, items)

    @property
    def keys(self) -> list[str]:
        return [f.key for f in self]

    def field(self, key: str) -> Field | None:
        for f in self:
            if f.key == key:
                return f
        return None


# ── presets ───────────────────────────────────────────────────────────────────


def freeform_schema() -> Schema:
    """No typed fields: everything is a free key/value extra."""
    return Schema(())


def flrcif_schema(extra_keys: Iterable[str] = ()) -> Schema:
    """The analysis metadata written into an flrCIF export.

    The common experiment keys as typed fields; *extra_keys* (the PDBx keys of
    the sample/environment dictionaries) join as plain strings.
    """
    fields = [
        Field("pH", kind="float", placeholder="7.4", help="Sample pH."),
        Field("temperature", kind="float", placeholder="298.15", help="Sample temperature [K]."),
        Field("ionic_strength", kind="float", help="Ionic strength [mM]."),
        Field("buffer_composition", kind="str", help="Buffer composition."),
        Field("solvent_phase", kind="str", help="Solvent phase."),
        Field("labeling_efficiency", kind="float", placeholder="0.95", help="Fraction of labelled molecules."),
        Field("donor_only_fraction", kind="float", help="Fraction of donor-only species."),
        Field("acceptor_only_fraction", kind="float", help="Fraction of acceptor-only species."),
    ]
    for key in extra_keys:
        if key not in {f.key for f in fields}:
            fields.append(Field(key))
    return Schema(fields)


def zenodo_schema() -> Schema:
    """A Zenodo deposit's metadata (the fields the deposit API takes)."""
    return Schema([
        Field("title", required=True, help="Deposit title."),
        Field("upload_type", kind="choice", options=("publication", "dataset", "image", "software", "lesson")),
        Field("publication_date", kind="date", help="Format: YYYY-MM-DD."),
        Field("description", kind="text", help="Deposit description (HTML allowed)."),
        Field("creators", kind="text", required=True,
              help="One creator per line: ``Family, Given; Affiliation; ORCID``."),
        Field("keywords", kind="str", help="Comma-separated keywords."),
        Field("license", kind="str", placeholder="MIT", help="License id (e.g. MIT, CC-BY-4.0)."),
        Field("access_right", kind="choice",
              options=("open", "embargoed", "restricted", "closed")),
        Field("embargo_date", kind="date", help="Applies when access is 'embargoed'."),
        Field("version", kind="str", help="Deposit version."),
        Field("related", kind="text", help="One related identifier per line: ``relation identifier``."),
    ])


# ── the editor state ──────────────────────────────────────────────────────────


class EditorModel:
    """The state one editor window edits: schema values plus free-form extras.

    ``values`` holds every schema key (missing ones empty); ``extras`` the
    entries beyond the schema, as displayed ``(key, value)`` strings. Hosts
    construct it from their store and read :meth:`entries` back on Apply.
    """

    def __init__(self, schema: Schema, initial: dict[str, Any] | None = None,
                 *, extra_key: str = "", extra_value: str = "") -> None:
        self.schema = schema
        initial = {str(k): v for k, v in (initial or {}).items()}
        self.values: dict[str, str] = {
            f.key: _as_text(initial.get(f.key, "")) for f in schema
        }
        known = set(self.values)
        self.extras: list[list[str]] = [
            [str(k), _as_text(v)] for k, v in initial.items() if str(k) not in known
        ]
        #: the free-form add row (key/value inputs of the widget)
        self.extra_key = extra_key
        self.extra_value = extra_value

    # -- the free-form add row ------------------------------------------------ #
    def add_extra(self, *_args: Any) -> None:
        key = self.extra_key.strip()
        if not key:
            raise ValueError("An entry needs a key.")
        value = self.extra_value
        if (field := self.schema.field(key)) is not None:  # a schema key: edit it in place
            self.values[key] = value
        elif (row := next((r for r in self.extras if r[0] == key), None)) is not None:
            row[1] = value
        else:
            self.extras.append([key, value])
        self.extra_key, self.extra_value = "", ""

    def remove_extra(self, record: dict) -> None:
        """``data_table`` delete hook: drop the extra (or clear a schema value)."""
        key = str((record or {}).get("key", ""))
        self.extras = [r for r in self.extras if r[0] != key]
        if key in self.values:
            self.values[key] = ""

    # -- validation and results ----------------------------------------------- #
    def errors(self) -> dict[str, str]:
        """Field key -> problem text; empty dict when everything checks out."""
        problems: dict[str, str] = {}
        for f in self.schema:
            text = self.values.get(f.key, "").strip()
            if f.required and not text:
                problems[f.key] = f"{f.display_label} is required."
                continue
            if not text:
                continue
            if f.kind == "int":
                try:
                    int(text)
                except ValueError:
                    problems[f.key] = f"{f.display_label} must be an integer."
            elif f.kind == "float":
                try:
                    float(text)
                except ValueError:
                    problems[f.key] = f"{f.display_label} must be a number."
            elif f.kind == "date" and len(text) != 10:
                problems[f.key] = f"{f.display_label} must be YYYY-MM-DD."
        return problems

    def entries(self) -> dict[str, str]:
        """Every non-empty entry, schema fields and extras merged (extras win)."""
        out = {k: v.strip() for k, v in self.values.items() if v.strip()}
        for key, value in self.extras:
            if key.strip():
                out[key.strip()] = value.strip()
        return out

    def rows(self) -> list[dict[str, str]]:
        """The entries table: every entry with an editor-friendly value preview."""
        return [{"key": k, "value": v.replace("\n", "; ")} for k, v in self.entries().items()]


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple)):  # e.g. creators, keywords from a deposit
        return "; ".join(
            "; ".join(str(part) for part in item.values()) if isinstance(item, dict) else str(item)
            for item in value
        )
    return str(value)
