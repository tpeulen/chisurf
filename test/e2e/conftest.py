"""Mark every test under ``test/e2e`` as ``e2e``."""

import pytest


def pytest_collection_modifyitems(config, items):
    """Mark every test under ``test/e2e`` as ``e2e``.

    The suites are carved out by marker (see ``test/test_suite_partition.py``), so the
    directory must announce itself with the marker rather than rely on a path list in
    the ``test-e2e`` task.
    """
    import pathlib

    here = pathlib.Path(__file__).parent.resolve()
    for item in items:
        if here in pathlib.Path(str(item.path)).resolve().parents:
            item.add_marker(pytest.mark.e2e)
