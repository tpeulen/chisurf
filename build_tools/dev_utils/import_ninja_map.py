"""Convert the reference game's village map into data the chigame port loads.

The reference (``junk/NinjaAdventure``) is a Godot 4 project; its one shipped
map, ``content/map/map_village.tscn``, is a scene file: two tile layers
(``PackedInt32Array`` triplets of packed cell / source / atlas), the actors
placed in it with their behaviors, a paired teleporter, and environment areas
driving weather and music. Godot is not a dependency of this package, and
``junk/`` is gitignored anyway, so the scene is converted **here** to plain
JSON that ships beside the game (``ninja_adventure/data/``).

Run from the repository root::

    PYTHONPATH=. python -m build_tools.dev_utils.import_ninja_map

Writes ``chisurf/plugins/misc/games/ninja_adventure/data/map_village.json``.
Re-run whenever the reference checkout moves; the JSON is committed so builds
never depend on ``junk/``.
"""

from __future__ import annotations

import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
SCENE = ROOT / "junk/NinjaAdventure/content/map/map_village.tscn"
TILESET = ROOT / "junk/NinjaAdventure/content/map/tileset.tres"
OUT = (
    ROOT
    / "chisurf/plugins/misc/games/ninja_adventure/data/map_village.json"
)

#: TileSet source id -> the chigame pixel pack's grid name for that sheet.
SOURCE_GRIDS = {
    0: "village",
    1: "floor",
    2: "interior",
    3: "animated",
    4: "wall",
}

#: Scene-collection source: atlas value -> destroyable kind.
SCENE_TILES = {1: "crate", 2: "grass", 3: "pot"}


def _signed16(value: int) -> int:
    """Read a 16-bit field as signed.

    Parameters
    ----------
    value : int
        The field.

    Returns
    -------
    int
    """
    return ((value & 0xFFFF) ^ 0x8000) - 0x8000


def _tileset_atlas() -> tuple[dict[int, set[tuple[int, int]]], dict[int, set[tuple[int, int]]]]:
    """Which atlas cells each source defines, and which of those are solid.

    Returns
    -------
    tuple of (dict, dict)
        ``(defined, solids)`` — source id -> set of ``(atlas_x, atlas_y)``.
    """
    text = TILESET.read_text(encoding="utf-8")
    blocks = re.split(r"\[sub_resource ", text)
    id_to_source: dict[str, int] = {}
    for match in re.finditer(r'sources/(\d+) = SubResource\("([^"]+)"\)', text):
        id_to_source[match.group(2)] = int(match.group(1))
    defined: dict[int, set[tuple[int, int]]] = {}
    solids: dict[int, set[tuple[int, int]]] = {}
    for block in blocks:
        header = re.match(r'type="[^"]+" id="([^"]+)"', block)
        if header is None:
            continue
        source = id_to_source.get(header.group(1))
        if source is None:
            continue
        cells = defined.setdefault(source, set())
        solid_cells = solids.setdefault(source, set())
        for match in re.finditer(r"^(\d+):(\d+)/0 = 0", block, re.M):
            cells.add((int(match.group(1)), int(match.group(2))))
        for match in re.finditer(
            r"(\d+):(\d+)/0/physics_layer_0/polygon_0/points", block
        ):
            solid_cells.add((int(match.group(1)), int(match.group(2))))
    return defined, solids


def _ext_resources(text: str) -> dict[str, dict]:
    """The scene's external resources, by id.

    Parameters
    ----------
    text : str
        Scene source.

    Returns
    -------
    dict of str, dict
        ``id -> {"path": ..., "type": ...}``.
    """
    table = {}
    for match in re.finditer(
        r'\[ext_resource type="([^"]+)"[^]]*?path="([^"]+)"[^\]]*?id="([^"]+)"',
        text,
    ):
        table[match.group(3)] = {"type": match.group(1), "path": match.group(2)}
    return table


def _sub_resources(text: str) -> dict[str, dict]:
    """The scene's sub-resources with their properties.

    Parameters
    ----------
    text : str
        Scene source.

    Returns
    -------
    dict of str, dict
        ``id -> {"type": ..., **properties}``.
    """
    out: dict[str, dict] = {}
    parts = re.split(r"\[sub_resource ", text)
    for part in parts[1:]:
        header = re.match(r'type="([^"]+)" id="([^"]+)"\]\n(.*)', part, re.S)
        if header is None:
            continue
        body = header.group(3).split("[node")[0]
        props: dict = {"type": header.group(1)}
        for line in body.splitlines():
            match = re.match(r"(\w+) = (.+)", line.strip())
            if match is not None:
                props[match.group(1)] = match.group(2)
        # Some values (a Curve2D's ``_data`` dict) span lines; keep the raw
        # body so callers can search it whole.
        props["_body"] = body
        out[header.group(2)] = props
    return out


