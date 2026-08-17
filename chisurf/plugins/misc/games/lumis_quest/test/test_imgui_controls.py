"""Unit tests for the ImGui-style menu controls in Lumis Quest.

The state tests are cheap. The one that matters is
:func:`test_every_control_draws_onto_a_scene`: the controls are Chimol's, drawn
against a painter, and the menu hands them a *scene* -- so a control that is
re-exported instead of adapted raises ``TypeError`` on the frame the pause menu
opens, which no amount of state testing sees.
"""

from __future__ import annotations

import pytest

from chisurf.plugins.misc.games.lumis_quest.gui import imgui_controls, overworld


class RecordingScene:
    """A scene that records what was drawn instead of drawing it.

    Stands in for :class:`~chisurf.gui.chigame.scene.Scene` with the two calls
    the painter adapter makes, so a control can be drawn with no GPU, no
    window and no asset pack.
    """

    #: No font: the adapter falls back to an estimated advance width, which is
    #: the same path a scene takes before its atlas is uploaded.
    font = None

    def __init__(self) -> None:
        self.quads: list[dict] = []
        self.strings: list[tuple[str, tuple[float, float], float]] = []

    def draw(self, kind, name="", at=(0.0, 0.0), size=(1.0, 1.0), **hints) -> None:
        """Record one quad."""
        self.quads.append({"kind": kind, "name": name, "at": at, "size": size, **hints})

    def text(self, content, at, height=4.0, color=(1, 1, 1, 1), align="left",
             shadow=True) -> float:
        """Record one string."""
        self.strings.append((content, at, height))
        return len(content) * height * 0.6


def _every_control() -> dict[str, object]:
    """One of each control, in a state worth drawing."""
    return {
        "SliderFloat": imgui_controls.SliderFloat("volume", 0.0, 1.0, 0.4),
        "ColorEdit4": imgui_controls.ColorEdit4("accent", color=(0.96, 0.88, 0.5, 1.0)),
        "Table": imgui_controls.Table(["name", "nm"], [["Iris", "560"], ["Lumi", "488"]]),
        "Checkbox": imgui_controls.Checkbox("crt shader", checked=True),
        "Combo": imgui_controls.Combo("soundtrack", ["one", "two"], index=1),
        "Button": imgui_controls.Button("quick save"),
        "ProgressBar": imgui_controls.ProgressBar("loading", 0.6),
        "TreeNode": imgui_controls.TreeNode("rig", expanded=True, children=["filter"]),
        "Separator": imgui_controls.Separator("display"),
        "Toggle": imgui_controls.Toggle("action combat", on=True),
        "RadioGroup": imgui_controls.RadioGroup("camera", ["scrolling", "screen"], 1),
        "InputInt": imgui_controls.InputInt("party size", 3, 1, 6),
        "ListBox": imgui_controls.ListBox("labels", [f"dye {i}" for i in range(9)], index=7),
        "Tabs": imgui_controls.Tabs(["STATUS", "MAP", "RIG"], index=2),
        "PlotLines": imgui_controls.PlotLines("frame ms", [16.0, 17.2, 15.9, 22.0]),
        "Histogram": imgui_controls.Histogram("counts", [3.0, 9.0, 1.0, 5.0]),
        "Tooltip": imgui_controls.Tooltip(["no provider wired", "set a key to enable"]),
        "TextInput": imgui_controls.TextInput("seed", "lumis", placeholder="random"),
    }


def test_every_control_draws_onto_a_scene():
    """Every control accepts the game's scene-native draw call and paints."""
    for name, widget in _every_control().items():
        scene = RecordingScene()
        widget.draw(scene, at=(0.0, 0.0), width=120.0, height=10.5, scale=1.0,
                    selected=True)
        assert scene.quads or scene.strings, f"{name} drew nothing"


