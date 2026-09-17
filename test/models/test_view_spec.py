"""Headless tests for the model view-spec layer (no Qt required)."""

from __future__ import annotations

import numpy as np

from chisurf.core.models import view_spec as vs


def test_view_spec_vocabulary_is_pure_data():
    """The view-spec dataclasses are plain, comparable, hashable data."""
    view = vs.ModelView(
        sections=(
            vs.ParameterGroupSection(target="generic", title="Generic"),
            vs.DynamicGroupSection(target="lifetimes", title="Lifetimes", row_width=2),
            vs.CustomSection(key="my_panel", target="anisotropy"),
        ),
        plots=(vs.PlotSpec("line", {"y_label": "counts"}),),
    )
    assert view.section_targets() == ["generic", "lifetimes", "anisotropy"]
    # frozen dataclasses are hashable / equality-comparable
    assert vs.PlotSpec("line") == vs.PlotSpec("line")


def _make_view(family):
    """A BFF-described TCSPC view on a tiny in-memory fit, or skip."""
    import pytest

    pytest.importorskip("IMP.bff")
    import chisurf.core.fitting.fit as fit_mod
    from chisurf.core.data import DataCurve
    from chisurf.core.models.description import for_family

    x = np.linspace(0, 25, 256)
    fit = fit_mod.Fit(model_class=for_family(family), data=DataCurve(x=x, y=np.ones_like(x)))
    model = fit.model
    if "generated_response" in model.scalar_names():
        model.set_scalar("generated_response", 1.0)  # a modelled IRF: the model builds
    model.problem
    return model


def test_lifetime_model_view_spec_structure():
    """The lifetime view derives its editor from the description, as data."""
    model = _make_view("tcspc_lifetime")
    spec = model.view_spec()
    assert isinstance(spec, vs.ModelView)
    targets = spec.section_targets()
    for expected in ("lifetimes", "instrument"):
        assert expected in targets, f"missing section target {expected!r}"
    plot_keys = [p.key for p in spec.plots]
    assert {"line", "residual", "distribution"} <= set(plot_keys)
    assert all(isinstance(p.key, str) for p in spec.plots)
    for target in targets:
        assert hasattr(model, target), f"unresolved target {target!r}"


def test_curve_input_section_loads_from_json():
    """The curve_input section type round-trips through the JSON loader as pure
    data (no Qt), carrying the action names and payload keys (PRD-38).
    """
    spec = vs.load_view_spec(
        {
            "sections": [
                {
                    "type": "curve_input",
                    "target": "convolve",
                    "label": "IRF",
                    "select_action": "model.change_irf",
                    "unload_action": "model.unload_irf",
                    "index_key": "irf_idx",
                    "name_key": "irf_name",
                    "name_attr": "irf",
                },
            ],
            "plots": [],
        }
    )
    sec = spec.sections[0]
    assert isinstance(sec, vs.CurveInputSection)
    assert sec.target == "convolve" and sec.label == "IRF"
    assert sec.select_action == "model.change_irf"
    assert sec.unload_action == "model.unload_irf"
    assert sec.index_key == "irf_idx" and sec.name_key == "irf_name"
    assert sec.name_attr == "irf"


def test_lifetime_view_has_irf_curve_input():
    """The lifetime editor binds a measured response through the view's dataset action."""
    spec = _make_view("tcspc_lifetime").view_spec()
    inputs = [s for s in spec.flat_sections() if isinstance(s, vs.CurveInputSection)]
    irf = next((s for s in inputs if (s.action_fixed or {}).get("slot") == "response"), None)
    assert irf is not None and irf.select_action == "model.set_dataset"


def test_choice_and_toggle_sections_load_from_json():
    """choice/toggle section types round-trip as pure data with their binding
    fields (attr- or action-bound).
    """
    spec = vs.load_view_spec(
        {
            "sections": [
                {
                    "type": "choice",
                    "target": "convolve",
                    "attr": "mode",
                    "label": "Type",
                    "options": ["per", "exp", "full"],
                },
                {
                    "type": "toggle",
                    "target": "convolve",
                    "attr": "do_convolution",
                    "label": "Convolve",
                },
                {
                    "type": "choice",
                    "target": "corrections",
                    "attr": "window_function",
                    "label": "Smoothing",
                    "options_source": "window_function_types",
                },
            ],
            "plots": [],
        }
    )
    choice, toggle, smoothing = spec.sections
    assert isinstance(choice, vs.ChoiceSection)
    assert choice.attr == "mode" and choice.options == ("per", "exp", "full")
    assert isinstance(toggle, vs.ToggleSection) and toggle.attr == "do_convolution"
    assert smoothing.options_source == "window_function_types"


def test_lifetime_view_exposes_its_settings():
    """What the hand-written widget's controls set are the description's scalars."""
    spec = _make_view("tcspc_lifetime").view_spec()
    attrs = {
        s.attr for s in spec.flat_sections() if isinstance(s, (vs.ToggleSection, vs.ValueSection))
    }
    assert {
        "scalars.convolve",
        "scalars.periodic_excitation",
        "scalars.pile_up",
        "scalars.autoscale",
        "scalars.lin_window",
    } <= attrs


