"""One visible control block per connected head; never a head selector."""
from emtk import im, SliderFlags
from chisurf.plugins.core.acq.live.laser import laser_diode_threshold


def _request(model,slot,value):
    model.power_selected_slot=slot
    model.power_poll(force=True)
    return model.request_power_target(value)


def _confirm_or_apply(app,model,action):
    nags_suppressed = getattr(model, 'power_change_nags_suppressed', None)
    suppressed = nags_suppressed() if nags_suppressed else bool(getattr(model, 'advanced', False) or getattr(model, 'power_change_ignore', False))
    if model.power_change_references() and not suppressed:
        dialogs=getattr(app,'_power_change_dialogs',None)
        if dialogs is None:
            from chisurf.plugins.core.acq.gui.power_controls import PowerChangeDialogs
            dialogs=app._power_change_dialogs=PowerChangeDialogs(model,width=650)
        def confirmed(yes):
            if yes:
                if getattr(dialogs, 'ignore_checked', False):
                    model.power_change_ignore = True
                action()
                model.power_change_invalidations.append({'kind':'timing_irf','reason':'laser drive or pulse mode changed','average_power_calibration':'preserved'})
        dialogs.confirm('Change laser drive / pulse mode?',
            'Changing laser drive or pulse mode may change the pulse shape and invalidate existing timing/IRF calibrations. Recorded files and diode calibration curves are retained. Apply this change?',
            on_answer=confirmed)
    else:
        action()
        if model.power_change_references():
            model.power_change_invalidations.append({'kind':'timing_irf','reason':'laser drive or pulse mode changed','average_power_calibration':'preserved'})


def _set_drive(model,slot,value):
    model.laser.set_head(slot,intensity_pct=value)
    model.laser_program=model.laser.capture()
    model.laser_applied=True
    model.power_message=f'Uncalibrated drive: {value:.1f} %. This is not measured optical power.'
    model.power_poll(force=True)


def _set_pulsed(model,slot,pulsed):
    model.laser_off()
    model.laser.set_head(slot,pulsed=pulsed)
    model.laser_program=model.laser.capture()
    model.laser_applied=True
    model.power_poll(force=True)


