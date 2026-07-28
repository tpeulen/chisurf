import numpy as np
from typing import List, Tuple, Dict

from chisurf.core.progress import progress


def compute_static_bva_line(
        prox_mean_bins: np.ndarray,  # Proximity ratio bins
        number_of_photons_per_slice: int = 4,
        n_samples: int = 10_000
) -> Tuple[np.ndarray, np.ndarray]:
    """Simulate the shot-noise-limited (static) BVA line.

    Simulates fluorescence burst variance analysis (BVA) by calculating the mean
    and standard deviation of proximity ratios for a static species based on the
    assumption of binomial photon emission distribution.

    In BVA, the proximity ratio between two fluorescent species (e.g., acceptor
    and donor) is calculated using the number of photons emitted in specific time
    slices. This function simulates photon counts using a binomial distribution,
    where photons are randomly assigned to each species based on the provided
    proximity ratios. Because every slice holds exactly
    ``number_of_photons_per_slice`` photons, the proximity ratio of a sample is
    simply the acceptor count divided by that constant.

    Parameters
    ----------
    prox_mean_bins : np.ndarray
        An array of proximity ratio bins, representing the expected ratio of
        emitted photons from the donor and acceptor species.
    number_of_photons_per_slice : int, optional
        The total number of photons emitted per time slice. Default is 4.
    n_samples : int, optional
        The number of samples to simulate for each proximity ratio bin.
        Default is 10,000.

    Returns
    -------
    Tuple[np.ndarray, np.ndarray]
        A tuple containing two arrays:

        - ``prox_mean``: mean proximity ratio for each bin.
        - ``prox_sd``: standard deviation of the proximity ratio for each bin.

    Notes
    -----
    A non-positive ``number_of_photons_per_slice`` carries no information about
    the proximity ratio; zeros are returned for both arrays rather than dividing
    by zero.
    """
    prox_mean_bins = np.asarray(prox_mean_bins, dtype=float)
    if number_of_photons_per_slice <= 0:
        zeros = np.zeros(len(prox_mean_bins))
        return zeros, zeros.copy()

    # One binomial draw per (sample, bin); ``p`` broadcasts along the bin axis.
    binom_samples = np.random.binomial(
        number_of_photons_per_slice,
        prox_mean_bins,
        size=(n_samples, len(prox_mean_bins))
    )
    prox_ratios = binom_samples / number_of_photons_per_slice
    return prox_ratios.mean(axis=0), prox_ratios.std(axis=0)



