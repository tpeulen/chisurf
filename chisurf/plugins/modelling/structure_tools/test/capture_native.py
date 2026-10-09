"""Capture a populated EMTK view of the structure-tools hub.

The hub is captured with the HydroPro child open. One size per process:
immediate-mode window/table layout state persists per process.

Usage: ``python -m chisurf.plugins.modelling.structure_tools.test.capture_native normal|narrow``
"""

import sys
from pathlib import Path

import numpy as np
from emtk.native import NativeHost
from PIL import Image

from ..app import make_app

SIZES = {"normal": (900, 660), "narrow": (520, 660)}


def main():
    size_name = sys.argv[1] if len(sys.argv) > 1 else "normal"
    width, height = SIZES[size_name]
    out = Path(__file__).parent / "renders"
    out.mkdir(exist_ok=True)
    app = make_app()
    app.select("HydroPro")
    host = NativeHost(app, size=(width, height), backend="offscreen")
    Image.fromarray(np.asarray(host.draw_frame())).save(out / f"native-{size_name}.png")
    host.close()
    print(f"wrote {out / f'native-{size_name}.png'}")


if __name__ == "__main__":
    main()
