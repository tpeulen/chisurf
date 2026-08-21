---
type: Concept
title: Third-party modules, and what IMP's build does to them
description: How IMP.bff plugs in through the modules/bff symlink, the generated files that decide its test suite and standards checks, and the SWIG and cereal conventions a module must follow to behave like IMP core.
resource: /Users/tpeulen/dev/imp/modules/bff
tags: [modules, imp.bff, swig, cereal, tests, standards]
timestamp: '2026-08-10T00:00:00Z'
---

# How the module plugs in

`modules/bff` is a symlink to `../../imp.bff`, so IMP's build treats an external
checkout as an in-tree module. Everything below is a consequence of that: the
module gets IMP's generated build files, its generated tests, and its
conventions, whether or not its own repository expects them.

# Generated files a module does not own

Two categories, and confusing them wastes time.

**`test/Files.cmake` and `pyext/src/Files.cmake` are generated** by
`tools/build/setup_cmake.py` on every configure and are gitignored in imp.bff
(`*/Files.cmake`). Editing them does not stick. `test/Files.cmake` is built from
a **glob of every `.py` under `test/`**, and `imp_add_tests` turns each into a
ctest case — so a helper module, or a test parked in a `broken/` subdirectory,
still runs and still fails. The fix is at the file level: delete or move the
file. This is how `constants.py` (importing a class removed years ago) and
`broken/test_bff_Session.py` were counted as two failing tests.

**`test/<module>/medium_test_standards.py` is generated** by
`tools/build/setup.py` from a template, per module. It enforces IMP's naming and
API conventions on the module's Python surface: verbs from a fixed list,
lower_case_with_underscores, spelling against a dictionary, `show()` on value
classes. A module opts out of specific findings through
**`test/standards_exceptions`** — a Python file in the module source read by
`setup.py`, defining `function_name_exceptions`, `spelling_exceptions`,
`show_exceptions`, `class_name_exceptions`, `value_object_exceptions`,
`plural_exceptions`. `modules/kinematics` and `modules/rotamer` are the examples
to copy.

That mechanism is the right answer when the names are public API or are
SWIG-generated. For IMP.bff, 128 of 172 flagged names were STL container
boilerplate (`MapString*.begin`, `.has_key`, `.iteritems`, …) that cannot be
renamed at all.

# SWIG conventions

**Pickling comes from a macro, not from cereal alone.** Adding a `serialize()`
member makes a class archivable in C++; it does **not** make it picklable from
Python. That needs `IMP_SWIG_VALUE_SERIALIZE_IMPL(Namespace, Name)` (values) or
`IMP_SWIG_OBJECT_SERIALIZE(Namespace, Name, Plural)` (Objects), from
`modules/kernel/pyext/include/IMP_kernel.types.i`, placed in the module's `.i`
before the `%include` of the header. The value macro `%extend`s the class with
`_get_as_binary`/`_set_from_binary` and the `__getstate__`/`__setstate__` pair;
`__setstate__` calls `self.__init__()`, so the class must be default
constructible from Python.

**A module that vendors `numpy.i` owns that copy's compatibility.** SWIG 4.3
added a third `is_void` argument to `SWIG_Python_AppendOutput`; a vendored
`numpy.i` predating it will not compile. The subtlety is in the *value*: pre-4.3
replaced a `Py_None` result with the first appended output unconditionally, so
the faithful translation is `is_void=1`. With `0`, every argout-array wrapper on
a `void` C++ function silently returns `[None, array]` instead of the array —
it compiles, and the breakage only shows at the call site.

**Two overloads that reduce to the same Python signature: the first wins.**
`PathMap::get_tile_values` has a `std::vector<float>` overload and a
`(float **output, int *nx, int *ny, int *nz, …)` numpy one. The output arguments
are consumed by typemaps, so both present as `(value_type, bounds,
feature_name)` to Python; the module `%ignore`s the vector one so the array
version is the one wrapped.

# Wrapping numpy arrays: use the stock suites, never a hand-written typemap

