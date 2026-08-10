# Subsystems

* [Core](core.md) - Domain objects, fitting, data, models, math, settings, actions, and the API facade.
* [Data model](data-model.md) - `Base`/`Data`/`DataCurve`, data groups, experiment readers, and dataset flow.
* [Data IO](data-io.md) - File loading, TTTR/photon readers, format registry, and slow-storage staging.
* [Image IO](image-io.md) - The one seam for reading and writing image files, and the axis labels that say whether a stack's pages are frames or colours.
* [Burst companion files](burst-companions.md) - The one contract every burst-analysis plugin follows when writing results beside the bursts, so a folder merges into one table without misaligning.
* [Fluorescence domain](fluorescence-domain.md) - Shared fluorescence math and algorithms used by models and plugins.
* [Fitting engine](fitting.md) - Fit/FitGroup, weighted residuals, global analysis, error analysis, and sampling.
* [Hidden Markov models](hidden-markov-models.md) - The in-tree Gaussian HMM (fused compiled E-step, data-driven initialisation, SQUAREM acceleration) and the shared analysis seam every state-reporting tool calls.
* [Machine learning estimators](machine-learning.md) - chisurf.core.ml: the in-tree GaussianMixture/KMeans/HDBSCAN/PCA/StandardScaler/MLPRegressor, and the compiled k-d tree and Borůvka MST the density clustering runs on.
* [Fitting models](models.md) - TCSPC/FCS/PDA/PCH/DEER/RICS/structure models and data-described editors.
* [MLE lifetime fitting (fit2x)](mle-lifetime-fitting.md) - The tttrlib Fit23/24/25/26 Poisson-MLE engine and the dt/period/background/gamma input contract shared by burst and imaging fits.
* [Parameters](parameters.md) - Scalar parameters, bounds, links, dependency graph, and fit degrees of freedom.
* [Graph layer (chinet.graph)](graph.md) - In-tree graph containers, algorithms, layouts and GraphML I/O shared by the factor graph, the node editor and the global-parameter view.
* [GUI & AutoForm](gui-autoform.md) - The Qt application and the data-driven AutoForm UI framework.
* [Columnar store](columnar-store.md) - The typed, masked, dictionary-encoded table container underneath ChiSurf's tables, and the seam that converts to and from a data frame without pretending the two mean the same thing by "missing".
* [Plotting (chiplot)](chiplot.md) - The single renderer-neutral 2-D plotting API every call site draws through, its backend contract, and the guard that keeps the rendering library behind it.
* [Tables (chitable)](gui-tables.md) - The shared model/view table family: sources, vectorised filtering, value colouring, column hiding and export.
* [Game engine (chigame)](chigame.md) - The shared 2-D game engine on WebGPU: scene, orthographic camera, instanced sprite/SDF batcher, a nine-action abstract controller, synthesised audio, and the AssetPack seam that makes the whole look and soundtrack swappable.
* [Toolbar action vocabulary](gui-action-vocabulary.md) - One icon, colour, tooltip and position per semantic action, including the run/restart/pause/stop transport controls.
* [Help buttons and guided tours](gui-help-and-guides.md) - The `?` and **Guide** pair every modern plugin carries, the one mixin that attaches them to any tool, and the shrinking allow-list that enforces it.
* [The documentation browser](documentation-browser.md) - The in-application help window: a tree read from the documentation's own toctrees, ranked full-text search, and a renderer that typesets the formulas and resolves the cross-references instead of showing their markup.
* [Internationalisation](i18n.md) - The Qt-free translation seam, QTranslator bootstrap, string-extraction kit, and view.json/manifest/.ui localization.
* [Retiring numba](numba-retirement.md) - Why numba is leaving the shipped package, the five routes a kernel can take out of it, the profile that shows it is already off the fitting hot path, and the shrinking allow-list that tracks the work.
* [Operation history](history.md) - Append-only action history, headless replay, and MMFDB event-log projection.
* [Macros, CLI & scripting](macros-cli.md) - Macros, `csc`, GUI scripts, and the in-tree chinsole console.
* [LLM agent](llm-agent.md) - The plain-language assistant: described, safety-tiered tools, the observe-act loop, and its head-less CLI.
* [Project persistence](project-persistence.md) - `.csp` archive format, UID-keyed project state, and UI-state capture.
* [Regions of interest](roi.md) - One ROI geometry for gating and imaging alike: point membership plus pixel rasterisation, boolean composition, JSON persistence, and the segmentation bridge.
* [Pipelines](pipeline.md) - Typed DAGs of transformer invocations persisted and replayed through MMFDB provenance.
* [Compiled Modules](compiled-modules.md) - The C++ extensions in `modules/` that must be built before tests.
* [The photon container](photon-container.md) - One measurement as one `.pto`: the instrument file verbatim and immutable, results as artifacts beside it, provenance from the mmCIF dictionaries.
* [IMP module conventions](imp-module-conventions.md) — how an out-of-tree module (IMP.bff) plugs into IMP's build, the generated files it does not own, and the SWIG/cereal/deprecation conventions it must follow.
