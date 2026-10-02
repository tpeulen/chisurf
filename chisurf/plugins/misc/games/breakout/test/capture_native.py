"""Capture genuine native GPU frames at normal and narrow dimensions."""
from pathlib import Path
import random

import numpy as np
from emtk.native import NativeHost
from PIL import Image

from ..app import make_app


def populate(app, mode):
    random.seed(48)
    app.clock = lambda: 0
    if mode != "serve":
        g = app.game
        g.score, g.level, g.lives = 170, 2, 2
        g.stuck = False
        g.paddle_x = 525
        g.ball_x, g.ball_y, g.ball_vx, g.ball_vy = 535, 350, 180, -280
        for index in (45, 55, 65, 75):
            g.bricks[index].hp = 0
        g.bricks[0].hp = 1
        g.spawn_particles(437, 216, g.bricks[65].nm, 12)
        for p in g.particles:
            p.update(.1)
        if mode == "paused":
            g.paused = True
        if mode == "gameover":
            g.lives = 0
            g.message = "Sample bleached"


def main():
    out = Path(__file__).parent / "renders"
    out.mkdir(exist_ok=True)
    for width, height, name in ((820,690,"normal"),(480,690,"narrow")):
        for mode in ("serve","rally","paused","gameover"):
            app = make_app()
            populate(app,mode)
            host = NativeHost(app,size=(width,height),backend="offscreen")
            Image.fromarray(np.asarray(host.draw_frame())).save(out/f"native-{name}-{mode}.png")
            host.close()


if __name__ == "__main__":
    main()
