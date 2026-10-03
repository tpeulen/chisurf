# FCS channel definitions

Choose a saved detector setup. Its detector and excitation windows define the
logical channels offered as A and B. Pair identical channels for ACF or different
channels for CCF. Pair names must be unique because database child rows use them
as keys.

Add a pair, then select its row to rename it, change its channels, or remove it.
Bins and cascades are positive whole-number overrides; blank fields inherit the
global correlator settings. Fine can inherit the global setting, be On, or Off.

Save validates and persists the selected setup's preset. Apply also marks it as
active and calls the host's correlator callback when connected; otherwise tools
read the active preset when they reload. Delete preset removes only these FCS
definitions, never the underlying detector setup.

Public sharing can be changed only by the preset owner. Import JSON reads and
persists a library; Export JSON includes the current draft. The native host state
preserves selection, drafts and dock layout. Reload deliberately discards drafts
and rereads saved definitions. Close asks the native host to end this tool; host
state is separate from saved scientific definitions.
