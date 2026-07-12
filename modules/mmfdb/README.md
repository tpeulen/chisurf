# MMFDB vendored package

MMFDB is the metadata/provenance database package used by ChiSurf.

The package is vendored here during prerelease extraction so ChiSurf can start
depending on `mmfdb` as a separate module before the code is moved to
`github.com/fluorescence-tools/mmfdb`.

Current state:

- Canonical source package: `modules/mmfdb/src/mmfdb`
- Target import for new code: `mmfdb`
- Runtime path/default-user configuration: `mmfdb.config`, with `MMFDB_*`
  environment variables for ChiSurf embedding and standalone tests.
- The package is host-neutral: code under `src/mmfdb` does not import `chisurf`.
- `import mmfdb` exposes a deliberately small API (`MFDatabase` and runtime
  configuration); domain, admin, and integration APIs use explicit submodules.
- Versioned API dispatch creates one request-scoped database/auth context rather
  than reopening and reauthenticating inside each function.
- ChiSurf callers use `mmfdb` directly; the former `chisurf.core.mmfdb` facade
  and its meta-path aliasing have been deleted.

This directory is intentionally package-shaped, not a documentation-only
placeholder.
