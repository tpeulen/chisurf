"""Capture a populated EMTK ChiMOL view with the actual native host.

Loads a real structure (chimol's built-in demo PDB) so the screenshot shows a
working viewer session.

Usage: ``python -m chisurf.plugins.chimol.capture_native normal|narrow``
"""

import sys
from pathlib import Path

import numpy as np
from emtk.native import NativeHost
from PIL import Image

from chisurf.plugins.chimol.app import make_app

SIZES = {"normal": (900, 620), "narrow": (520, 620)}


def main():
    size_name = sys.argv[1] if len(sys.argv) > 1 else "normal"
    width, height = SIZES[size_name]
    out = Path(__file__).parent / "test" / "renders"
    out.mkdir(exist_ok=True)
    app = make_app()
    app.draw(
        __import__("emtk.testing", fromlist=["RecordingPainter"]).RecordingPainter(),
        0,
        0,
        width,
        height,
    )
    if app._chimol_error:
        raise SystemExit(f"chimol unavailable: {app._chimol_error}")
    demo = Path(__import__("chimol").__file__).parent / "data" / "demos" / "148l.pdb"
    app._chimol.load([str(demo)])
    host = NativeHost(app, size=(width, height), backend="offscreen")
    Image.fromarray(np.asarray(host.draw_frame())).save(out / f"native-{size_name}.png")
    host.close()
    print(f"wrote {out / f'native-{size_name}.png'}")


if __name__ == "__main__":
    main()
