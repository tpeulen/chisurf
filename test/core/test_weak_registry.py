"""The registries of open editors and help windows must not keep their members alive."""

import gc

import pytest

from chisurf.core.support.weak_registry import WeakOrderedRegistry


class _Window:
    pass


def test_entries_keep_their_order_and_membership():
    registry = WeakOrderedRegistry()
    first, second = _Window(), _Window()
    registry.append(first)
    registry.append(second)
    registry.append(first)  # twice is once
    assert list(registry) == [first, second]
    assert list(reversed(registry)) == [second, first]
    assert first in registry and len(registry) == 2
    registry.remove(first)
    assert first not in registry and list(registry) == [second]
    with pytest.raises(ValueError):
        registry.remove(first)


def test_a_collected_window_leaves_the_registry():
    registry = WeakOrderedRegistry()
    window = _Window()
    registry.append(window)
    assert registry
    del window
    gc.collect()
    assert not registry and len(registry) == 0


def test_the_shipped_registries_are_weak():
    from chisurf.emtk.code_links import _ACTIVE_EMTK_EDITORS
    from chisurf.plugins.core.help.gui.help_app import _ACTIVE_HELP_INSTANCES

    assert isinstance(_ACTIVE_EMTK_EDITORS, WeakOrderedRegistry)
    assert isinstance(_ACTIVE_HELP_INSTANCES, WeakOrderedRegistry)
