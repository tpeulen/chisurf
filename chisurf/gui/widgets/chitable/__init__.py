"""chitable — the one table widget family for ChiSurf.

ChiSurf's tables used to be a third-party ``DataFrameEditor`` plus a few dozen
hand-rolled ``QTableWidget``s, none of which shared sorting, filtering, column
hiding, colouring or export. chitable is the single model/view implementation
those call sites now share, in the spirit of the ``chiplot`` plotting seam: one
facade, swappable internals, no third-party GUI dependency.

Typical use — a frame with every feature switched on::

    from chisurf.gui.widgets.chitable import ChiTableWidget

    table = ChiTableWidget()
    table.set_dataframe(df)

A modal editor with staged Apply/Cancel::

    from chisurf.gui.widgets.chitable import edit_dataframe

    edited = edit_dataframe(df, parent=self, title="Model parameters",
                            readonly_columns=("name",), bool_columns=("fixed",))
    if edited is not None:
        ...

An existing model that must keep its own edit semantics::

    table = ChiTableWidget(model=my_model)   # gains search/filter/hide/copy

See :doc:`the subsystem concept </subsystems/gui-tables.md>` in the OKF bundle
for the design rationale.
"""

from chisurf.gui.widgets.chitable.colorize import ValueColorScheme
from chisurf.gui.widgets.chitable.columns import (
    DEFAULT_FORMAT,
    ColumnSpec,
    is_valid_format,
)
from chisurf.gui.widgets.chitable.delegates import (
    BooleanToggleDelegate,
    ChoiceDelegate,
    FloatEditDelegate,
    RichTextDelegate,
    RichTextHeaderView,
    delegate_for,
)
from chisurf.gui.widgets.chitable.dialogs import ColumnFilterDialog, ColumnPickerDialog
from chisurf.gui.widgets.chitable.editor import (
    ChiTableDialog,
    edit_dataframe,
    show_dataframe,
)
from chisurf.gui.widgets.chitable.filters import ColumnFilter, FilterSpec
from chisurf.gui.widgets.chitable.model import ChiTableModel
from chisurf.gui.widgets.chitable.proxy import ForeignTableProxy, ReadOnlyColumnProxy
from chisurf.gui.widgets.chitable.source import (
    ArraySource,
    DataFrameSource,
    DataStoreSource,
    RecordSource,
    TableSource,
)
from chisurf.gui.widgets.chitable.view import ChiTableView
from chisurf.gui.widgets.chitable.widget import (
    DEFAULT_FEATURES,
    ChiTableWidget,
    TableFeature,
)

__all__ = [
    "ArraySource",
    "BooleanToggleDelegate",
    "ChiTableDialog",
    "ChiTableModel",
    "ChiTableView",
    "ChiTableWidget",
    "ChoiceDelegate",
    "ColumnFilter",
    "ColumnFilterDialog",
    "ColumnPickerDialog",
    "ColumnSpec",
    "DEFAULT_FEATURES",
    "DEFAULT_FORMAT",
    "DataFrameSource",
    "DataStoreSource",
    "FilterSpec",
    "FloatEditDelegate",
    "ForeignTableProxy",
    "ReadOnlyColumnProxy",
    "RecordSource",
    "RichTextDelegate",
    "RichTextHeaderView",
    "TableFeature",
    "TableSource",
    "ValueColorScheme",
    "delegate_for",
    "edit_dataframe",
    "is_valid_format",
    "show_dataframe",
]
