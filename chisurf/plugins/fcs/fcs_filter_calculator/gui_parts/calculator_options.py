"""AutoForm view-model for compact Filter Calculator options."""

from __future__ import annotations

import pathlib
from collections.abc import Callable

_VIEW = pathlib.Path(__file__).with_name("calculator_options.view.json")


class CalculatorOptionsViewModel:
    def __init__(
        self,
        on_polarized: Callable[[bool], None],
        on_background: Callable[[bool], None],
    ) -> None:
        self.polarized = False
        self.fit_background = True
        self.scatter_irf = True
        self._on_polarized = on_polarized
        self._on_background = on_background
        self._refresh: Callable[[], None] | None = None

    def set_refresh_callback(self, callback: Callable[[], None]) -> None:
        self._refresh = callback

    def view_spec(self):
        from chisurf.core.dataspec import load_view_spec

        return load_view_spec(_VIEW)

    def polarized_changed(self, value: bool) -> None:
        self._on_polarized(bool(value))

    def background_changed(self, value: bool) -> None:
        self._on_background(bool(value))

    def nuisance_changed(self, _value=None) -> None:
        self._on_background(bool(self.fit_background))
