"""Dilution advisor: plain-language plans a novice can follow verbatim.

Every plan must read like a recipe: one sentence per physical action,
microliters spelled out, nothing left to guess.
"""
import math

import pytest


def test_direct_single_step_plan_320_to_50_in_50ul():
    from chisurf.plugins.core.acq.live.dilution import plan_dilution
    plan = plan_dilution(320.0, 50.0)
    assert plan.direct is True
    assert len(plan.steps) == 1
    step = plan.steps[0]
    assert step.take_ul == pytest.approx(8.0)
    assert step.into_ul == pytest.approx(42.0)
    assert step.total_ul == pytest.approx(50.0)
    assert step.conc_after == pytest.approx(51.2)
    assert plan.achieved_conc == pytest.approx(51.2)
    assert plan.rel_error == pytest.approx(0.024)
    assert plan.ok is True
    assert plan.reason is None
    assert plan.instruction_lines == [
        'Put 42.0 uL buffer on the slide, add 8.0 uL of the FCS stock.'
    ]


def test_rounding_compensation_keeps_total_volume_exact():
    from chisurf.plugins.core.acq.live.dilution import plan_dilution
    plan = plan_dilution(295.0, 50.0, volume_step_ul=0.5)
    step = plan.steps[0]
    assert step.take_ul == pytest.approx(8.5)          # raw 8.47 -> 8.5
    assert step.into_ul == pytest.approx(41.5)         # buffer compensates
    assert step.take_ul + step.into_ul == pytest.approx(50.0)
    assert step.total_ul == pytest.approx(50.0)
    assert plan.achieved_conc == pytest.approx(295.0 * 8.5 / 50.0)


def test_instruction_lines_are_physical_and_explicit():
    from chisurf.plugins.core.acq.live.dilution import plan_dilution
    plan = plan_dilution(320.0, 50.0)
    (line,) = plan.instruction_lines
    assert '8.0 uL' in line and '42.0 uL' in line and 'uL' in line
    nums = [float(tok) for tok in line.replace('uL', ' ').split() if tok.replace('.', '', 1).isdigit()]
    sample = nums[1] if 'add' in line.split('buffer')[0] else nums[0]
    buffer_vol = nums[1] if sample == nums[0] else nums[0]
    assert buffer_vol + sample == pytest.approx(50.0)
    assert line.endswith('.')


def test_plan_marked_not_ok_when_rounding_error_exceeds_tolerance():
    from chisurf.plugins.core.acq.live.dilution import plan_dilution
    plan = plan_dilution(320.0, 50.0, volume_step_ul=5.0)  # 7.8 uL forced up to 10 uL
    assert plan.achieved_conc == pytest.approx(64.0)
    assert plan.rel_error == pytest.approx(0.28)
    assert plan.ok is False
    assert plan.reason and 'error' in plan.reason


def test_pre_dilution_inserted_when_direct_take_too_small():
    from chisurf.plugins.core.acq.live.dilution import plan_dilution
    plan = plan_dilution(3200.0, 50.0)          # 3.2 nM -> 50 pM: direct take 0.78 uL < 2
    assert plan.direct is False
    assert plan.ok is True
    assert len(plan.steps) == 2
    pre, final = plan.steps
    assert pre.take_ul == pytest.approx(5.0)
    assert pre.into_ul == pytest.approx(45.0)
    assert pre.conc_after == pytest.approx(320.0)
    assert final.take_ul == pytest.approx(8.0)
    assert final.into_ul == pytest.approx(42.0)
    assert final.conc_after == pytest.approx(51.2)
    assert plan.achieved_conc == pytest.approx(51.2)
    assert plan.rel_error == pytest.approx(0.024)
    assert plan.instruction_lines[0] == \
        'Mix 5.0 uL of the FCS stock with 45.0 uL buffer (1:10 pre-dilution).'
    assert plan.instruction_lines[1] == \
        'Put 42.0 uL buffer on the slide, add 8.0 uL of the pre-dilution (1:10).'


