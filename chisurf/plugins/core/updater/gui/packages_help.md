# ChiSurf Package Manager

Manage the packages, environments and channels of this ChiSurf installation with the same solver the updater uses
(micromamba, mamba or conda).

## Installed Packages

The packages of the current environment. **Filter** keeps the rows whose name contains the text. Select a row, then
**Update Selected** (no question), **Remove Selected** (asks first). **Update All** updates every package after a
question. **Refresh List** reloads the list.

## Search & Install

Type a package name and press Enter (or **Search**). The results list one row per version, newest first. Select a row and
press **Install Selected**; it asks first. Several rows cannot be selected at once; install them one after the other.

## Environments

The conda environments on this machine. **Create New** and **Clone Selected** ask for a name, **Remove Selected** asks
whether to delete. **Export to File** writes the selected (or the current) environment as YAML, **Import from File**
creates one from a YAML file (the name is optional).

## Channels

The channels packages are searched in. **Add Channel** asks for a name or URL; **Remove Selected** removes the selected one.

## The log

Every step with its time; an operation that fails also opens an error message.

## Further reading

- [Updating ChiSurf](docs/guides/90_updater.md)
