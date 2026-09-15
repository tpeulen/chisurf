"""Access to the machine-readable registry of tttrlib (and IMP.bff, and chisurf).

tttrlib publishes what it can do as JSON: which burst searches exist, which file
containers it reads, and for anything callable a JSON Schema of its parameters
with types, defaults, units and ranges (``tttrlib.registry()``, see
``include/Registry.h`` in tttrlib). Before that existed, chisurf hard-coded those
lists in several places and drifted out of step whenever tttrlib gained a feature.

This module is the single point where chisurf reads that registry, so nothing
else needs to know which tttrlib version is installed or what its accessor is
called. Two things follow from routing everything through here:

* **Generality.** The registry is not burst-specific. Any category tttrlib adds —
  file containers today, correlators or filters tomorrow — is reachable through
  the same functions, and :func:`entry_form_view` builds a Qt form for any of
  them without new code.
* **Version tolerance.** Older tttrlib builds published only burst searches,
  through a different accessor. :func:`categories` falls back to it, and returns
  an empty result rather than raising on a build with no registry at all, so
  chisurf degrades to its own implementations instead of failing to import.

The schema is standard JSON Schema rather than a bespoke format, which is what
lets :class:`~chisurf.core.dataspec.rpc.RpcMethodView` render it directly — see
:func:`entry_form_view`.
"""

from __future__ import annotations

import typing

import tttrlib

#: The registry category holding burst searches.
BURST_SEARCH = "burst_search"
#: The registry category holding readable/writable TTTR file containers.
FILE_CONTAINER = "file_container"
#: The registry category holding the MLE lifetime fit models (fit23/24/25/26).
FIT_MODEL = "fit"
#: The registry category holding the shared Fit2x construction inputs.
FIT_SETUP = "fit_setup"


def registry() -> typing.Dict[str, typing.Dict[str, typing.Any]]:
    """The whole registry as ``{category: {name: entry}}``.

    Not only tttrlib's any more: IMP.bff publishes its registry with the same
    mechanism, and chisurf registers what only it implements in the same shape,
    so this is :func:`chisurf.core.registry.catalog.registry` -- every function in
    this module (``entries``, ``describe``, ``defaults``, ``entry_form_view``) works
    for an entry from any of them.

    Returns an empty dict when no library publishes a registry, so callers can offer
    the registry-driven features when available and fall back otherwise.
    """
    from chisurf.core.registry import catalog
    return catalog.registry()


def categories() -> typing.List[str]:
    """Names of the available registry categories."""
    return sorted(registry())


def entries(category: str) -> typing.Dict[str, typing.Dict[str, typing.Any]]:
    """Every entry of ``category``, keyed by name.

    Returns an empty dict for a category this tttrlib does not publish, so a
    caller can test availability without catching.
    """
    return registry().get(category, {})


def describe(category: str, name: str) -> typing.Dict[str, typing.Any]:
    """One registry entry.

    Raises
    ------
    ValueError
        If the category or the entry is unknown, naming the alternatives.
    """
    available = registry()
    if category not in available:
        raise ValueError(
            f"unknown registry category {category!r}; available: {sorted(available)}"
        )
    if name not in available[category]:
        # Category names are snake_case identifiers; spell them out so the
        # message reads as prose rather than as a key.
        raise ValueError(
            f"unknown {category.replace(chr(95), chr(32))} {name!r}; "
            f"available: {sorted(available[category])}"
        )
    return available[category][name]


def is_available(category: str = BURST_SEARCH) -> bool:
    """Whether this tttrlib publishes ``category``."""
    return bool(entries(category))


def defaults(category: str, name: str) -> typing.Dict[str, typing.Any]:
    """Default parameters of an entry, as ``{name: value}``.

    Empty for an entry that describes something without parameters, such as a
    file container.
    """
    schema = describe(category, name).get("params_schema") or {}
    return {
        prop_name: prop["default"]
        for prop_name, prop in (schema.get("properties") or {}).items()
        if "default" in prop
    }


