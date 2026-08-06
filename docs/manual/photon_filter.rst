Photon filter
~~~~~~~~~~~~~

The photon filter in Step 2 selects which photons of the stream are carried forward; only the selected ones are correlated in the later steps. Photons can be selected by the detection channel, micro time ranges, and by applying count rate filters to the photon stream. Macro time differences between photons, the selection mask, intensity time-traces, and micro time histograms of all photons and selected photons are displayed in the photon filtering window (:strong:`Fig.28`).

:emphasis:`Channel & micro time selection.` The channel selection widget (:strong:`Fig.28, 2a`) is used to define selections based on the detector number of registered photons and to define micro time ranges. By default, all photons in the photon stream are selected. Specifying channel numbers restricts the selected photons to the specified channels. Channels are given as a list, and a micro-time range restricts the selection further — which is how a prompt or a delayed time window is cut out of a pulsed-interleaved measurement.

:emphasis:`Macro time interval.` The time between two consecutively registered photons can be used as a filter to select high count rate regions in a photon stream. Thresholds on minimum and maximum time between two consecutive photons are applied in the Macro time interval group (:strong:`Fig.28, 2b`). The selector in the macro time interval plot corresponds to the values set by the user in the "Macro time interval" group.

:emphasis:`Count rate filter.` For every photon, the photons falling within a time window around it are counted. If that count exceeds the threshold (maximum number of photons), the photon is rejected — which removes bright aggregates. Inverting the selection keeps those regions instead and discards the rest.

Tab.1. Photon filter and plotting parameters.

The photon filter creates a folder for the intermediate steps of the analysis pipeline, e.g., the generated 'sl5' folder contains compressed JSON file with the filter parameters and the photon selection mask.
