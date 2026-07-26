"""Regression tests for the lazy ``chisurf.action_*`` attributes (RF-174).

Resolving ``chisurf.action_dispatcher`` imports ``chisurf.core.actions``, whose
``@action`` decorators read ``chisurf.action_registry`` and therefore re-enter the
module ``__getattr__``. If the outer frame builds a *second* dispatcher, the 60
registered actions end up in a registry nobody dispatches through. The invariant
``chisurf.action_registry is chisurf.action_dispatcher.registry`` has to hold no
matter which of the two attributes is touched first, so each case runs in its own
fresh interpreter.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

_CHECK = """
import chisurf as cs

{first_access}

dispatcher = cs.action_dispatcher
registry = cs.action_registry

assert registry is dispatcher.registry, "action_registry is not the dispatcher's registry"
assert registry.has("fit.add.start"), "actions did not register into the live registry"
assert len(dispatcher.registry.list_actions()) == len(registry.list_actions())
print(len(registry.list_actions()))
"""


def _run_check(first_access: str) -> int:
    """Run the invariant check in a fresh interpreter and return the action count.

    Parameters
    ----------
    first_access : str
        Statement executed before the invariant is checked — it decides which
        lazy attribute is resolved first.

    Returns
    -------
    int
        Number of actions in the live registry.
    """
    result = subprocess.run(
        [sys.executable, "-c", _CHECK.format(first_access=first_access)],
        cwd=ROOT,
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    return int(result.stdout.strip().splitlines()[-1])


def test_dispatcher_accessed_first_keeps_the_registered_actions():
    """Touching the dispatcher first must not orphan the registered actions."""
    assert _run_check("cs.action_dispatcher") > 0


def test_registry_accessed_first_keeps_the_registered_actions():
    """The mirror order — registry first — must bind to the same dispatcher."""
    assert _run_check("cs.action_registry") > 0


def test_actions_package_imported_first_keeps_the_registered_actions():
    """Importing the package directly is the order the main window happens to use."""
    assert _run_check("import chisurf.core.actions") > 0


def test_action_counts_agree_across_import_orders():
    """No import order may register more (or fewer) actions than another."""
    counts = {
        _run_check("cs.action_dispatcher"),
        _run_check("cs.action_registry"),
        _run_check("import chisurf.core.actions"),
    }
    assert len(counts) == 1, f"import order changes the action count: {counts}"
