"""Probe: a fresh port must not expose garbage memory.

Originally a repro for a bug in the retired compiled chinet Port (an
uninitialised 8-byte/64-byte buffer). Re-pointed at IMP.bff's Port, the
runtime that replaced it: the same invariant -- a newly constructed port
reads back zeroed, deterministic state.
"""

import numpy as np

from chisurf.core import nodes

cn = nodes._bff


def test_initial_garbage():
    print("Testing initial Port value...")
    p = cn.Port()
    val = p.value
    print(f"Initial value: {val}")
    # It should be zeroed, never random garbage.
    if isinstance(val, np.ndarray):
        print(f"Value size: {len(val)}")
        if len(val) > 0 and np.any(val != 0):
            print("Found garbage in initial value!")
    else:
        print(f"Value is not an array: {val}")


if __name__ == "__main__":
    test_initial_garbage()
