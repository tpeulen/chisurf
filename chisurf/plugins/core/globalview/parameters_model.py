"""Tiny AutoForm model backing the Global View's *Parameters* tab.

The Parameters tab is not the editor of a single fitting model — it spans every
fit and every registered out-of-fit group. So instead of a real
:class:`~chisurf.core.models.model.Model`, it is driven by this minimal object
whose :meth:`view_spec` emits one
:class:`~chisurf.core.dataspec.CustomSection` (key ``"global_parameter_table"``).
The concrete widget (rows, editing, linking) lives GUI-side in
:mod:`chisurf.gui.autoform.sections.global_parameter_table`.
"""

from __future__ import annotations

from chisurf.core.dataspec import CustomSection, ModelView


class GlobalViewParametersModel:
    """AutoForm-compatible stand-in exposing the global parameter table.

    Only :meth:`view_spec` is required by
    :class:`~chisurf.gui.autoform.auto_form.AutoForm`.
    """

    #: Human-readable name (used by some AutoForm fallbacks).
    name = "Global parameters"

    def view_spec(self) -> ModelView:
        """Return a one-section view spec hosting the global parameter table."""
        return ModelView(
            sections=(
                CustomSection(
                    key="global_parameter_table",
                    title="All fitting parameters",
                ),
            )
        )
