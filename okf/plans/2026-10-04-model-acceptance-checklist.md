# Full experiment/model acceptance checklist

Each unchecked item blocks the all-model claim. Class resolution is verified by the parent inventory; scientific round-trip, nondefault state, GUI and history acceptance remain separate gates. Catalogue source: `chisurf/core/settings/experiment_configs.yaml`.

## tcspc

- [ ] `chisurf.core.models.description.tcspc_polarized` — data/config/parameters/dependencies; fresh restore/edit/recompute/resave; GUI state; history undo/redo.
- [ ] `chisurf.core.models.description.tcspc_mixture` — data/config/parameters/dependencies; fresh restore/edit/recompute/resave; GUI state; history undo/redo.
- [ ] `chisurf.core.models.description.tcspc_fret_gaussian` — data/config/parameters/dependencies; fresh restore/edit/recompute/resave; GUI state; history undo/redo.
- [ ] `chisurf.core.models.description.tcspc_fret_discrete` — data/config/parameters/dependencies; fresh restore/edit/recompute/resave; GUI state; history undo/redo.
- [ ] `chisurf.core.models.description.tcspc_fret_worm_like_chain` — data/config/parameters/dependencies; fresh restore/edit/recompute/resave; GUI state; history undo/redo.
- [ ] `chisurf.core.models.description.tcspc_fret_saw_nu` — data/config/parameters/dependencies; fresh restore/edit/recompute/resave; GUI state; history undo/redo.
- [ ] `chisurf.core.models.description.tcspc_fret_ising_chain` — data/config/parameters/dependencies; fresh restore/edit/recompute/resave; GUI state; history undo/redo.
- [ ] `chisurf.core.models.description.tcspc_pddem` — data/config/parameters/dependencies; fresh restore/edit/recompute/resave; GUI state; history undo/redo.
- [ ] `chisurf.core.models.description.tcspc_fret_acceptor_density` — data/config/parameters/dependencies; fresh restore/edit/recompute/resave; GUI state; history undo/redo.
- [ ] `chisurf.core.models.tcspc.parse.tcspc_parse.ParseDecayModel` — data/config/parameters/dependencies; fresh restore/edit/recompute/resave; GUI state; history undo/redo.
- [ ] `chisurf.core.models.tcspc.fret_structure.FRETStructure` — data/config/parameters/dependencies; fresh restore/edit/recompute/resave; GUI state; history undo/redo.
- [ ] `chisurf.core.models.description.tcspc_maxent_lifetime` — data/config/parameters/dependencies; fresh restore/edit/recompute/resave; GUI state; history undo/redo.
- [ ] `chisurf.core.models.description.tcspc_maxent_fret` — data/config/parameters/dependencies; fresh restore/edit/recompute/resave; GUI state; history undo/redo.

## stopped_flow

- [ ] `chisurf.core.models.stopped_flow.parse.ParseStoppedFlowModel` — data/config/parameters/dependencies; fresh restore/edit/recompute/resave; GUI state; history undo/redo.
- [ ] `chisurf.core.models.stopped_flow.reaction.ReactionModel` — data/config/parameters/dependencies; fresh restore/edit/recompute/resave; GUI state; history undo/redo.

## pda

- [ ] `chisurf.core.models.pda2c.simple.Pda2cSimpleModel` — data/config/parameters/dependencies; fresh restore/edit/recompute/resave; GUI state; history undo/redo.
- [ ] `chisurf.core.models.pda2c.pdagauss.Pda2cGaussianDistanceModel` — data/config/parameters/dependencies; fresh restore/edit/recompute/resave; GUI state; history undo/redo.
- [ ] `chisurf.core.models.pda2c.saw_nu.Pda2cSawNuModel` — data/config/parameters/dependencies; fresh restore/edit/recompute/resave; GUI state; history undo/redo.
- [ ] `chisurf.core.models.pda2c.dynamic.Pda2cDynamicTwoStateModel` — data/config/parameters/dependencies; fresh restore/edit/recompute/resave; GUI state; history undo/redo.
- [ ] `chisurf.core.models.pda2c.dynamic_mc.Pda2cDynamicNStateModel` — data/config/parameters/dependencies; fresh restore/edit/recompute/resave; GUI state; history undo/redo.
- [ ] `chisurf.core.models.pda2c.anisotropy.Pda2cAnisotropyModel` — data/config/parameters/dependencies; fresh restore/edit/recompute/resave; GUI state; history undo/redo.
- [ ] `chisurf.core.models.pda3c.pda3c.Pda3cModel` — data/config/parameters/dependencies; fresh restore/edit/recompute/resave; GUI state; history undo/redo.

