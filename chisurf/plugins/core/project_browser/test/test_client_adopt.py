"""The adopting ProjectBrowserClient carries every per-instance field of its base."""

from chisurf.core.plugin.client import InProcessClient
from chisurf.plugins.core.mmfdb_admin.gui.client import MMFDBClient
from chisurf.plugins.core.project_browser.gui.client import ProjectBrowserClient
from chisurf.server.dispatcher import ServiceDispatcher
from chisurf.server.session import SessionState


def test_adopting_a_client_sets_every_field_the_base_constructor_sets():
    """``ProjectBrowserClient(mmfdb_client=...)`` skips ``MMFDBClient.__init__``.

    A field added to the base constructor and not to the adopting branch raised
    ``AttributeError`` on the first call (``_closed``), so compare the instance
    dictionaries rather than naming fields.
    """
    base = MMFDBClient(client=InProcessClient(ServiceDispatcher(SessionState())))
    adopted = ProjectBrowserClient(mmfdb_client=base)
    missing = set(vars(base)) - set(vars(adopted))
    assert not missing, f"adopting ProjectBrowserClient lacks {sorted(missing)}"
    assert adopted._client is base._client
