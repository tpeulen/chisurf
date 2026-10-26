# Burstwise → PTO

This tool imports legacy burstwise analysis folders into the project, as measurement containers
conformant to the flrCIF dictionary. Drop the folder on the ChiSurf window: the drop hands it to this
tool. After **Run**, each measurement's photon file is a photon stream of the Datasets workspace and
its burst runs are children of it; the containers are kept in the project (`.cs.pto`), not written
beside the legacy folder. The command line (`burstwise-import convert -o …`) still writes
containers to a folder of your choice.

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
To link the raw measurement with its burst tables, the importer matches each measurement stem to
its raw TTTR file (a measurement whose file is not found is not converted; the log says so):
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
- **Local root prefix** — typed: the local folder that replaces the `.mti` prefix.
