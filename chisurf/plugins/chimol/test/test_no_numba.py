"""chimol must reach the browser, and numba does not exist there.

Pyodide has no numba, so every ``njit`` in ``chimol/`` is a wall between the
renderer and the WebGPU port that shares its WGSL with the desktop. The cheap
way round is measured and dead: a no-op ``njit`` shim — exactly what
``NUMBA_DISABLE_JIT=1`` gives you — runs **300–680× slower** on these kernels,
and mypyc cannot rescue it either (**1.04×** on numpy code, because it unboxes
Python natives and cannot see through a numpy buffer). So the kernels are being
rerouted one at a time: to scipy's compiled equivalents where one exists, to
vectorised NumPy where the loop was avoidable, and to plain Python where the
recurrence is sequential and the arrays are small.

:data:`ALLOWED` is the list of files that have **not** been rerouted yet. It
shrinks and never grows. A file you touch is a file you port.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

CHIMOL = pathlib.Path(__file__).resolve().parents[1] / "chimol"

#: Not yet ported. Both are the CPU ray tracer: `closest_hit` is a per-ray
#: descent of a BVH with its own traversal stack, and `_jit_trace` is a
#: per-pixel loop around it. Neither is a kernel that vectorises by rewriting an
#: expression -- they need the tracer restructured into ray batches, or moved to
#: a WGSL compute pass with a CPU route beside it.
ALLOWED = {
    "renderer/bvh.py",
    "renderer/raytracer.py",
}


def _imports_numba(path: pathlib.Path) -> bool:
    """Whether a module imports numba under any spelling.

    Parameters
    ----------
    path : pathlib.Path
        File to inspect.

    Returns
    -------
    bool
        True when an ``import`` statement names ``numba`` or a submodule.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(a.name.split(".")[0] == "numba" for a in node.names):
                return True
        elif isinstance(node, ast.ImportFrom):
            if (node.module or "").split(".")[0] == "numba":
                return True
    return False


def _modules() -> list[pathlib.Path]:
    """Every shipped chimol module, sorted."""
    return sorted(p for p in CHIMOL.rglob("*.py") if "test" not in p.parts)


@pytest.mark.parametrize(
    "module", _modules(), ids=lambda p: str(p.relative_to(CHIMOL))
)
def test_no_new_numba_importer(module: pathlib.Path):
    relative = str(module.relative_to(CHIMOL))
    if relative in ALLOWED:
        pytest.skip(f"{relative} is on the shrinking not-yet-ported list")
    assert not _imports_numba(module), (
        f"{relative} imports numba, which does not exist in Pyodide. Route the "
        f"kernel through scipy, vectorised NumPy or plain Python instead of "
        f"adding it to ALLOWED."
    )


def test_the_allow_list_holds_only_files_that_still_need_it():
    """A file that no longer imports numba must be struck from the list.

    Without this the list would record work as outstanding after it was done,
    and the next session would go looking for a kernel that is not there.
    """
    stale = [
        name for name in sorted(ALLOWED)
        if not (CHIMOL / name).exists() or not _imports_numba(CHIMOL / name)
    ]
    assert not stale, f"strike these from ALLOWED: {stale}"
