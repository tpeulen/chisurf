"""The hub numbers its steps gaplessly: Advanced-only steps get a sub-number of the step before."""

from chisurf.emtk.tool_hub import number_steps


def test_steps_are_numbered_without_gaps_and_advanced_steps_are_sub_numbers():
    panels = number_steps(
        [
            {"name": "Pipeline steps", "separator": True},
            {"name": "0. Setup", "role": "setup"},
            {"name": "1. Data", "role": "data"},
            {"name": "2. Selection", "role": "selection"},
            {"name": "9. Fusion", "role": "fusion", "advanced": True},
            {"name": "4. BVA", "role": "bva", "background": True},
            {"name": "6. MLE", "role": "mle"},
            {"name": "7. H2MM", "role": "h2mm", "advanced": True},
            {"name": "Side tools", "separator": True},
            {"name": "Browser", "role": "browser"},
        ]
    )
    names = [p["name"] for p in panels]
    assert names == [
        "Pipeline steps", "0. Setup", "1. Data", "2. Selection", "2.1 Fusion", "2.2 BVA",
        "3. MLE", "3.1 H2MM", "Side tools", "Browser",
    ]


def test_a_hub_counting_from_one_keeps_its_base():
    names = [p["name"] for p in number_steps([{"name": "1. A"}, {"name": "3. B"}, {"name": "3.2 C"}])]
    assert names == ["1. A", "2. B", "3. C"]


def test_burst_analysis_rail_in_simple_counts_0_to_3():
    from chisurf.plugins.burst.burst_analysis.gui.native import STEPS

    numbered = number_steps([dict(p) for p in STEPS])
    simple = [p["name"].split(" ", 1)[0] for p in numbered
              if not p.get("separator") and p["name"][0].isdigit()
              and not (p.get("advanced") or p.get("background"))]
    assert simple == ["0.", "1.", "2.", "3."]
