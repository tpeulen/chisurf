"""Column description for :mod:`chisurf.gui.widgets.chitable`.

A :class:`ColumnSpec` is the declarative unit every chitable source hands to the
model: it names the column, says how to format it, whether it may be edited, and
which delegate (if any) paints it. Sources that wrap self-describing data (a
``DataFrame``) synthesise specs; sources that wrap records (parameter rows) are
handed them explicitly.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from typing import Any

#: Default format applied to floating-point columns when a spec sets none.
DEFAULT_FORMAT = "%.6g"

#: Column kinds understood by the model, delegates and value coercion.
KIND_FLOAT = "float"
KIND_INT = "int"
KIND_BOOL = "bool"
KIND_STR = "str"
KIND_AUTO = "auto"

NUMERIC_KINDS = frozenset({KIND_FLOAT, KIND_INT})


@dataclass(frozen=True)
class ColumnSpec:
    """Declarative description of one table column.

    Parameters
    ----------
    key : str
        Stable identifier. For a ``DataFrame`` source this is the column label;
        for a record source it is the attribute/item name used by the getter.
    label : str
        Header text. Falls back to ``key`` when empty.
    kind : str
        One of ``"float"``, ``"int"``, ``"bool"``, ``"str"`` or ``"auto"``.
        Drives alignment, value coercion and the default delegate.
    fmt : str
        Printf-style format for the display role (e.g. ``"%.6g"``). Empty means
        "use the table default" for numeric kinds and ``str`` otherwise.
    editable : bool
        Whether cells in this column accept edits. A source may still veto an
        individual cell through :meth:`TableSource.is_editable`.
    align : str
        ``"left"``, ``"right"``, ``"center"`` or ``""`` (derive from ``kind``).
    width : int
        Preferred pixel width; ``0`` means "size to contents".
    tooltip : str
        Column-level tooltip, shown on the header and as a fallback in cells.
    colorize : bool
        Opt this column into value-scaled cell backgrounds. Ignored unless the
        table's colour scheme is enabled.
    delegate : str
        Delegate hint: ``"bool"``, ``"float"``, ``"richtext"``, ``"choice"``,
        ``"bar"`` or ``""`` for none.
    choices : tuple of str
        Allowed values for ``delegate="choice"``.
    visible : bool
        Initial visibility. The column picker toggles this at runtime.
    value_range : tuple of float
        ``(lo, hi)`` for ``delegate="bar"``: the value is drawn as that fraction
        of the cell under its text, diverging from zero when the range spans it.
    """

    key: str
    label: str = ""
    kind: str = KIND_AUTO
    fmt: str = ""
    editable: bool = False
    align: str = ""
    width: int = 0
    tooltip: str = ""
    colorize: bool = False
    delegate: str = ""
    choices: tuple = field(default_factory=tuple)
    visible: bool = True
    value_range: tuple = field(default_factory=tuple)

    @property
    def title(self) -> str:
        """Return the header text, falling back to :attr:`key`.

        Returns
        -------
        str
        """
        return self.label or str(self.key)

    @property
    def is_numeric(self) -> bool:
        """Return whether the column holds numbers.

        Returns
        -------
        bool
        """
        return self.kind in NUMERIC_KINDS

    def resolved_format(self, default: str = DEFAULT_FORMAT) -> str:
        """Return the effective format string for this column.

        Parameters
        ----------
        default : str
            Table-wide fallback used for float columns without an explicit
            ``fmt``.

        Returns
        -------
        str
            A printf-style format, or ``""`` when values should be rendered
            with :func:`str`.
        """
        if self.fmt:
            return self.fmt
        if self.kind == KIND_FLOAT:
            return default
        return ""

    def with_(self, **changes: Any) -> ColumnSpec:
        """Return a copy of this spec with ``changes`` applied.

        Parameters
        ----------
        **changes
            Field overrides passed to :func:`dataclasses.replace`.

        Returns
        -------
        ColumnSpec
        """
        return replace(self, **changes)


def is_valid_format(fmt: str) -> bool:
    """Return whether ``fmt`` is a usable printf-style numeric format.

    Mirrors guidata's validation: a format must start with ``%`` and survive
    being applied to a float.

    Parameters
    ----------
    fmt : str
        Candidate format string.

    Returns
    -------
    bool
    """
    if not fmt.startswith("%"):
        return False
    try:
        fmt % 1.1
    except (TypeError, ValueError):
        return False
    return True


def specs_by_key(specs: Sequence[ColumnSpec]) -> dict:
    """Return a ``{key: index}`` lookup for a spec sequence.

    Parameters
    ----------
    specs : sequence of ColumnSpec
        Columns in table order.

    Returns
    -------
    dict
        Mapping of column key to its positional index.
    """
    return {spec.key: i for i, spec in enumerate(specs)}
