"""Persistent live-analysis plots for every stage of the measurement wizard."""
import numpy as np
from emtk import im,implot

_COLOURS=((0.,.85,.95,1.),(.95,.2,.75,1.),(1.,.8,.2,1.))


def es_marginals(counts,x_edges,y_edges):
    """Marginal projections of the E/S burst histogram: E sums over S bins, S over E bins."""
    counts=np.asarray(counts,dtype=float)
    x_edges=np.asarray(x_edges,dtype=float);y_edges=np.asarray(y_edges,dtype=float)
    return {'e_values':counts.sum(axis=1),'s_values':counts.sum(axis=0),
            'e_centers':(x_edges[:-1]+x_edges[1:])/2,'s_centers':(y_edges[:-1]+y_edges[1:])/2}


def draw_guided_plots(model,state):
    snap=model.display_snapshot()
    live=snap.get('reference_live') or {}
    stale_stage=bool(live) and live.get('stage')!=model.step_id
    if stale_stage:live={}
    width=im.get_content_region_avail()[0]
    remaining=im.get_content_region_avail()[1]
    height=max(72.,min(260.,(remaining-160.)/2-18.))
    if not im.begin_table('guided_live_grid',2):return
    entries=[('guided_count_plot','Burst / intensity trace','Time (s)','Count rate (kHz)'),
             ('guided_corr_plot','Correlation','Lag time τ (s)','G(τ) − 1'),
             ('guided_decay_plot','Decays / IRF','Microtime (ns)','Photons'),
             ('guided_stage_plot','FRET / stoichiometry' if model.step_id in ('dna','sample') else
              ('IRF peak' if model.step_id=='water' else 'Detector counts'),'','')]
    for key,title,xlabel,ylabel in entries:
        im.table_next_column();im.push_id(key)
        top=im.get_cursor_screen_pos();im.text(title)
        w=im.get_content_region_avail()[0]
        hist=None
        if key=='guided_stage_plot':
            histograms={} if stale_stage else (snap.get('histograms') or {})
            histograms=histograms.values() if isinstance(histograms,dict) else histograms
            hist=next((h for h in histograms if isinstance(h,dict) and 'y' in h and 'counts' in h),None)
        marginal_cell=key=='guided_stage_plot' and model.step_id in ('dna','sample')
        if marginal_cell:height=max(height,220.)
        axis_flags = (implot.AXIS_FLAGS_NO_GRID_LINES | implot.AXIS_FLAGS_NO_TICK_MARKS | implot.AXIS_FLAGS_NO_TICK_LABELS) if not live else 0
        plot_flags = implot.FLAGS_NO_TITLE | ((implot.FLAGS_NO_INPUTS | implot.FLAGS_NO_FRAME) if not live else 0)
        if not marginal_cell and implot.begin_plot('##curve',(w,height),plot_flags):
            if not live:
                implot.setup_axes(xlabel,ylabel,axis_flags,axis_flags)
            else:
                implot.setup_axes(xlabel,ylabel)
            if key=='guided_count_plot':
                t=np.asarray(live.get('rate_t_s',()))
                for i,(ch,values) in enumerate((live.get('rate_curves_hz') or {}).items()):
                    values=np.asarray(values);n=min(t.size,values.size)
                    if n:
                        implot.set_next_line_style(_COLOURS[i%len(_COLOURS)])
                        x=t[-n:];y=values[-n:]/1000
                        if n==1:
                            x=np.array([0.,max(float(x[0]),1e-9)])
                            y=np.repeat(y,2)
                        implot.plot_line(f'Det {ch}',x,y)
            elif key=='guided_corr_plot':
                implot.setup_axis_scale(implot.AXIS_X1,implot.SCALE_LOG10)
                if not live.get('correlations'):
                    implot.setup_axis_limits(implot.AXIS_X1,1e-6,1.,implot.COND_ALWAYS)
                for i,(ch,corr) in enumerate((live.get('correlations') or {}).items()):
                    t=np.asarray(corr['tau_s']);g=np.asarray(corr['g'])
                    times=np.asarray(live.get('rate_t_s',()))
                    end=float(times[-1]) if times.size else 1.
                    keep=(t>0)&(t<end/5)&np.isfinite(g)
                    if keep.any():
                        implot.set_next_line_style(_COLOURS[i%len(_COLOURS)])
                        implot.plot_line(f'Det {ch}',t[keep],g[keep])
            elif key=='guided_decay_plot' or (key=='guided_stage_plot' and model.step_id=='water'):
                implot.setup_axes('Microtime (ns)', 'Photons', axis_flags, axis_flags)
                implot.setup_axis_scale(implot.AXIS_Y1,implot.SCALE_LOG10)
                if key=='guided_stage_plot':implot.setup_axis_limits(implot.AXIS_X1,0.,2.,implot.COND_ALWAYS)
                for i,(ch,values) in enumerate((live.get('decays') or {}).items()):
                    values=np.asarray(values)
                    t=np.arange(values.size)*float(live.get('micro_res_s',1e-12))*1e9
                    keep=values>0
                    if keep.any():
                        implot.set_next_line_style(_COLOURS[i%len(_COLOURS)])
                        implot.plot_line(f'Det {ch}',t[keep],values[keep])
            elif key=='guided_stage_plot':
                implot.setup_axes('Detector', 'Photons', axis_flags, axis_flags)
                decays=live.get('decays') or {}
                if decays:
                    channels=np.asarray(list(decays),dtype=float)
                    counts=np.asarray([np.sum(v) for v in decays.values()],dtype=float)
                    implot.plot_bars('Photons',channels,counts,bar_size=.6)
            implot.end_plot()
        elif marginal_cell:
            has_data = hist is not None and hist.get('counts') is not None and np.any(hist['counts'])
            if not has_data:
                hist = {'x': 'E', 'y': 'S', 'counts': np.zeros((1, 1)),
                        'x_edges': np.array([0., 1.]), 'y_edges': np.array([0., 1.])}
                counts = hist['counts']
                marg = {'e_values': np.zeros(0), 's_values': np.zeros(0),
                        'e_centers': np.zeros(0), 's_centers': np.zeros(0)}
                grid = np.zeros((1, 1))
            else:
                ver_key = (id(hist), int(snap.get('photons', 0)), int(snap.get('bursts', 0)))
                cached = getattr(model, '_cached_guided_marg', None)
                if cached is not None and cached[0] == ver_key:
                    counts, marg, grid = cached[1:]
                else:
                    counts = np.asarray(hist['counts'], dtype=float)
                    marg = es_marginals(counts, hist['x_edges'], hist['y_edges'])
                    grid = np.log10(1 + counts.T[::-1])
                    model._cached_guided_marg = (ver_key, counts, marg, grid)
            xe, ye = hist['x_edges'], hist['y_edges']
            heat_h = max(56., height * 0.5)
            axis_flags = (implot.AXIS_FLAGS_NO_GRID_LINES | implot.AXIS_FLAGS_NO_TICK_MARKS | implot.AXIS_FLAGS_NO_TICK_LABELS) if not has_data else 0
            plot_flags = implot.FLAGS_NO_TITLE | ((implot.FLAGS_NO_INPUTS | implot.FLAGS_NO_FRAME) if not has_data else 0)
            if implot.begin_plot('##es2d', (w, heat_h), plot_flags):
                implot.setup_axes(str(hist['x']), str(hist['y']), axis_flags, axis_flags)
                if has_data:
                    implot.plot_heatmap('Burst counts', grid, grid.shape[0], grid.shape[1], 0.,
                                        max(1., float(grid.max())), None, (float(xe[0]), float(ye[0])),
                                        (float(xe[-1]), float(ye[-1])))
                else:
                    implot.setup_axis_limits(implot.AXIS_X1, 0., 1., implot.COND_ALWAYS)
                    implot.setup_axis_limits(implot.AXIS_Y1, 0., 1., implot.COND_ALWAYS)
                implot.end_plot()
            marg_h = max(40., height - heat_h - 30.)
            half = (w - 8.) / 2
            if implot.begin_plot('##es_e', (half, marg_h), plot_flags):
                implot.setup_axes(f'{hist["x"]} marginal', 'Bursts', axis_flags, axis_flags)
                if has_data:
                    implot.plot_bars('E marginal', marg['e_centers'], marg['e_values'])
                else:
                    implot.setup_axis_limits(implot.AXIS_X1, 0., 1., implot.COND_ALWAYS)
                implot.end_plot()
            im.same_line()
            if implot.begin_plot('##es_s', (half, marg_h), plot_flags):
                implot.setup_axes(f'{hist["y"]} marginal', 'Bursts', axis_flags, axis_flags)
                if has_data:
                    implot.plot_bars('S marginal', marg['s_centers'], marg['s_values'])
                else:
                    implot.setup_axis_limits(implot.AXIS_X1, 0., 1., implot.COND_ALWAYS)
                implot.end_plot()
        bottom=im.get_cursor_screen_pos()
        state.rects[key]=(top[0],top[1],w,max(height,bottom[1]-top[1]))
        im.pop_id()
    im.end_table()
