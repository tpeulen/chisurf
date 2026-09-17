"""Where the ADPCM decode is worth dispatching to the GPU, and where it is not.

The codec is sequential by construction -- every sample needs the predictor the
one before left -- which looks like the worst possible fit for a GPU. It is not,
because the stream is cut into *independent* blocks: the sequential part is the
few hundred steps inside one block, and thousands of blocks run at once.

Both routes are real and both are kept, so this table decides one number:
``adpcm.MIN_BLOCKS_FOR_GPU``, the size below which the dispatch is not worth
paying for. A short sound effect decodes in numpy in well under the fixed cost
of submitting anything at all.

The routes are asserted **bit-identical**, not merely close. A lossy codec that
decoded differently depending on which route ran would change the audio behind
the caller's back, and that is a far worse failure than being slow.

Run it::

    pixi run python test/benchmarks/benchmark_adpcm.py
"""

from __future__ import annotations

import argparse
import sys
import time

import numpy as np

sys.path.insert(0, __file__.rsplit("/test/", 1)[0])

from chisurf.gui.chigame import adpcm  # noqa: E402

#: Clip lengths to sweep, in seconds at 22.05 kHz -- from a footstep to a music
#: loop.
DURATIONS = (0.05, 0.2, 1.0, 5.0, 20.0, 80.0)

#: What the clips are stored at.
RATE = 22050


def make_clip(seconds: float) -> bytes:
    """A clip with realistic content of a given length.

    Parameters
    ----------
    seconds : float
        Duration.

    Returns
    -------
    bytes
        An encoded clip.
    """
    time_axis = np.arange(int(RATE * seconds)) / RATE
    signal = (
        np.sin(2 * np.pi * 220 * time_axis) * 0.5
        + np.sin(2 * np.pi * 660 * time_axis) * 0.25
        + np.sin(2 * np.pi * 1830 * time_axis) * 0.12
    )
    return adpcm.encode((signal * 32767).astype(np.int16), RATE)


def main(argv: list[str]) -> int:
    """Print the table.

    Parameters
    ----------
    argv : list of str
        Command line.

    Returns
    -------
    int
        Process status.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeats", type=int, default=5)
    options = parser.parse_args(argv)

    if adpcm.device() is None:
        print("no GPU adapter: only the numpy route is available here")
        return 1
    print(f"threshold in force: MIN_BLOCKS_FOR_GPU = {adpcm.MIN_BLOCKS_FOR_GPU}")
    print()
    print("| seconds | samples | blocks | numpy [ms] | wgsl [ms] | speedup | identical |")
    print("| ---: | ---: | ---: | ---: | ---: | ---: | :---: |")

    for seconds in DURATIONS:
        raw = make_clip(seconds)
        _, count, _, _, blocks = adpcm._header(raw)

        on_cpu, _ = adpcm.decode_cpu(raw)
        on_gpu = adpcm.decode_gpu(raw)
        if on_gpu is None:
            print(f"| {seconds} | {count} | {blocks} | - | (no device) | - | - |")
            continue
        identical = bool(np.array_equal(on_cpu, on_gpu[0]))

        start = time.perf_counter()
        for _ in range(options.repeats):
            adpcm.decode_cpu(raw)
        cpu_ms = (time.perf_counter() - start) / options.repeats * 1e3

        start = time.perf_counter()
        for _ in range(options.repeats):
            adpcm.decode_gpu(raw)
        gpu_ms = (time.perf_counter() - start) / options.repeats * 1e3

        print(
            f"| {seconds} | {count:,} | {blocks:,} | {cpu_ms:.2f} | {gpu_ms:.2f} "
            f"| {cpu_ms / max(gpu_ms, 1e-9):.1f}x | {'yes' if identical else 'NO'} |"
        )
        if not identical:
            return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