def entry_form_view(
    category: str,
    name: str,
    values: typing.Optional[typing.Mapping[str, typing.Any]] = None,
    on_change: typing.Optional[typing.Callable] = None,
):
    """An :class:`~chisurf.gui.autoform.AutoForm` model for one registry entry.

    The entry's ``params_schema`` is JSON Schema, and chisurf already renders
    JSON Schema, so the parameter widgets — labels, ranges, units, tooltips and
    defaults — are generated rather than authored, for any category. Usage::

        from chisurf.gui.autoform import AutoForm
        view = entry_form_view("burst_search", "maxtree")
        form = AutoForm(view)
        view.params()   # -> the edited parameter values

    Importing this pulls in Qt; the rest of this module does not.

    Raises
    ------
    ValueError
        If the entry is unknown, or describes nothing callable.
    """
    spec = describe(category, name)
    if not spec.get("params_schema"):
        raise ValueError(
            f"{category}/{name} publishes no parameters, so it has no form"
        )
    return GroupedEntryView(category, name, values=values, on_change=on_change)


#: Panel title used for properties a schema marks ``advanced``.
ADVANCED_GROUP = "Advanced"


def _group_sections(sections, properties, title, description):
    """Split one flat parameter list into foldable panels.

    A search with a dozen parameters is unreadable as a single column, and which
    parameters belong together is a property of the algorithm, not of the GUI —
    so the grouping is declared in the schema and read from here rather than
    written into chisurf per algorithm. A property may carry ``group: "Name"``,
    and ``advanced: true`` is shorthand for a group that starts folded.

    Properties with no group stay in the entry's own panel, so a schema that
    declares nothing renders exactly as it did before.

    Returns a tuple of :class:`PanelSection`, the entry's own panel first.
    """
    from chisurf.core.dataspec import PanelSection

    main, grouped = [], {}
    for section in sections:
        prop = properties.get(getattr(section, "attr", None) or "", {})
        name = prop.get("group") or (ADVANCED_GROUP if prop.get("advanced") else None)
        if name is None:
            main.append(section)
        else:
            grouped.setdefault(name, []).append(section)

    panels = [PanelSection(
        title=title, description=description, n_col=1, sections=tuple(main),
    )]
    # Advanced always sorts last: it is the panel a user should be able to
    # ignore, so it belongs at the bottom regardless of where the schema happened
    # to declare its first member.
    ordered = sorted(grouped, key=lambda n: (n == ADVANCED_GROUP, list(grouped).index(n)))
    for name in ordered:
        members = grouped[name]
        panels.append(PanelSection(
            title=name,
            n_col=1,
            # Advanced parameters are the ones a user should not have to see to
            # get a sensible result, so that panel starts folded.
            collapsed=(name == ADVANCED_GROUP),
            sections=tuple(members),
        ))
    return tuple(panels)


class GroupedEntryView:
    """A registry entry's form, with its parameters in foldable panels.

    Wraps :class:`~chisurf.core.dataspec.rpc.RpcMethodView` and regroups the
    sections it produced; the binding, value handling and JSON Schema support are
    unchanged, so this only affects layout.
    """

    def __init__(self, category, name, values=None, on_change=None):
        from chisurf.core.dataspec import ModelView
        from chisurf.core.dataspec.rpc import RpcMethodView

        spec = describe(category, name)
        self._inner_view = RpcMethodView(
            spec, values=values or None, on_change=on_change,
            title=spec.get("label", name),
        )
        panel = self._inner_view.view_spec().sections[0]
        self._view = ModelView(sections=_group_sections(
            panel.sections,
            (spec.get("params_schema") or {}).get("properties") or {},
            panel.title, panel.description,
        ))

    @property
    def _params_group(self):
        return self._inner_view._params_group

    def view_spec(self):
        return self._view

    def params(self):
        return self._inner_view.params()


def _linked_property(spec: typing.Mapping) -> typing.Optional[typing.Tuple[str, str, str]]:
    """Find a property whose schema is delegated to another registry entry.

    Returns ``(property_name, category, selector_property)`` for the first
    property carrying a ``parameters_of`` link, or ``None``. See the note on
    composite entries in tttrlib's ``include/Registry.h``.
    """
    properties = (spec.get("params_schema") or {}).get("properties") or {}
    for name, prop in properties.items():
        link = prop.get("parameters_of")
        if isinstance(link, typing.Mapping) and link.get("selector"):
            return name, link.get("category", BURST_SEARCH), link["selector"]
    return None


