(reference-parameters)=
# Parameter glossary

Every named fit/model parameter known to ChiSurf, with its meaning and the analysis contexts it appears in. Generated from the parameter registry (`chisurf/core/settings/constants/parameter_registry.json`), which is built from the model and plugin source. Plugin-specific UI controls are listed on each [plugin page](plugins/index.md).

Total registered parameters: **228**.

| Parameter | Meaning | Keywords |
| --- | --- | --- |
| `alpha` | Anomalous-diffusion exponent (α<1 sub-diffusion, α=1 normal, α>1 super-diffusion). |  |
| `aT` | Triplet/blinking amplitude — fraction of molecules transiently in a dark state. |  |
| `AtB` | Model parameter AtB used in TCSPC decay models. Refer to the specific model documentation for the detailed physical meaning. | TCSPC, lifetime |
| `b` | Correlation baseline offset G(τ→∞): ~1 for normalized ACFs, 0 for background-subtracted curves. |  |
| `ba` | Bunching (blinking/triplet) amplitude of a relaxation term. |  |
| `BG` | Background count rate used in the correlation-amplitude correction (kHz). |  |
| `bg` | Constant background level added to the time-resolved decay curve (counts per time channel). | TCSPC, lifetime, background, offset, counts |
| `bg0` | Background count rate in detection channel 0 (kHz). |  |
| `bg1` | Background count rate in detection channel 1 (kHz). |  |
| `BR` | Brightness ratio between species. |  |
| `brightness` | Molecular brightness — background-corrected count rate per molecule, (CR−bg)/N (kHz). |  |
| `bt` | Bunching (blinking/triplet) relaxation time. |  |
| `BtA` | Model parameter BtA used in TCSPC decay models. Refer to the specific model documentation for the detailed physical meaning. | TCSPC, lifetime |
| `conc` | Molecular concentration derived from N and the effective volume. |  |
| `cont` | Model parameter cont used in TCSPC decay models. Refer to the specific model documentation for the detailed physical meaning. | TCSPC, lifetime |
| `cpm` | Counts per molecule (molecular brightness), (I−B)/N. |  |
| `cpm_all` | Counts per molecule summed over all detection channels. |  |
| `D` | Model parameter D used in TCSPC decay models. Refer to the specific model documentation for the detailed physical meaning. | TCSPC, lifetime |
| `diam` | Known inter-focus distance (two-focus FCS) or scan diameter (scanning FCS), in µm. |  |
| `dt` | Time bin width of the TCSPC histogram (time per channel). | TCSPC, lifetime, time bin, resolution |
| `dtMT[ns]` | Macro-time resolution (ns). |  |
| `dtTAC[ns]` | Micro-time (TAC) channel width (ns). |  |
| `E_FRET` | Apparent FRET efficiency parameter E_FRET (0e00..1). | TCSPC, lifetime, FRET, efficiency |
| `eps1` | Molecular brightness of species 1 (counts/molecule/s). |  |
| `eps2` | Molecular brightness of species 2 (counts/molecule/s). |  |
| `eps3` | Molecular brightness of species 3 (counts/molecule/s). |  |
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
| `fcs.tb1` | Relaxation (bunching) time constant of the 1st term. |  |
| `fcs.tb2` | Relaxation (bunching) time constant of the 2nd term. |  |
| `fcs.tb3` | Relaxation (bunching) time constant of the 3rd term. |  |
| `fcs.tb4` | Relaxation (bunching) time constant of the 4th term. |  |
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
| `gG` | Detection efficiency / g-factor of the green (donor) channel. |  |
| `gR` | Detection efficiency / g-factor of the red (acceptor) channel. |  |
| `ik` | Shape parameter of the synthetic IRF model. | TCSPC, lifetime, IRF, shape |
| `irf_start` | Start index (or time) of the IRF region used for convolution. | TCSPC, lifetime, IRF, window, start |
| `irf_stop` | Stop index (or time) of the IRF region used for convolution. | TCSPC, lifetime, IRF, window, stop |
| `iw` | Width parameter of the synthetic IRF model. | TCSPC, lifetime, IRF, width |
| `k2` | Orientation factor  governing dipole-dipole coupling in FRET. | TCSPC, lifetime, FRET, orientation factor, kappa2 |
| `kQ` | Dynamic-quenching rate constant. |  |
| `l` | Model parameter l used in TCSPC decay models. Refer to the specific model documentation for the detailed physical meaning. | TCSPC, lifetime |
| `l1` | Model parameter l1 used in TCSPC decay models. Refer to the specific model documentation for the detailed physical meaning. | TCSPC, lifetime |
| `l2` | Model parameter l2 used in TCSPC decay models. Refer to the specific model documentation for the detailed physical meaning. | TCSPC, lifetime |
| `lam_em` | Emission wavelength (nm). |  |
| `lam_ex` | Excitation wavelength (nm). |  |
| `lb` | Lamp background level subtracted from the instrument response function. | TCSPC, lifetime, lamp, background, IRF |
| `line_dur` | Line duration in a confocal scan (s). |  |
| `lp` | Model parameter lp used in TCSPC decay models. Refer to the specific model documentation for the detailed physical meaning. | TCSPC, lifetime |
| `mA` | Model parameter mA used in TCSPC decay models. Refer to the specific model documentation for the detailed physical meaning. | TCSPC, lifetime |
| `mag` | Magnification of the imaging optics. |  |
| `mB` | Model parameter mB used in TCSPC decay models. Refer to the specific model documentation for the detailed physical meaning. | TCSPC, lifetime |
| `N` | Mean number of molecules in the confocal detection volume; sets the correlation amplitude G(0)=1/N. |  |
| `n` | Refractive index of the immersion/sample medium. |  |
| `n curves` | Number of correlation curves. |  |
| `n photons` | Number of photons. |  |
| `n0` | Initial number of excited donor molecules used to scale the model decay to the experimental counts. | TCSPC, lifetime, normalization, excited molecules |
| `N1` | Mean number of molecules of species 1 in the detection volume. |  |
| `N2` | Mean number of molecules of species 2 in the detection volume. |  |
| `N3` | Mean number of molecules of species 3 in the detection volume. |  |
| `n_rh` | Number of hydrodynamic-radius grid points (distribution fit). |  |
| `n_td` | Number of diffusion-time grid points (distribution fit). |  |
| `nPh_bg` | Output: estimated number of background photons in the TCSPC trace based on background level and measurement timing settings. | TCSPC, background, photons, output |
| `nPh_fl` | Output: estimated number of fluorescence photons (after background subtraction) in the TCSPC trace. | TCSPC, fluorescence, photons, output |
| `nPh_max` | Maximum number of photons per burst considered. |  |
| `nPh_min` | Minimum number of photons per burst considered. |  |
| `nTAC` | Number of micro-time (TAC) channels. |  |
| `offset` | Constant additive offset of the model curve. |  |
| `pinhole` | Confocal pinhole diameter (µm). |  |
| `pureA` | Model parameter pureA used in TCSPC decay models. Refer to the specific model documentation for the detailed physical meaning. | TCSPC, lifetime |
| `pureB` | Model parameter pureB used in TCSPC decay models. Refer to the specific model documentation for the detailed physical meaning. | TCSPC, lifetime |
| `pxl_dur` | Pixel dwell time in an image scan (s). |  |
| `pxl_size` | Pixel size in an image scan (µm). |  |
| `QYA` | Fluorescence quantum yield of the acceptor. |  |
| `QYD` | Fluorescence quantum yield of the donor. |  |
| `R0` | Frster radius R0 of the donor-acceptor pair. | TCSPC, lifetime, FRET, Forster radius, distance |
| `r0` | Frster radius R0 of the donor-acceptor pair. | TCSPC, lifetime, FRET, Forster radius, distance |
| `r_ss_i` | Intensity-domain steady-state anisotropy. For dual-channel data, ChiSurf background-corrects VV and VH (per-channel metadata when available), compensates objective mixing via l1/l2, and evaluates rS,I from channel sums using the ChiSurf convention r = (VV - VH) / (g*VV + 2*VH). For single-channel fallback, VM is reconstructed from the active anisotropy model before summation. | TCSPC, anisotropy, steady state, intensity |
| `r_ss_l` | Lifetime-domain steady-state anisotropy derived from the model lifetime spectrum and rotational spectrum. This value is model-predicted (spectrum/integral domain) and does not depend on direct VV/VH channel integration. | TCSPC, anisotropy, steady state, lifetime |
| `rc_ele` | Model parameter rc_ele used in TCSPC decay models. Refer to the specific model documentation for the detailed physical meaning. | TCSPC, lifetime |
| `reg` | Regularization weight for distribution (MEM/Tikhonov) fits. |  |
| `rep` | Laser repetition rate of the excitation source. | TCSPC, lifetime, repetition rate, laser, frequency |
| `rh_max` | Upper bound of the hydrodynamic-radius axis. |  |
| `rh_min` | Lower bound of the hydrodynamic-radius axis. |  |
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
| `s` | Structure (aspect) parameter of the confocal volume, s = w_z / w_xy. |  |
| `sc` | Relative amplitude of a prompt scattering contribution that is added to the model decay. | TCSPC, lifetime, scatter, prompt, amplitude |
| `slowf` | Model parameter slowf used in TCSPC decay models. Refer to the specific model documentation for the detailed physical meaning. | TCSPC, lifetime |
| `start` | Start time (or channel) of the fit/convolution window. | TCSPC, lifetime, fit window, start |
| `stop` | Stop time (or channel) of the fit/convolution window. | TCSPC, lifetime, fit window, stop |
| `t0` | Fluorescence lifetime or characteristic decay time of this component. | TCSPC, lifetime, decay time |
| `tau0` | Fluorescence lifetime or characteristic decay time of this component. | TCSPC, lifetime, decay time |
| `tauD` | Diffusion time — mean residence time in the confocal volume, τ_D = w_xy²/(4D). |  |
| `tauT` | Triplet/blinking relaxation time. |  |
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
| `td_max` | Upper bound of the diffusion-time axis. |  |
| `td_min` | Lower bound of the diffusion-time axis. |  |
| `tDead` | Model parameter tDead used in TCSPC decay models. Refer to the specific model documentation for the detailed physical meaning. | TCSPC, lifetime |
| `temp` | Sample temperature. |  |
| `tMeas` | Measurement time of the main TCSPC experiment. | TCSPC, lifetime, measurement time, experiment |
| `ts` | Additional temporal shift applied to align IRF and decay. | TCSPC, lifetime, timeshift, alignment |
| `Veff` | Effective confocal detection volume, V_eff = π^{3/2}·γ·w_xy³. |  |
| `vh_bg_int` | Background-corrected summed VH intensity used by anisotropy diagnostics. Derived after channel/background extraction and channel-wise summation over the active trace. | TCSPC, anisotropy, background, VH |
| `vv_bg_int` | Background-corrected summed VV intensity used by anisotropy diagnostics. Derived after channel/background extraction and channel-wise summation over the active trace. | TCSPC, anisotropy, background, VV |
| `w` | Model parameter w used in TCSPC decay models. Refer to the specific model documentation for the detailed physical meaning. | TCSPC, lifetime |
| `w0` | Lateral 1/e² radius of the confocal detection volume (µm). |  |
| `w_r` | Lateral 1/e² radius of the confocal detection volume (µm). |  |
| `w_z` | Axial 1/e² radius of the confocal detection volume (µm). |  |
| `wem` | Emission-side Gauss–Lorentz detection waist. |  |
| `win-size` | Model parameter win-size used in TCSPC decay models. Refer to the specific model documentation for the detailed physical meaning. | TCSPC, lifetime |
| `xA` | Model parameter xA used in TCSPC decay models. Refer to the specific model documentation for the detailed physical meaning. | TCSPC, lifetime |
| `xB` | Model parameter xB used in TCSPC decay models. Refer to the specific model documentation for the detailed physical meaning. | TCSPC, lifetime |
| `xDOnly` | Fraction of donors subject to additional quenching or rate channels (dimensionless). | TCSPC, lifetime, donor fraction, population fraction |
