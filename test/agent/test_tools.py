"""Tool-level tests: every agent tool against a real ChiSurf session.

These run the same code paths the language model drives, without a model, so
a broken tool is caught here rather than blamed on the LLM.
"""

from __future__ import annotations

import pathlib

import pytest

from chisurf.core.agent import ToolError, build_default_registry
from chisurf.core.agent.tools import data as data_tools
from chisurf.core.agent.tools import fitting as fitting_tools
from chisurf.core.agent.tools import scripting as scripting_tools

TCSPC_RELATIVE = "tcspc/EasyTau300"
MODEL_NAME = "Lifetime (new)"


# ── registry ──────────────────────────────────────────────────────────


def test_registry_exposes_the_workflow_tools():
    registry = build_default_registry()
    for name in (
        "list_files",
        "load_data",
        "list_experiments",
        "create_fit",
        "run_fit",
        "set_parameter",
        "export_fit_results",
    ):
        assert name in registry.names()


def test_every_tool_has_a_schema_and_a_description():
    for spec in build_default_registry().tools.values():
        assert spec.description.strip(), f"{spec.name} has no description"
        assert spec.parameters.get("type") == "object"
        for argument, schema in spec.parameters.get("properties", {}).items():
            assert schema.get("description"), f"{spec.name}.{argument} has no description"


def test_openai_tool_definitions_are_well_formed():
    tools = build_default_registry().to_openai_tools()
    assert tools
    for tool in tools:
        assert tool["type"] == "function"
        assert set(tool["function"]) == {"name", "description", "parameters"}


def test_safety_filter_hides_dangerous_tools():
    registry = build_default_registry()
    permitted = {spec.name for spec in registry.filtered("write")}
    assert "run_python" not in permitted
    assert "write_file" not in permitted
    assert "create_fit" in permitted
    assert "list_files" in permitted


def test_missing_required_argument_is_reported_with_the_expected_names():
    spec = build_default_registry().get("create_fit")
    with pytest.raises(ToolError) as excinfo:
        spec.validate_arguments({})
    assert "model_name" in str(excinfo.value)


def test_unknown_arguments_are_dropped_rather_than_crashing_the_handler():
    spec = build_default_registry().get("run_fit")
    assert spec.validate_arguments({"fit": 0, "hallucinated": 7}) == {"fit": 0}


# ── file discovery ────────────────────────────────────────────────────


def test_list_files_annotates_the_experiment_type(context):
    result = data_tools.list_files(context, directory=TCSPC_RELATIVE, pattern="*.dat")
    assert result["ok"]
    assert result["n_files"] >= 4
    assert {entry["experiment"] for entry in result["files"]} == {"TCSPC"}


def test_list_files_rejects_a_missing_directory(context):
    with pytest.raises(ToolError, match="does not exist"):
        data_tools.list_files(context, directory="no/such/place")


# ── loading ───────────────────────────────────────────────────────────


def test_load_data_loads_a_whole_directory(context):
    result = data_tools.load_data(context, directory=TCSPC_RELATIVE, pattern="*.dat")
    assert result["ok"]
    assert result["n_loaded"] == len(result["dataset_indices"]) >= 4
    assert result["dataset_indices"] == list(range(result["n_loaded"]))
    assert all(entry["experiment"] == "TCSPC" for entry in result["datasets"])


def test_load_data_reports_the_path_it_could_not_find(context):
    with pytest.raises(ToolError, match="does not exist"):
        data_tools.load_data(context, paths=["nope.dat"])


def test_load_data_needs_something_to_load(context):
    with pytest.raises(ToolError, match="no files to load"):
        data_tools.load_data(context, directory=TCSPC_RELATIVE, pattern="*.nothing")


def test_unknown_extension_asks_for_an_explicit_reader(context, tmp_path):
    mystery = tmp_path / "measurement.qqq"
    mystery.write_text("1 2\n3 4\n")
    with pytest.raises(ToolError, match="list_experiments"):
        data_tools.load_data(context, paths=[str(mystery)])


def test_list_experiments_reports_readers_and_models(context):
    result = data_tools.list_experiments(context, experiment="TCSPC")
    assert result["ok"]
    tcspc = result["experiments"]["TCSPC"]
    assert "TXT/CSV" in tcspc["readers"]
    assert MODEL_NAME in tcspc["models"]


def test_list_experiments_rejects_an_invented_experiment(context):
    with pytest.raises(ToolError, match="unknown experiment"):
        data_tools.list_experiments(context, experiment="Raman")


