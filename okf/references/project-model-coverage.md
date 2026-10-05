# Scientific project/model acceptance matrix

**Status: REQUEST_CHANGES — October 4, 2026.** Every row below is required. Successful runtime class resolution is inventory evidence only; it is not roundtrip or scientific approval.

Catalogue: `chisurf/core/settings/experiment_configs.yaml`; actual import identities retained in `chisurf-all-models-inventory.json`. Counts: 11 experiment families, 42 configured model entries.

Acceptance for each checklist row requires the appropriate configured dataset/reader, edited nondefault state, exact parameter/native UID/bounds/fixed/error roles and dependency targets, prediction equality, editing/refitting after fresh restore, second save/reload, and actual GUI controls/capture when exposed. No skips, default-only/constructor-only coverage, summed overlapping counts, or inferred acceptance from a different alias.

## tcspc

- [ ] `tcspc-1` — **Lifetime**; configured `chisurf.core.models.description.tcspc_polarized`; runtime `chisurf.core.models.description.DescriptionModel_tcspc_polarized`. **UNVERIFIED**.
- [ ] `tcspc-2` — **Lifetime mixture**; configured `chisurf.core.models.description.tcspc_mixture`; runtime `chisurf.core.models.description.DescriptionModel_tcspc_mixture`. **UNVERIFIED**.
- [ ] `tcspc-3` — **FRET: Gaussian distances**; configured `chisurf.core.models.description.tcspc_fret_gaussian`; runtime `chisurf.core.models.description.DescriptionModel_tcspc_fret_gaussian`. **UNVERIFIED**.
- [ ] `tcspc-4` — **FRET: discrete distances**; configured `chisurf.core.models.description.tcspc_fret_discrete`; runtime `chisurf.core.models.description.DescriptionModel_tcspc_fret_discrete`. **UNVERIFIED**.
- [ ] `tcspc-5` — **FRET: worm-like chain**; configured `chisurf.core.models.description.tcspc_fret_worm_like_chain`; runtime `chisurf.core.models.description.DescriptionModel_tcspc_fret_worm_like_chain`. **UNVERIFIED**.
- [ ] `tcspc-6` — **FRET: self-avoiding chain (SAW-ν)**; configured `chisurf.core.models.description.tcspc_fret_saw_nu`; runtime `chisurf.core.models.description.DescriptionModel_tcspc_fret_saw_nu`. **UNVERIFIED**.
- [ ] `tcspc-7` — **FRET: Ising two-state chain**; configured `chisurf.core.models.description.tcspc_fret_ising_chain`; runtime `chisurf.core.models.description.DescriptionModel_tcspc_fret_ising_chain`. **UNVERIFIED**.
- [ ] `tcspc-8` — **PDDEM: partial donor-donor energy migration**; configured `chisurf.core.models.description.tcspc_pddem`; runtime `chisurf.core.models.description.DescriptionModel_tcspc_pddem`. **UNVERIFIED**.
- [ ] `tcspc-9` — **FRET: acceptor density (1, 2 or 3 dimensions)**; configured `chisurf.core.models.description.tcspc_fret_acceptor_density`; runtime `chisurf.core.models.description.DescriptionModel_tcspc_fret_acceptor_density`. **UNVERIFIED**.
- [ ] `tcspc-10` — **Parse-Model**; configured `chisurf.core.models.tcspc.parse.tcspc_parse.ParseDecayModel`; runtime `chisurf.core.models.tcspc.parse.tcspc_parse.EquationModel_parse`. **UNVERIFIED**.
- [ ] `tcspc-11` — **FRET: Structure fit**; configured `chisurf.core.models.tcspc.fret_structure.FRETStructure`; runtime `chisurf.core.models.tcspc.fret_structure.FRETStructure`. **UNVERIFIED**.
- [ ] `tcspc-12` — **Lifetime: MaxEnt**; configured `chisurf.core.models.description.tcspc_maxent_lifetime`; runtime `chisurf.core.models.description.DescriptionModel_tcspc_maxent_lifetime`. **UNVERIFIED**.
- [ ] `tcspc-13` — **FRET: MaxEnt distances**; configured `chisurf.core.models.description.tcspc_maxent_fret`; runtime `chisurf.core.models.description.DescriptionModel_tcspc_maxent_fret`. **UNVERIFIED**.

