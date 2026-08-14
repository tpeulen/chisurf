"""Render the ported systems as one composed room, for eyes-on verification.

Run::

    QT_QPA_PLATFORM=offscreen PYTHONPATH=. python \\
        -m test.gui.renders.chigame_port_demo [out.png]

Draws a 320x176 room on the engine's real paths: tile map, sheet actors with
weapons, destroyables, weather, hearts — the systems mined from the reference
game, in one picture.
"""

from __future__ import annotations

import pathlib
import sys

import numpy as np

from chisurf.gui import chigame
from chisurf.gui.chigame.actors import Actor, Damage, Destroyable, Team, Weapon, strike
from chisurf.gui.chigame.behavior import Patrol
from chisurf.gui.chigame.fx import Weather
from chisurf.gui.chigame.tilemap import TileMap

TILE = 16.0
COLS, ROWS = 20, 11

# Cell picks in the shipped sheets: (row, column) per terrain kind. Chosen by
# reading the magnified contact sheets; see okf/subsystems/chigame.md.
GROUND = [(0, 0), (1, 2), (2, 5), (3, 8)]
GRASS = [(6, 1), (7, 11), (13, 4)]
WATER = [(22, 4), (23, 7), (24, 8)]
STONE = [(14, 3), (15, 6), (16, 9)]
WALL_TOP = [(4, 0), (4, 6)]
WALL_FACE = [(6, 1), (7, 7)]

KINDS = {"ground": GROUND, "grass": GRASS, "water": WATER, "stone": STONE,
         "wall_top": WALL_TOP, "wall_face": WALL_FACE}


def _uv_table(pack):
    table = []
    for kind, cells in KINDS.items():
        for row, column in cells:
            table.append((kind, pack.cell_uv("floor" if kind not in ("wall_top", "wall_face") else "wall", row, column)))
    return table


def _grid():
    rng = np.random.default_rng(7)
    grid = np.zeros((ROWS, COLS), dtype=np.int32)
    ground = np.array([0, 1, 2, 3])
    grass = np.array([4, 5, 6])
    for row in range(ROWS):
        for col in range(COLS):
            grid[row, col] = ground[rng.integers(0, 4)]
    # grass patch, upper left
    for row in range(2, 5):
        for col in range(2, 7):
            if rng.random() < 0.8:
                grid[row, col] = grass[rng.integers(0, 3)]
    # stone plaza, lower right
    for row in range(7, 10):
        for col in range(13, 18):
            grid[row, col] = 7 + int(rng.integers(0, 3))
    # pond with shore ring
    for row in range(5, 8):
        for col in range(9, 13):
            edge = row in (5, 7) or col in (9, 12)
            grid[row, col] = 11 if edge else 10
    # top wall
    grid[0, :] = 13
    return grid, (13, 14)


class DemoRoom(chigame.Game):
    """One composed room on the ported systems."""

    title = "chigame port demo"
    background = (0.09, 0.10, 0.14, 1.0)

    def __init__(self) -> None:
        super().__init__()
        self.clock = 0.0
        self.tiles: TileMap | None = None
        self.hero: Actor | None = None
        self.foes: list[Actor] = []
        self.crates: list[Destroyable] = []
        self.weapon: Weapon | None = None
        self.weather = Weather()
        self.patrols: list[Patrol] = []
        self.swing_hit: set = set()

    def setup(self, host) -> None:
        pack = host.scene.pack
        pack.texture(host.ctx.device)
        camera = chigame.RoomCamera()
        camera.snap_to((320.0, 176.0))
        host.scene.camera = camera
        host.camera = camera

        table = _uv_table(pack)
        uv = np.zeros((len(table), 4), dtype=np.float32)
        for index, (_kind, rect) in enumerate(table):
            uv[index] = rect
        grid, wall = _grid()
        solids = set(range(10, 12)) | set(wall)
        # Cell ids: 0-3 ground, 4-6 grass, 7-9 stone, 10-11 water, 13-14 walls.
        # The room is offset onto the cell whose centre is (320, 176); room
        # centres that sit exactly between cells round the wrong way.
        self.tiles = TileMap(grid, uv, tile=TILE, offset=(160.0, 88.0),
                             solid_ids=solids)

        solid = self.tiles.solid_at
        self.hero = Actor((250.0, 200.0), alias="hero", speed=90.0, solid=solid,
                          team=Team("villagers"), maximum_life=8.0)
        self.weapon = Weapon("club", Damage(2.0, 140.0), team=self.hero.team)
        foe_team = Team("beasts")
        self.foes = [
            Actor((220.0, 150.0), alias="guardian", speed=40.0, solid=solid,
                  team=foe_team, maximum_life=6.0),
            Actor((410.0, 160.0), alias="warden", speed=36.0, solid=solid,
                  team=foe_team, maximum_life=6.0),
        ]
        self.patrols = [
            Patrol(self.foes[0], [(220.0, 150.0), (310.0, 128.0), (370.0, 160.0)], loop=True),
            Patrol(self.foes[1], [(410.0, 160.0), (360.0, 210.0)], loop=True),
        ]
        self.crates = [Destroyable((260.0, 218.0)), Destroyable((278.0, 218.0))]
        self.weather.set(["rain"])

    def update(self, dt: float, keys) -> None:
        self.clock += dt
        move = np.zeros(2)
        if keys.is_held(chigame.Action.RIGHT):
            move[0] += 1.0
        if keys.is_held(chigame.Action.LEFT):
            move[0] -= 1.0
        if keys.is_held(chigame.Action.DOWN):
            move[1] += 1.0
        if keys.is_held(chigame.Action.UP):
            move[1] -= 1.0
        if keys.just_pressed(chigame.Action.CONFIRM):
            if self.weapon.swing():
                self.hero.attack()
                self.swing_hit = set()
        if np.any(move):
            self.hero.move_vector[:] = move / np.hypot(*move)
        else:
            self.hero.move_vector[:] = 0.0
        self.hero.update(dt)
        self.weapon.update(dt, self.hero)
        strike(self.weapon, self.foes + self.crates, once=self.swing_hit)
        for patrol in self.patrols:
            patrol.update(dt)
        for foe in self.foes:
            foe.update(dt)
        for crate in self.crates:
            crate.update(dt)
        self.weather.update(dt)

    def draw(self, scene) -> None:
        camera = scene.camera
        width, height = scene.batch._ctx.size
        aspect = width / max(height, 1)
        self.tiles.draw_visible(scene, camera, aspect)
        scene.batch  # tiles first, then figures in painter order
        everyone = [self.hero, *self.foes, *self.crates]
        for actor in sorted(everyone, key=lambda a: a.draw_order):
            if actor is self.hero:
                self.weapon.draw(scene, actor)
            actor.draw(scene)
        self.weather.draw(scene, camera)
        # Hearts: eight life in units of two a heart.
        hearts = self.hero.health.maximum / 2.0
        filled = self.hero.health.current / 2.0
        for index in range(int(hearts)):
            step = 4 if filled >= index + 1 else (3 if filled > index else 0)
            scene.draw("tile", "hearts", at=(174.0 + index * 17.0, 100.0),
                       size=(16.0, 16.0), state=f"0,{step}")


def main(argv: list[str]) -> int:
    """Render the room to a PNG.

    Parameters
    ----------
    argv : list of str
        Optional output path.

    Returns
    -------
    int
        Exit status.
    """
    out = pathlib.Path(argv[0]) if argv else pathlib.Path("chigame_port_demo.png")
    game = DemoRoom()
    image = chigame.capture(game, size=(640, 352), frames=90, pack=chigame.SheetPack())
    chigame.save_png(image, out)
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
