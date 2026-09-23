from __future__ import annotations

from chisurf.server.services import ServiceResult
from chisurf.server.session import SessionState


def build_fit_graph(
    state: SessionState,
    fit_indices: list[int] | None = None,
    fit_uids: list[str] | None = None,
    include_fixed: bool = True,
    connect_owners: bool = False,
) -> ServiceResult:
    """Build the parameter network of the session's fits, as JSON.

    The network is :func:`chisurf.core.fitting.parameter_network.build_parameter_network`'s,
    the one the Global View draws, so the service and the window cannot
    disagree about which edges exist.

    Parameters
    ----------
    state : SessionState
        The session.
    fit_indices : list of int, optional
        Positions of the fits to include; ignored when *fit_uids* is given.
    fit_uids : list of str, optional
        Unique identifiers of the fits to include. Defaults to every fit.
    include_fixed : bool
        Include fixed parameters as nodes.
    connect_owners : bool
        Join every pair of owner nodes.

    Returns
    -------
    dict
        ``{"ok": True, "graph": {"nodes": [...], "edges": [...]}}``.
    """
    from chisurf.core.fitting.parameter_network import (
        build_parameter_network,
        session_owners,
    )

    fits = list(state.fits)
    if fit_uids:
        wanted = set(fit_uids)
        selected = [
            i for i, f in enumerate(fits) if str(getattr(f, "unique_identifier", "")) in wanted
        ]
    elif fit_indices:
        selected = [i for i in fit_indices if 0 <= i < len(fits)]
    else:
        selected = list(range(len(fits)))
    owners = session_owners([fits[i] for i in selected], indices=selected)
    network = build_parameter_network(owners, include_fixed, connect_owners)
    return {"ok": True, "graph": network.to_dict()}
