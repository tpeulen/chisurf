---
type: PRD
prd: "95"
title: "PRD-95: One serialization story — cereal aligned with IMP, and JSON a human can read"
description: imp.bff's cereal coverage is real but unnamed — zero CEREAL_NVP in the tree, so a JSON archive would emit value0/value1 keys — and IMP's own pickle registry is hard-wired to binary archives. Name every field (free for the binary format), add a per-class JSON surface next to _get_as_binary, and draw the line between object-state JSON (cereal) and interchange JSON (fps.json stays nlohmann).
status: proposed
resource: /Users/tpeulen/dev/imp.bff
tags: [prd, imp.bff, cereal, serialization, json, pickle, swig]
timestamp: '2026-08-10T00:00:00Z'
---

# PRD-95: One serialization story — cereal aligned with IMP, and JSON a human can read

## What exists (measured 2026-08-10)

The cereal port is further along than folklore says, and the conventions are
already written down in
[imp-module-conventions](../subsystems/imp-module-conventions.md):

- Nine headers carry archive-agnostic serialization: single `serialize()` on
  `AVPairDistanceMeasurement`, `PathMapHeader`, `PathMapTileEdge`,
  `AVNetworkRestraint` (branching correctly inside one function because
  `IMP::Restraint` supplies one), and a legitimate `save`/`load` pair on
  `PathMapTile` (standalone class; `load` clears the transient `previous`
  pointer that path search rebuilds).
- The SWIG pickle macros are in place: `IMP_SWIG_OBJECT_SERIALIZE` for
  `AVNetworkRestraint`, `IMP_SWIG_VALUE_SERIALIZE_IMPL` for
  `AVPairDistanceMeasurement`, `PathMapHeader`, `PathMapTile`,
  `PathMapTileEdge`. `AV` itself is a decorator — its state is Model
  attributes, pickled with the Model, and that is correct.
- `AVNetworkRestraint` is the module's only `IMP_OBJECT_SERIALIZE_DECL`.

Three hard facts shape what "support JSON" can mean:

1. **Not one field is named.** `grep -rn "CEREAL_NVP|make_nvp"` over
   `include/` and `src/` returns **zero**. Instantiating
   `cereal::JSONOutputArchive` today compiles and round-trips, but emits
   `"value0": …, "value1": …` — machine-valid, humanly useless, and silently
   coupled to member *order*.
2. **IMP's polymorphic registry is binary-only by construction.**
   `IMP_OBJECT_SERIALIZE_DECL` hard-codes `cereal::BinaryOutputArchive` /
   `BinaryInputArchive` (`kernel/include/object_macros.h:98-107`), and the
   Python `_get_as_binary`/`__getstate__` surface in
   `IMP_kernel.types.i:770-841` is binary throughout. JSON through the
   Object-pointer registry is not on the table without patching IMP; JSON is
   **per-class direct archiving**, which the templated `serialize()`
   functions already permit.
3. **The JSON archive is already shipped.** The `arm64` env's cereal has
   `archives/{binary,portable_binary,json,xml}.hpp` — no new dependency.
   (Note in passing: IMP picked `binary`, not `portable_binary`, so pickles
   are endianness-bound; JSON becomes the *portable* representation for
   free.)

And one line that must be drawn: **there are two JSONs here and they must not
merge.** `fps.json` is an *interchange format* with frozen keys
(`Positions`, `Distances`, `χ²` — never renamed, per
[modelling](/plugins/modelling.md) and PRD-58), read by
`FPSReaderWriter`/`AVNetworkRestraint` through the vendored nlohmann
(`internal/json.h`). Cereal-JSON is *object state* — whatever `serialize()`
says, keyed by member names. This PRD adds the second and does not touch the
first. The `Decay*` headers are deprecated at 2.25 (the functionality lives
in tttrlib) and are out of scope entirely.

### Why nlohmann is not replaced by cereal (challenged, answered from the code)

cereal is a *serializer*: the structure is declared at compile time by your
types, and the archive walks it. nlohmann is a *DOM*: the structure is
discovered at runtime from the document. `fps.json` needs the DOM, and the
proof is four specific operations `FPSReaderWriter` performs today
(`src/FPSReaderWriter.cpp`):