# ── fitting ───────────────────────────────────────────────────────────


@pytest.fixture()
def loaded(context):
    """Load the TCSPC sample directory and return the context."""
    data_tools.load_data(context, directory=TCSPC_RELATIVE, pattern="*.dat")
    return context


def test_create_fit_makes_one_runnable_fit_per_dataset(loaded):
    result = fitting_tools.create_fit(loaded, model_name=MODEL_NAME)
    assert result["ok"]
    assert result["n_created"] == len(loaded.datasets)
    for entry in result["fits"]:
        assert entry["fit_range"][1] > entry["fit_range"][0], "fit range was not initialised"


def test_create_fit_rejects_an_invented_model_name(loaded):
    with pytest.raises(ToolError, match="unknown model"):
        fitting_tools.create_fit(loaded, model_name="Exponential-ish")


def test_model_names_tolerate_case_and_stray_whitespace(loaded):
    """The daily-driver model is registered as 'Lifetime ' — with the space."""
    exact = fitting_tools.resolve_model_name(MODEL_NAME)
    assert exact == MODEL_NAME
    assert fitting_tools.resolve_model_name(MODEL_NAME.upper()) == MODEL_NAME
    assert fitting_tools.resolve_model_name(f"  {MODEL_NAME}  ") == MODEL_NAME


def test_an_ambiguous_model_name_asks_for_the_full_one(monkeypatch):
    """Against a fixed registry, so the answer does not depend on Qt state."""
    monkeypatch.setattr(
        fitting_tools,
        "_model_names",
        lambda: {"TCSPC": ["Lifetime (new)", "Lifetime mixer (new)"]},
    )
    with pytest.raises(ToolError, match="ambiguous"):
        fitting_tools.resolve_model_name("Lifetime")


def test_a_prefix_resolves_when_it_is_unique(monkeypatch):
    monkeypatch.setattr(
        fitting_tools, "_model_names", lambda: {"TCSPC": ["Lifetime ", "FRET: PDDEM"]}
    )
    assert fitting_tools.resolve_model_name("Lifetime") == "Lifetime "
    assert fitting_tools.resolve_model_name("fret") == "FRET: PDDEM"


def test_create_fit_reports_the_name_it_resolved_to(loaded):
    result = fitting_tools.create_fit(loaded, model_name=MODEL_NAME.upper(), datasets=[0])
    assert result["model"] == MODEL_NAME


def test_create_fit_can_group_datasets_into_one_fit(loaded):
    result = fitting_tools.create_fit(loaded, model_name=MODEL_NAME, datasets=[0, 1], grouped=True)
    assert result["n_created"] == 1


def test_run_fit_improves_and_reports_chi2r(loaded):
    fitting_tools.create_fit(loaded, model_name=MODEL_NAME, datasets=[0])
    result = fitting_tools.run_fit(loaded, fit=0)
    assert result["ok"]
    entry = result["results"][0]
    assert entry["ok"]
    assert entry["chi2r"] is not None and entry["chi2r"] > 0
    # The optimiser really ran: the reduced chi2 moved off its starting value.
    assert entry["chi2r"] < entry["chi2r_before"]


def test_create_fit_withholds_chi2r_until_the_fit_has_been_run(loaded):
    result = fitting_tools.create_fit(loaded, model_name=MODEL_NAME, datasets=[0])
    entry = result["fits"][0]
    assert "chi2r" not in entry, "a starting value must not look like a result"
    assert entry["optimised"] is False
    assert "run_fit" in result["next_step"]


def test_run_fit_without_any_fit_says_what_to_do(context):
    with pytest.raises(ToolError, match="create_fit"):
        fitting_tools.run_fit(context)


def test_get_fit_lists_named_parameters(loaded):
    fitting_tools.create_fit(loaded, model_name=MODEL_NAME, datasets=[0])
    result = fitting_tools.get_fit(loaded, fit=0)
    names = [parameter["name"] for parameter in result["parameters"]]
    assert names, "model exposes no parameters"
    assert result["fit_range"][1] > 0


def test_set_parameter_changes_value_fixed_and_bounds(loaded):
    fitting_tools.create_fit(loaded, model_name=MODEL_NAME, datasets=[0])
    name = fitting_tools.get_fit(loaded, fit=0)["parameters"][0]["name"]

    result = fitting_tools.set_parameter(
        loaded, parameter=name, fit=0, value=2.5, fixed=True, bounds=[0.1, 10.0]
    )
    assert result["ok"]
    changed = result["changed"][0]
    assert changed["value"] == pytest.approx(2.5, rel=1e-6)
    assert changed["fixed"] is True
    assert changed["bounds"] == [0.1, 10.0]


