"""Regenerate the synthetic legacy burstwise sample the plugin tests read.

The writer is the shipped :mod:`chisurf.plugins.burst.burstwise_import.sample`
(the plugin's Load example writes the same bytes into the settings cache); this
script only places its output beside the tests. Run
``python chisurf/plugins/burst/burstwise_import/tests/data/make_burstwise_sample.py``
from the repository root; the output is byte-identical across runs.
"""

from __future__ import annotations

import pathlib

from chisurf.plugins.burst.burstwise_import.sample import write_sample

HERE = pathlib.Path(__file__).resolve().parent


def main() -> None:
    """Write the sample under ``burstwise/burstwise_All 0.1066#60``."""
    write_sample(HERE / "burstwise")


if __name__ == "__main__":
    main()
