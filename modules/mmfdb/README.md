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

## Standalone service (Docker Compose)

From the repository root, start a persistent local MMFDB instance with:

```bash
docker compose -f docker-compose.mmfdb.yml up --build -d
curl http://127.0.0.1:8080/healthz
```

The local prerelease profile is deliberately bound to loopback and bootstraps
the requested default login `admin` / `admin`. Change it without editing YAML:

```bash
MMFDB_ADMIN_PASSWORD='Replace-this1!' \
  docker compose -f docker-compose.mmfdb.yml up --build -d
```

Bootstrap is one-shot: after an active administrator exists, restarts preserve
its current password and ignore the bootstrap secret. To apply a changed
bootstrap password, start with a genuinely new data volume. Do not expose the
local `admin` / `admin` profile on a public interface.

The service provides:

- browser administration at `http://127.0.0.1:8080/login`;
- JSON-RPC at `http://127.0.0.1:8080/rpc`;
- health/readiness at `http://127.0.0.1:8080/healthz`;
- persistent SQLite and object data in the `mmfdb-data` volume.

The image runs as a non-root user with a read-only root filesystem in Compose.
Its build context is `modules/mmfdb`, so the root `.dockerignore` cannot discard
MMFDB's required JSON package data. The base image digest and production runtime
dependencies are pinned in `Dockerfile` and `docker-constraints.txt`; update them
together and verify a clean multi-architecture build.

## YAML configuration

[`mmfdb.example.yaml`](mmfdb.example.yaml) is the generic standalone template;
[`mmfdb.compose.yaml`](mmfdb.compose.yaml) is the explicitly local-only profile.
Validate or initialize a configuration without Docker:

```bash
export MMFDB_ADMIN_PASSWORD='Replace-this1!'
mmfdb check-config --config mmfdb.example.yaml
mmfdb init --config mmfdb.example.yaml
mmfdb serve --config mmfdb.example.yaml
```

Configuration version 1 has these top-level sections:

- `mode`: `embedded` or `standalone`; standalone is additive and does not remove
  MMFDB's in-process use by ChiSurf;
- `server`: HTTP bind host and port;
- `database`: exactly one of a SQLite `path` or server `url`;
- `object_store`: local root or S3-compatible target;
- `auth`: local or LDAP provider settings;
- `admin`: first-admin bootstrap user/password and the explicit weak-password
  development gate;
- `client`: `embedded`/`remote` mode, base URL, and username hints reusable by
  ChiSurf. Client passwords are intentionally not persisted. Client processes
  use `mmfdb.load_client_config`, which does not resolve unrelated server-side
  admin, LDAP, database, or object-store secrets.

Relative database/object paths resolve relative to the YAML file. Unknown keys,
invalid ports, conflicting database targets, missing environment variables, and
weak bootstrap passwords fail closed. String values support `${NAME}` and
`${NAME:-local-default}` interpolation. Prefer `${NAME}` for secrets so generic
deployment files do not store credentials.

Remote client URLs must use HTTPS unless the host is loopback. Plain HTTP on an
isolated development network requires `client.allow_insecure_http: true`;
embedded credentials, query strings, and fragments are never accepted in the
base URL.

The YAML password is only a first-admin bootstrap input. It is excluded from
configuration object representations, never emitted by CLI JSON, and never
resets an established administrator on restart.

## Object storage

MMFDB defaults to its atomic local content-addressed store under
`$MMFDB_SETTINGS_DIR/objects`. An S3-compatible backend can be selected without
changing repository/API callers:

```text
MMFDB_OBJECT_STORE_BACKEND=s3
MMFDB_S3_BUCKET=research-data
MMFDB_S3_PREFIX=mmfdb/blobs                 # optional
MMFDB_S3_ENDPOINT_URL=https://minio.example # optional for AWS S3
MMFDB_S3_REGION=eu-central-1                # optional
```

The S3 backend uses conditional create, streams payloads, verifies every object
against both its content address and SHA-256 metadata, and materializes remote
objects through an atomic verified local cache. It imports `boto3` only when S3
is selected; deployments enabling S3 must provide `boto3` in their runtime.
Uploads currently use S3's conditional single-object operation and therefore
reject payloads larger than 5 GiB with an explicit error; multipart publishing
must be added before MMFDB is used for larger individual files.

MMFDB deliberately has no access-key or secret-key setting. Credentials are
resolved by boto3's standard AWS provider chain (environment variables, shared
AWS config, web identity, workload/container identity, or instance role), so
secrets are never serialized into MMFDB runtime configuration or database rows.

## SQL database targets

Local SQLite remains the zero-configuration backend. Set
`MMFDB_DATABASE_URL` (or `configure_runtime(database_url=...)`) to select a
server database explicitly:

```text
MMFDB_DATABASE_URL=postgresql://user:password@db.example.org/mmfdb
```

Install `mmfdb[postgres]` for SQLAlchemy and the Psycopg driver. MMFDB never
interprets an unknown or malformed URL as a local filename, and credentials are
redacted from backend diagnostics.

PostgreSQL runtime connectivity supports parameterized repository queries,
mapping rows, nested savepoint transactions, schema-version validation, and
dictionary DAO introspection. The server must currently be provisioned at the
package's exact schema version by the deployment system. Automatic fresh-schema
bootstrap, historical migrations, SQLite PRAGMAs, and SQLite online backups are
intentionally rejected with `DatabaseCapabilityError`; use native PostgreSQL
migration and backup tooling. This is an explicit prerelease boundary, not a
claim that SQLite DDL is portable.
