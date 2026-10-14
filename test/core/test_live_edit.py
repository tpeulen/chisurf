"""The Qt-free live-object write seam GUI code uses instead of poking fits."""

import types

import pytest

from chisurf.core.api import (
    add_dataset,
    dataset_objects,
    edit_parameter,
    move_dataset,
    restore_parameter_value,
    set_fit_range,
    set_parameter_array,
    update_fit,
)


def _param(**kw):
    return types.SimpleNamespace(
        value=1.0, fixed=False, bounds=(None, None), bounds_on=False, link=None, **kw
    )


def test_edit_parameter_writes_each_field():
    p, other = _param(), _param()
    edit_parameter(p, value=2.5, fixed=True, bounds=(0.0, 9.0), bounds_on=True, link=other)
    assert (p.value, p.fixed, p.bounds, p.bounds_on, p.link) == (2.5, True, (0.0, 9.0), True, other)
    edit_parameter(p, link=None)
    assert p.link is None


def test_edit_parameter_rejects_unknown_field():
    with pytest.raises(TypeError):
        edit_parameter(_param(), colour="red")


def test_restore_parameter_value_keeps_fixed():
    class Guarded:
        fixed = True
        _v = 1.0

        @property
        def value(self):
            return self._v

        @value.setter
        def value(self, v):
            if self.fixed:
                raise RuntimeError("fixed parameter written")
            self._v = v

    p = Guarded()
    restore_parameter_value(p, 4.0)
    assert p.value == 4.0 and p.fixed is True


def test_fit_update_and_range():
    calls = []
    fit = types.SimpleNamespace(fit_range=None, update=lambda: calls.append("u"))
    set_fit_range(fit, 3, 9)
    assert fit.fit_range == (3, 9) and calls == []
    set_fit_range(fit, 1, 2, update=True)
    assert fit.fit_range == (1, 2) and calls == ["u"]
    update_fit(fit)
    assert calls == ["u", "u"]


def test_set_parameter_array():
    p = types.SimpleNamespace(_port=types.SimpleNamespace(value=None))
    set_parameter_array(p, [1, 2])
    assert p._port.value == [1, 2]


def test_dataset_add_and_move():
    import chisurf as cs

    saved = list(cs.imported_datasets)
    try:
        a, b = types.SimpleNamespace(name="a"), types.SimpleNamespace(name="b")
        add_dataset(a)
        add_dataset(b)
        move_dataset(b, len(saved))
        assert dataset_objects()[-2:] == [b, a]
    finally:
        cs.imported_datasets[:] = saved
