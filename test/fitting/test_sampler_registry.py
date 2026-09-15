"""The samplers come from the registry, not from a list.

chisurf's sampler list, its dispatcher and its engine read one registry: the
compiled libraries' (IMP.bff publishes its sampler kernels with their options,
requirements and default warm-up) merged with chisurf's own registrations beside
each sampling function. These tests hold that contract: a kernel registered in
IMP.bff appears in chisurf without a chisurf edit, names resolve through the
entries' aliases, the warm-up defaults are the kernels' declared ones, and no
dispatcher branches on a sampler name.
"""

import json
import pathlib
import re
import uuid

import pytest

import chisurf.core.data  # noqa: F401  (import order: fit wires factorgraph before sample)
import chisurf.core.fitting.fit  # noqa: F401
from chisurf.core.fitting import sample
from chisurf.core.registry import catalog

bff = pytest.importorskip("IMP.bff")
if not hasattr(bff, "registry"):
    pytest.skip("this IMP.bff publishes no registry", allow_module_level=True)

ROOT = pathlib.Path(__file__).resolve().parents[2]


def test_every_sampler_has_a_label_a_description_and_a_function():
    assert {"ensemble", "slice", "de", "blocked", "collapsed", "mcmc"} <= set(sample.SAMPLERS)
    for name, entry in sample.SAMPLERS.items():
        assert entry.get("label") and entry.get("description"), name
        assert callable(sample.sampler_function(name)), name


def test_legacy_samplers_are_listed_last():
    names = list(sample.SAMPLERS)
    legacy = [n for n in names if sample.SAMPLERS[n].get("legacy")]
    assert legacy and names[-len(legacy):] == legacy


@pytest.mark.parametrize("alias,key", [("emcee", "ensemble"), ("stretch", "ensemble"), ("affine", "ensemble"),
                                       ("metropolis", "blocked"), ("zeus", "slice"),
                                       ("differential_evolution", "de"), ("Blocked", "blocked")])
def test_names_resolve_through_the_entries_aliases(alias, key):
    assert sample.resolve_sampler(alias) == key


def test_a_kernel_implemented_in_chisurf_takes_its_description_from_the_kernel_unless_overridden():
    stretch = bff.registry("sampler")["stretch"]
    assert sample.SAMPLERS["ensemble"]["description"] == stretch["description"]
    assert sample.SAMPLERS["ensemble"]["default_warmup"] == stretch["default_warmup"]
    # 'blocked' does more than the kernel (independent sub-problems): its own text
    assert sample.SAMPLERS["blocked"]["description"] != bff.registry("sampler")["metropolis"]["description"]


def test_a_sampler_that_needs_a_gradient_is_not_offered():
    assert "nuts" in catalog.registry("sampler")
    assert "nuts" not in sample.SAMPLERS


def test_a_kernel_registered_in_bff_appears_without_a_chisurf_edit():
    key = "test_kernel_" + uuid.uuid4().hex[:8]
    entry = {"label": "A test kernel", "summary": "s", "description": "registered by a test",
             "params_schema": {"type": "object", "properties": {}}, "kind": "chain", "population": "single",
             "requires_gradient": False, "aliases": [], "default_warmup": {"rule": "fixed", "value": 0}}
    assert bff.register_algorithm_json("sampler", key, json.dumps(entry))
    catalog.refresh()
    try:
        assert key in sample.SAMPLERS
        assert sample.SAMPLERS[key]["function"] == "sample_registered_kernel"
        assert sample.resolve_sampler(key) == key
        assert [n for n, _ in sample.sampler_choices()].count(key) == 1
    finally:
        catalog.refresh()


def test_warmup_defaults_are_the_kernels_declared_ones():
    from chisurf.core.fitting import sampler_bff
    for steps in (10, 200, 2000, 20000):
        assert sampler_bff._default_n_adapt("de", steps) == min(500, max(50, steps // 4))
        assert sampler_bff._default_n_adapt("metropolis", steps) == min(500, max(100, steps // 20))
        assert sampler_bff._default_n_adapt("stretch", steps) == 0


def test_no_dispatcher_branches_on_a_sampler_name():
    names = set(sample.SAMPLERS) | {"emcee"}
    for rel in ("chisurf/core/fitting/fit.py", "chisurf/core/fitting/engine.py", "chisurf/core/fitting/sampler_bff.py"):
        text = (ROOT / rel).read_text()
        for name in names:
            assert not re.search(r"(method|algorithm|backend)\s*[=!]=\s*['\"]%s['\"]" % re.escape(name), text), (rel, name)
            assert not re.search(r"^\s*['\"]%s['\"]\s*:\s*cs\.core\.fitting\.sample\." % re.escape(name), text, re.M), (rel, name)
    sample_text = (ROOT / "chisurf/core/fitting/sample.py").read_text()
    assert "SAMPLERS = {" not in sample_text and "SAMPLER_ALIASES" not in sample_text
