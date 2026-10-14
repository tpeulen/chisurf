"""A view spec carries per-parameter priors.

The Qt per-parameter prior selector went with the Qt shell (the prior itself is covered by the
fitting tests); the spec loader keeps the ``priors`` mapping of a parameter group section.
"""


def test_view_spec_loader_round_trips_priors():
    from chisurf.core.models import view_spec as vs

    view = vs.load_view_spec(
        {
            "sections": [
                {
                    "type": "parameter_group",
                    "target": "g",
                    "priors": {"tau1": {"kind": "normal", "mu": 2.0, "sigma": 0.3}},
                }
            ],
        }
    )
    section = view.sections[0]
    assert isinstance(section, vs.ParameterGroupSection)
    assert section.priors == {"tau1": {"kind": "normal", "mu": 2.0, "sigma": 0.3}}
