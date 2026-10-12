"""``cs.macros`` resolves in a fresh interpreter, without the GUI importing it first."""

import subprocess
import sys


def test_macros_is_reachable_from_a_bare_import():
    code = (
        "import chisurf as cs; "
        "assert callable(cs.macros.core_fit.add_fit), cs.macros; "
        "assert cs.macros.core_fit is __import__('chisurf.macros.core_fit', fromlist=['x'])"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=300)
    assert result.returncode == 0, result.stderr[-2000:]