## stopped_flow

- [ ] `stopped_flow-1` — **Parse stopped-flow**; configured `chisurf.core.models.stopped_flow.parse.ParseStoppedFlowModel`; runtime `chisurf.core.models.stopped_flow.parse.EquationModel_stopped_flow`. **UNVERIFIED**.
- [ ] `stopped_flow-2` — **Reaction-System**; configured `chisurf.core.models.stopped_flow.reaction.ReactionModel`; runtime `chisurf.core.models.stopped_flow.reaction.ReactionModel`. **UNVERIFIED**.

## pda

- [ ] `pda-1` — **PDA2c-discrete**; configured `chisurf.core.models.pda2c.simple.Pda2cSimpleModel`; runtime `chisurf.core.models.pda2c.simple.Pda2cSimpleModel`. **UNVERIFIED**.
- [ ] `pda-2` — **PDA2c-Gaussian-distance**; configured `chisurf.core.models.pda2c.pdagauss.Pda2cGaussianDistanceModel`; runtime `chisurf.core.models.pda2c.pdagauss.Pda2cGaussianDistanceModel`. **UNVERIFIED**.
- [ ] `pda-3` — **PDA2c-SAW-ν-distance**; configured `chisurf.core.models.pda2c.saw_nu.Pda2cSawNuModel`; runtime `chisurf.core.models.pda2c.saw_nu.Pda2cSawNuModel`. **UNVERIFIED**.
- [ ] `pda-4` — **PDA2c-dynamic-2-state**; configured `chisurf.core.models.pda2c.dynamic.Pda2cDynamicTwoStateModel`; runtime `chisurf.core.models.pda2c.dynamic.Pda2cDynamicTwoStateModel`. **UNVERIFIED**.
- [ ] `pda-5` — **PDA2c-dynamic-N-state**; configured `chisurf.core.models.pda2c.dynamic_mc.Pda2cDynamicNStateModel`; runtime `chisurf.core.models.pda2c.dynamic_mc.Pda2cDynamicNStateModel`. **UNVERIFIED**.
- [ ] `pda-6` — **PDA2c-anisotropy**; configured `chisurf.core.models.pda2c.anisotropy.Pda2cAnisotropyModel`; runtime `chisurf.core.models.pda2c.anisotropy.Pda2cAnisotropyModel`. **UNVERIFIED**.
- [ ] `pda-7` — **PDA3c (three-colour)**; configured `chisurf.core.models.pda3c.pda3c.Pda3cModel`; runtime `chisurf.core.models.pda3c.pda3c.Pda3cModel`. **UNVERIFIED**.

## deer

- [ ] `deer-1` — **DEER Gaussian(s)**; configured `chisurf.core.models.deer.deer.DeerGaussianModel`; runtime `chisurf.core.models.deer.deer.DeerGaussianModel`. **UNVERIFIED**.
- [ ] `deer-2` — **DEER Rice**; configured `chisurf.core.models.deer.deer.DeerRiceModel`; runtime `chisurf.core.models.deer.deer.DeerRiceModel`. **UNVERIFIED**.
- [ ] `deer-3` — **DEER model-free (Tikhonov)**; configured `chisurf.core.models.deer.deer.DeerTikhonovModel`; runtime `chisurf.core.models.deer.deer.DeerTikhonovModel`. **UNVERIFIED**.
- [ ] `deer-4` — **DEER model-free (MaxEnt)**; configured `chisurf.core.models.deer.deer.DeerMaxEntModel`; runtime `chisurf.core.models.deer.deer.DeerMaxEntModel`. **UNVERIFIED**.

## fcs

