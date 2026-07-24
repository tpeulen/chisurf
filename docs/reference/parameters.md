(reference-parameters)=
# Parameter glossary

Every named fit/model parameter known to ChiSurf, with its meaning and the analysis contexts it appears in. Generated from the parameter registry (`chisurf/core/settings/constants/parameter_registry.json`), which is built from the model and plugin source. Plugin-specific UI controls are listed on each [plugin page](plugins/index.md).

Total registered parameters: **228**.

| Parameter | Meaning | Keywords |
| --- | --- | --- |
| `alpha` |  |  |
| `aT` |  |  |
| `AtB` | Model parameter AtB used in TCSPC decay models. Refer to the specific model documentation for the detailed physical meaning. | TCSPC, lifetime |
| `b` |  |  |
| `ba` |  |  |
| `BG` |  |  |
| `bg` | Constant background level added to the time-resolved decay curve (counts per time channel). | TCSPC, lifetime, background, offset, counts |
| `bg0` |  |  |
| `bg1` |  |  |
| `BR` |  |  |
| `brightness` |  |  |
| `bt` |  |  |
| `BtA` | Model parameter BtA used in TCSPC decay models. Refer to the specific model documentation for the detailed physical meaning. | TCSPC, lifetime |
| `conc` |  |  |
| `cont` | Model parameter cont used in TCSPC decay models. Refer to the specific model documentation for the detailed physical meaning. | TCSPC, lifetime |
| `cpm` |  |  |
| `cpm_all` |  |  |
| `D` | Model parameter D used in TCSPC decay models. Refer to the specific model documentation for the detailed physical meaning. | TCSPC, lifetime |
| `diam` |  |  |
| `dt` | Time bin width of the TCSPC histogram (time per channel). | TCSPC, lifetime, time bin, resolution |
| `dtMT[ns]` |  |  |
| `dtTAC[ns]` |  |  |
| `E_FRET` | Apparent FRET efficiency parameter E_FRET (0e00..1). | TCSPC, lifetime, FRET, efficiency |
| `eps1` |  |  |
| `eps2` |  |  |
| `eps3` |  |  |
| `fcs.a` | Fractional amplitude or population of this diffusion/kinetic component (dimensionless, typically between 0 and 1). | FCS, amplitude, population fraction |
| `fcs.a1` | Fractional amplitude or population of this diffusion/kinetic component (dimensionless, typically between 0 and 1). | FCS, amplitude, population fraction |
| `fcs.a2` | Fractional amplitude or population of this diffusion/kinetic component (dimensionless, typically between 0 and 1). | FCS, amplitude, population fraction |
| `fcs.a21` | Fractional amplitude or population of this diffusion/kinetic component (dimensionless, typically between 0 and 1). | FCS, amplitude, population fraction |
| `fcs.a22` | Fractional amplitude or population of this diffusion/kinetic component (dimensionless, typically between 0 and 1). | FCS, amplitude, population fraction |
| `fcs.a31` | Fractional amplitude or population of this diffusion/kinetic component (dimensionless, typically between 0 and 1). | FCS, amplitude, population fraction |
| `fcs.aab` | Amplitude of the photon antibunching term (very fast correlation component). | FCS, antibunching, triplet, amplitude |
| `fcs.ab1` | Amplitude of an individual antibunching / anisotropy / anticorrelation component (dimensionless). | FCS, antibunching, anisotropy, amplitude |
| `fcs.ab2` | Amplitude of an individual antibunching / anisotropy / anticorrelation component (dimensionless). | FCS, antibunching, anisotropy, amplitude |
| `fcs.ab3` | Amplitude of an individual antibunching / anisotropy / anticorrelation component (dimensionless). | FCS, antibunching, anisotropy, amplitude |
| `fcs.ab4` | Amplitude of an individual antibunching / anisotropy / anticorrelation component (dimensionless). | FCS, antibunching, anisotropy, amplitude |
| `fcs.aba` | Amplitude of an individual antibunching / anisotropy / anticorrelation component (dimensionless). | FCS, antibunching, anisotropy, amplitude |
| `fcs.aba1` | Amplitude of an individual antibunching / anisotropy / anticorrelation component (dimensionless). | FCS, antibunching, anisotropy, amplitude |
| `fcs.aba2` | Amplitude of an individual antibunching / anisotropy / anticorrelation component (dimensionless). | FCS, antibunching, anisotropy, amplitude |
| `fcs.aba3` | Amplitude of an individual antibunching / anisotropy / anticorrelation component (dimensionless). | FCS, antibunching, anisotropy, amplitude |
| `fcs.aba4` | Amplitude of an individual antibunching / anisotropy / anticorrelation component (dimensionless). | FCS, antibunching, anisotropy, amplitude |
| `fcs.abf` | Total amplitude factor for a group of anticorrelation components. | FCS, anticorrelation, amplitude |
| `fcs.abt` | Time constant of an antibunching or anticorrelation component. | FCS, antibunching, anticorrelation, correlation time |
| `fcs.abt1` | Amplitude of an individual antibunching / anisotropy / anticorrelation component (dimensionless). | FCS, antibunching, anisotropy, amplitude |
| `fcs.abt2` | Amplitude of an individual antibunching / anisotropy / anticorrelation component (dimensionless). | FCS, antibunching, anisotropy, amplitude |
| `fcs.abt3` | Amplitude of an individual antibunching / anisotropy / anticorrelation component (dimensionless). | FCS, antibunching, anisotropy, amplitude |
| `fcs.abt4` | Amplitude of an individual antibunching / anisotropy / anticorrelation component (dimensionless). | FCS, antibunching, anisotropy, amplitude |
| `fcs.abt5` | Amplitude of an individual antibunching / anisotropy / anticorrelation component (dimensionless). | FCS, antibunching, anisotropy, amplitude |
| `fcs.af` | Overall amplitude factor for a set of anticorrelation components. | FCS, anticorrelation, amplitude |
| `fcs.aR` | Amplitude of a relaxation or anticorrelation term (dimensionless). | FCS, relaxation, anticorrelation, amplitude |
| `fcs.aR1` | Amplitude of a relaxation or anticorrelation term (dimensionless). | FCS, relaxation, anticorrelation, amplitude |
| `fcs.aR2` | Amplitude of a relaxation or anticorrelation term (dimensionless). | FCS, relaxation, anticorrelation, amplitude |
| `fcs.aRa` | Amplitude of a relaxation or anticorrelation term (dimensionless). | FCS, relaxation, anticorrelation, amplitude |
| `fcs.aroc` | Amplitude of the rotational correlation (anisotropy) contribution. | FCS, anisotropy, rotation, amplitude |
| `fcs.b` | Additive baseline/offset of the correlation function. | FCS, baseline, offset, background |
| `fcs.ba` | Fractional amplitude of a dark or bunching state (e.g. triplet or blinking); dimensionless and typically between 0 and 1. | FCS, bunching, triplet, dark state, amplitude |
| `fcs.ba1` | Fractional amplitude of a dark or bunching state (e.g. triplet or blinking); dimensionless and typically between 0 and 1. | FCS, bunching, triplet, dark state, amplitude |
| `fcs.ba11` | Fractional amplitude of a dark or bunching state (e.g. triplet or blinking); dimensionless and typically between 0 and 1. | FCS, bunching, triplet, dark state, amplitude |
| `fcs.ba12` | Fractional amplitude of a dark or bunching state (e.g. triplet or blinking); dimensionless and typically between 0 and 1. | FCS, bunching, triplet, dark state, amplitude |
| `fcs.ba2` | Fractional amplitude of a dark or bunching state (e.g. triplet or blinking); dimensionless and typically between 0 and 1. | FCS, bunching, triplet, dark state, amplitude |
| `fcs.ba21` | Fractional amplitude of a dark or bunching state (e.g. triplet or blinking); dimensionless and typically between 0 and 1. | FCS, bunching, triplet, dark state, amplitude |
| `fcs.ba22` | Fractional amplitude of a dark or bunching state (e.g. triplet or blinking); dimensionless and typically between 0 and 1. | FCS, bunching, triplet, dark state, amplitude |
| `fcs.ba3` | Fractional amplitude of a dark or bunching state (e.g. triplet or blinking); dimensionless and typically between 0 and 1. | FCS, bunching, triplet, dark state, amplitude |
| `fcs.ba31` | Fractional amplitude of a dark or bunching state (e.g. triplet or blinking); dimensionless and typically between 0 and 1. | FCS, bunching, triplet, dark state, amplitude |
| `fcs.ba32` | Fractional amplitude of a dark or bunching state (e.g. triplet or blinking); dimensionless and typically between 0 and 1. | FCS, bunching, triplet, dark state, amplitude |
| `fcs.ba4` | Fractional amplitude of a dark or bunching state (e.g. triplet or blinking); dimensionless and typically between 0 and 1. | FCS, bunching, triplet, dark state, amplitude |
| `fcs.ba5` | Fractional amplitude of a dark or bunching state (e.g. triplet or blinking); dimensionless and typically between 0 and 1. | FCS, bunching, triplet, dark state, amplitude |
| `fcs.ba6` | Fractional amplitude of a dark or bunching state (e.g. triplet or blinking); dimensionless and typically between 0 and 1. | FCS, bunching, triplet, dark state, amplitude |
| `fcs.ba7` | Fractional amplitude of a dark or bunching state (e.g. triplet or blinking); dimensionless and typically between 0 and 1. | FCS, bunching, triplet, dark state, amplitude |
| `fcs.bs2` | Stretching exponent for a stretched-exponential relaxation term. | FCS, stretched exponential, relaxation, exponent |
| `fcs.bs21` | Stretching exponent for a stretched-exponential relaxation term. | FCS, stretched exponential, relaxation, exponent |
| `fcs.bs22` | Stretching exponent for a stretched-exponential relaxation term. | FCS, stretched exponential, relaxation, exponent |
| `fcs.bt` | Correlation/relaxation time constant of a dark or bunching state. | FCS, bunching, triplet, dark state, correlation time |
| `fcs.bt1` | Correlation/relaxation time constant of a dark or bunching state. | FCS, bunching, triplet, dark state, correlation time |
| `fcs.bt11` | Correlation/relaxation time constant of a dark or bunching state. | FCS, bunching, triplet, dark state, correlation time |
| `fcs.bt12` | Correlation/relaxation time constant of a dark or bunching state. | FCS, bunching, triplet, dark state, correlation time |
| `fcs.bt2` | Correlation/relaxation time constant of a dark or bunching state. | FCS, bunching, triplet, dark state, correlation time |
| `fcs.bt21` | Correlation/relaxation time constant of a dark or bunching state. | FCS, bunching, triplet, dark state, correlation time |
| `fcs.bt22` | Correlation/relaxation time constant of a dark or bunching state. | FCS, bunching, triplet, dark state, correlation time |
| `fcs.bt3` | Correlation/relaxation time constant of a dark or bunching state. | FCS, bunching, triplet, dark state, correlation time |
| `fcs.bt31` | Correlation/relaxation time constant of a dark or bunching state. | FCS, bunching, triplet, dark state, correlation time |
| `fcs.bt32` | Correlation/relaxation time constant of a dark or bunching state. | FCS, bunching, triplet, dark state, correlation time |
| `fcs.bt4` | Correlation/relaxation time constant of a dark or bunching state. | FCS, bunching, triplet, dark state, correlation time |
| `fcs.bt5` | Correlation/relaxation time constant of a dark or bunching state. | FCS, bunching, triplet, dark state, correlation time |
| `fcs.bt6` | Correlation/relaxation time constant of a dark or bunching state. | FCS, bunching, triplet, dark state, correlation time |
| `fcs.bt7` | Correlation/relaxation time constant of a dark or bunching state. | FCS, bunching, triplet, dark state, correlation time |
| `fcs.C` | Dimensionless factor C used in the rotational correlation / anisotropy term. | FCS, anisotropy, rotation |
| `fcs.N` | Average number of fluorescent particles in the observation volume. In standard FCS models the correlation amplitude scales roughly as 1/N. | FCS, number of molecules, concentration, amplitude |
| `fcs.N3` | Average number of fluorescent particles in the observation volume. In standard FCS models the correlation amplitude scales roughly as 1/N. | FCS, number of molecules, concentration, amplitude |
| `fcs.s` | Structure parameter s = z0 / w0 describing the axial-to-radial extent of the detection volume. | FCS, structure parameter, PSF, geometry |
| `fcs.tab` | Correlation time of the photon antibunching term (fast time scale). | FCS, antibunching, correlation time |
| `fcs.tb1` |  |  |
| `fcs.tb2` |  |  |
| `fcs.tb3` |  |  |
| `fcs.tb4` |  |  |
| `fcs.td` | Characteristic diffusion time of this component (time scale on which particles traverse the observation volume). | FCS, diffusion, correlation time |
| `fcs.td1` | Characteristic diffusion time of this component (time scale on which particles traverse the observation volume). | FCS, diffusion, correlation time |
| `fcs.td2` | Characteristic diffusion time of this component (time scale on which particles traverse the observation volume). | FCS, diffusion, correlation time |
| `fcs.td21` | Characteristic diffusion time of this component (time scale on which particles traverse the observation volume). | FCS, diffusion, correlation time |
| `fcs.td22` | Characteristic diffusion time of this component (time scale on which particles traverse the observation volume). | FCS, diffusion, correlation time |
| `fcs.td3` | Characteristic diffusion time of this component (time scale on which particles traverse the observation volume). | FCS, diffusion, correlation time |
| `fcs.td31` | Characteristic diffusion time of this component (time scale on which particles traverse the observation volume). | FCS, diffusion, correlation time |
| `fcs.td32` | Characteristic diffusion time of this component (time scale on which particles traverse the observation volume). | FCS, diffusion, correlation time |
| `fcs.tR` | Relaxation or anticorrelation time constant of a kinetic component. | FCS, relaxation, kinetics, correlation time |
| `fcs.tR1` | Relaxation or anticorrelation time constant of a kinetic component. | FCS, relaxation, kinetics, correlation time |
| `fcs.tR2` | Relaxation or anticorrelation time constant of a kinetic component. | FCS, relaxation, kinetics, correlation time |
| `fcs.tR3` | Relaxation or anticorrelation time constant of a kinetic component. | FCS, relaxation, kinetics, correlation time |
| `fcs.tRa` | Relaxation or anticorrelation time constant of a kinetic component. | FCS, relaxation, kinetics, correlation time |
| `fcs.trc1` | Rotational correlation time used in the anisotropy / rotational diffusion term. | FCS, anisotropy, rotation, correlation time |
| `fcs.trc2trc1` | Rotational correlation time used in the anisotropy / rotational diffusion term. | FCS, anisotropy, rotation, correlation time |
| `g` | Model parameter g used in TCSPC decay models. Refer to the specific model documentation for the detailed physical meaning. | TCSPC, lifetime |
| `gG` |  |  |
| `gR` |  |  |
| `ik` | Shape parameter of the synthetic IRF model. | TCSPC, lifetime, IRF, shape |
| `irf_start` | Start index (or time) of the IRF region used for convolution. | TCSPC, lifetime, IRF, window, start |
| `irf_stop` | Stop index (or time) of the IRF region used for convolution. | TCSPC, lifetime, IRF, window, stop |
| `iw` | Width parameter of the synthetic IRF model. | TCSPC, lifetime, IRF, width |
| `k2` | Orientation factor  governing dipole-dipole coupling in FRET. | TCSPC, lifetime, FRET, orientation factor, kappa2 |
| `kQ` |  |  |
| `l` | Model parameter l used in TCSPC decay models. Refer to the specific model documentation for the detailed physical meaning. | TCSPC, lifetime |
| `l1` | Model parameter l1 used in TCSPC decay models. Refer to the specific model documentation for the detailed physical meaning. | TCSPC, lifetime |
| `l2` | Model parameter l2 used in TCSPC decay models. Refer to the specific model documentation for the detailed physical meaning. | TCSPC, lifetime |
| `lam_em` |  |  |
| `lam_ex` |  |  |
| `lb` | Lamp background level subtracted from the instrument response function. | TCSPC, lifetime, lamp, background, IRF |
| `line_dur` |  |  |
| `lp` | Model parameter lp used in TCSPC decay models. Refer to the specific model documentation for the detailed physical meaning. | TCSPC, lifetime |
| `mA` | Model parameter mA used in TCSPC decay models. Refer to the specific model documentation for the detailed physical meaning. | TCSPC, lifetime |
| `mag` |  |  |
| `mB` | Model parameter mB used in TCSPC decay models. Refer to the specific model documentation for the detailed physical meaning. | TCSPC, lifetime |
| `N` |  |  |
| `n` |  |  |
| `n curves` |  |  |
| `n photons` |  |  |
| `n0` | Initial number of excited donor molecules used to scale the model decay to the experimental counts. | TCSPC, lifetime, normalization, excited molecules |
| `N1` |  |  |
| `N2` |  |  |
| `N3` |  |  |
| `n_rh` |  |  |
| `n_td` |  |  |
| `nPh_bg` | Output: estimated number of background photons in the TCSPC trace based on background level and measurement timing settings. | TCSPC, background, photons, output |
| `nPh_fl` | Output: estimated number of fluorescence photons (after background subtraction) in the TCSPC trace. | TCSPC, fluorescence, photons, output |
| `nPh_max` |  |  |
| `nPh_min` |  |  |
| `nTAC` |  |  |
| `offset` |  |  |
| `pinhole` |  |  |
| `pureA` | Model parameter pureA used in TCSPC decay models. Refer to the specific model documentation for the detailed physical meaning. | TCSPC, lifetime |
| `pureB` | Model parameter pureB used in TCSPC decay models. Refer to the specific model documentation for the detailed physical meaning. | TCSPC, lifetime |
| `pxl_dur` |  |  |
| `pxl_size` |  |  |
| `QYA` |  |  |
| `QYD` |  |  |
| `R0` | Frster radius R0 of the donor-acceptor pair. | TCSPC, lifetime, FRET, Forster radius, distance |
| `r0` | Frster radius R0 of the donor-acceptor pair. | TCSPC, lifetime, FRET, Forster radius, distance |
| `r_ss_i` | Intensity-domain steady-state anisotropy. For dual-channel data, ChiSurf background-corrects VV and VH (per-channel metadata when available), compensates objective mixing via l1/l2, and evaluates rS,I from channel sums using the ChiSurf convention r = (VV - VH) / (g*VV + 2*VH). For single-channel fallback, VM is reconstructed from the active anisotropy model before summation. | TCSPC, anisotropy, steady state, intensity |
| `r_ss_l` | Lifetime-domain steady-state anisotropy derived from the model lifetime spectrum and rotational spectrum. This value is model-predicted (spectrum/integral domain) and does not depend on direct VV/VH channel integration. | TCSPC, anisotropy, steady state, lifetime |
| `rc_ele` | Model parameter rc_ele used in TCSPC decay models. Refer to the specific model documentation for the detailed physical meaning. | TCSPC, lifetime |
| `reg` |  |  |
| `rep` | Laser repetition rate of the excitation source. | TCSPC, lifetime, repetition rate, laser, frequency |
| `rh_max` |  |  |
| `rh_min` |  |  |
| `rics.aT` | Triplet/blinking fraction a_T (0–1). | RICS, triplet, blinking, fraction |
| `rics.D` | Diffusion coefficient D in µm²/s. | RICS, diffusion, mobility |
| `rics.line_dur` | Time between successive scanned lines in milliseconds. | RICS, imaging, timing, line scan |
| `rics.n` | Average number of fluorescent molecules in the observation volume N. RICS/ICS amplitude G(0) is proportional to 1/N. | RICS, ICS, number of molecules, concentration |
| `rics.offset` | Additive offset of the correlation function. | RICS, baseline, correlation |
| `rics.pxl_dur` | Pixel dwell time (line scan) in microseconds. | RICS, imaging, timing, pixel dwell time |
| `rics.pxl_size` | Pixel size in the sample plane in nanometers. | RICS, imaging, pixel size, spatial sampling |
| `rics.tauT` | Triplet/blinking correlation time τ_T in milliseconds. | RICS, triplet, blinking, kinetics |
| `rics.w_r` | Radial waist of the detection PSF in µm. | RICS, PSF, waist, radial |
| `rics.w_z` | Axial waist of the detection PSF in µm. | RICS, PSF, waist, axial |
| `s` |  |  |
| `sc` | Relative amplitude of a prompt scattering contribution that is added to the model decay. | TCSPC, lifetime, scatter, prompt, amplitude |
| `slowf` | Model parameter slowf used in TCSPC decay models. Refer to the specific model documentation for the detailed physical meaning. | TCSPC, lifetime |
| `start` | Start time (or channel) of the fit/convolution window. | TCSPC, lifetime, fit window, start |
| `stop` | Stop time (or channel) of the fit/convolution window. | TCSPC, lifetime, fit window, stop |
| `t0` | Fluorescence lifetime or characteristic decay time of this component. | TCSPC, lifetime, decay time |
| `tau0` | Fluorescence lifetime or characteristic decay time of this component. | TCSPC, lifetime, decay time |
| `tauD` |  |  |
| `tauT` |  |  |
| `tBg` | Measurement time of the background acquisition. | TCSPC, lifetime, background, measurement time |
| `tcspc.a` | Pre-exponential amplitude or population fraction of this decay component (dimensionless contribution to the overall time-resolved signal). | TCSPC, lifetime, amplitude, population fraction |
| `tcspc.a1` | Pre-exponential amplitude of this decay component (fractional contribution to the overall time-resolved signal; dimensionless). | TCSPC, lifetime, amplitude, population fraction |
| `tcspc.a2` | Pre-exponential amplitude of this decay component (fractional contribution to the overall time-resolved signal; dimensionless). | TCSPC, lifetime, amplitude, population fraction |
| `tcspc.a3` | Pre-exponential amplitude of this decay component (fractional contribution to the overall time-resolved signal; dimensionless). | TCSPC, lifetime, amplitude, population fraction |
| `tcspc.aD` | Fraction of donors subject to additional quenching or rate channels (dimensionless). | TCSPC, lifetime, donor fraction, population fraction |
| `tcspc.ad1` | Pre-exponential amplitude of this decay component (fractional contribution to the overall time-resolved signal; dimensionless). | TCSPC, lifetime, amplitude, population fraction |
| `tcspc.aDA` | Pre-exponential amplitude of this decay component (fractional contribution to the overall time-resolved signal; dimensionless). | TCSPC, lifetime, amplitude, population fraction |
| `tcspc.aDAA` | Pre-exponential amplitude of this decay component (fractional contribution to the overall time-resolved signal; dimensionless). | TCSPC, lifetime, amplitude, population fraction |
| `tcspc.aDO` | Pre-exponential amplitude of this decay component (fractional contribution to the overall time-resolved signal; dimensionless). | TCSPC, lifetime, amplitude, population fraction |
| `tcspc.af1A` | Pre-exponential amplitude or population fraction of this decay component (dimensionless contribution to the overall time-resolved signal). | TCSPC, lifetime, amplitude, population fraction |
| `tcspc.b` | Empirical coefficient of the sqrt(time) term in the transient-quenching decay model; controls deviations from a pure single-exponential decay. | TCSPC, lifetime, empirical, transient quenching |
| `tcspc.Ddye` | Translational diffusion coefficient of the fluorescent dye. | TCSPC, lifetime, diffusion, coefficient |
| `tcspc.kf1A` | Effective FRET or energy-transfer rate constant for this channel. | TCSPC, lifetime, FRET, rate constant, energy transfer |
| `tcspc.kf1AA` | Effective FRET or energy-transfer rate constant for this channel. | TCSPC, lifetime, FRET, rate constant, energy transfer |
| `tcspc.kf2A` | Effective FRET or energy-transfer rate constant for this channel. | TCSPC, lifetime, FRET, rate constant, energy transfer |
| `tcspc.kQ` | Quenching rate constant added to the inverse lifetime (1/tau + kQ). | TCSPC, lifetime, quenching, rate constant |
| `tcspc.Nq` | Effective number or concentration of quenchers in the interaction volume. | TCSPC, lifetime, quenchers, concentration, quenching |
| `tcspc.p0` | Overall normalization or intensity at time zero of the decay curve. | TCSPC, lifetime, normalization, initial intensity |
| `tcspc.Rdye` | Characteristic interaction radius or distance parameter for the dye3quencher system. | TCSPC, lifetime, distance, interaction radius, quenching |
| `tcspc.tau0` | Fluorescence lifetime or characteristic decay time of this component. | TCSPC, lifetime, decay time |
| `tcspc.tau1` | Fluorescence lifetime or characteristic decay time of this component. | TCSPC, lifetime, decay time |
| `tcspc.tau2` | Fluorescence lifetime or characteristic decay time of this component. | TCSPC, lifetime, decay time |
| `tcspc.tau3` | Fluorescence lifetime or characteristic decay time of this component. | TCSPC, lifetime, decay time |
| `tcspc.td1` | Fluorescence lifetime or characteristic decay time of this component. | TCSPC, lifetime, decay time |
| `tcspc.td2` | Fluorescence lifetime or characteristic decay time of this component. | TCSPC, lifetime, decay time |
| `tcspc.Vav` | Effective averaging volume used in the transient-quenching model. | TCSPC, lifetime, volume, quenching model |
| `tcspc.xD` | Fraction of donors subject to additional quenching or rate channels (dimensionless). | TCSPC, lifetime, donor fraction, population fraction |
| `td_max` |  |  |
| `td_min` |  |  |
| `tDead` | Model parameter tDead used in TCSPC decay models. Refer to the specific model documentation for the detailed physical meaning. | TCSPC, lifetime |
| `temp` |  |  |
| `tMeas` | Measurement time of the main TCSPC experiment. | TCSPC, lifetime, measurement time, experiment |
| `ts` | Additional temporal shift applied to align IRF and decay. | TCSPC, lifetime, timeshift, alignment |
| `Veff` |  |  |
| `vh_bg_int` | Background-corrected summed VH intensity used by anisotropy diagnostics. Derived after channel/background extraction and channel-wise summation over the active trace. | TCSPC, anisotropy, background, VH |
| `vv_bg_int` | Background-corrected summed VV intensity used by anisotropy diagnostics. Derived after channel/background extraction and channel-wise summation over the active trace. | TCSPC, anisotropy, background, VV |
| `w` | Model parameter w used in TCSPC decay models. Refer to the specific model documentation for the detailed physical meaning. | TCSPC, lifetime |
| `w0` |  |  |
| `w_r` |  |  |
| `w_z` |  |  |
| `wem` |  |  |
| `win-size` | Model parameter win-size used in TCSPC decay models. Refer to the specific model documentation for the detailed physical meaning. | TCSPC, lifetime |
| `xA` | Model parameter xA used in TCSPC decay models. Refer to the specific model documentation for the detailed physical meaning. | TCSPC, lifetime |
| `xB` | Model parameter xB used in TCSPC decay models. Refer to the specific model documentation for the detailed physical meaning. | TCSPC, lifetime |
| `xDOnly` | Fraction of donors subject to additional quenching or rate channels (dimensionless). | TCSPC, lifetime, donor fraction, population fraction |