def test_selection_highlight_is_drawn_behind_the_control():
    """A selected row gets a highlight quad before the control's own drawing."""
    plain, lit = RecordingScene(), RecordingScene()
    imgui_controls.Button("quick save").draw(plain, at=(0.0, 0.0), width=80.0,
                                             height=10.0, selected=False)
    imgui_controls.Button("quick save").draw(lit, at=(0.0, 0.0), width=80.0,
                                             height=10.0, selected=True)
    assert len(lit.quads) == len(plain.quads) + 1
    assert lit.quads[0]["color"] == imgui_controls.SELECTED_BG


def test_text_alignment_reaches_the_scene():
    """A centred control centres its text rather than left-anchoring it."""
    scene = RecordingScene()
    imgui_controls.Button("go").draw(scene, at=(50.0, 0.0), width=40.0, height=10.0)
    content, at, _ = scene.strings[-1]
    assert "go" in content
    assert at[0] == pytest.approx(50.0)


def test_adapter_takes_float_and_int_colours():
    """The adapter speaks the game's 0-1 floats and Chimol's 0-255 ints."""
    adapter = imgui_controls.ScenePainterAdapter(RecordingScene())
    assert adapter._color((255, 128, 0, 255))[0] == pytest.approx(1.0)
    assert adapter._color((255, 128, 0, 255))[1] == pytest.approx(128 / 255)
    assert adapter._color((0.5, 0.25, 0.125, 1.0))[0] == pytest.approx(0.5)


def test_slider_float_stepping_bounds_and_fraction():
    slider = imgui_controls.SliderFloat("Volume", v_min=0.0, v_max=1.0, value=0.5, fmt="%.2f")
    assert pytest.approx(slider.fraction) == 0.5
    assert slider.label == "Volume"

    # Step up
    slider.step(0.2)
    assert pytest.approx(slider.value) == 0.7
    assert pytest.approx(slider.fraction) == 0.7

    # Clamping max
    slider.step(1.0)
    assert pytest.approx(slider.value) == 1.0
    assert pytest.approx(slider.fraction) == 1.0

    # Clamping min
    slider.step(-2.0)
    assert pytest.approx(slider.value) == 0.0
    assert pytest.approx(slider.fraction) == 0.0

    # Set fraction directly
    slider.set_fraction(0.4)
    assert pytest.approx(slider.value) == 0.4


def test_checkbox_toggle():
    box = imgui_controls.Checkbox("CRT Retro Shader", checked=False)
    assert box.checked is False
    assert box.toggle() is True
    assert box.checked is True
    assert box.toggle() is False
    assert box.checked is False


def test_combo_cycling():
    combo = imgui_controls.Combo("Soundtrack", ["Ninja Adventure (CC0)", "Classic Chiptune", "Synthesiser"], index=0)
    assert combo.value == "Ninja Adventure (CC0)"
    assert combo.cycle(1) == "Classic Chiptune"
    assert combo.cycle(1) == "Synthesiser"
    assert combo.cycle(1) == "Ninja Adventure (CC0)"
    assert combo.cycle(-1) == "Synthesiser"


def test_button_label():
    btn = imgui_controls.Button("Quick Save")
    assert btn.label == "Quick Save"


def test_color_edit4():
    swatch = imgui_controls.ColorEdit4("Accent Color", color=(0.96, 0.88, 0.50, 1.0))
    assert swatch.label == "Accent Color"
    assert swatch.color == (0.96, 0.88, 0.50, 1.0)


def test_toggle_switches():
    switch = imgui_controls.Toggle("particle bursts", on=False)
    assert switch.toggle() is True
    assert switch.on is True
    assert switch.press(5.0, 5.0, 0.0, 0.0, 40.0, 10.0) is True
    assert switch.on is False
    # A press outside the box leaves it alone.
    assert switch.press(500.0, 5.0, 0.0, 0.0, 40.0, 10.0) is False
    assert switch.on is False


def test_radio_group_picks_by_press_position():
    group = imgui_controls.RadioGroup("", ["a", "b", "c"], index=0)
    assert group.press(70.0, 5.0, 0.0, 0.0, 90.0, 10.0) == "c"
    assert group.index == 2
    assert group.cycle(1) == "a"
    assert group.select(99) == "c"


