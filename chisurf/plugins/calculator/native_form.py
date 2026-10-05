"""Small spec-backed controls used by native calculator ports."""

import html
import re

from emtk import im

from .inputs import bounded_float, bounded_int


def plain(text):
    return html.unescape(re.sub("<[^>]*>", " ", str(text)))


def resolve(model, path):
    for name in path.split("."):
        model = getattr(model, name)
    return model


def fields(model, sections, changed=lambda: None, item_rects=None, on_used=None):
    for section in sections:
        kind = section.get("type")
        if kind in ("panel", "dock_area"):
            title = section.get("title", "")
            expanded = True
            if title:
                flags = 0 if section.get("collapsed", False) else im.TreeNodeFlags.DEFAULT_OPEN
                expanded = im.collapsing_header(title, flags)
                im.set_item_tooltip(
                    plain(section.get("description") or f"Expand or collapse {title}.")
                )
            if expanded:
                fields(model, section.get("sections", []), changed, item_rects, on_used)
            continue
        if kind not in ("value", "choice", "toggle"):
            continue
        target = resolve(model, section["target"]) if section.get("target") else model
        attr = section["attr"]
        value = getattr(target, attr)
        label = section.get("label", attr)
        im.push_id(attr)
        im.begin_disabled(bool(section.get("read_only")))
        control_label = label
        if kind != "toggle":
            im.text_wrapped(plain(label))
            im.set_item_tooltip(plain(section.get("description") or f"Edit {label}."))
            control_label = "##value"
        if kind == "toggle":
            edited, value = im.checkbox(label, bool(value))
        elif kind == "choice":
            options = section.get("options") or list(resolve(target, section["options_source"])())
            index = options.index(value) if value in options else 0
            edited, index = im.combo(control_label, index, section.get("labels") or options)
            value = options[index] if options else value
        elif section.get("kind") == "str":
            edited, value = im.input_text(control_label, str(value))
        else:
            control = bounded_int if section.get("kind") == "int" else bounded_float
            edited, value = control(
                control_label,
                value,
                minimum=section.get("minimum", -1e12),
                maximum=section.get("maximum", 1e12),
                step=section.get("step", 1 if section.get("kind") == "int" else 0.01),
            )
        im.set_item_tooltip(plain(section.get("description") or f"Edit {label}."))
        if callable(on_used) and (edited or im.is_item_clicked()):
            on_used(attr)
        if item_rects is not None:
            item_rects[attr] = im.get_item_rect()
        im.end_disabled()
        im.pop_id()
        if edited:
            setattr(target, attr, value)
            changed()


def parameter_field(parameter, label=None):
    """Edit a live parameter's value, fixed state and optional interval bounds."""
    label = plain(label or parameter.name)
    im.push_id(getattr(parameter, "canonical_id", parameter.name))
    low, high = parameter.bounds
    enabled = bool(parameter.bounds_on)
    im.text_wrapped(label)
    im.set_item_tooltip(plain(getattr(parameter, "description", None) or f"Edit {label}."))
    edited, value = bounded_float(
        "##value",
        float(parameter.value),
        minimum=low if enabled and low is not None else -1e12,
        maximum=high if enabled and high is not None else 1e12,
        step=0.01,
    )
    im.set_item_tooltip(
        plain(getattr(parameter, "description", None) or f"Numerical value of {label}.")
    )
    if edited:
        parameter.value = value
    expanded = im.collapsing_header("Fitting state and bounds")
    im.set_item_tooltip(f"Edit {label} fixed state and lower/upper limits.")
    if expanded:
        changed, fixed = im.checkbox("Fixed", bool(parameter.fixed))
        im.set_item_tooltip(
            "Hold this parameter constant during fitting; its manually entered value remains editable."
        )
        if changed:
            parameter.fixed = fixed
            edited = True
        changed, enabled = im.checkbox("Bounds enabled", bool(parameter.bounds_on))
        im.set_item_tooltip("Apply the lower and upper limits to this parameter.")
        if changed:
            parameter.bounds_on = enabled
            edited = True
        for index, title in enumerate(["Lower bound", "Upper bound"]):
            changed, text = im.input_text(title, str(parameter.bounds[index]))
            im.set_item_tooltip("Numeric fitting limit; use inf or -inf for an unbounded side.")
            if changed:
                try:
                    value = float(text)
                    pair = list(parameter.bounds)
                    pair[index] = value
                    if pair[0] <= pair[1]:
                        parameter.bounds = tuple(pair)
                        edited = True
                except ValueError:
                    pass
    im.pop_id()
    return edited
