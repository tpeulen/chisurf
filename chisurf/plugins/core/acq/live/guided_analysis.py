"""Live reference diagnostics beside the normal lossless recording path.

Uses tttrlib's existing online correlator. Amplitude-derived N/brightness are
explicitly preliminary (no fitted diffusion/lifetime or background correction is
claimed). Scientific checks require bounds in the approved protocol. A recorded
file passing acquisition checks is not proof of a validated dye calibration.
"""
from __future__ import annotations

import numpy as np

from .fcs import LiveFcs
from .session import RecordSession
from .calibration.measurements import irf_fwhm_ns


class GuidedLiveAnalysis:
    def __init__(self,macro_clock_s,micro_res_s,n_micro,stage,limits=None):
        self.clock=float(macro_clock_s)
        self.micro_res=float(micro_res_s)
        self.n_micro=int(n_micro)
        self.stage=str(stage)
        self.limits=dict(limits or {})
        self.correlators={}
        self.decays={}
        self.counts={}
        self.first=None;self.last=None
        self.rate_times=[];self.rate_series={}
        self._rng=np.random.default_rng(2941)
        self.decimated=False

    def push(self,batch):
        batch=batch.photons()
        if not len(batch):return
        if self.first is None:self.first=int(batch.macro[0])
        previous=self.last if self.last is not None else self.first
        self.last=int(batch.macro[-1])
        elapsed=max(self.clock,(self.last-self.first)*self.clock)
        interval=max(self.clock,(self.last-previous)*self.clock)
        self.rate_times.append(elapsed)
        for ch in np.unique(batch.channel):
            key=int(ch);sel=batch.channel==ch
            macro=batch.macro[sel];micro=batch.micro[sel]
            if key not in self.correlators:
                self.correlators[key]=LiveFcs(self.clock)
                self.decays[key]=np.zeros(self.n_micro,dtype=np.uint64)
                self.counts[key]=0
                self.rate_series[key]=[0.]*(len(self.rate_times)-1)
            # Bound this optional analysis work; all photons have already passed
            # through the writer and ordinary recording accumulators. Never thin PTU data.
            if macro.size>25000:
                keep=np.sort(self._rng.choice(macro.size,25000,replace=False))
                self.correlators[key].push_np(macro[keep])
                self.decimated=True
            else:self.correlators[key].push_np(macro)
            self.decays[key]+=np.bincount(micro.astype(np.int64),minlength=self.n_micro)[:self.n_micro].astype(np.uint64)
            self.counts[key]+=int(sel.sum())
        for key in self.rate_series:
            rate=float(np.sum(batch.channel==key))/interval
            if len(self.rate_series[key])<len(self.rate_times):self.rate_series[key].append(rate)
        if len(self.rate_times)>300:
            self.rate_times=self.rate_times[-300:]
            self.rate_series={key:values[-300:] for key,values in self.rate_series.items()}

    def snapshot(self):
        elapsed=((self.last-self.first)*self.clock) if self.last is not None and self.first is not None else 0.
        correlations={};rates={};metrics={};rows=[]
        def check(channel,name,value,metric,tip):
            bounds=self.limits.get(metric)
            valid=value is not None and np.isfinite(value)
            if not valid:status,limit='waiting','—'
            elif bounds is None:status,limit='unverified','not configured'
            else:
                lo,hi=map(float,bounds)
                status='pass' if lo<=value<=hi else 'fail'
                limit=f'{lo:g} – {hi:g}'
            rows.append({'metric':f'Det {channel}: {name}','value':f'{value:.4g}' if valid else '—',
                         'limit':limit,'status':status,'guidance':tip})
        for key,corr in self.correlators.items():
            view=corr.snapshot()
            correlations[key]=view['correlation']
            rate=self.counts[key]/elapsed if elapsed>0 else 0.
            rates[key]=rate
            n=view['n_focus']
            n=float(n) if np.isfinite(n) and n>0 else None
            amp=1/n if n is not None else None
            bright=rate/n/1000 if n is not None else None
            width,_=irf_fwhm_ns(self.decays[key],self.micro_res*1e9)
            metrics[key]={'rate_khz':rate/1000,'amplitude':amp,'n_amplitude_estimate':n,
                          'raw_brightness_estimate_khz':bright,'irf_fwhm_ns':width}
            check(key,'rate (kHz)',rate/1000,'rate_khz','Actual accumulated photons / measured duration; compare with a limit approved for this detector and step.')
            if self.stage=='water':
                check(key,'IRF FWHM (ns)',width,'irf_fwhm_ns','Main-peak width of the measured decay; not a fitted fluorescence lifetime.')
            elif self.stage in ('fcs','green_reference','red_reference','dna','sample'):
                check(key,'G amplitude',amp,'amplitude','Live multi-tau autocorrelation plateau. Not a diffusion-model fit; afterpulsing/background may bias the estimate.')
                check(key,'raw brightness (kHz)',bright,'raw_brightness_estimate_khz','Preliminary full-rate / amplitude-derived N. No background correction or calibrated molecular-brightness claim.')
        if self.stage in ('green_reference','red_reference'):
            rows.append({'metric':'Diffusion / lifetime fit','value':'not fitted','limit':'validated model required',
                         'status':'unverified','guidance':'Curves are measured live. No fitted diffusion time or lifetime is claimed without a validated model, IRF and appropriate fit ranges.'})
        if self.decimated:
            rows.append({'metric':'Live correlation','value':'throttled','limit':'analysis budget',
                         'status':'watch','guidance':'Only correlation input was subsampled. Recorded photons and full count-rate/decay accumulators are not thinned.'})
        return {'stage':self.stage,'correlations':correlations,'rates_hz':rates,
                'decays':{key:h.copy() for key,h in self.decays.items()},
                'micro_res_s':self.micro_res,'n_micro':self.n_micro,
                'rate_t_s':np.asarray(self.rate_times),
                'rate_curves_hz':{key:np.asarray(v) for key,v in self.rate_series.items()},
                'metrics':metrics,'quality':rows,'analysis_decimated':self.decimated}


class GuidedRecordSession(RecordSession):
    """Keep the ordinary burst/PTU path; add simultaneous reference diagnostics."""
    def __init__(self,source,experiment,*,stage,reference_limits=None,**kwargs):
        self.stage=stage
        self._last_reference_live = {}
        info=source.info
        self.reference_analysis=GuidedLiveAnalysis(info.macro_clock_s,info.micro_res_s,
                                                   info.n_micro,stage,reference_limits)
        super().__init__(source,experiment,**kwargs)

    def _push(self,batch):
        super()._push(batch)
        self.reference_analysis.push(batch)

    def snapshot(self):
        snap=super().snapshot()
        if snap.get('analysis_gap'):
            snap['reference_live'] = {'stage': self.stage, 'metrics': {}, 'correlations': {},
                'quality': [{'metric': 'Live analysis', 'value': 'incomplete', 'limit': 'complete',
                             'status': 'fail', 'guidance': 'Repeat this stage; live analysis has a gap.'}]}
            return snap
        if self._lock.acquire(blocking=False):
            try:
                self._last_reference_live = self.reference_analysis.snapshot()
            finally:
                self._lock.release()
        snap['reference_live'] = self._last_reference_live
        return snap
