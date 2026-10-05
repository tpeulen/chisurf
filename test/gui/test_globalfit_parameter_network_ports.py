"""Global-fit global ports must be addressable GUI ports, not invisible state."""

from __future__ import annotations

import pytest


@pytest.fixture
def global_session():
    from test.project.test_global_snapshot_contracts import _global

    fit, sources = _global()
    return fit, sources


def test_session_owners_include_declared_global_ports(global_session):
    """``shared rate`` is a document-owned port; the GUI table must see it.

    ``parameter_network.session_owners`` deliberately skips the aggregate
    ``GlobalFitModel`` so member parameters are not listed twice. That skip
    also removed the model's *own* declared global ports (``shared rate``) —
    the exact port the catalogue producer edits and that
    ``owned_scientific_objects`` (via ``get_session_parameters``) owns — so the
    Global View's parameter table rendered no row for it and the actual-Main
    probe could not address the edit through any generated control.
    """
    fit, sources = global_session
    from chisurf.core.fitting.parameter_network import parameter_rows, session_owners

    shared = fit.model.global_parameters_all[0]
    owners = session_owners([fit, *sources])
    rows = parameter_rows(owners)

    assert any(row.param is shared for row in rows), (
        "declared GlobalFitModel global port is absent from session_owners"
    )
    # Member parameters stay single-listed: the member's own ports appear once.
    member_param = sources[0].model.parameters_all[0]
    member_rows = [row for row in rows if row.param is member_param]
    assert len(member_rows) == 1


def test_session_owners_skip_stays_exact_without_global_ports(global_session):
    """Ordinary fits keep their existing enumeration unchanged."""
    fit, sources = global_session
    from chisurf.core.fitting.parameter_network import parameter_rows, session_owners

    # A session that contains only the member fits must not grow a fake owner.
    rows = parameter_rows(session_owners(list(sources)))
    assert len(rows) == sum(len(m.model.parameters_all) for m in sources)
    assert all(row.kind == "fit" for row in rows)
