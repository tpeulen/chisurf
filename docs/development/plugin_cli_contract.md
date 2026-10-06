---
type: Guide
title: Plugin CLI discovery and invocation contract
description: Metadata-authoritative command discovery, import identity, invocation and failure contracts for plugin authors.
tags: [development, plugins, cli, testing]
---

# Plugin CLI discovery and invocation contract

`csc` discovers commands from metadata and imports a plugin only when its command is invoked. Top-level `csc --help` does not import `chisurf.plugins`, plugin initializers, Qt bindings, or `jsonschema`.

## Declare the command in its manifest

```json
{
  "id": "example_tool",
  "version": "1.0",
  "display_name": "Tools:Example",
  "entrypoints": {
    "cli": "example=chisurf.plugins.example_tool.cli:command"
  }
}
```

The public name is `example`, regardless of the Click object's implementation name. Without an explicit `alias=`, the public name is the manifest ID with underscores changed to hyphens. A target without `:attribute` uses the `cli` attribute in the production lazy CLI.

The shared manifest loader validates the complete consumed metadata, not just the CLI string. A **valid manifest is authoritative**: an absent or null `entrypoints.cli` means no command, even when `__init__.py` contains an older `cli_entrypoint` assignment. A missing or invalid manifest may fall back to literal legacy metadata; malformed metadata is diagnosed with its source path. Legacy fallback does not accept the invalid manifest's unchecked CLI string or ID.

## Import identity and collisions

The built-in root is searched before `~/.chisurf/plugins`, with stable lexicographic package order within each root. A shared `PackageResolver` checks Python's filesystem import precedence without executing loaders:

- A regular package can shadow a later package or an entire later subtree.
- Namespace parents can merge across roots; a later regular parent takes precedence over namespace portions.
- An unnamed or legacy package still owns its Python import identity.
- The first valid manifest ID owns that identity; a later package with the same ID is ignored even if it declares another alias.
- Existing command aliases remain owned by the first registered command.

Shadowed paths and duplicate IDs are reported with the selected and ignored sources. Hidden/cache/template descendants are excluded relative to the root; the hidden `.chisurf` ancestor does not hide legitimate user plugins. Fresh discovery invalidates Python finder caches so a newly installed package is visible even when filesystem timestamps are unchanged.

## Invocation semantics

Real Click commands and groups are invoked in a context replacing the lazy proxy, under its original parent. The root context object and nested `default_map` remain available, help/errors use the full public path, and Click context resources close after successful context creation, on return or invocation error.

Explicit plugin exit statuses are preserved: `ctx.exit(7)` produces status 7; option parsing errors produce status 2 without a second generic wrapper error. Returning an integer from a Click callback is not interpreted as an exit status. No arguments retain the existing behavior of requesting the plugin's help.

Plain callable/argparse entrypoints remain supported: their arguments are placed in `sys.argv`, whose values are restored in `finally`, including on exceptions. Duck-typed objects exposing `.main(args=..., prog_name=..., standalone_mode=True)` retain their compatibility path and explicit `SystemExit` status. Missing imports and non-callable targets produce actionable CLI errors.

## Limits

An existing Click parsing limitation remains: an eager option callback can register `call_on_close` before a later argument fails parsing, and that callback is not guaranteed to run when `make_context` raises. Avoid acquiring persistent resources in eager parsing callbacks; acquire them during invocation instead. This change does not claim a stronger parsing-failure cleanup guarantee than Click itself.

Metadata-only discovery is not a sandbox: invoked plugin code is trusted code. This does not hot-reload already imported modules or refresh commands in an already registered `csc` group. A fresh CLI process sees installation/removal changes. Registry dependency ordering and the production CLI's metadata iteration remain separate concerns; command-alias ties across different IDs are not unified by this change.

This contract is covered by `test/core/test_plugin_cli_robustness.py`, the shipped CLI declaration tests, metadata-reader tests and registry registration tests. See [the CLI architecture concept](../../okf/architecture/plugin-cli.md) for current evidence and the reproducible verification command.
