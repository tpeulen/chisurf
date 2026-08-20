"""One row per fitting model, read from the experiment registry.

Two things this fixes about how the manager used to read the registry.

**The list was empty.** ``Experiment.model_classes`` is filled by whoever
registers the models -- the GUI does it during startup, and
:func:`~chisurf.core.experiments.bootstrap.ensure_experiments_registered` is the
headless equivalent. The manager iterated the registry without ensuring either
had run, so opening it before a fit was set up showed nothing at all, with no
message saying why.

**Rows were keyed by display name, which is not unique.** ``ParseFCSModel``
(fcs) and ``ParsePCFModel`` (pcf) are both called ``Parse-Model``, so the second
overwrote the first: selecting the FCS row showed PCF's module and docstring.
Rows are keyed by ``module.qualname`` here. The *setting* stays keyed by display
name, because that is what ``chisurf/gui/main.py`` matches against when it
filters the model combo -- so a shared name really does disable both models, and
:attr:`ModelRow.shares_name_with` says so rather than leaving it a surprise.
"""

from __future__ import annotations

import pathlib
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ModelRow:
    """Everything the manager shows about one fitting model."""

    key: str
    name: str
    experiment: str
    experiment_label: str
    module: str
    qualname: str
    doc: str
    #: Path declared by ``view_spec_file``, if the class declares one.
    view_spec: str = ""
    #: Whether that declared spec actually resolves on disk.
    view_spec_ok: bool = False
    #: Whether the class is still a Qt widget subclass (PRD-38 migration debt).
    qt_bound: bool = False
    disabled: bool = False
    #: Other models sharing this display name -- disabling hits all of them.
    shares_name_with: list[str] = field(default_factory=list)

    def as_record(self) -> dict[str, Any]:
        """The row as a flat table record."""
        return {
            "name": self.name,
            "experiment": self.experiment_label,
            "status": "disabled" if self.disabled else "enabled",
            "spec": self.spec_text(),
            "ui": "Qt class" if self.qt_bound else "spec-driven",
            "module": self.module,
            "shared": ", ".join(self.shares_name_with),
        }

    def spec_text(self) -> str:
        """How this model's parameter UI is described."""
        if not self.view_spec:
            return "none"
        return "ok" if self.view_spec_ok else "missing file"


def _qt_bound(model_class) -> bool:
    """Whether *model_class* still inherits from a Qt widget."""
    for base in getattr(model_class, "__mro__", ()):
        if base.__module__.startswith(("PyQt", "PySide", "qtpy")):
            return True
    return False


def _view_spec_of(model_class) -> tuple[str, bool]:
    """The declared ``view_spec_file`` and whether it resolves."""
    declaring = next(
        (
            c for c in getattr(model_class, "__mro__", ())
            if "view_spec_file" in c.__dict__ and c.__dict__["view_spec_file"]
        ),
        None,
    )
    if declaring is None:
        return "", False
    spec = str(declaring.__dict__["view_spec_file"])
    try:
        import importlib

        module = importlib.import_module(declaring.__module__)
        base = pathlib.Path(module.__file__).parent
    except Exception:
        return spec, False
    return spec, (base / spec).is_file()


def collect_model_rows(
    experiments: dict[str, Any] | None = None,
    *,
    disabled: list[str] | None = None,
    ensure_registered: bool = True,
) -> list[ModelRow]:
    """Build one :class:`ModelRow` per registered model.

    Parameters
    ----------
    experiments : dict, optional
        ``{key: Experiment}``. Defaults to the live registry.
    disabled : list of str, optional
        Display names from ``plugins.disabled_models``.
    ensure_registered : bool, optional
        Run the headless registration first when the registry looks empty.
        This is what stops the list being blank outside a GUI session.

    """
    if experiments is None:
        import chisurf.core.experiments as experiments_module

        if ensure_registered and not any(
            getattr(e, "model_classes", []) for e in experiments_module.types.values()
        ):
            try:
                from chisurf.core.experiments.bootstrap import (
                    ensure_experiments_registered,
                )

                ensure_experiments_registered()
            except Exception:  # pragma: no cover - registration is best-effort
                pass
        experiments = experiments_module.types

    off = {str(x) for x in (disabled or [])}
    rows: list[ModelRow] = []
    for exp_key, experiment in experiments.items():
        label = getattr(experiment, "name", "") or exp_key
        for model_class in getattr(experiment, "model_classes", []) or []:
            name = str(getattr(model_class, "name", "") or model_class.__name__)
            spec, spec_ok = _view_spec_of(model_class)
            rows.append(
                ModelRow(
                    key=f"{model_class.__module__}.{model_class.__qualname__}",
                    name=name,
                    experiment=exp_key,
                    experiment_label=str(label),
                    module=model_class.__module__,
                    qualname=model_class.__qualname__,
                    doc=(model_class.__doc__ or "").strip(),
                    view_spec=spec,
                    view_spec_ok=spec_ok,
                    qt_bound=_qt_bound(model_class),
                    disabled=name in off,
                )
            )

    by_name: dict[str, list[ModelRow]] = {}
    for row in rows:
        by_name.setdefault(row.name, []).append(row)
    for name, group in by_name.items():
        if len(group) > 1:
            for row in group:
                row.shares_name_with = sorted(
                    f"{other.experiment_label}" for other in group if other is not row
                )
    return rows
