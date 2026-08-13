# The UI data scheme: view specs and guided tours

Two of ChiSurf's file formats are written by hand, by everyone, in every plugin:

- the **view spec** (`*.view.json`) — a tool's panel, declared as data and built
  by AutoForm;
- the **guided tour** (`gui/guide.json`) — the steps that point at that panel's
  controls and wait for the user to press them.

Both are validated against a declared scheme, and a test asserts every shipped
file follows it.

## Why a scheme, when both already load

Because both loaders are forgiving in the same expensive way.
`chisurf.core.dataspec.load_view_spec` keeps only the keys its section
dataclasses declare and **silently drops the rest**; the tour loader returns an
empty tour rather than raising. So a misspelled key is not an error. It is a
control that never appears, or a step that points at nothing — found by a user,
months later, with nothing in a log to explain it.

Writing the scheme found nine such defects already shipped:

| What was written | What happened |
| --- | --- |
| `rebuild_on_change` on three `value` sections | dropped — only `choice` implements it, [deliberately](#rebuild-on-change) |
| `kind: "combo"` on a `choice` | dropped — the key is `style` |
| `kind: "path"` on two `value` sections | not an implemented kind, so both rendered as a plain string field with **no browse button** |
| `n_col` on an `info`, `key` on an `info`, `hide_label` on a `value` | dropped |
| `target.widget` on **nine tour steps** | the loader reads `target.name`; nine steps resolved to nothing and rendered as a centred bubble pointing at no control — in a guided tour |

None of them raised anything, anywhere.

## Where it lives

```text
chisurf/core/dataspec/schema.py             the generator + validators
chisurf/core/dataspec/schemas/view.schema.json    generated artifacts
chisurf/core/dataspec/schemas/guide.schema.json
test/test_ui_schemas.py                     every shipped file, validated
```

```python
from chisurf.core.dataspec.schema import validate_view_spec, validate_guide

problems = validate_view_spec(json.loads(path.read_text()))   # list[str], empty = fine
```

The messages name the path into the document — `sections/0/sections/2:
Additional properties are not allowed ('rebuild_on_change' was unexpected)` —
because "does not validate" tells a plugin author nothing about *where*.

## It is generated, not transcribed

`build_view_schema()` derives the scheme from `_SECTION_TYPES`: every registered
section type contributes one branch whose properties are exactly the fields its
dataclass declares. A field added to the loader is legal the moment it exists,
and a key the loader would drop is not. A transcription would be a second source
of truth that drifts; this one cannot.

The written `.schema.json` files are the artifacts editors and CI consume, and a
test fails when they no longer match the generator. Regenerate with:

```bash
python -m chisurf.core.dataspec.schema
```

The tour scheme is written out rather than derived, because the tour loader
reads a plain dict by hand instead of declaring dataclasses — there is nothing
to derive from. The test that walks all 38 shipped tours is what keeps it
honest.

## Strictness, and the two carve-outs

`additionalProperties` is **false** everywhere. That is the entire point:
permitting unknown keys would validate exactly the files that are broken. Two
exceptions are deliberate and named:

- `_comment`, at any level — the established convention for saying what a file
  is and what reads it. 99 of the 128 view specs carry one;
- `options` on a `custom` section — free-form by design, forwarded verbatim to a
  registered factory whose signature is Python, not JSON.

(#rebuild-on-change)=
## `rebuild_on_change` is a `choice` key on purpose

`ChoiceSection` explains it in its own docstring: a full rebuild is safe for a
discrete mode selector and not for a spin box or a slider, where it would fire
mid-drag. The three specs that set it on a count were asking for something the
framework declines to do, and the scheme now says so at the file rather than
leaving the key to be dropped in silence. If a count really must change which
parameters exist, `call` plus the host refresh is the mechanism.

## One dialect, two renderers

ChiMOL reads the same files. Its chrome is painted into the 3-D viewport rather
than built from Qt widgets — so the desktop app and the browser run one code
path — and a view spec becomes rows in the painted settings editor instead of
widgets:

```text
form chisurf/plugins/chimol/chimol/gui/appearance.view.json
```

That is an adapter (`chimol/renderer/ui/view_spec.py`), not a second renderer,
and the shared scheme is what keeps it one dialect: ChiMOL's own spec is
validated by the same test as every other, so it cannot quietly grow a
convenient spelling of its own. Sections a painted panel cannot draw — a
`parameter_group_table`, a `plot`, an embedded widget — are **reported** through
`unsupported_sections()` rather than dropped, because a form quietly missing
half its controls looks like a tool that has none.

Two top-level keys exist for that reader and are ignored by AutoForm: `title`
(the window's name) and `model` (which object the spec edits — ChiMOL
understands `settings` and `viewer`). They are in the scheme because a key one
reader honours and another ignores is still part of the format.
