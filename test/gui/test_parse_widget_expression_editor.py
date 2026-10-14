"""The parse models' equation: seeding from the catalogue and the declared scalar rows.

The shared Qt ``ExpressionInput`` (validity badge, preview, parameter discovery) went with the Qt
shell; what is checked here is the model side every parse editor depends on.
"""

from __future__ import annotations

import numpy as np
import pytest


@pytest.fixture()
def model():
    """Return a TCSPC parse model over a synthetic decay with a response."""
    import chisurf.core.fitting.fit as fit_mod
    from chisurf.core.curve import Curve
    from chisurf.core.data import DataCurve
    from chisurf.core.models.tcspc.parse.tcspc_parse import ParseDecayModel

    x = np.linspace(0.05, 25, 256)
    data = DataCurve(name="synthetic", load_filename_on_init=False, x=x, y=np.exp(-x / 4.0) + 1.0)
    m = fit_mod.Fit(model_class=ParseDecayModel, data=data).model
    # The equations are convolved with a response, which the model needs.
    m.set_dataset("response", Curve(x=x, y=np.exp(-0.5 * ((x - 1.0) / 0.1) ** 2)))
    m.set_scalar("period", 12.5)
    return m


def test_the_model_opens_on_the_catalogue_equation(model):
    """It opens showing a non-empty equation the selected catalogue entry defines."""
    assert str(model.func).strip()
    assert model.model_name in list(model.catalogue_names)


def test_choosing_a_catalogue_entry_changes_the_equation(model):
    """The ``choice`` over ``catalogue_names`` drives ``func`` through the model."""
    names = list(model.catalogue_names)
    if len(names) < 2:
        pytest.skip("catalogue has fewer than two entries")
    before = str(model.func)
    model.model_name = next(n for n in names if n != model.model_name)
    assert str(model.func) != before


def test_committing_an_equation_discovers_its_parameters(model):
    """Writing a valid equation to the model makes its free names parameters."""
    model.func = "a1*exp(-x/tau1) + b"
    model.find_parameters()
    assert "b" in model.parameters_all_dict
    assert "tau1" in model.parameters_all_dict


def test_parse_convolution_rows_only_declare_persisted_scalars(model):
    """Generated ParseDecay rows cannot expose an inert non-persisted scalar."""
    unsupported = []
    for parameter in model.parameters_all:
        binding = getattr(parameter, "display_binding", None)
        if binding and binding["kind"] == "model_scalar":
            if binding["path"] not in model.scalar_names():
                unsupported.append((parameter.name, binding["path"]))
    assert not unsupported