A kernel that takes or returns numpy arrays should expose a C++ signature that
matches one of the suites in the vendored `pyext/numpy.i` — `IN_ARRAY2/3`,
`ARGOUTVIEWM_ARRAY2/3`, and friends — bound with `%apply(...)`, never a custom
`%typemap(in, ...)`. Learned from `IMP_bff.avdistance.i` on 2026-08-21:

* **A hand-written `%typemap(in)` on a multi-arg group breaks in three ways.**
  `PyArray_SIZE($input)` fails because `$input` is a `PyObject *`, not a
  `PyArrayObject *`, so the `PyArray_DIMS`/`PyArray_NDIM` macros inside it have
  no viable call — you must cast. The dims are by-value `int` parameters, so
  `$2 = &local` assigns an `int *` to an `int`. And the lifetime of any
  converted array is yours to free, which the stock `freearg` suite does for
  you. All three were hit in one afternoon; each cost a build cycle.
* **When no stock suite matches, reshape the C++ signature, not the binding.**
  `random_distances` took what the old Python `.ravel()`'d — which admitted the
  empty 1-D `np.zeros(0)` as an input. The clean contract is a `(n, 4)` point
  cloud, which is exactly `IN_ARRAY2`; the empty cloud is then `np.zeros((0,4))`,
  and the test that passed a 1-D empty array was updated to the 2-D shape. The
  rule that fell out of the port: **state the shape once, on the kernel; if a
  Python caller's ravel/reshape disagrees with it, fix the caller, not the
  typemap.**
* **The stock suite only works when the header's dim parameters come after the
  pointer, in the order `(DATA_TYPE* ptr, DIM_TYPE dim1, DIM_TYPE dim2, ...)`.**
  numpy.i also has the reversed order `(DIM1, DIM2, ptr)`; both exist because
  IMP headers historically used both. Pick the matching one — do not reorder a
  signature mid-contract to force a suite.

# cereal conventions

IMP core's pattern is `friend class cereal::access;` plus a
`template<class Archive> void serialize(Archive &ar)`, with
`IMP_OBJECT_SERIALIZE_DECL(Name)` in the header and
`IMP_OBJECT_SERIALIZE_IMPL(Full::Name)` in the `.cpp` for `IMP::Object`
subclasses — which also require a **default constructor**, because the
generated `load_cereal` does `new Name()`.

Three things a module has to get right, all learned from IMP.bff:

1. **A class whose base already has `serialize()` must supply `serialize()`,
   not a `save`/`load` pair.** cereal counts candidate functions and rejects a
   type offering two. Where the load path genuinely differs from the save path,
   branch inside the single function on
   `std::is_base_of<cereal::detail::InputArchiveBase, Archive>::value` —
   `modules/kernel/include/internal/ListLikeContainer.h` does exactly this.
2. **Pointers that are views, not state, must be rebuilt rather than
   archived.** A decorator handle is a view onto a model-owned particle: store
   the `ParticleIndex` and re-decorate on load. A non-owning pointer to a
   caller's object would otherwise be deep-copied, silently transferring
   ownership. An intra-container back-pointer (a path-search `previous`) should
   be cleared and recomputed.
3. **A base without `serialize()` blocks the whole subtree.**
   `IMP::em::SampledDensityMap` has none, so `IMP.bff.PathMap` cannot be
   serialized however its own members are written — `IMP::em::DensityMap`, one
   level further up, does have one.

# Deprecating part of a module

`IMPBFF_DEPRECATED_HEADER(version, "message")` inside the namespace block emits
a compile-time `#pragma message` for anything including that header; the
`*_VALUE_DECL` / `*_OBJECT_DECL` variants attach the deprecated attribute to a
class, and the `*_DEF` variants add a runtime warning from a constructor. The
macros are generated per module into `<module>_config.h`. IMP.bff's eleven
`Decay*` headers carry the header form at 2.25 — that functionality now lives in
tttrlib, and the module keeps only the structure-related classes.