1. **Path navigation with a runtime segment** —
   `fps_json_["χ²"][score_set_]["distances"]` (line 42), where `score_set_`
   is a constructor argument. An archive has no random access by
   runtime-chosen key.
2. **Iteration over dynamic keys** — the distance and position names are
   user-invented labels; `for key in distances` (line 51) walks keys no C++
   type declares.
3. **Optional fields with defaults** — `distance.value("Forster_radius",
   52.0)` (lines 54–61), and the whole of `AV::set_av_parameter`
   (`AV.cpp:203-215`) is `.value(key, default)` per field. cereal *throws*
   on a missing NVP; there is no value-or-default. Files come from FPS,
   OLGA and chisurf, and tolerance is the contract.
4. **Subtree extraction of unmodeled content** — `get_used_positions()`
   copies `fps_json_["Positions"][name]` fragments (line 81) the class never
   models. An archive can only read what the types declare; "whatever else
   was in the file" is unrepresentable.

Two more facts close the question. cereal's JSON encoding of `std::map` is
an **array of key/value pairs**, not a `{name: {…}}` object — the FPS wire
format does not match cereal's own representation, so even the modeled parts
would need hand-rolled `getNodeName()` loops against `cereal::rapidjson`,
an internal namespace that is not public API. And replacing nlohmann does
not remove a JSON parser from the build: **cereal vendors rapidjson
internally** — the trade is a 20,891-line DOM used directly for a different
vendored DOM reachable only through cereal's implementation details. The
reverse replacement (nlohmann-based object state, drop cereal-JSON) is also
wrong: pickle rides cereal-binary through IMP's macros, and IMP alignment
is the point of this PRD. Where structure is ours, cereal; where the
document is theirs, nlohmann — and after the `Decay*` retirement, nlohmann's
reach shrinks to the two fps.json-facing files.

## Requirements

1. **Name every field.** Every `serialize()`/`save`/`load` wraps each member
   in `cereal::make_nvp("name", member)`, name = member sans trailing
   underscore. Binary archives *ignore* names, so this is **bit-free for the
   existing pickle format** — and acceptance criterion 1 holds the project to
   that.
2. **A JSON surface beside the binary one, same shape.** Mirror the kernel's
   `_get_as_binary`/`_set_from_binary` pattern with an `%extend` macro in
   `BFF.types.i`: `_get_as_json()` → `std::string` via `JSONOutputArchive`,
   `_set_from_json(str)` via `JSONInputArchive`, applied to every class that
   has the pickle macros today. C++ side gets the same as two small free
   templates in one header (`bff/json_archive.h`) — no per-class code.
3. **Finish the alignment sweep.** Rides on PRD-93 stage 1 (the four
   structure value-classes get real `IMP_SWIG_VALUE` declarations): any
   value class with `serialize()` but no `IMP_SWIG_VALUE_SERIALIZE_IMPL`
   gets one; any `save`/`load` pair on a class whose base grows a
   `serialize()` collapses to the single function (rule 1 of the
   conventions page).
4. **`PathMap` stays honestly blocked, and the block is named.**
   `IMP::em::SampledDensityMap` has no `serialize()` (conventions note 3),
   so `PathMap` cannot archive through its base however its own members are
   written. The unblock is an upstream PR to IMP (golden rule: never a
   commit in the checkout) — filed as its own task, not smuggled in here.
   JSON for a whole density grid is out of scope regardless; a grid in JSON
   is a mistake, not a feature.
5. **Names become API.** A committed golden `.json` per class in
   `imp.bff/test/`; the round-trip test diffs against it so a member rename
   that silently changes the schema fails a test instead of a user.

## Acceptance criteria

1. A pickle written *before* the NVP sweep loads *after* it, for every class
   with the pickle macros — the binary format did not move.
2. For each such class: construct → `_get_as_json` → `_set_from_json` on a
   fresh instance → `_get_as_binary` equal to the original's. JSON and
   binary agree on what the state is.
3. The JSON of a `PathMapHeader` read aloud names every parameter
   (`grid_spacing`, `max_path_length`, …) — no `value0` anywhere in any
   golden file.
4. `fps.json` files and their reader are byte-for-byte untouched by this
   PRD.
5. The conventions page gains the JSON section — the pattern, the two-JSONs
   rule, and the binary-archives-ignore-names fact — so the next module gets
   it right without rediscovery.
