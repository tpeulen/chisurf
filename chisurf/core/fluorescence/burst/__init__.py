# BVA module -- the shot-noise reference line only; the analysis itself is
# tttrlib.BVA, driven from the burst_bva plugin one batched call per measurement.
import chisurf.core.fluorescence.burst.bocpd

# Import with module prefix to avoid name conflict
import chisurf.core.fluorescence.burst.kalman

# Background estimation module
from chisurf.core.fluorescence.burst.background import (
    BackgroundDiagnostics,
    background_diagnostics_from_bursts,
    estimate_background_from_bursts,
    estimate_background_from_interphoton_times,
    interphoton_time_diagnostics,
)

# BOCPD module — thin wrapper around tttrlib C++ engine
from chisurf.core.fluorescence.burst.bocpd import (
    bocpd_burst_detection,
    bocpd_burst_detection_multi,
    bocpd_filter,
)
from chisurf.core.fluorescence.burst.bocpd import (
    convert_bursts_to_start_stop as bocpd_convert_bursts_to_start_stop,
)

# Burst module
from chisurf.core.fluorescence.burst.burst import burst_filter
from chisurf.core.fluorescence.burst.bva import compute_static_bva_line

# Count rate module
from chisurf.core.fluorescence.burst.count_rate import count_rate_filter

# CUSUM module
from chisurf.core.fluorescence.burst.cusum import cusum_filter

# IRF + background from non-burst photons
from chisurf.core.fluorescence.burst.irf_bg import (
    DetectorIrfBackground,
    extract_irf_background,
    extract_mle_irf_background,
    non_burst_mask,
)

# Kalman module — forwards to the tttrlib C++ engine; the Python fallback
# was dead code and has been deleted.
from chisurf.core.fluorescence.burst.kalman import (
    kalman_burst_search,
    kalman_filter,
)

# Utils module
from chisurf.core.fluorescence.burst.utils import create_array_with_ones
