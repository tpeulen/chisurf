"""Capture the populated native Pong viewport using the real GPU host."""
from pathlib import Path

import numpy as np
from emtk.native import NativeHost
from PIL import Image

from ..app import make_app


def main():
    out = Path(__file__).parent / "renders"
    out.mkdir(exist_ok=True)
    for width, height, name in ((820, 640, "normal"), (480, 640, "narrow")):
        for mode in ("serve", "rally", "paused", "winner"):
            app = make_app()
            app.clock = lambda: 0
            if mode != "serve":
                app.game.serve_timer = 0
                app.game.player_score, app.game.cpu_score = 3, 2
                app.game.rally = 6
                app.game.paddle_y, app.game.cpu_y = 245, 380
                app.game.ball_x, app.game.ball_y = 545, 245
                app.game.spawn_particles(545, 245, (1, .5, 0), 8)
                for particle in app.game.particles:
                    particle.update(.1)
            if mode == "paused":
                app.game.paused = True
            if mode == "winner":
                app.game.player_score = 7
                app.game.winner = "Donor"
            host = NativeHost(app, size=(width, height), backend="offscreen")
            pixels = host.draw_frame()
            Image.fromarray(np.asarray(pixels)).save(out / f"native-{name}-{mode}.png")
            host.close()


if __name__ == "__main__":
    main()
