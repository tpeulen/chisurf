#!/usr/bin/env python3
"""What one frame of ChiMOL chrome costs to build, and which half costs it.

Why this shape
--------------
The chrome is immediate mode, and there are two questions about it that get
confused with each other:

* what a frame costs when the panel **changes** -- every hover, every
  keystroke, every menu move, which is precisely while somebody is using the
  interface;
* what it costs when the panel **has not changed** and only the camera is
  moving, which is the only time anybody watches the frame rate.

They have completely different answers -- roughly ten to one -- and quoting the
first as "the cost of the chrome" makes the panel look ruinous, while quoting
the second makes it look free. So both are measured, separately, and the
rebuild is split into the two things it is made of: emitting the quads in
Python, and converting them to the float32 the GPU is handed.

The second table is the diagnostic. It runs the same panel at four viewport
sizes. The old chrome rasterised itself into a viewport-sized image, so its
cost tracked *pixels*; this one tracks *content*, and content does not change
when the window does. A row that grows with the viewport means something has
started scaling with area again.

What is deliberately **not** here: the GPU side. A repeated frame no longer
allocates a vertex buffer, two uniform buffers or two bind groups -- see
``wgpu_backend._draw_ui`` and the test that counts them -- but the saving is
driver work below the binding, which a Python clock cannot see. Counting the
allocations is the honest measurement, and it is a test rather than a table.

Runs headless: no GL context, no device, no window.

Run
---
    QT_QPA_PLATFORM=offscreen PYTHONPATH=. \\
        python test/benchmarks/benchmark_chimol_chrome.py
"""
from __future__ import annotations

import os
import statistics
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

#: Viewport sizes, in logical pixels. The first is the size the chrome
#: baseline images were captured at, so the quad counts here can be read
#: against them.
SIZES = ((1280, 860), (1920, 1080), (2560, 1720), (3840, 2160))

#: Repeats per measurement. The median is reported: the first build of a frame
#: pays for list growth that a steady state does not.
REPEATS = 200

#: A panel with enough in it to be worth measuring -- forty objects and three
#: sequences is a real integrative model, not a demo.
OBJECTS = 40
RESIDUES = 600


def build_gui():
    """Return an ``InternalGui`` carrying a realistic panel."""
    from chimol.chrome.gui import GuiRow, InternalGui, SequenceRow

    gui = InternalGui()
    gui.visible = True
    gui.command_line.visible = True
    gui.set_rows(
        [GuiRow(name="all", is_header=True)]
        + [
            GuiRow(name=f"object_{index:03d}", enabled=index % 3 != 0)
            for index in range(OBJECTS)
        ]
    )
    gui.set_sequences(
        [
            SequenceRow(name=f"chain {chain}", codes="ACDEFGHIKLMNPQRSTVWY" * (RESIDUES // 20))
            for chain in "ABC"
        ]
    )
    gui.command_line.set_text("color skyblue, chain A")
    for index in range(6):
        gui.command_line.append(f"loaded object_{index}: 1363 atoms", "message")
    return gui


def median_ms(call, repeats: int = REPEATS) -> float:
    """Median wall-clock time of *call*, in milliseconds."""
    call()
    samples = []
    for _ in range(repeats):
        start = time.perf_counter()
        call()
        samples.append((time.perf_counter() - start) * 1000.0)
    return statistics.median(samples)


def measure(width: int, height: int) -> dict:
    """Time one viewport size."""
    from chimol.cmtk.quad_painter import (
        FLOATS_PER_QUAD,
        QuadPainter,
    )

    gui = build_gui()
    painter = QuadPainter()
    gui.layout(width, height)
    painter.clear()
    gui.paint(painter)
    vertices = painter.vertices()

    def paint():
        painter.clear()
        gui.paint(painter)

    def rebuild():
        gui.layout(width, height)
        painter.clear()
        gui.paint(painter)
        return painter.vertices()

    def steady():
        gui.layout(width, height)
        return gui.chrome_fingerprint()

    return {
        "size": f"{width}x{height}",
        "quads": len(vertices) // 6,
        "floats": len(painter._data),
        "bytes": vertices.nbytes,
        "layout": median_ms(lambda: gui.layout(width, height)),
        "paint": median_ms(paint),
        "convert": median_ms(painter.vertices),
        "rebuild": median_ms(rebuild),
        "steady": median_ms(steady),
        "floats_per_quad": FLOATS_PER_QUAD,
    }


def main() -> int:
    """Print both tables as markdown, ready to paste into the benchmarks page."""
    rows = [measure(width, height) for width, height in SIZES]

    print("\n### One frame of chrome\n")
    print("| Viewport | Quads | Emit | Convert | Layout | **Rebuild** | Unchanged |")
    print("| --- | --- | --- | --- | --- | --- | --- |")
    for row in rows:
        print(
            f"| {row['size']} | {row['quads']} | {row['paint']:.2f} ms | "
            f"{row['convert']:.2f} ms | {row['layout']:.2f} ms | "
            f"**{row['rebuild']:.2f} ms** | {row['steady']:.2f} ms |"
        )

    first = rows[0]
    print(
        f"\nFloats emitted per quad: {first['floats_per_quad']}. "
        f"Vertex buffer at {first['size']}: {first['bytes'] / 1024:.0f} KB "
        f"({first['quads']} quads)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
