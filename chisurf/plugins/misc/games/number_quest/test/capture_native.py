"""Capture populated normal and narrow EMTK views with the actual GPU host."""
from pathlib import Path

import numpy as np
from emtk.native import NativeHost
from PIL import Image

from ..app import make_app


def main():
    out = Path(__file__).parent / 'renders'
    out.mkdir(exist_ok=True)
    for width, height, name in ((560, 420, 'normal'), (360, 420, 'narrow')):
        app = make_app()
        app.clock = lambda: 0
        app.game.reset(target=37)
        for value in (50, 25):
            app.estimate = value
            app.submit()
        app.estimate = 37
        host = NativeHost(app, size=(width, height), backend='offscreen')
        Image.fromarray(np.asarray(host.draw_frame())).save(out / f'native-{name}.png')
        host.close()


if __name__ == '__main__':
    main()
