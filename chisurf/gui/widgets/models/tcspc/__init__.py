# This file imports all widget classes from their respective modules
# to maintain backward compatibility with existing code.

# Define plot_cls_dist_default here to avoid circular imports
import chisurf.gui.plots
import chisurf.core.math.datatools

plot_cls_dist_default = [
    (
        chisurf.gui.plots.LinePlot,
        {
            'd_scalex': 'lin',
            'd_scaley': 'log',
            'r_scalex': 'lin',
            'r_scaley': 'lin',
            'x_label': 'time (ns)',
            'y_label': 'counts',
            'plot_irf': True
        }
     ),
    (chisurf.gui.plots.FitTablePlot, {}),
    (chisurf.gui.plots.FitInfo, {}),
    (chisurf.gui.plots.ParameterScanPlot, {}),
    (chisurf.gui.plots.ResidualPlot, {}),
    (
        chisurf.gui.plots.DistributionPlot,
        {
            'distribution_options': {
                'Distance': {
                    'attribute': 'distance_distribution',
                    'accessor': lambda x, **kwargs: (x[0][0], x[0][1]),
                    'accessor_kwargs': {'sort': False},
                    'curve_options': {
                        'symbol': "t",
                        'bar_mode': 'sticks',
                    }
                },
                'FRET-rate constant': {
                    'attribute': 'fret_rate_spectrum',
                    'accessor': chisurf.core.math.datatools.interleaved_to_two_columns,
                    'accessor_kwargs': {'sort': True},
                    'curve_options': {
                        'symbol': "o"
                    }
                },
                'Lifetime': {
                    'attribute': 'lifetime_spectrum',
                    'accessor': chisurf.core.math.datatools.interleaved_to_two_columns,
                    'accessor_kwargs': {'sort': True},
                    'curve_options': {
                        'symbol': "o"
                    }
                }
            }
        }
    )
]

# Deprecated model-class aliases. Every TCSPC model is a pure compute model whose
# editor comes from a ``*.view.json``; these names stay importable because user
# copies of ``experiment_configs.yaml`` *replace* the bundled model list and
# pickled projects pin class paths, so a path that no longer resolves drops the
# entry from the model menu without saying so.
#
# The hand-written widget layer they used to name is gone: ``LifetimeWidget``,
# ``LifetimeModelWidgetBase``, ``ConvolveWidget``, ``CorrectionsWidget``,
# ``GenericWidget``, ``AnisotropyWidget``, ``GaussianWidget`` and
# ``DiscreteDistanceWidget`` were reachable only from each other once every model
# became data-described.
from chisurf.core.models.tcspc.fret import (
    FRETrateModel,
    GaussianModel,
    IsingChainModel,
    SawNuModel,
    WormLikeChainModel,
)
from chisurf.core.models.tcspc.fret_structure import FRETStructure
from chisurf.core.models.tcspc.lifetime import LifetimeMixtureModel, LifetimeModel
from chisurf.core.models.tcspc.maxent import MaxEntFRETModel, MaxEntLifetimeModel
from chisurf.core.models.tcspc.parse.tcspc_parse import ParseDecayModel
from chisurf.core.models.tcspc.pddem import PDDEM, PDDEMModel

LifetimeModelWidget = LifetimeModel
LifetimeMixtureModelWidget = LifetimeMixtureModel
LifetimeMixModelWidget = LifetimeMixtureModel
GaussianModelWidget = GaussianModel
FRETrateModelWidget = FRETrateModel
WormLikeChainModelWidget = WormLikeChainModel
SawNuChainModelWidget = SawNuModel
IsingChainModelWidget = IsingChainModel
ParseDecayModelWidget = ParseDecayModel
FRETStructureWidget = FRETStructure
MaxEntLifetimeModelWidget = MaxEntLifetimeModel
MaxEntFRETModelWidget = MaxEntFRETModel
PDDEMModelWidget = PDDEMModel
PDDEMWidget = PDDEM

#: Deprecated and **unopenable**: ``EtModelFreeWidget`` was abstract (no
#: ``update_model``), so selecting it in the model menu raised ``TypeError``. Its
#: compute never left the GUI file. Resolves to ``None`` so an old config drops the
#: entry rather than crashing when it is chosen.
EtModelFreeWidget = None