- [ ] `fcs-1` — **Parse-Model**; configured `chisurf.core.models.fcs.parse.ParseFCSModel`; runtime `chisurf.core.models.fcs.parse.EquationModel_fcs`. **UNVERIFIED**.
- [ ] `fcs-2` — **FCS dye shape**; configured `chisurf.core.models.fcs.dye_shape.DyeShapeFCSModel`; runtime `chisurf.core.models.fcs.dye_shape.DyeShapeFCSModel`. **UNVERIFIED**.
- [ ] `fcs-3` — **FCS MDF (Gauss-Lorentz)**; configured `chisurf.core.models.fcs.mdf.MdfFCSModel`; runtime `chisurf.core.models.fcs.mdf.MdfFCSModel`. **UNVERIFIED**.
- [ ] `fcs-4` — **FCS (general: diffusion + bunching/anticorr)**; configured `chisurf.core.models.fcs.general.GeneralFCSModel`; runtime `chisurf.core.models.fcs.general.GeneralFCSModel`. **UNVERIFIED**.
- [ ] `fcs-5` — **FCS (kinetics)**; configured `chisurf.core.models.fcs.kinetics.FCSKineticsModel`; runtime `chisurf.core.models.fcs.kinetics.FCSKineticsModel`. **UNVERIFIED**.
- [ ] `fcs-6` — **FCS MaxEnt**; configured `chisurf.core.models.fcs.maxent_models.MaxEntFCSModel`; runtime `chisurf.core.models.fcs.maxent_models.MaxEntFCSModel`. **UNVERIFIED**.
- [ ] `fcs-7` — **FCS MaxEnt rH**; configured `chisurf.core.models.fcs.maxent_models.MaxEntRHModel`; runtime `chisurf.core.models.fcs.maxent_models.MaxEntRHModel`. **UNVERIFIED**.

## pcf

- [ ] `pcf-1` — **Parse-Model**; configured `chisurf.core.models.pcf.parse.ParsePCFModel`; runtime `chisurf.core.models.pcf.parse.EquationModel_pcf`. **UNVERIFIED**.

## ics

- [ ] `ics-1` — **Image correlation (RICS/STICS/TICS/iMSD)**; configured `chisurf.core.models.ics.ics.ImageCorrelationModel`; runtime `chisurf.core.models.ics.ics.EquationModel_ics`. **UNVERIFIED**.
- [ ] `ics-2` — **ICS 2D Gaussian (2 sigma + angle)**; configured `chisurf.core.models.ics.ics.IcsGaussian2DModel`; runtime `chisurf.core.models.ics.ics.EquationModel_ics`. **UNVERIFIED**.

## mfd

- [ ] `mfd-1` — **MFD 2D**; configured `chisurf.core.models.mfd.Mfd2DModel`; runtime `chisurf.core.models.mfd.two_dimensional.Mfd2DModel`. **UNVERIFIED**.

## pch

- [ ] `pch-1` — **PCH multi-component**; configured `chisurf.core.models.pch.pch_model.PchMultiComponentModel`; runtime `chisurf.core.models.pch.pch_model.PchMultiComponentModel`. **UNVERIFIED**.
- [ ] `pch-2` — **FIDA**; configured `chisurf.core.models.pch.fida_model.FidaModel`; runtime `chisurf.core.models.pch.fida_model.FidaModel`. **UNVERIFIED**.

## structure

- [ ] `structure-1` — **ProteinMC**; configured `chisurf.core.models.structure.proteinmc_model.ProteinMCModel`; runtime `chisurf.core.models.structure.proteinmc_model.ProteinMCModel`. **UNVERIFIED**.

## global

- [ ] `global-1` — **Global fit**; configured `chisurf.core.models.global_model.globalfit.GlobalFitModel`; runtime `chisurf.core.models.global_model.globalfit.GlobalFitModel`. **UNVERIFIED**.
- [ ] `global-2` — **Parameter Transform**; configured `chisurf.core.models.parameter_transform.model.ParameterTransformModel`; runtime `chisurf.core.models.parameter_transform.model.ParameterTransformModel`. **UNVERIFIED**.

## Cross-cutting gates

- [ ] Local/global/cross-fit parameter chains and separate model-input dependencies (mixtures/parameter transforms), including duplicate names, cycles/dangling references and source edits after reload.
- [ ] Full document-owned history cursor/baseline/redo/checkpoints/resources, fresh reopen after deleting original inputs, branch edits, and science/view rollback on failure.
- [ ] Main/macro/local/hybrid/server/proxy capture and ordinary Save retain all per-fit GUI model/plot state and typed history.
- [ ] File-only actual startup/science/history with MMFDB imports blocked; real configured authenticated MMFDB version/export/import readbacks.
- [ ] Independent specification PASS, then independent quality approval, then full integrated reruns.