def _vector2(value: str) -> tuple[float, float]:
    """Parse ``Vector2(x, y)``.

    Parameters
    ----------
    value : str

    Returns
    -------
    tuple of float
    """
    match = re.match(r"Vector2\(([-\d.e]+), ([-\d.e]+)\)", value)
    return float(match.group(1)), float(match.group(2))


def _int_array(value: str) -> list[int]:
    """Parse ``PackedInt32Array(...)``.

    Parameters
    ----------
    value : str

    Returns
    -------
    list of int
    """
    return [int(item) for item in re.findall(r"-?\d+", value)]


def convert() -> dict:
    """Convert the village scene to the game's JSON map format.

    Returns
    -------
    dict
        The map: offset, layers of cells, solids, destroyables, actors,
        teleporters and environment areas.
    """
    text = SCENE.read_text(encoding="utf-8")
    ext = _ext_resources(text)
    subs = _sub_resources(text)
    atlas_cells, solids = _tileset_atlas()

    # -- tile layers ------------------------------------------------------
    tilemap = re.search(
        r'\[node name="Tilemap"[^\]]*\]\nposition = Vector2\(([-\d.]+), ([-\d.]+)\)',
        text,
    )
    offset = (
        float(tilemap.group(1)) if tilemap else 0.0,
        float(tilemap.group(2)) if tilemap else 0.0,
    )
    layers = []
    for match in re.finditer(
        r"layer_(\d+)/tile_data = PackedInt32Array\(([^)]*)\)", text
    ):
        values = _int_array(match.group(2))
        cells = []
        for index in range(0, len(values), 3):
            packed, mid, third = values[index : index + 3]
            source = mid & 0xFFFF
            atlas_y = (mid >> 16) & 0xFFFF
            atlas_x = third & 0xFFFF
            alternative = (third >> 16) & 0xFFFF
            if source == 5:
                # Scene-collection source: the alternative slot carries the
                # scene id (crate/grass/pot) and there is no atlas cell.
                cells.append(
                    {
                        "x": _signed16(packed),
                        "y": _signed16(packed >> 16),
                        "source": source,
                        "ax": alternative,
                        "ay": 0,
                    }
                )
                continue
            # A cell the atlas source does not define is a dead reference:
            # Godot draws nothing there, and neither do we.
            if (atlas_x, atlas_y) not in atlas_cells.get(source, set()):
                continue
            cells.append(
                {
                    "x": _signed16(packed),
                    "y": _signed16(packed >> 16),
                    "source": source,
                    "ax": atlas_x,
                    "ay": atlas_y,
                }
            )
        layers.append({"index": int(match.group(1)), "cells": cells})

    # -- nodes: actors, behaviors, teleporters, environment ---------------
    node_blocks = re.split(r"(?=\[node )", text)
    actors: list[dict] = []
    teleporters: list[dict] = []
    environments: list[dict] = []
    by_name: dict[str, dict] = {}
    for block in node_blocks:
        header = re.match(
            r'\[node name="([^"]+)"(?: type="[^"]+")?(?: parent="([^"]+)")?', block
        )
        if header is None:
            continue
        node = {
            "name": header.group(1),
            "parent": header.group(2),
            "block": block,
        }
        by_name[header.group(1)] = node

        position = re.search(r"\nposition = (Vector2\([^)]+\))", block)
        if position is not None:
            node["position"] = _vector2(position.group(1))

        if "instance=ExtResource" in block:
            kind = ext.get(re.search(r'instance=ExtResource\("([^"]+)"\)', block).group(1), {})
            node["scene"] = kind.get("path", "")
        if "script = ExtResource" in block:
            node["script"] = ext.get(
                re.search(r'script = ExtResource\("([^"]+)"\)', block).group(1), {}
            ).get("path", "")

    # Behaviors attach to their parent character node.
    for node in by_name.values():
        block = node["block"]
        if node.get("script", "").endswith("behavior_follow.gd"):
            target = re.search(r'target = NodePath\("\.\./\.\./([^"]+)"\)', block)
            if node["parent"] and target:
                actors.append(
                    {
                        "node": node["parent"],
                        "behavior": {
                            "type": "follow",
                            "target": target.group(1),
                            **_props(block, ("min_dist", "max_dist")),
                        },
                    }
                )
        if node.get("script", "").endswith("behavior_follow_path.gd"):
            if node["parent"]:
                actors.append(
                    {
                        "node": node["parent"],
                        "behavior": {
                            "type": "patrol",
                            **_props(block, ("wait_time", "loop", "wait_mode")),
                        },
                    }
                )
        if node.get("script", "").endswith("teleporter.gd"):
            target = re.search(r'target = NodePath\("\.\./([^"]+)"\)', block)
            direction = re.search(r"\ndirection = (Vector2\([^)]+\))", block)
            teleporters.append(
                {
                    "name": node["name"],
                    "position": node.get("position", (0.0, 0.0)),
                    "target": target.group(1) if target else None,
                    "direction": _vector2(direction.group(1)) if direction else (0.0, 1.0),
                }
            )
        if node.get("script", "").endswith("environment_shape.gd"):
            resource = re.search(
                r'resource_environment = (?:Ext|Sub)Resource\("([^"]+)"\)', block
            )
            shape = re.search(r"shape = SubResource\(\"([^\"]+)\"\)", block)
            env_resource = subs.get(resource.group(1), {}) if resource else {}
            kinds = [
                int(value)
                for value in re.findall(r"\d+", env_resource.get("meteo_list", ""))
            ]
            music = env_resource.get("music", "")
            music_name = ""
            if isinstance(music, str) and 'ExtResource("' in music:
                music_id = re.search(r'ExtResource\("([^"]+)"\)', music).group(1)
                music_path = ext.get(music_id, {}).get("path", "")
                music_name = pathlib.Path(music_path).stem
            size = (0.0, 0.0)
            if shape is not None and shape.group(1) in subs:
                size = _vector2(subs[shape.group(1)].get("size", "Vector2(0, 0)"))
            environments.append(
                {
                    "position": node.get("position", (0.0, 0.0)),
                    "size": size,
                    "meteo": kinds,
                    "music": music_name,
                }
            )

    # Character nodes themselves (instances of a character scene). They are
    # children of the Tilemap node, so the tilemap's own offset places them.
    characters = []
    for node in by_name.values():
        scene = node.get("scene", "")
        if "/content/character/" not in scene:
            continue
        base = node.get("position", (0.0, 0.0))
        characters.append(
            {
                "name": node["name"],
                "sheet": pathlib.Path(scene).parent.name,
                "position": (base[0] + offset[0], base[1] + offset[1]),
                "speed": _scalar(node["block"], "speed"),
            }
        )

    # Patrol paths. A Curve2D point is six numbers — in-handle, out-handle,
    # position — and only the position is a waypoint.
    paths = {}
    for name, node in by_name.items():
        block = node["block"]
        if 'type="Path2D"' not in block:
            continue
        curve = re.search(r"curve = SubResource\(\"([^\"]+)\"\)", block)
        if curve is None:
            continue
        points_text = re.search(
            r"PackedVector2Array\(([^)]*)\)",
            subs.get(curve.group(1), {}).get("_body", ""),
        )
        if points_text is None:
            continue
        numbers = [float(value) for value in re.findall(r"-?\d+\.?\d*", points_text.group(1))]
        base = node.get("position", (0.0, 0.0))
        points = [
            (
                base[0] + offset[0] + numbers[index + 4],
                base[1] + offset[1] + numbers[index + 5],
            )
            for index in range(0, len(numbers) - 5, 6)
        ]
        if points:
            paths[name] = points

    return {
        "source": "NinjaAdventure map_village.tscn (CC0, pixel-boy)",
        "tile_size": 16.0,
        "offset": offset,
        "layers": layers,
        "solids": {
            str(source): sorted(cells) for source, cells in solids.items() if cells
        },
        "characters": characters,
        "behaviors": actors,
        "paths": {name: points for name, points in paths.items() if points},
        "teleporters": teleporters,
        "environments": environments,
    }


def _props(block: str, names: tuple[str, ...]) -> dict:
    """Read scalar properties off a node block.

    Parameters
    ----------
    block : str
        Node source.
    names : tuple of str
        Property names.

    Returns
    -------
    dict
    """
    out = {}
    for name in names:
        match = re.search(rf"\n{name} = ([-\d.]+)", block)
        if match is not None:
            value = float(match.group(1))
            out[name] = int(value) if value == int(value) else value
    return out


def _scalar(block: str, name: str) -> float | None:
    """Read one numeric property off a node block.

    Parameters
    ----------
    block : str
        Node source.
    name : str
        Property name.

    Returns
    -------
    float or None
    """
    match = re.search(rf"\n{name} = ([-\d.]+)", block)
    return float(match.group(1)) if match is not None else None


def main() -> int:
    """Write the converted map.

    Returns
    -------
    int
        Exit status.
    """
    data = convert()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")
    cells = sum(len(layer["cells"]) for layer in data["layers"])
    print(
        f"{OUT.relative_to(ROOT)}: {cells} cells in {len(data['layers'])} layers, "
        f"{len(data['characters'])} characters, "
        f"{len(data['teleporters'])} teleporters, "
        f"{len(data['environments'])} environments"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
