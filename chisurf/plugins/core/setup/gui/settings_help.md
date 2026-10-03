# ChiSurf Settings

This destination edits settings_chisurf.yaml, the file every ChiSurf tool reads its defaults from.

## Language

The language selector at the top stores gui.language and switches the native catalogue at once. Save keeps it for the next start.

## Typed fields

Every setting is a field of its stored type: a switch, a whole number, a decimal or text. Type in the search box to keep only the settings whose full name contains the text. A list or other structured value is edited as YAML text and must keep its type.

## Source

Edit source shows the complete YAML or JSON document. Validate checks the syntax without writing. Save replaces the file only when the document is valid; Reload discards unsaved edits; Save as writes a copy; Open file edits any other YAML or JSON configuration.

Saving the active settings file refreshes the in-memory settings. Components that read their settings at start-up pick the new value up when reopened.