def compute_bva(
        df,  # Target data frame
        tttrs: Dict[str, 'tttrlib.TTTR'],  # Dictionary of TTTR data indexed by 'First File'
        donor_channels: List[int] = [0, 8],  # Channels for donor fluorescence detection
        donor_micro_time_ranges: List[Tuple[int, int]] = [(0, 4096)],  # Microtime ranges for donor photons
        acceptor_channels: List[int] = [1, 9],  # Channels for acceptor fluorescence detection
        acceptor_micro_time_ranges: List[Tuple[int, int]] = [(0, 4096)],  # Microtime ranges for acceptor photons
        minimum_window_length: float = 0.01,  # Minimum time window length within burst
        number_of_photons_per_slice: int = -1  # Number of photons per time slice (-1 to use time windows)
):
    """
    Computes proximity ratio statistics (mean and standard deviation) for fluorescence bursts using
    Burst Variance Analysis (BVA). The proximity ratio compares the number of photons detected from
    donor and acceptor species within a burst, helping to analyze dynamic changes in Förster resonance
    energy transfer (FRET) or other fluorescence events.

    Burst Variance Analysis (BVA) involves breaking down fluorescence bursts into time windows or slices,
    calculating the ratio of photons detected from two fluorophores (donor and acceptor) in each time window.
    The proximity ratio is used to examine fluctuations within bursts, providing insight into the dynamic
    behavior of molecular interactions.

    Parameters:
    ----------
    df : pd.DataFrame
        The DataFrame containing burst data with columns 'First File', 'Last File', 'First Photon', and 'Last Photon'.
    tttrs : Dict[str, 'tttrlib.TTTR']
        Dictionary containing TTTR (Time Tagging and Time Resolved) data for each burst indexed by 'First File'.
    donor_channels : List[int], optional
        List of routing channels for donor photon detection. Default is [0, 8].
    donor_micro_time_ranges : List[Tuple[int, int]], optional
        Microtime ranges for donor photons. Default is [(0, 4096)].
    acceptor_channels : List[int], optional
        List of routing channels for acceptor photon detection. Default is [1, 9].
    acceptor_micro_time_ranges : List[Tuple[int, int]], optional
        Microtime ranges for acceptor photons. Default is [(0, 4096)].
    minimum_window_length : float, optional
        Minimum time window length within burst for dividing photon events into slices. Default is 0.01.
    number_of_photons_per_slice : int, optional
        If set to a positive value, divides bursts into slices containing a fixed number of photons.
        If set to -1, divides bursts based on time windows of `minimum_window_length`. Default is -1.

    Returns:
    -------
    pd.DataFrame
        Updated DataFrame with added columns for proximity ratio mean ('Proximity Ratio Mean') and
        standard deviation ('Proximity Ratio Std') for each burst.
    """
    # Initialize lists to store the proximity ratio statistics
    proximity_ratios_mean, proximity_ratios_sd = list(), list()

    # Iterate through rows using iterrows()
    for index, row in progress(df.iterrows(), total=df.shape[0], desc="BVA bursts"):
        # Select tttr data of burst out of dictionary
        ff, fl = row['First File'], row['Last File']
        tttr = tttrs[ff]
        time_calibration = tttr.header.tag('MeasDesc_GlobalResolution')['value']

        # Select events within burst
        burst_start, burst_stop = int(row['First Photon']), int(row['Last Photon'])
        burst_tttr = tttr[burst_start:burst_stop]

        # Split bursts into time windows or photon slices
        if number_of_photons_per_slice < 0:
            # Use time windows to split the burst
            burst_tws = burst_tttr.get_ranges_by_time_window(minimum_window_length,
                                                             macro_time_calibration=time_calibration)
            burst_tws = burst_tws.reshape((len(burst_tws) // 2, 2))
            # get_ranges_by_time_window returns an INCLUSIVE [start, stop]:
            # measured on real data, a window reaches the requested duration only
            # when its stop photon is counted, and none of them do when it is
            # dropped. Slicing [start:stop] loses the last photon of every slice
            # -- a small, uniform downward bias in every slice's photon count,
            # which is exactly what the proximity-ratio variance is computed from.
            burst_tws_tttr = [burst_tttr[start:stop + 1] for start, stop in burst_tws]
        else:
            # Split bursts into chunks with a fixed number of photons
            chunk_size = number_of_photons_per_slice
            burst_tws_tttr = [burst_tttr[i:i + chunk_size] for i in range(0, len(burst_tttr), chunk_size)]

        # Compute proximity ratios for each time window in the burst
        n_acceptor, n_donor = list(), list()
        for tw_tttr in burst_tws_tttr:
            mt = tw_tttr.micro_times
            ch = tw_tttr.routing_channels

            # Donor photons
            donor_time_mask = np.zeros_like(mt, dtype=bool)
            for start, stop in donor_micro_time_ranges:
                donor_time_mask |= (mt >= start) & (mt <= stop)
            donor_channel_mask = np.isin(ch, donor_channels)
            combined_donor_mask = donor_time_mask & donor_channel_mask

            # Acceptor photons
            acceptor_time_mask = np.zeros_like(mt, dtype=bool)
            for start, stop in acceptor_micro_time_ranges:
                acceptor_time_mask |= (mt >= start) & (mt <= stop)
            acceptor_channel_mask = np.isin(ch, acceptor_channels)
            combined_acceptor_mask = acceptor_time_mask & acceptor_channel_mask

            # Count donor and acceptor photons
            n_donor.append(np.sum(combined_donor_mask))
            n_acceptor.append(np.sum(combined_acceptor_mask))

        # Calculate proximity ratios
        tw_n_acceptor = np.array(n_acceptor)
        tw_n_donor = np.array(n_donor)
        tw_total = tw_n_acceptor + tw_n_donor
        tw_proximity_ratios = tw_n_acceptor / tw_total
        proximity_ratio_mean, proximity_ratio_sd = np.nanmean(tw_proximity_ratios), np.nanstd(tw_proximity_ratios)

        # Store results
        proximity_ratios_mean.append(proximity_ratio_mean)
        proximity_ratios_sd.append(proximity_ratio_sd)

    # Update DataFrame with computed proximity ratio statistics
    df['Proximity Ratio Mean'] = np.array(proximity_ratios_mean)
    df['Proximity Ratio Std'] = np.array(proximity_ratios_sd)

    return df