def test_two_pre_dilutions_chained_when_one_is_not_enough():
    from chisurf.plugins.core.acq.live.dilution import plan_dilution
    plan = plan_dilution(32000.0, 50.0)         # needs 1:100 -> two 1:10 mixes
    assert plan.ok is True
    assert plan.direct is False
    assert len(plan.steps) == 3
    assert plan.steps[-1].conc_after == pytest.approx(51.2)
    assert plan.instruction_lines[0].endswith('(1:10 pre-dilution).')
    assert plan.instruction_lines[1].endswith('(1:100 pre-dilution).')
    assert '5.0 uL of the pre-dilution (1:10)' in plan.instruction_lines[1]
    assert plan.instruction_lines[2] == \
        'Put 42.0 uL buffer on the slide, add 8.0 uL of the pre-dilution (1:100).'
    # every physical mix keeps its volumes explicit and consistent
    assert all('uL' in line for line in plan.instruction_lines)


def test_impossible_after_max_pre_steps_returns_failure_not_a_plan():
    from chisurf.plugins.core.acq.live.dilution import plan_dilution
    plan = plan_dilution(320000.0, 50.0, max_pre_steps=2)   # would need 1:1000
    assert plan.ok is False
    assert plan.reason and 'pre-dilution' in plan.reason and 'too concentrated' in plan.reason
    assert plan.instruction_lines == []
    assert plan.steps == []
    assert plan.achieved_conc == 0.0 and plan.rel_error == 0.0 and plan.direct is False


def test_recommended_pre_dilution_factor_is_smallest_power_of_ten():
    from chisurf.plugins.core.acq.live.dilution import recommended_pre_dilution_factor
    assert recommended_pre_dilution_factor(320.0, 50.0, 2.0, 50.0) == 1.0
    assert recommended_pre_dilution_factor(3200.0, 50.0, 2.0, 50.0) == 10.0
    assert recommended_pre_dilution_factor(32000.0, 50.0, 2.0, 50.0) == 100.0
    assert recommended_pre_dilution_factor(320000.0, 50.0, 2.0, 50.0) == 1000.0


def test_invalid_inputs_are_refused_with_clear_messages():
    from chisurf.plugins.core.acq.live.dilution import plan_dilution
    with pytest.raises(ValueError, match='above'):
        plan_dilution(50.0, 50.0)                       # already at target
    with pytest.raises(ValueError, match='above'):
        plan_dilution(40.0, 50.0)                       # already above target
    with pytest.raises(ValueError, match='positive'):
        plan_dilution(0.0, 50.0)
    with pytest.raises(ValueError, match='positive'):
        plan_dilution(-320.0, 50.0)
    with pytest.raises(ValueError, match='positive'):
        plan_dilution(320.0, 0.0)
    with pytest.raises(ValueError, match='positive'):
        plan_dilution(320.0, -50.0)
    with pytest.raises(ValueError, match='finite'):
        plan_dilution(float('nan'), 50.0)
    with pytest.raises(ValueError, match='finite'):
        plan_dilution(320.0, float('nan'))
    with pytest.raises(ValueError, match='min_take_ul'):
        plan_dilution(320.0, 50.0, min_take_ul=0.0)
    with pytest.raises(ValueError, match='min_take_ul'):
        plan_dilution(320.0, 50.0, min_take_ul=-2.0)
    with pytest.raises(ValueError, match='target_volume_ul'):
        plan_dilution(320.0, 50.0, target_volume_ul=0.0)
    with pytest.raises(ValueError, match='volume_step_ul'):
        plan_dilution(320.0, 50.0, volume_step_ul=0.0)


def test_allow_direct_use_returns_use_as_is_plan():
    from chisurf.plugins.core.acq.live.dilution import plan_dilution
    plan = plan_dilution(50.0, 50.0, allow_direct_use=True)
    assert plan.ok is True and plan.direct is True
    assert plan.achieved_conc == pytest.approx(50.0)
    assert plan.rel_error == pytest.approx(0.0)
    assert plan.instruction_lines == [
        'Put 50.0 uL of the FCS stock on the slide, no dilution needed.'
    ]


def test_format_conc_renders_value_and_unit():
    from chisurf.plugins.core.acq.live.dilution import format_conc
    assert format_conc(51.2) == '51.2 pM'
    assert format_conc(3200.0, 'pM') == '3200 pM'
    assert format_conc(3.2, 'nM') == '3.2 nM'
