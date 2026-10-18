# Burstwise → PTO

This tool imports legacy burstwise analysis folders into standardized
`.mmfdb.pto` containers conformant to the flrCIF dictionary.

## Legacy folder structure
The importer recognizes the multi-file legacy burst analysis format:
- `bi4_bur/*.bur` or `bur/*.bur` — primary burst summary tables.
- `bg4/*.bg4` and `br4/*.br4` — MLE lifetime and fluorescence companions.
- `bv4/*.bv4` — BVA burst variance tables.
- `2c4/*.2c4` — 2CDE kernel-density burst tables.
- `BIDs/*.bst` — burst photon start/stop indices.
- `Info/*info.txt` — acquisition and analysis settings.
- `*.mti` — original TTTR file paths and durations.

## Source TTTR Resolution
To pack the raw measurement along with the burst tables into `.mmfdb.pto`,
the importer matches each measurement stem to its raw TTTR file:
1. **Resolve via .mti prefix mapping** — rewrites original paths recorded in the
   `.mti` (e.g. `N:\Data\...`) by substituting the old drive or server prefix with
   your local directory path.
2. **Stems beside folder** — finds matching instrument files (`<stem>.ht3`,
   `<stem>.spc`, `<stem>.ptu`, etc.) located beside the burstwise folder.

## Options
- **Dry run** — inspects the tables, tests source resolution, and reports what
  containers would be created without writing any files to disk.
- **Report unmapped columns** — flags any legacy table columns that do not have
  an exact or normalized match in the `mmfdb_workflow_ext.dic` dictionary.
- **Output directory** — destination for generated `.mmfdb.pto` containers
  (default: parent directory beside the burstwise folder).
