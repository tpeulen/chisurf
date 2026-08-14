# Ninja Adventure (the reference game, ported)

The playable port of **Ninja Adventure** by pixel-boy (CC0): the author's own
village map — ``content/map/map_village.tscn`` from the Godot 4 checkout —
converted to shipped JSON by
``build_tools.dev_utils.import_ninja_map`` and run on the chigame engine's
ported systems (`chisurf.gui.chigame`: actors, weapons, behaviors, tile maps,
the room camera, weather, transitions).

What is the author's: the tile layout (3,477 cells over four layers), the
ninja's spawn at (64, 48), the pig trailing the green samurai who trails you,
the blue samurai's patrol with its 3-second waits, the 48 crates and grass
tufts, the paired teleporter between the village and the swamp, and the
environment areas (fog, snow, cloud) that drive the weather.

What the checkout does not ship — hostiles and a losing condition — is added
on the reference's own terms: enemy samurai beyond the teleporter that sense,
chase and swing, on the author's `enemy_team`.

Open it from **Tools → Miscellaneous → Games → Ninja Adventure**. Arrows walk,
Enter swings the club. The swamp is past the teleporter at the village's north
gate.