def test_parameter_group_view_adapter_builds_a_section():
    """PRD-40 Task 4: a FittingParameterGroup renders via ParameterGroupView with
    no JSON — the adapter yields a one-section ModelView targeting the group.
    """
    from chisurf.core import dataspec as ds
    from chisurf.core.fitting.parameter import FittingParameter, FittingParameterGroup

    group = FittingParameterGroup(
        name="kinetics",
        parameters=[
            FittingParameter(name="k1", value=1.0),
            FittingParameter(name="k2", value=2.0),
        ],
    )

    view = ds.ParameterGroupView(group, collapsed=True).view_spec()
    assert isinstance(view, ds.ModelView)
    assert len(view.sections) == 1
    section = view.sections[0]
    assert isinstance(section, ds.ParameterGroupSection)
    assert section.target == "group"  # resolved by AutoForm via getattr
    assert section.title == "kinetics"  # defaults to the group's name
    assert section.collapsed is True
    # the adapter exposes the group at the resolved attribute name
    assert ds.ParameterGroupView(group).group is group


def test_value_section_loads_from_json():
    """PRD-40: the generic scalar field (int/float/str) parses from JSON."""
    spec = vs.load_view_spec(
        {
            "sections": [
                {
                    "type": "value",
                    "label": "N bins",
                    "kind": "int",
                    "target": "setup",
                    "attr": "n_bins",
                    "minimum": 1,
                    "maximum": 64,
                },
                {
                    "type": "value",
                    "label": "Name",
                    "kind": "str",
                    "target": "setup",
                    "attr": "name",
                    "placeholder": "untitled",
                },
            ],
            "plots": [],
        }
    )
    n_bins, name = spec.sections
    assert isinstance(n_bins, vs.ValueSection)
    assert n_bins.kind == "int" and n_bins.attr == "n_bins"
    assert (n_bins.minimum, n_bins.maximum) == (1, 64)
    assert name.kind == "str" and name.placeholder == "untitled"


def test_parameter_group_table_section_round_trips_from_json():
    """PRD-44: ParameterGroupTableSection parses from JSON with column
    subsetting and folds through flat_sections().
    """
    spec = vs.load_view_spec(
        {
            "sections": [
                {
                    "type": "parameter_group_table",
                    "target": "convolve",
                    "collapsible": False,
                    "columns": ["name", "value", "fixed", "error"],
                },
                {
                    "type": "panel",
                    "title": "Outer",
                    "sections": [
                        {
                            "type": "parameter_group_table",
                            "target": "lifetimes",
                            "columns": ["name", "value"],
                        },
                    ],
                },
            ],
            "plots": [],
        }
    )
    assert len(spec.sections) == 2

    table = spec.sections[0]
    assert isinstance(table, vs.ParameterGroupTableSection)
    assert table.target == "convolve"
    assert table.collapsible is False
    assert table.columns == ("name", "value", "fixed", "error")

    # nested inside a panel
    panel = spec.sections[1]
    assert isinstance(panel, vs.PanelSection)
    nested = panel.sections[0]
    assert isinstance(nested, vs.ParameterGroupTableSection)
    assert nested.target == "lifetimes"
    assert nested.columns == ("name", "value")

    # flat_sections covers both top-level and nested
    flat = spec.flat_sections()
    table_ids = [id(s) for s in flat if isinstance(s, vs.ParameterGroupTableSection)]
    assert len(table_ids) == 2
    assert id(table) in table_ids
    assert id(nested) in table_ids

    # section_targets resolves correctly
    assert "convolve" in spec.section_targets()
    assert "lifetimes" in spec.section_targets()

    # empty columns means all columns
    spec2 = vs.load_view_spec(
        {
            "sections": [
                {"type": "parameter_group_table", "target": "g", "columns": []},
            ],
        }
    )
    assert spec2.sections[0].columns == ()


def test_parameter_group_table_section_hashable():
    """ParameterGroupTableSection is frozen and hashable like the rest."""
    s1 = vs.ParameterGroupTableSection(target="a", columns=("name", "value"))
    s2 = vs.ParameterGroupTableSection(target="a", columns=("name", "value"))
    s3 = vs.ParameterGroupTableSection(target="a", columns=("name",))
    assert s1 == s2
    assert s1 != s3
    assert hash(s1) == hash(s2)

    # works in sets
    _ = {s1, s2, s3}  # no error
    assert len({s1, s2, s3}) == 2


def test_mix_model_view_spec_structure():
    """The mixture view shows its sources in a fit_mixer section and a lifetime distribution."""
    spec = _make_view("tcspc_mixture").view_spec()
    customs = [s for s in spec.flat_sections() if isinstance(s, vs.CustomSection)]
    assert any(s.key == "fit_mixer" for s in customs)
    assert {"line", "residual"} <= {p.key for p in spec.plots}


def test_plot_section_axis_ranges_are_parsed():
    """A plot section can pin its axes to the quantity's natural domain.

    Without it a single divide-by-almost-zero burst (an acceptor-only molecule
    has no donor signal, so its "efficiency" is unbounded) squeezes an entire
    E-S plot into one pixel column.
    """
    from chisurf.core.dataspec import _section_from_dict

    section = _section_from_dict(
        {
            "type": "plot",
            "source": "es_series",
            "x_range": [-0.1, 1.1],
            "y_range": [-0.1, 1.1],
        }
    )
    assert section.x_range == (-0.1, 1.1)
    assert section.y_range == (-0.1, 1.1)
    # absent by default -> the renderer autoscales
    assert _section_from_dict({"type": "plot", "source": "s"}).x_range == ()
