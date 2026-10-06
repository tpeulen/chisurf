"""Regression coverage for degraded plugin dependency ordering."""

from itertools import permutations

from chisurf.core.plugin.dependencies import ordered_manifests, resolve


def test_cycle_dependants_follow_the_actual_component():
    """Only mutually dependent plugins form a cycle; their tail follows them."""
    report = resolve([
        {"id": "x", "requires": {"y": "*"}},
        {"id": "y", "requires": {"x": "*"}},
        {"id": "a", "requires": {"x": "*"}},
        {"id": "z", "requires": {"a": "*"}},
    ])
    assert report.cycles == [["x", "y"]]
    assert report.order == ["x", "y", "a", "z"]


def test_duplicate_ids_use_the_first_declaration():
    """Discovery's first declaration supplies both requirements and version."""
    report = resolve([
        {"id": "x", "version": "1.0", "requires": {"y": "*"}},
        {"id": "x", "version": "2.0", "requires": {"absent": "*"}},
        {"id": "y", "version": "1.0"},
        {"id": "z", "requires": {"x": "<2"}},
    ])
    assert report.ok
    assert report.order == ["y", "x", "z"]


def test_separate_and_self_cycles_keep_their_blocked_tails():
    """Distinct SCCs remain separate, including a self-dependent singleton."""
    report = resolve([
        {"id": "x", "requires": {"y": "*"}},
        {"id": "y", "requires": {"x": "*"}},
        {"id": "p", "requires": {"q": "*"}},
        {"id": "q", "requires": {"p": "*"}},
        {"id": "s", "requires": {"s": "*"}},
        {"id": "a", "requires": {"x": "*", "s": "*"}},
        {"id": "b", "requires": {"a": "*", "p": "*"}},
    ])
    assert report.cycles == [["p", "q"], ["s"], ["x", "y"]]
    assert report.order == ["p", "q", "s", "x", "y", "a", "b"]


def test_long_chain_and_cycle_do_not_require_recursion():
    """Traversal handles graphs longer than the normal Python recursion limit."""
    ids = [f"p{index:04d}" for index in range(2500)]
    items = [
        {"id": plugin_id, "requires": {ids[index + 1]: "*"} if index + 1 < len(ids) else {}}
        for index, plugin_id in enumerate(ids)
    ]
    assert resolve(items).order == ids[::-1]
    items[-1]["requires"] = {ids[0]: "*"}
    report = resolve(items)
    assert report.cycles == [ids]
    assert report.order == ids


def test_healthy_diamond_preserves_ready_waves_under_permutation():
    """Newly ready lexical leaders wait for the previous ready wave to finish."""
    items = [
        {"id": "a", "requires": {"b": "*", "c": "*"}},
        {"id": "b", "requires": {"d": "*"}},
        {"id": "c", "requires": {"d": "*"}},
        {"id": "d"},
        {"id": "z"},
    ]
    for permutation in permutations(items):
        ordered, report = ordered_manifests(permutation)
        assert report.ok
        assert report.order == ["d", "z", "b", "c", "a"]
        assert [item["id"] for item in ordered] == report.order
        assert {id(item) for item in ordered} == {id(item) for item in items}


def test_sorting_retains_duplicates_and_empty_ids():
    """Sorting preserves every object and the input order of equal-ranked ids."""
    items = [{"id": "x"}, {"id": "x"}, {"id": ""}, {}]
    for permutation in permutations(items):
        ordered, report = ordered_manifests(permutation)
        assert report.order == ["x"]
        expected = [item for item in permutation if item.get("id") == "x"]
        expected += [item for item in permutation if not item.get("id")]
        assert [id(item) for item in ordered] == [id(item) for item in expected]


def test_optional_bounds_report_without_constraining_order():
    """Optional coupling validates versions but never introduces ordering edges."""
    report = resolve([
        {"id": "a", "optional_requires": {"z": ">=2", "missing": "*"}},
        {"id": "z", "version": "1.0", "requires": {"a": "*"}},
    ])
    assert report.order == ["a", "z"]
    assert report.cycles == []
    assert report.missing == {}
    assert report.unknown == {"a": ["missing"]}
    assert report.out_of_bounds == {"a": ["optionally requires z >=2, but z is 1.0"]}


def test_cycle_order_and_diagnostics_are_permutation_invariant():
    """Input traversal order cannot affect component membership or degraded order."""
    items = [
        {"id": "x", "requires": {"y": "*"}},
        {"id": "y", "requires": {"x": "*"}},
        {"id": "a", "requires": {"x": "*"}},
        {"id": "z", "requires": {"a": "*"}},
    ]
    for permutation in permutations(items):
        ordered, report = ordered_manifests(permutation)
        assert report.cycles == [["x", "y"]]
        assert report.order == ["x", "y", "a", "z"]
        assert [item["id"] for item in ordered] == report.order



def test_cycle_message_reports_members_not_an_invented_edge_path():
    report = resolve([
        {"id": "a", "requires": {"b": "*", "c": "*"}},
        {"id": "b", "requires": {"a": "*"}},
        {"id": "c", "requires": {"a": "*"}},
    ])
    assert report.cycles == [["a", "b", "c"]]
    # This component has no b->c edge, nor a cycle visiting every node once.
    assert report.problems() == ["dependency cycle involving: a, b, c"]
