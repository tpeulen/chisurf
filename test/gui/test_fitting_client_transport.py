"""A fit must not be sent over a socket to the process it is already in.

The GUI runs ``ChiSurfServer`` on a thread of *itself*, owning the very same fit
objects the GUI holds. Sending ``fit.run`` over ZMQ was therefore a round trip to
ourselves, and it did three bad things at once:

* the GUI thread blocked in ``recv``, so nothing repainted for the whole fit;
* the work happened on the *server* thread, where a progress callback cannot
  touch a widget anyway;
* the 5-second transport deadline expired mid-fit and **disabled RPC for the
  rest of the session** --

      FittingClient: disabling RPC after transport failure in 'fit.run':
      timeout: no response within 5000ms

A real MFD fit takes about two minutes, so it lost that race every time, and what
the user saw was a frozen window with no progress bar.
"""

from __future__ import annotations

import numpy as np
import pytest

import chisurf.core.data
import chisurf.core.fitting.fit
import chisurf.core.models.parse


class _Dispatcher:
    """Records what it was asked to dispatch."""

    def __init__(self):
        self.calls = []

    def dispatch(self, method, params=None):
        self.calls.append((method, dict(params or {})))
        return {"ok": True, "fit_index": 0}


class _Server:
    def __init__(self):
        self.dispatcher = _Dispatcher()


@pytest.fixture
def client():
    from chisurf.gui.widgets.fitting.fitting_client import FittingClient

    return FittingClient()


def test_an_embedded_server_is_called_in_process(client, monkeypatch):
    """No socket, so no deadline and no blocked GUI thread."""
    import chisurf

    server = _Server()
    monkeypatch.setattr(chisurf, "__chisurf_rpc_server__", server, raising=False)
    monkeypatch.setattr(
        client,
        "_try_rpc",
        lambda *a, **k: pytest.fail("a fit went over the wire to this process"),
    )
    result = client.run_fit(fit_uid="abc")
    assert result["ok"] is True
    assert server.dispatcher.calls == [("fit.run", {"fit_uid": "abc"})]


def test_a_remote_server_still_goes_over_the_wire(client, monkeypatch):
    """A blocking call is what the transport is *for* when the fit is elsewhere."""
    import chisurf

    monkeypatch.setattr(chisurf, "__chisurf_rpc_server__", None, raising=False)
    monkeypatch.setattr(chisurf, "__mmfdb_rpc_server__", None, raising=False)
    sent = []

    def _rpc(method, params):
        sent.append((method, params))
        return {"ok": True}

    monkeypatch.setattr(client, "_try_rpc", _rpc)
    assert client.run_fit(fit_index=2)["ok"] is True
    assert sent == [("fit.run", {"fit_index": 2})]


def test_a_call_already_inside_the_server_does_not_recurse(client, monkeypatch):
    """Dispatching from within a dispatch would re-enter the service."""
    import chisurf

    monkeypatch.setattr(chisurf, "__chisurf_rpc_server__", _Server(), raising=False)
    monkeypatch.setattr(client, "_in_server_dispatch", lambda: True)
    assert client._embedded_dispatcher() is None


def test_the_in_process_fit_reports_progress_on_the_calling_thread():
    """The whole point: the bar is driven from the thread that can repaint it."""
    import threading

    from chisurf.server.services.fits import run_fit
    from chisurf.server.session import SessionState

    x = np.linspace(0.0, 5.0, 48)
    curve = chisurf.core.data.DataCurve(x=x, y=3.0 + 1.2 * x**2, ey=np.full_like(x, 0.05))
    fit = chisurf.core.fitting.fit.Fit(data=curve, model_class=chisurf.core.models.parse.ParseModel)
    fit.fit_range = 0, len(fit.model.y)
    fit.model.func = "c+a*x**2"
    fit.model.find_parameters()

    state = SessionState()
    state.add_fit(fit)
    caller = threading.current_thread()
    threads = set()

    def on_progress(done, total, **kwargs):
        threads.add(threading.current_thread())

    with fit.reporting_progress(on_progress):
        assert run_fit(state, fit_uid=str(fit.unique_identifier))["ok"] is True
    assert threads == {caller}