class CompositeEntryView:
    """Form model for an entry that delegates part of itself to another entry.

    The coincident burst search runs whichever search you name inside each
    detector group, so its ``parameters`` argument is *that* search's parameters.
    Rendered as a plain JSON Schema object it becomes a text box you type JSON
    into. This composes two forms instead: the entry's own parameters, and a
    nested panel built from the schema of the entry its selector currently names.

    Nothing here knows about burst searches specifically — the link is read from
    the schema — so any composite entry tttrlib adds later renders the same way.

    The nested schema depends on a value the user can change, so a caller must
    rebuild the form when :attr:`selector_value` changes; :meth:`should_rebuild`
    answers that. Values already entered for the outer parameters survive a
    rebuild because the caller passes them back in as ``values``.
    """

    def __init__(
        self,
        category: str,
        name: str,
        values: typing.Optional[typing.Mapping[str, typing.Any]] = None,
        on_change: typing.Optional[typing.Callable] = None,
    ):
        from chisurf.core.dataspec import ModelView, PanelSection
        from chisurf.core.dataspec.rpc import RpcMethodView
        import dataclasses

        spec = describe(category, name)
        link = _linked_property(spec)
        if link is None:
            raise ValueError(f"{category}/{name} has no delegated parameters")
        self._inner_name, self._inner_category, self._selector = link

        values = dict(values or {})
        inner_values = dict(values.pop(self._inner_name, None) or {})

        # Outer form: the entry's own schema minus the delegated property, which
        # the nested panel replaces.
        outer_spec = dict(spec)
        schema = dict(spec["params_schema"])
        schema["properties"] = {
            k: v for k, v in schema["properties"].items() if k != self._inner_name
        }
        schema["required"] = [
            r for r in schema.get("required", ()) if r != self._inner_name
        ]
        outer_spec["params_schema"] = schema
        self._outer = RpcMethodView(
            outer_spec, values=values or None, on_change=on_change,
            title=spec.get("label", name),
        )
        self._outer_properties = schema["properties"]

        inner_entry = entries(self._inner_category).get(self.selector_value)
        self._inner = None
        outer_panel = self._outer.view_spec().sections[0]
        sections = list(_group_sections(
            outer_panel.sections, self._outer_properties,
            outer_panel.title, outer_panel.description,
        ))
        if inner_entry is not None and inner_entry.get("params_schema"):
            self._inner = RpcMethodView(
                inner_entry, values=inner_values or None, on_change=on_change,
                title=inner_entry.get("label", self.selector_value),
            )
            # Sections bind through `target`, resolved with getattr on this
            # object; the inner sections are re-pointed at the inner group so the
            # two forms edit separate value dicts.
            inner_panel = self._inner.view_spec().sections[0]
            inner_props = (inner_entry.get("params_schema") or {}).get(
                "properties") or {}
            # Sections bind through `target`, resolved with getattr on this
            # object; the inner sections are re-pointed at the inner group so the
            # two forms edit separate value dicts. Grouping is applied after the
            # rebind so the nested parameters fold exactly like a top-level form.
            rebound = tuple(
                dataclasses.replace(child, target="_inner_group")
                for child in inner_panel.sections
            )
            for panel in _group_sections(
                rebound, inner_props,
                f"{inner_panel.title} parameters",
                inner_entry.get("summary", ""),
            ):
                sections.append(panel)
        self._view = ModelView(sections=tuple(sections))

    # AutoForm resolves section targets against this object.
    @property
    def _params_group(self):
        return self._outer._params_group

    @property
    def _inner_group(self):
        return self._inner._params_group if self._inner is not None else None

    @property
    def selector_value(self) -> str:
        """Current value of the property naming the inner entry."""
        return self._outer.params().get(self._selector, "")

    def should_rebuild(self, built_for: typing.Optional[str]) -> bool:
        """Whether the nested panel is stale for the current selector value."""
        return built_for != self.selector_value

    def view_spec(self):
        return self._view

    def params(self) -> typing.Dict[str, typing.Any]:
        """Outer parameters, with the nested form folded into the linked one."""
        out = self._outer.params()
        if self._inner is not None:
            out[self._inner_name] = self._inner.params()
        return out


def entry_form_view_auto(
    category: str,
    name: str,
    values: typing.Optional[typing.Mapping[str, typing.Any]] = None,
    on_change: typing.Optional[typing.Callable] = None,
):
    """A form model for any entry, nesting delegated parameters when present.

    Returns a :class:`CompositeEntryView` for entries that delegate part of their
    schema to another entry, and the plain :func:`entry_form_view` otherwise, so
    callers do not need to know which is which.
    """
    if _linked_property(describe(category, name)) is not None:
        return CompositeEntryView(category, name, values=values, on_change=on_change)
    return entry_form_view(category, name, values=values, on_change=on_change)
