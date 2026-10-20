"""Generate `quest/gui/quest.view.json` from the parameter catalog.

Same arrangement as `doc/generate_parameter_docs.py`: the catalog is written by
hand, everything derived from it is generated, and the generated file is
committed so it can be read and diffed. Never hand-edit `quest.view.json` —
edit `quest/settings/parameter_catalog.json` and run::

    python -m quest.gui.generate_view_spec

`tests/test_view_spec.py` regenerates in memory and fails if any committed file
differs, so they cannot drift.

One spec is written per language: `quest.view.json` (English) plus
`quest.view.<code>.json` for every locale in `quest/settings/locales/`. The
parameter text comes from the translated catalog and the rest from
`quest.i18n.ui_strings`, so a translation reaches the desktop form, the docs and
the web UI from one place.

What is generated: one panel per catalog *category*, one field per parameter,
with the catalog's label, type, unit and description. What is authored here:
the arrangement — which categories share a dock, where the structure viewer and
the plots go, and the toolbar. Those are judgements about a form, not facts
about a parameter, so they do not belong in the catalog.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from chisurf.plugins.quenching_estimator.core.i18n import (
    DEFAULT_LOCALE,
    available_locales,
    translate_catalog,
    ui_strings,
)
from chisurf.plugins.quenching_estimator.gui.form_model import FIELD_PATHS

__all__ = [
    "VIEW_SPEC_PATH",
    "build_view_spec",
    "view_spec_path",
    "write_view_spec",
    "write_all_view_specs",
]

VIEW_SPEC_PATH = Path(__file__).resolve().parent / "quest.view.json"


def view_spec_path(locale: str = DEFAULT_LOCALE) -> Path:
    """Where the spec for *locale* lives. English keeps the unsuffixed name."""
    if locale == DEFAULT_LOCALE:
        return VIEW_SPEC_PATH
    return VIEW_SPEC_PATH.with_name(f"quest.view.{locale}.json")


#: Catalog path → attribute on :class:`~quest.gui.form_model.ProjectFormModel`.
_ATTR_BY_PATH = {path: attr for attr, path in FIELD_PATHS.items()}
_ATTR_BY_PATH["fret.R0_matrix"] = "fret_R0"

#: Catalog ``type`` → AutoForm value ``kind``.
_KINDS = {"number": "float", "integer": "int", "text": "str", "file": "file"}

#: Sensible editor bounds per catalog path. A spin box needs *some* range; the
#: physics does not always imply one, so where it does not this is a
#: usability choice, not a constraint the simulation enforces.
_RANGES: dict[str, tuple[float, float]] = {
    "av_parameter.linker_length": (0.0, 200.0),
    "av_parameter.linker_width": (0.0, 50.0),
    "av_parameter.radius1": (0.0, 50.0),
    "av_parameter.allowed_sphere_radius": (0.0, 20.0),
    "av_parameter.radius_scale": (0.5, 1.5),
    "dg": (0.1, 5.0),
    "tau0": (0.0, 1000.0),
    "fret.dyes.0.D": (0.0, 1000.0),
    "fret.dyes.1.D": (0.0, 1000.0),
    # 0 = perpendicular transition dipoles, 4 = collinear.
    "fret.kappa2": (0.0, 4.0),
    "critical_distance": (0.0, 50.0),
    "slow_radius": (0.0, 50.0),
    "t_max": (0.0, 1e9),
    "t_step": (1e-6, 1000.0),
    "n_photons": (1, 2147483647),
    "n_bins": (1, 65535),
    "skip_frame": (1, 1000000),
    "parallel_trajectories": (-1, 1024),
    "random_seed": (0, 2147483647),
    "attachment.residue": (-100000, 100000),
    "fret.dyes.1.attachment.residue": (-100000, 100000),
    "fret.R0_matrix": (0.0, 500.0),
    "fret.dyes.1.av_parameter.linker_length": (0.0, 200.0),
    "fret.dyes.1.av_parameter.linker_width": (0.0, 50.0),
    "fret.dyes.1.av_parameter.radius1": (0.0, 50.0),
}

#: Decimals for float editors that need more than the default 3.
_DECIMALS = {"t_step": 6, "dg": 3}

#: Which catalog categories go in which panel of the left dock, in what order,
#: and under which translatable title. The first element is a stable key used in
#: the code; the visible title comes from `ui_strings`.
_PANELS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("structure", "panel.structure", ("Structure", "Labeling site")),
    ("dye", "panel.dye", ("Accessible volume",)),
    ("simulation", "panel.simulation", ("Simulation",)),
    ("quenching", "panel.quenching", ("Quenching",)),
    ("fret", "panel.fret", ("FRET Acceptor",)),
    ("advanced", "panel.advanced", ("Advanced",)),
)

#: Categories are laid out by :data:`_PANELS`; a parameter whose category is not
#: listed there would silently vanish from the form, so generation fails instead.
_LAID_OUT = {category for _, _, categories in _PANELS for category in categories}

#: Not rendered as a field of their own: the quencher table owns the donor's
#: chemistry, and the acceptor's defaults to it (see NON_SCALAR_PARAMETERS in
#: `form_model.py`, which documents where each one actually lives).
_TABLE_PATHS = {
    "fret.dyes.1.amino_acid_interactions",
    "amino_acid_interactions",
    "amino_acid_interactions.kQ",
    "amino_acid_interactions.quench_radius",
    "amino_acid_interactions.quench_atoms",
    "amino_acid_interactions.slow_factor",
}


def _field(path: str, entry: dict) -> dict[str, Any]:
    """One value/toggle section for a catalog parameter."""
    attr = _ATTR_BY_PATH[path]
    kind = entry.get("type", "text")
    description = entry.get("description", "")
    unit = entry.get("unit")
    label = entry.get("label", path)
    if unit:
        label = f"{label} ({unit})"

    if kind == "boolean":
        return {"type": "toggle", "attr": attr, "label": label, "description": description}

    if kind == "choice":
        # A parameter with a fixed set of values gets a combo, not a text box
        # someone can misspell. The values are the model's, so they are not
        # translated — only the label and the help are.
        return {
            "type": "choice",
            "attr": attr,
            "label": label,
            "description": description,
            "options": list(entry.get("options", ())),
        }

    section: dict[str, Any] = {
        "type": "value",
        "attr": attr,
        "kind": _KINDS.get(kind, "str"),
        "label": label,
        "description": description,
    }
    bounds = _RANGES.get(path)
    if bounds is not None:
        section["minimum"], section["maximum"] = bounds
    if path in _DECIMALS:
        section["decimals"] = _DECIMALS[path]
    return section


def _quencher_table(parameters: dict, strings: dict) -> dict[str, Any]:
    """The per-residue chemistry table. Column help comes from the catalog."""

    def column(
        key: str, label: str, width: int, path: str | None = None, description: str = ""
    ) -> dict[str, Any]:
        return {
            "key": key,
            "label": label,
            "width": width,
            "description": (parameters[path]["description"] if path else description),
        }

    return {
        "type": "table",
        "description": strings["table.quencher.description"],
        "source": "quencher_rows",
        "editable": True,
        "update_call": "update_quencher_cell",
        "expand": True,
        "height": 220,
        "columns": [
            column(
                "residue",
                strings["table.residue"],
                80,
                description=strings["table.residue.description"],
            ),
            # Table headers get their own short strings rather than the
            # catalog's form labels. A column header has a column's worth of
            # room, and "Löschrate kQ (1/ns)" does not fit in it — the full
            # wording stays as the tooltip, which is where it is readable.
            # The units are the model's, not the language's: kQ is 1/ns and the
            # radius is Å in every locale.
            column("kQ", strings["table.kQ"], 100, "amino_acid_interactions.kQ"),
            column(
                "quench_radius",
                strings["table.radius"],
                100,
                "amino_acid_interactions.quench_radius",
            ),
            column(
                "quench_atoms", strings["table.atoms"], 200, "amino_acid_interactions.quench_atoms"
            ),
            column(
                "slow_factor",
                strings["table.slow_factor"],
                90,
                "amino_acid_interactions.slow_factor",
            ),
        ],
    }


def _parameter_panels(parameters: dict, strings: dict) -> list[dict]:
    unknown = {
        entry.get("category")
        for path, entry in parameters.items()
        if path not in _TABLE_PATHS and entry.get("category") not in _LAID_OUT
    }
    if unknown:
        raise ValueError(
            f"parameter categories with no panel: {sorted(unknown)} — add them to "
            "_PANELS, or they would not appear in the form at all"
        )

    panels = []
    for key, title_key, categories in _PANELS:
        sections: list[dict] = [
            _field(path, entry)
            for path, entry in parameters.items()
            if path not in _TABLE_PATHS and entry.get("category") in categories
        ]
        if key == "quenching":
            sections.append(_quencher_table(parameters, strings))

        panels.append(
            {
                "type": "panel",
                "title": strings[title_key],
                "description": strings[f"{title_key}.description"],
                # One column throughout: the parameter dock is narrow by default
                # and QuEst's labels are long ("Donor diffusion coefficient
                # (Å²/ns)"), so two columns clip the field the user is typing in.
                # Translations are longer still — German more so than English.
                "n_col": 1,
                # Advanced starts folded — it is the panel nobody needs on the
                # first run, and it is long enough to push FRET off the screen.
                "collapsed": key == "advanced",
                "sections": sections,
            }
        )
    return panels


def _plot(source: str, prefix: str, strings: dict, **extra: Any) -> dict[str, Any]:
    section = {
        "type": "plot",
        "source": source,
        "title": strings[f"{prefix}.title"],
        "x_label": strings[f"{prefix}.x"],
        "y_label": strings[f"{prefix}.y"],
        "description": strings[f"{prefix}.description"],
    }
    section.update(extra)
    return section


def build_view_spec(locale: str = DEFAULT_LOCALE) -> dict[str, Any]:
    """The whole form in one language, as a view spec AutoForm can render."""
    catalog = translate_catalog(locale)
    parameters = catalog["parameters"]
    strings = ui_strings(locale)

    return {
        "_comment": (
            "GENERATED by quest/gui/generate_view_spec.py from "
            "quest/settings/parameter_catalog.json and "
            "quest/settings/locales/ — do not hand-edit. Bound to "
            "quest.gui.form_model.ProjectFormModel, whose state is a QuEst "
            "project dict, so what this form saves is what the CLI runs."
        ),
        "locale": catalog.get("locale", locale),
        "sections": [
            {
                "type": "custom",
                "key": "help",
                "description": strings["help.description"],
                "options": {
                    "title": strings["help.title"],
                    "text": strings["help.text"],
                },
            },
            {
                "type": "dock_area",
                "split": "horizontal",
                "height": 620,
                # Remember how the user arranged the docks. A form whose layout
                # resets on every launch gets rearranged on every launch.
                "persist": "quest",
                "sections": [
                    {
                        "type": "panel",
                        "title": strings["dock.project"],
                        "description": strings["dock.project.description"],
                        "sections": _parameter_panels(parameters, strings),
                    },
                    {
                        "type": "panel",
                        "title": strings["dock.structure"],
                        "description": strings["dock.structure.description"],
                        "sections": [
                            {
                                "type": "value",
                                "attr": "structure_label",
                                "kind": "str",
                                "label": strings["dock.structure"],
                                "read_only": True,
                                "description": strings["field.state.description"],
                            }
                        ],
                    },
                    {
                        "type": "panel",
                        "title": strings["dock.results"],
                        "description": strings["dock.results.description"],
                        "sections": [
                            {
                                "type": "value",
                                "attr": "status",
                                "kind": "str",
                                "label": strings["field.state"],
                                "read_only": True,
                                "description": strings["field.state.description"],
                            },
                            _plot("decay_series", "plot.decay", strings, log_y=True, height=240),
                            _plot("trajectory_series", "plot.trajectory", strings, height=200),
                            _plot(
                                "autocorrelation_series",
                                "plot.autocorrelation",
                                strings,
                                log_x=True,
                                height=200,
                            ),
                        ],
                    },
                ],
            },
            {
                "type": "button_row",
                "buttons": [
                    {
                        "label": strings["button.simulate"],
                        # The form's one primary action (emtk button roles).
                        "role": "primary",
                        "action": "run_simulation",
                        "description": strings["button.simulate.description"],
                    },
                    {
                        "label": strings["button.load_example"],
                        "icon": "🧪",
                        "action": "load_example",
                        "description": strings["button.load_example.description"],
                    },
                    {
                        "label": strings["button.load_project"],
                        "action": "load_project_dialog",
                        "description": strings["button.load_project.description"],
                    },
                    {
                        "label": strings["button.save_project"],
                        "action": "save_project_dialog",
                        "description": strings["button.save_project.description"],
                    },
                ],
            },
        ],
    }


def write_view_spec(path: Path | str | None = None, locale: str = DEFAULT_LOCALE) -> Path:
    """Write one language's spec. Defaults to that locale's canonical path."""
    destination = Path(path) if path is not None else view_spec_path(locale)
    destination.write_text(
        json.dumps(build_view_spec(locale), indent=2, ensure_ascii=False) + "\n",
        encoding="utf8",
    )
    return destination


def write_all_view_specs() -> list[Path]:
    """Regenerate every language. This is what the `__main__` entry point runs."""
    return [write_view_spec(locale=code) for code in sorted(available_locales())]


if __name__ == "__main__":  # pragma: no cover - a one-line entry point
    for written in write_all_view_specs():
        print(f"wrote {written}")