## deer

- [ ] `chisurf.core.models.deer.deer.DeerGaussianModel` — data/config/parameters/dependencies; fresh restore/edit/recompute/resave; GUI state; history undo/redo.
- [ ] `chisurf.core.models.deer.deer.DeerRiceModel` — data/config/parameters/dependencies; fresh restore/edit/recompute/resave; GUI state; history undo/redo.
- [ ] `chisurf.core.models.deer.deer.DeerTikhonovModel` — data/config/parameters/dependencies; fresh restore/edit/recompute/resave; GUI state; history undo/redo.
- [ ] `chisurf.core.models.deer.deer.DeerMaxEntModel` — data/config/parameters/dependencies; fresh restore/edit/recompute/resave; GUI state; history undo/redo.

## fcs

- [ ] `chisurf.core.models.fcs.parse.ParseFCSModel` — data/config/parameters/dependencies; fresh restore/edit/recompute/resave; GUI state; history undo/redo.
- [ ] `chisurf.core.models.fcs.dye_shape.DyeShapeFCSModel` — data/config/parameters/dependencies; fresh restore/edit/recompute/resave; GUI state; history undo/redo.
- [ ] `chisurf.core.models.fcs.mdf.MdfFCSModel` — data/config/parameters/dependencies; fresh restore/edit/recompute/resave; GUI state; history undo/redo.
- [ ] `chisurf.core.models.fcs.general.GeneralFCSModel` — data/config/parameters/dependencies; fresh restore/edit/recompute/resave; GUI state; history undo/redo.
- [ ] `chisurf.core.models.fcs.kinetics.FCSKineticsModel` — data/config/parameters/dependencies; fresh restore/edit/recompute/resave; GUI state; history undo/redo.
- [ ] `chisurf.core.models.fcs.maxent_models.MaxEntFCSModel` — data/config/parameters/dependencies; fresh restore/edit/recompute/resave; GUI state; history undo/redo.
- [ ] `chisurf.core.models.fcs.maxent_models.MaxEntRHModel` — data/config/parameters/dependencies; fresh restore/edit/recompute/resave; GUI state; history undo/redo.

## pcf

- [ ] `chisurf.core.models.pcf.parse.ParsePCFModel` — data/config/parameters/dependencies; fresh restore/edit/recompute/resave; GUI state; history undo/redo.

## ics

- [ ] `chisurf.core.models.ics.ics.ImageCorrelationModel` — data/config/parameters/dependencies; fresh restore/edit/recompute/resave; GUI state; history undo/redo.
- [ ] `chisurf.core.models.ics.ics.IcsGaussian2DModel` — data/config/parameters/dependencies; fresh restore/edit/recompute/resave; GUI state; history undo/redo.

## mfd

- [ ] `chisurf.core.models.mfd.Mfd2DModel` — data/config/parameters/dependencies; fresh restore/edit/recompute/resave; GUI state; history undo/redo.

## pch

- [ ] `chisurf.core.models.pch.pch_model.PchMultiComponentModel` — data/config/parameters/dependencies; fresh restore/edit/recompute/resave; GUI state; history undo/redo.
- [ ] `chisurf.core.models.pch.fida_model.FidaModel` — data/config/parameters/dependencies; fresh restore/edit/recompute/resave; GUI state; history undo/redo.

## structure

- [ ] `chisurf.core.models.structure.proteinmc_model.ProteinMCModel` — data/config/parameters/dependencies; fresh restore/edit/recompute/resave; GUI state; history undo/redo.

## global

- [ ] `chisurf.core.models.global_model.globalfit.GlobalFitModel` — data/config/parameters/dependencies; fresh restore/edit/recompute/resave; GUI state; history undo/redo.
- [ ] `chisurf.core.models.parameter_transform.model.ParameterTransformModel` — data/config/parameters/dependencies; fresh restore/edit/recompute/resave; GUI state; history undo/redo.

## Common blocking gates

- [ ] Correct dataset subtype/dimensionality/auxiliary arrays for every configured reader output.
- [ ] Exact UID/native port and node identity across local/global/cross-fit dependencies.
- [ ] Shared source curves, mixture fit inputs, transformation inputs, structure resources and solver configuration.
- [ ] Canonical history cursor/checkpoints/branch semantics after fresh file and authenticated database reload.
- [ ] Restore/cancel/save/remote/presentation failure retains science, resources, history/cursor and all views.
- [ ] Actual edited model controls and plots after restore, not constructors alone.
- [ ] Independent specification then quality approval with exact per-model evidence.
