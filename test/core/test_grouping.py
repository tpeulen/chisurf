import chisurf.core.data
import chisurf.macros.core_data


def test_dataset_grouping():
    # Create two mock FCS data groups which inherit from DataCurveGroup
    mock_fcs1 = chisurf.core.data.ExperimentDataCurveGroup([chisurf.core.data.DataCurve()])
    mock_fcs1.name = "FCS_File_1"
    mock_fcs2 = chisurf.core.data.ExperimentDataCurveGroup([chisurf.core.data.DataCurve()])
    mock_fcs2.name = "FCS_File_2"

    # Backup original datasets
    original_datasets = chisurf.imported_datasets
    try:
        # Import them
        chisurf.imported_datasets = [mock_fcs1, mock_fcs2]

        # Group them together
        chisurf.macros.core_data.group_datasets([0, 1], _from_controller=True)

        # Expect the resulting group to be an ExperimentDataCurveGroup
        grouped = chisurf.imported_datasets[-1]
        assert isinstance(grouped, chisurf.core.data.ExperimentDataCurveGroup)
        assert hasattr(grouped, "x")
        assert grouped.x is not None
    finally:
        # Restore original datasets
        chisurf.imported_datasets = original_datasets


def test_a_local_api_groups_its_own_session_not_the_process_lists():
    """``ChiSurfAPI(mode="local", state=...)`` groups and ungroups the datasets of *its* session
    (it once reached for ``chisurf.imported_datasets`` and raised IndexError there)."""
    import numpy as np

    from chisurf.core.api import ChiSurfAPI
    from chisurf.core.data import DataCurve
    from chisurf.server.session import SessionState

    api = ChiSurfAPI(mode="local", state=SessionState())
    for name in ("a", "b"):
        api.load_dataset(dataset=DataCurve(x=np.arange(4.0), y=np.ones(4), name=name))
    result = api.group_datasets(dataset_indices=[0, 1], group_name="both")
    assert result["ok"] and result["member_count"] == 2
    (row,) = api.list_datasets()
    assert row["name"] == "both"
    assert api.ungroup_datasets(dataset_indices=[0])["ok"]
    assert sorted(r["name"] for r in api.list_datasets()) == ["a", "b"]