def test_input_int_steps_and_clamps():
    stepper = imgui_controls.InputInt("party", value=3, v_min=1, v_max=4)
    assert stepper.increment() == 4
    assert stepper.increment() == 4
    assert stepper.decrement() == 3
    assert stepper.set_value(-5) == 1
    # The right-hand button steps up, the one two boxes left of it steps down.
    assert stepper.press(99.0, 5.0, 0.0, 0.0, 100.0, 10.0) == 2
    assert stepper.press(75.0, 5.0, 0.0, 0.0, 100.0, 10.0) == 1


def test_list_box_window_follows_the_selection():
    box = imgui_controls.ListBox("labels", [f"row {i}" for i in range(10)],
                                 index=0, visible_rows=4)
    assert box.first_visible == 0
    box.index = 6
    assert box.first_visible == 3
    box.index = 9
    assert box.first_visible == 6
    assert box.move(1) == "row 0"
    assert box.first_visible == 0


def test_tabs_select_and_cycle():
    tabs = imgui_controls.Tabs(["ONE", "TWO", "THREE"], index=0)
    assert tabs.value == "ONE"
    assert tabs.cycle(-1) == "THREE"
    assert tabs.press(35.0, 5.0, 0.0, 0.0, 90.0, 10.0) == 1
    assert tabs.value == "TWO"
    assert tabs.press(35.0, 500.0, 0.0, 0.0, 90.0, 10.0) is None


def test_plot_and_histogram_ranges():
    plot = imgui_controls.PlotLines("ms", [4.0, 8.0, 6.0])
    assert plot.range() == (4.0, 8.0)
    assert imgui_controls.PlotLines("ms", [5.0, 5.0]).range() == (5.0, 6.0)
    # A histogram floors at zero, so bar lengths stay proportional.
    assert imgui_controls.Histogram("n", [3.0, 9.0]).range() == (0.0, 9.0)


def test_text_input_editing():
    field = imgui_controls.TextInput("seed", "lumi")
    assert field.text == "lumi"
    assert field.cursor == 4
    assert field.insert("s") == "lumis"
    assert field.backspace() == "lumi"
    field.move(-2)
    assert field.insert("X") == "luXmi"
    # Newlines and tabs never reach the buffer -- they draw as nothing or as a
    # missing glyph, and a paste is full of them.
    assert field.insert("\n\t") == "luXmi"


def test_menu_rows_map_to_the_expected_controls():
    """Each settings row draws as the control that fits what it changes."""
    game = overworld.OverworldGame()

    game.menu_tab = game.TABS.index("OPTIONS")
    options = [type(game._menu_widget("OPTIONS", i, row)).__name__
               for i, row in enumerate(game._menu_rows())]
    # Three short schemes fit side by side; "screen by screen" does not, so
    # the camera gets a selector rather than a row that overlaps itself.
    assert options[:2] == ["RadioGroup", "Combo"]
    assert options[2:10] == ["SliderFloat"] * 8
    assert options[10] == "NoneType"          # the llm row stays text: it has a light
    assert options[11:13] == ["Button", "Button"]

    game.menu_tab = game.TABS.index("GAMELOGIC")
    logic = [type(game._menu_widget("GAMELOGIC", i, row)).__name__
             for i, row in enumerate(game._menu_rows())]
    assert logic[0] == "Combo"
    assert logic[1:6] == ["SliderFloat"] * 5
    assert logic[6:9] == ["Toggle"] * 3
    assert logic[9] == "ColorEdit4"
    assert logic[10:13] == ["Button"] * 3


def test_soundtrack_control_and_option_share_one_list():
    """The combo cannot offer a theme the option that applies it cannot reach."""
    game = overworld.OverworldGame()
    game.menu_tab = game.TABS.index("GAMELOGIC")
    combo = game._menu_widget("GAMELOGIC", 0, "")
    assert combo.options == list(game.SOUNDTRACKS)
    game.menu_row = 0
    game._gamelogic_confirm(direction=1)
    assert game.soundtrack_theme == combo.options[1]
