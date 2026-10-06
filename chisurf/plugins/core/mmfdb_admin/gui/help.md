# MMFDB Admin

Browse, edit, import and export the **Multiparametric Fluorescence Database**
(MMFDB): samples and their chemistry, experiments and their data, provenance,
users, curated spectra and the workflow records (studies, protocols, lifecycle,
calibrations, reagent lots, pipelines). MMFDB Admin is a client: every change is
made by the MMFDB server, which checks who you are and what you may do.

Theory and the full walk-through: [MMFDB Admin guide](docs/guides/102_mmfdb_admin.md).

## Signing in

The toolbar names the server (**Host** and **Port**, or a base URL for a
standalone server), the **User** and a **Password**. **Login** connects and signs
in: a session this ChiSurf process already holds is reused, an account that may
sign in without a password needs none, and otherwise the login dialog asks.
**...** opens that dialog directly (its *Advanced* fold changes user, host and
ports). **Logout** drops the session. The dot is green when connected, yellow
while connecting and red when not.

MMFDB Admin is for **administrators**. A user who is not one is signed in but
refused: the panels stay empty and the status bar says why. While no
administrator exists yet (a fresh database) anyone may administer it.

Passwords are never stored by MMFDB Admin.

## The rail

The left rail lists the panels, grouped as the database is: *Samples &
chemistry*, *Experiments & data*, *Provenance*, *Administration* and *Workflows &
QC*. Type in **Search...** to find one. **Back** and **Next** in the status bar
step through the rail. A panel loads when you first open it; **Refresh** reloads
the open one.

## Entity panels

Most panels are one table of the database (Samples, Experiments, Setups, Raw
Data, Users, ...). The **table** lists its records: click a row to open it in the
**form** below, click a header to sort, type in the filter box to keep the
matching rows, right-click the header to choose columns. Drag the bar between
table and form to share the space.

The form's fields come from the mmCIF dictionary (the FLR / PDBx categories), so
a field's tooltip is its dictionary definition. **An edit is saved when you
commit the field** (Enter, or a click elsewhere): there is no Save button, as in
the Qt tool. Read-only entities (raw data, products, analyses, objects, projects,
the setup's channels) show their fields read-only.

An **underlined** cell names another record (a sample's condition, an
experiment's setup): **double-click** it to open that record in its own panel.

**New** creates a record at once (an `untitled_N` id you then rename, or an id
the server assigns) and opens it. **Delete** deletes the **ticked** rows, after
asking.

Some entities have their own actions:

| Panel | Actions |
|---|---|
| Users | **Change password** (administrators need a medium-strength password and cannot be cleared), **Jump to branch** (start a branch at a recorded operation and make it the user's active branch) |
| Branches | **Set head** |
| Raw Data, Processed Products | **Copy ID**, **Reveal** (open the file or URL), **Use as provenance seed**, **Validate** (set the validation status), **Delete** (soft delete, asks) |
| Analyses | **Copy ID**, **Details** (parameters and input / output products), **Use as provenance seed** |
| Objects | **Copy UUID**, **Reveal** (a downloaded copy; the server path is never shown), **Delete object** (drops one reference while others remain) |

## The other panels

* **Overview** — the connection, the database's location, schema and counts, and
  samples without a description.
* **All items** — every record of every type; double-click a row to open it.
* **Measurements** — raw data, processing runs and processed products together.
* **Sample Metadata** — one sample's key / value / details rows. Pick a key from
  the mmCIF catalogue (type in the list to filter it) or type your own in the
  table; **Known values** offers values other samples use for the key.
  **Save all** writes the rows.
* **Spectra** — curate fluorophores, filters, dichroics, detectors and light
  sources: **Approve**, **Reject**, the **Review queue**, **AI triage**
  (deterministic checks), **Import ref. set**, **Find Duplicates** (merge
  near-duplicates into a primary). Tick rows to overlay their spectra.
* **Provenance Graph** — pick a seed (type and ID) and load its **upstream**,
  **downstream** or **full** graph; export it as JSON or a ZIP archive. *Use as
  provenance seed* on a record loads it here directly.
* **Import / Export** — import a PDBx / PDB-IHM / FLR CIF file, export the sample
  selected in Samples as FLR CIF (validated first), preview it, export the sample
  table.
* **eLabFTW** — connect to an eLabFTW notebook (the API key is kept in memory
  only), import ticked experiments, export ours.
* **Studies**, **Protocols**, **Lifecycle**, **Calibrations**, **Reagent Lots**,
  **Pipelines** — the workflow and QC records.

## Menus

**File**: Import, Export selected sample, Backup database, Reset (replaces the
user database with the curated source; a backup is written first and the
default administrator restored), Close. **Settings**: Reset window layout.
**Help**: this help, the guided tour, About.
