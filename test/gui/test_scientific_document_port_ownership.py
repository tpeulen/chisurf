"""Display-only table scalars lead to portable model state.

The AutoForm table inventory (owner path, kind, editable) these tests used to read from the Qt
editor went with the Qt shell. What stays is the model side: a declared display scalar edits the
model state the project persists, and a read-only output never dereferences an absent slot.
"""

from __future__ import annotations

import math

import pytest

pytest.importorskip("IMP.bff")

from chisurf.core.project.session import capture_session, restore_session
from chisurf.core.project.storage import load_file, save_file
from test.gui.test_classic_tcspc_editor import _fit


def test_tcspc_display_scalar_survives_a_project_round_trip(tmp_path):
    """``rep`` projects the description scalar ``period`` as MHz and persists as such.

    ``rep`` is intentionally not in ``parameters_all``; editing it must change the model scalar,
    which must then survive an ordinary ``.cs.pto`` round trip.
    """
    fit, model = _fit("tcspc_polarized")
    row = next(parameter for parameter in model.convolve.parameters_all if parameter.name == "rep")
    row.value = 12.5
    assert model.get_scalar("period") == pytest.approx(80.0)

    member = fit.grouped_fits[0]
    project = capture_session([member.data], [fit], name="tcspc-display-binding")
    adapter_state = project.fits[0]["members"][0]["model"]["adapter_state"]
    assert adapter_state["scalars"]["period"] == pytest.approx(80.0)

    archive = save_file(project, tmp_path / "tcspc-display-binding.cs.pto")
    restored = restore_session(load_file(archive)).fits[0].grouped_fits[0].model
    assert restored.get_scalar("period") == pytest.approx(80.0)


def test_maxent_generic_output_display_handles_an_absent_background_slot():
    """A read-only photon-count display cannot dereference an undeclared source."""
    from test.project.test_maxent_snapshot_contracts import _description_fit

    fit = _description_fit("tcspc_maxent_lifetime")
    model = fit.model
    assert not model.has_dataset("background_pattern")
    assert model.generic.background_curve is None
    assert math.isfinite(float(model.generic.n_ph_bg))
