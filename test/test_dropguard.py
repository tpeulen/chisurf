"""The drop-guard registry (chisurf.gui.widgets.dropguard) is opt-in per drop zone.

No guard named -> nothing happens, nothing is shown. Two guards named -> each
only ever sees the paths its own ``applies()`` accepted, and does not
interfere with the other's. These two properties are what make the pattern
usable by drop zones that disagree about what should nag them.
"""

from __future__ import annotations

from chisurf.gui.widgets.dropguard import (
    DropGuard,
    apply_drop_guards,
    get_drop_guard,
    register_drop_guard,
)


def test_no_guards_named_is_inert():
    """The default (`guard_names=()`) returns the paths unchanged."""
    paths = ["a.ptu", "b.spc"]
    assert apply_drop_guards(None, paths) == paths
    assert apply_drop_guards(None, paths, ()) == paths


def test_unregistered_guard_name_is_ignored():
    """A typo'd/unknown guard name never blocks the drop -- it is skipped."""
    paths = ["a.ptu"]
    assert apply_drop_guards(None, paths, ["does_not_exist"]) == paths


def test_two_guards_compose_without_interfering():
    """Each guard only transforms the paths its own applies() accepted."""

    @register_drop_guard("test_uppercase_txt")
    class _UppercaseTxt(DropGuard):
        def applies(self, path):
            return path.endswith(".txt")

        def resolve(self, parent, paths):
            return [p.upper() for p in paths]

    @register_drop_guard("test_reverse_csv")
    class _ReverseCsv(DropGuard):
        def applies(self, path):
            return path.endswith(".csv")

        def resolve(self, parent, paths):
            return [p[::-1] for p in paths]

    try:
        paths = ["a.txt", "b.csv", "c.dat"]
        result = apply_drop_guards(None, paths, ["test_uppercase_txt", "test_reverse_csv"])
        assert result == ["A.TXT", "vsc.b", "c.dat"]
    finally:
        from chisurf.gui.widgets import dropguard

        dropguard._REGISTRY.pop("test_uppercase_txt", None)
        dropguard._REGISTRY.pop("test_reverse_csv", None)


def test_guard_may_drop_a_path_outright():
    """resolve() returning fewer paths than it was given removes the rest."""

    @register_drop_guard("test_refuse_bak")
    class _RefuseBak(DropGuard):
        def applies(self, path):
            return path.endswith(".bak")

        def resolve(self, parent, paths):
            return []

    try:
        result = apply_drop_guards(None, ["keep.txt", "drop.bak"], ["test_refuse_bak"])
        assert result == ["keep.txt"]
    finally:
        from chisurf.gui.widgets import dropguard

        dropguard._REGISTRY.pop("test_refuse_bak", None)


def test_guard_that_raises_is_skipped_not_fatal():
    """A guard that blows up in resolve() must not take the whole drop down with it."""

    @register_drop_guard("test_broken")
    class _Broken(DropGuard):
        def applies(self, path):
            return True

        def resolve(self, parent, paths):
            raise RuntimeError("boom")

    try:
        result = apply_drop_guards(None, ["a.ptu"], ["test_broken"])
        assert result == ["a.ptu"]
    finally:
        from chisurf.gui.widgets import dropguard

        dropguard._REGISTRY.pop("test_broken", None)


def test_builtin_tttr_to_pto_guard_is_registered():
    """The one guard ChiSurf ships lazily registers on first real use."""
    guard = get_drop_guard("tttr_to_pto")
    assert guard is not None