def test_set_parameter_needs_something_to_change(loaded):
    fitting_tools.create_fit(loaded, model_name=MODEL_NAME, datasets=[0])
    with pytest.raises(ToolError, match="at least one"):
        fitting_tools.set_parameter(loaded, parameter="tL1", fit=0)


def test_set_parameter_lists_the_real_names_when_the_name_is_wrong(loaded):
    fitting_tools.create_fit(loaded, model_name=MODEL_NAME, datasets=[0])
    with pytest.raises(ToolError, match="Parameters of fit 0"):
        fitting_tools.set_parameter(loaded, parameter="not_a_parameter", fit=0, value=1.0)


def test_set_parameter_can_target_every_fit(loaded):
    fitting_tools.create_fit(loaded, model_name=MODEL_NAME, datasets=[0, 1])
    name = fitting_tools.get_fit(loaded, fit=0)["parameters"][0]["name"]
    result = fitting_tools.set_parameter(loaded, parameter=name, value=3.0, all_fits=True)
    assert len(result["changed"]) == 2


def test_set_fit_range_explicit_and_auto(loaded):
    fitting_tools.create_fit(loaded, model_name=MODEL_NAME, datasets=[0])
    explicit = fitting_tools.set_fit_range(loaded, fit=0, start=100, stop=900)
    assert explicit["fit_range"] == [100, 900]
    automatic = fitting_tools.set_fit_range(loaded, fit=0, auto=True)
    assert automatic["fit_range"] != [100, 900]


def test_export_fit_results_writes_a_table(loaded, tmp_path):
    fitting_tools.create_fit(loaded, model_name=MODEL_NAME, datasets=[0, 1])
    fitting_tools.run_fit(loaded)
    target = tmp_path / "results.csv"
    result = fitting_tools.export_fit_results(loaded, path=str(target))
    assert result["n_rows"] == 2
    text = target.read_text()
    assert "chi2r" in text.splitlines()[0]
    assert len(text.strip().splitlines()) == 3


# ── reference resolution ──────────────────────────────────────────────


def test_a_fit_can_be_addressed_by_name(loaded):
    fitting_tools.create_fit(loaded, model_name=MODEL_NAME, datasets=[0])
    name = loaded.fits[0].name
    assert loaded.resolve_fit(name)[1] == 0


def test_an_ambiguous_reference_asks_for_an_index(loaded):
    fitting_tools.create_fit(loaded, model_name=MODEL_NAME, datasets=[0, 1])
    with pytest.raises(ToolError, match="say which one"):
        loaded.resolve_fit(None)


def test_an_out_of_range_index_reports_the_session_size(loaded):
    fitting_tools.create_fit(loaded, model_name=MODEL_NAME, datasets=[0])
    with pytest.raises(ToolError, match="out of range"):
        loaded.resolve_fit(17)


# ── scripting ─────────────────────────────────────────────────────────


def test_run_python_sees_the_live_session(loaded):
    fitting_tools.create_fit(loaded, model_name=MODEL_NAME, datasets=[0])
    result = scripting_tools.run_python(
        loaded, code="print(len(datasets), len(fits))", purpose="count objects"
    )
    assert result["ok"]
    assert result["stdout"].split() == [str(len(loaded.datasets)), "1"]


def test_run_python_returns_the_result_variable(loaded):
    result = scripting_tools.run_python(loaded, code="result = 6 * 7")
    assert result["result"] == "42"


def test_run_python_reports_an_exception_without_raising(loaded):
    result = scripting_tools.run_python(loaded, code="1 / 0")
    assert result["ok"] is False
    assert "ZeroDivisionError" in result["error"]


def test_run_python_is_blocked_when_execution_is_disabled(context):
    context.allow_code_execution = False
    with pytest.raises(ToolError, match="disabled"):
        scripting_tools.run_python(context, code="print(1)")


def test_write_and_read_file_round_trip(context, tmp_path):
    target = tmp_path / "scripts" / "analysis.py"
    written = scripting_tools.write_file(context, path=str(target), content="print('hi')\n")
    assert written["ok"] and pathlib.Path(written["path"]).is_file()
    read_back = scripting_tools.read_file(context, path=str(target))
    assert read_back["content"].strip() == "print('hi')"