def draw_laser_cards(app,model,state,width):
    model.power_poll(force=not bool(model._power_heads))
    heads=list(model._power_heads)
    if not heads:
        im.text_disabled('Connect a laser to see its heads.')
        return
    if not hasattr(app,'_head_targets'):app._head_targets={}
    if not hasattr(app,'_head_edits'):app._head_edits={}
    laser_state=getattr(model,'_power_laser_state',None) or model.laser.state()
    busy=bool(model.power_servo is not None and model.power_servo.active)
    if getattr(model, "overcount_alert", False) and not getattr(model, "advanced", False):
        im.push_style_color(im.Col.TEXT, (1.0, 0.25, 0.25, 1.0))
        im.text("⚠ COUNT RATE TOO HIGH (> 1 MHz/ch) — Excitation shutter closed to protect detectors.")
        im.pop_style_color()
        if im.small_button("Override protection##laser_cards_override"):
            model.overcount_override = True
            model.overcount_alert = False
            model.set_shutter('Excitation', True)
        im.set_item_tooltip("Click to override 1 MHz protection and reopen excitation shutter.")
        im.separator()
    for head in heads:
        slot=head.slot;name=model._power_label(head)
        im.push_id(f'laser_card_{slot}')
        im.separator()
        if getattr(app, '_editing_laser_name_slot', None) == slot:
            im.set_next_item_width(min(150.0, max(80.0, width - 40.0)))
            cur_edit = getattr(app, '_editing_laser_name_val', name)
            changed, new_val = im.input_text(f'##rename_{slot}', cur_edit)
            if changed:
                app._editing_laser_name_val = new_val
            state.rects[f'laser_rename_{slot}'] = im.get_item_rect()
            if im.is_item_deactivated_after_edit() or im.is_key_pressed(im.Key.ENTER):
                if not hasattr(model, 'laser_custom_names'):
                    model.laser_custom_names = {}
                clean_name = app._editing_laser_name_val.strip() or str(head.name or f'Laser slot {slot}')
                model.laser_custom_names[slot] = clean_name
                app._editing_laser_name_slot = None
            elif im.is_item_deactivated():
                app._editing_laser_name_slot = None
        else:
            im.text(name)
            state.rects[f'laser_name_{slot}'] = im.get_item_rect()
            if im.is_item_hovered() and im.is_mouse_double_clicked(0):
                app._editing_laser_name_slot = slot
                app._editing_laser_name_val = name
            im.set_item_tooltip('Double-click to rename this laser.')
        try:
            points=model.power_book._record(name)
        except ValueError:
            points=None
        if slot not in app._head_targets:
            effective=model.power_effective or {}
            app._head_targets[slot]=float(effective.get('uw',0)) if effective.get('laser')==name else 0.
        if points:
            if slot not in app._head_edits and slot in model.power_targets_uw:
                app._head_targets[slot]=model.power_targets_uw[slot]
            if busy:im.begin_disabled()
            im.set_next_item_width(max(60.,width-85.))
            changed,value=im.slider_float('Target (µW)',app._head_targets[slot],points[0][1],points[-1][1],
                                         fmt='%.3g µW',flags=SliderFlags.ALWAYS_CLAMP)
            rect=im.get_current_context().get_item_rect()
            state.rects[f'laser_target_{slot}']=rect
            if slot==model.power_selected_slot:state.rects['power_target_uw']=rect
            if changed:
                app._head_targets[slot]=value;app._head_edits[slot]=value
            if slot in app._head_edits and not im.is_item_active() and not busy and not getattr(app,'_rendering_inert',False):
                value=app._head_edits.pop(slot)
                _request(model,slot,value)
            im.set_item_tooltip('Drag and release, or Ctrl-click and press Enter. Automatically turns other heads off and tunes this head using fresh diode readings. Changing power may change pulse shape and invalidate timing calibrations.')
            if busy:im.end_disabled()
        else:
            if busy:im.begin_disabled()
            im.set_next_item_width(max(60.,width-85.))
            changed,value=im.slider_float('Drive (%)',head.intensity_pct,0.,100.,fmt='%.1f %%',flags=SliderFlags.ALWAYS_CLAMP)
            state.rects[f'laser_drive_{slot}']=im.get_item_rect()
            key=('percent',slot)
            if changed:app._head_edits[key]=value
            if key in app._head_edits and not im.is_item_active() and not busy and not getattr(app,'_rendering_inert',False):
                value=app._head_edits.pop(key)
                _confirm_or_apply(app,model,lambda slot=slot,value=value:_set_drive(model,slot,value))
            im.set_item_tooltip('No valid µW calibration: raw drive percentage. Editing the drive does not enable emission. Calibrate this head to use measured µW.')
            if busy:im.end_disabled()
        on=(not laser_state.emission_blocked and head.intensity_pct>0
            and (laser_state.oscillator is None or head.output<0 or laser_state.oscillator.output_enabled[head.output]))
        if busy:im.begin_disabled()
        changed,enabled=im.checkbox('On',on)
        state.rects[f'laser_on_{slot}']=im.get_item_rect()
        if changed:
            if enabled:
                target=app._head_targets.get(slot,0.)
                if points and target>0:_request(model,slot,target)
                elif points is None and head.intensity_pct>0:
                    if model.set_shutter('Excitation',True) and model.shutters.get_parameter('reported_excitation')==1:
                        model.laser.set_head(slot,enabled=True)
                        model.laser.set_emission(True)
                        model.laser_program=model.laser.capture()
                    else:model.power_message='Excitation shutter is not confirmed open; emission was not enabled.'
                else:model.power_message='Enter a positive calibrated µW target for this head first.'
            else:
                model.laser.set_head(slot,enabled=False,intensity_pct=0.)
                remaining=model.laser.state().heads
                if not any(h.intensity_pct>0 for h in remaining):model.laser_off()
                model.laser_program=model.laser.capture()
            model.power_poll(force=True)
        im.set_item_tooltip('Per-head optical switch. On uses this head’s entered calibrated target; Off sets its drive to zero. Global Laser off remains available while recording.')
        im.same_line()
        changed,pulsed=im.checkbox('Pulsed',head.pulsed)
        state.rects[f'laser_pulsed_{slot}']=im.get_item_rect()
        if changed:
            _confirm_or_apply(app,model,lambda slot=slot,pulsed=pulsed:_set_pulsed(model,slot,pulsed))
        im.set_item_tooltip('Checked: pulsed. Unchecked: CW. Switching blocks emission; previous timing calibrations cannot be reused at a different pulse mode.')
        im.same_line()
        if im.small_button('Calibrate'):
            model.power_selected_slot=slot
            app.power_panel.model.laser_name=name
            app.focus_dock('power_calibration')
        state.rects[f'laser_calibrate_{slot}']=im.get_item_rect()
        im.set_item_tooltip('Open the manual average-power calibration panel for this laser.')
        im.same_line()
        if im.small_button('Full pwr'):
            max_target = points[-1][1] if points else 1000.0
            if points:
                app._head_targets[slot] = max_target
                _confirm_or_apply(app, model, lambda slot=slot, max_target=max_target: _request(model, slot, max_target))
            else:
                _confirm_or_apply(app, model, lambda slot=slot: _set_drive(model, slot, 100.0))
        state.rects[f'laser_full_{slot}']=im.get_item_rect()
        im.set_item_tooltip('Set laser to maximum power (1000 µW / 1 mW when calibrated, or 100% drive). Changing power may change pulse shape and invalidate timing calibrations.')
        if busy:im.end_disabled()
        drive_pct = float(head.intensity_pct)
        th = laser_diode_threshold(head)
        near_threshold = (0.0 < drive_pct <= th + 2.0)
        th_str = f"~{th:.0f}%"
        AMBER = (1.0, 0.72, 0.15, 1.0)
        if points:
            if near_threshold:
                im.text_colored(AMBER, f"Drive: {drive_pct:.1f}% (near threshold)")
                im.set_item_tooltip(
                    f"Diode drive: {drive_pct:.1f}%. "
                    f"⚠ Near or below lasing threshold ({th_str}). In this regime, diode laser output is unstable, "
                    f"spontaneous emission dominates, and timing jitter increases. Increase power above {th_str} for stable pulsed emission."
                )
            else:
                im.text(f"Drive: {drive_pct:.1f}%")
                im.set_item_tooltip(f"Laser diode drive: {drive_pct:.1f}%. Stable lasing regime is above {th_str}.")
            state.rects[f'laser_drive_pct_{slot}']=im.get_item_rect()
        else:
            if near_threshold:
                im.text_colored(AMBER, f"Drive: {drive_pct:.1f}% (near threshold)")
                im.set_item_tooltip(
                    f"Diode drive: {drive_pct:.1f}%. "
                    f"⚠ Near/below lasing threshold ({th_str}): emission is unstable and timing fluctuates."
                )
            else:
                im.text(f"Drive: {drive_pct:.1f}%")
                im.set_item_tooltip(f"Laser diode drive: {drive_pct:.1f}%.")
            state.rects[f'laser_drive_pct_{slot}']=im.get_item_rect()
        if slot==model.power_selected_slot:
            reading = model.power_reading()
            offset = getattr(model, 'calculate_diode_offset', lambda s: 0.0)(slot)
            raw = float(model.shutters.get_parameter('diode_raw', -1)) if getattr(model, 'shutters', None) else (
                float(model.laser.get_parameter('diode_raw', -1)) if hasattr(getattr(model, 'laser', None), 'get_parameter') else -1.0
            )
            if reading and reading != '— µW':
                if near_threshold:
                    im.text_colored(AMBER, f"{reading} ⚠")
                    im.set_item_tooltip(
                        f"Calibrated power at objective: {reading}. "
                        f"Warning: Near lasing threshold ({th_str} drive); output may fluctuate. "
                        f"Diode raw: {raw:g}, offset from other lasers: {offset:g}."
                    )
                else:
                    im.text(reading)
                    im.set_item_tooltip(
                        f"Calibrated power at objective: {reading}. "
                        f"Diode raw: {raw:g}, offset from other lasers: {offset:g}."
                    )
            else:
                im.text_disabled('— µW')
                im.set_item_tooltip('Power reading unavailable (laser off, shutter closed, or uncalibrated).')
            state.rects[f'laser_info_{slot}']=im.get_item_rect()
        im.pop_id()
    if model.power_message:im.text_wrapped(model.power_message)
