"""``chisurf.core.fitting.sample`` imports on its own.

Its sampler decorators use ``chisurf.core.fitting.factorgraph`` at import time;
without importing it explicitly the module only loaded when something else had
imported ``factorgraph`` first, so ``import chisurf.core.fitting.sample`` as the
first statement of a script raised ``AttributeError``.
"""

import subprocess
import sys


def test_sample_module_imports_in_a_fresh_interpreter():
    result = subprocess.run(
        [sys.executable, "-c", "import chisurf.core.fitting.sample"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr[-2000:]
