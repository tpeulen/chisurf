# Project Browser

Projects store the current ChiSurf datasets, fitted models, instrument state and links as versioned MMFDB records.

Use **Refresh** to load the database. Search matches project names, IDs, owners and notes. **Show public** includes records shared with other authenticated users. Expand a project to inspect its versions. Click a project and **Open / Restore** for its newest version, or select an exact version. Double-clicking restores the same selection. Restoring replaces the current session, so save current work first.

**Save Current Project** creates a new project or another version of the current project. New projects need a name. Existing projects retain their name and parent version. Visibility and notes are recorded for the new version.

**Export .cs.pto** writes the selected exact version to a portable project archive. **Import Project** checks the archive before showing its contents and identifier collisions. Confirming import remaps conflicting IDs; cancelling the preview makes no database change.

**Delete Version** asks for confirmation and soft-deletes only the selected version. MMFDB enforces manage permission. Browse and restore are subject to read permission.

The row context menu provides restore, inspection, export and delete actions. **Inspect stored version** loads the stored artifacts, fit parameter values, branches and version ancestry into the detail tabs. Database and archive operations run in the background; errors appear in the project status line.
