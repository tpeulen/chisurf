"""A run survives a session, and is stored by identifier rather than by value."""

from __future__ import annotations

import json

import pytest

from chisurf.plugins.misc.games.lumis_quest.api import save


def test_a_run_round_trips(tmp_path):
    """Everything that carries between sessions comes back."""
    path = tmp_path / "run.json"
    state = save.RunState(
        position=(123.5, 456.5),
        team=[(11, 40), (22, 5)],
        collection=[33, 44],
        inventory=[55],
        emission_id=55,
        detector_id=None,
        cleared=["docs/a.md", "docs/b.md"],
        order="clarity",
    )
    state.save(path)
    back = save.RunState.load(path)
    assert back == state


def test_a_missing_save_is_a_fresh_run(tmp_path):
    """Refusing to start because there is no save would be worse than none."""
    assert save.RunState.load(tmp_path / "nothing.json") == save.RunState()


def test_a_corrupt_save_is_a_fresh_run(tmp_path):
    """Losing a run is annoying; refusing to launch is worse."""
    path = tmp_path / "run.json"
    path.write_text("{ this is not json", encoding="utf-8")
    assert save.RunState.load(path) == save.RunState()

    path.write_text(json.dumps({"version": 999, "team": [[1, 2]]}), encoding="utf-8")
    assert save.RunState.load(path) == save.RunState(), "a future version must not be guessed at"

    path.write_text(json.dumps({"version": save.VERSION, "collection": ["not an id"]}),
                    encoding="utf-8")
    assert save.RunState.load(path) == save.RunState()


def test_creatures_are_stored_by_id_not_by_value(tmp_path):
    """So a corrected measurement in the database reaches a saved game.

    Storing the stat block would freeze whatever the numbers were on the day
    the run was saved, including any since fixed.
    """
    path = tmp_path / "run.json"
    save.RunState(team=[(11, 40)], inventory=[55], emission_id=55).save(path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["team"] == [[11, 40]]
    assert raw["inventory"] == [55]
    flat = json.dumps(raw)
    for leaked in ("ext_coeff", "quantum_yield", "emission_nm", "curve"):
        assert leaked not in flat


def test_a_vanished_part_is_left_unfitted_rather_than_failing(tmp_path):
    """A catalogue entry that disappears must not break the load."""
    state = save.RunState(emission_id=-999, detector_id=-998)
    loadout = save.restore_loadout(state, pool=[])
    assert loadout.emission is None and loadout.detector is None


def test_the_game_uses_the_save_path_it_was_given(qapp, tmp_path):
    """A test must never read or write the player's real run."""
    pytest.importorskip("wgpu")
    from chisurf.gui import chigame
    from chisurf.plugins.misc.games.lumis_quest.gui.overworld import OverworldGame

    docs = tmp_path / "docs" / "guides"
    docs.mkdir(parents=True)
    (docs / "one.md").write_text("# One\n", encoding="utf-8")
    (docs / "index.md").write_text("# Guides\n\n```{toctree}\n\none\n```\n", encoding="utf-8")

    from chisurf.plugins.misc.games.lumis_quest.api.world import build_world

    try:
        context = chigame.create_offscreen(size=(160, 120))
    except Exception as error:  # pragma: no cover - depends on the machine
        pytest.skip(f"no usable GPU adapter: {error}")

    run = tmp_path / "run.json"
    game = OverworldGame(world=build_world(tmp_path / "docs"), save_path=run)
    chigame.GameHost(game, context, with_text=False, with_audio=False)
    game.finish_loading()
    game.iris = [321.0, 654.0]
    game.save_run()

    assert run.is_file()
    assert save.RunState.load(run).position == (321.0, 654.0)
