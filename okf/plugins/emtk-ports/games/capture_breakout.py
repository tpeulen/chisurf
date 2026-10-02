"""Breakout inside the hub, populated (round in play), at both sizes."""
import pathlib, sys
from emtk.testing import RecordingPainter
from test.gui.emtk_port_parity import emtk_screenshot
from chisurf.plugins.misc.games.gui.app import make_app
out = pathlib.Path(sys.argv[1])
for size in [(1200, 800), (800, 600)]:
    a = make_app(); a.select("Breakout"); g = a.child.game
    a.child.clock = lambda: 0
    g.score, g.level, g.lives, g.stuck = 170, 2, 2, False
    g.paddle_x, g.ball_x, g.ball_y, g.ball_vx, g.ball_vy = 525, 535, 350, 180, -280
    for i in (45, 55, 65, 75): g.bricks[i].hp = 0
    g.spawn_particles(437, 216, g.bricks[65].nm, 12)
    for _ in range(3): a.draw(RecordingPainter(), 0, 0, *size)
    emtk_screenshot(a, out / f"breakout_hub_playing_{size[0]}x{size[1]}.png", size)
    a.close()
