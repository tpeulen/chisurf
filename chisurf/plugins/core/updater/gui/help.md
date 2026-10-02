# ChiSurf Updater

Check whether a newer ChiSurf exists, read what changed, and install it.

## Checking

**Check for Updates** asks the update server which versions it offers, fills the **Available versions** list (newest
first) and says on the status line whether a version newer than yours exists. The check runs in the background; the
window stays usable. When the window opens it checks once by itself.

**Check for updates on startup** and **Ignore updates (do not prompt on startup)** control what ChiSurf does when it
*starts*: whether it looks at all, and whether it asks you about what it finds. Both are saved the moment you change
them. Opening this window yourself always checks.

**Development** is on and cannot be changed: ChiSurf has no stable release yet, so the changelog is read from the
development branch.

## The changelog

Picking a version shows the changes between the previous listed version and the picked one (the newest entry shows
the changes since the version before it; the oldest, those since the one you have). It is read from the project's commit
history on the development branch, merge commits left out.

## Updating

**Update Now** installs the selected version with the package manager (micromamba, mamba or conda, whichever the
status panel names). It asks first: the update **closes all ChiSurf windows** and continues in a separate window, so
unsaved work is lost, and you start ChiSurf again yourself once it has finished. Without a listed version the newest
package of the project's channels is installed.

## Package Manager

Opens the window for the packages, environments and channels of this installation.

## Further reading

- [Updating ChiSurf](docs/guides/90_updater.md)
