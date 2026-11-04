"""Guide 21's Burst MLE shift figures, from the owner's session (not in the repository).

usage: python docs/guides/screenshots/guide_21_mle_shifts.py SETTINGS_DIR DATA_DIR OUT_DIR

SETTINGS_DIR holds the detector setup library with RVZMT150; DATA_DIR the session
TP_20261031_DNA_KHM.sptw (DNA13bp_3.ptu, Rh110_thick_1.ptu, Alexa647_thick_1.ptu beside each
other). The hub runs in Simple mode: setup, DNA13bp_3 handed in (the references beside it are
proposed by Data Selection), the burst search, Burst MLE and Fit bursts. Written: the Data
Selection rows, Burst MLE's Fit parameters per detector, its IRF tab, and the reference fits.
The numbers it prints are guide 21's.
"""
import json, os, sys, time

OUT = sys.argv[3] if len(sys.argv) > 3 else "."


def main():
    os.environ["CHISURF_SETTINGS_DIR"] = sys.argv[1]
    from emtk import testing
    from emtk.testing import Driver
    from chisurf.plugins.burst.burst_analysis.gui.native import make_app, receive_photons
    D = os.path.join(sys.argv[2], "")
    hub = make_app(); drv = Driver(hub, (1500, 950)); drv.draw(4)
    hub.set_advanced(False); drv.draw(2)
    hub.select("setup"); drv.draw(3); hub.children["setup"].select_setup("RVZMT150"); drv.draw(4)
    if os.environ.get("SWAP_RED"):
        # RVZMT150's red pair has VV and VH swapped (Alexa 647's anisotropy starts at -0.10):
        # SWAP_RED=1 shows the session with the order put right, as the warning asks
        for det in ("R|G", "R|R"):
            info = hub.setup_model.data["detectors"][det]
            info["chs"] = list(reversed(info["chs"]))
        hub.setup_model.changed()
        hub.context.channel_settings = hub.setup_model.get_settings()
        drv.draw(3)

    def shot(name):
        drv.draw(3)
        p = None
        for _ in range(3):
            p = testing.PixelPainter(1500, 950)
            hub.draw(p, 0.0, 0.0, 1500.0, 950.0)
        open(f"{OUT}/{name}.png", "wb").write(testing.png_encode(p.width, p.height, p.px))

    def wait(pred, what, t=1800):
        end = time.time() + t
        while not pred():
            assert time.time() < end, what
            drv.draw(1); time.sleep(0.1)
        drv.draw(3)

    print("setup:", json.dumps({d: {k: v.get(k) for k in ("chs", "micro_time_ranges")} for d, v in hub.setup_model.data["detectors"].items()}), hub.setup_model.data.get("windows"), flush=True)
    receive_photons(hub, {"files": [D + "DNA13bp_3.ptu"], "datasets": []}); drv.draw(4)
    data = hub.children["data"]
    print("rows:", {os.path.basename(p): r for p, r in data.source.rows().items()}, flush=True)
    t0 = time.time()
    wait(lambda: (data.source.calibration or {}).get("colours") and not data.job.busy, "calibration")
    print("calibration", round(time.time() - t0), "s; setup G:", {d: v.get("g_factor") for d, v in hub.setup_model.data["detectors"].items()}, flush=True)
    hub.select("data"); drv.draw(4); shot("data_selection_rows_simple")
    hub.select("selection"); drv.draw(4)
    sel = hub.children["selection"]; sel.run()
    wait(lambda: not sel.running and hub.context.bur_files, "search")
    print("bursts:", hub.context.bur_files, round(time.time() - t0), "s", flush=True)
    hub.select("mle"); drv.draw(4)
    mle = hub.children["mle"]
    wait(lambda: not mle.pending and all(mle.model.session.irf_np.get(d) is not None for d in mle.model.session.detectors), "mle ready")
    for _ in range(30):
        drv.draw(1); time.sleep(0.1)
    s = mle.model.session
    print("MLE G:", {d: s.detectors[d].get("g_factor") for d in s.detectors}, flush=True)
    keys = ("tau_ns", "tau_listed_ns", "rho_ns", "r0", "anisotropy_peak", "shift_vv", "shift_vh", "shift", "fit_chi2r", "fit_g", "fit_g_fitted", "fit_chi2r_g_free", "calibrated_on", "offset_bins", "dye", "files", "single_molecule", "reference_rate_khz", "burst_rate_khz", "warning")
    for d, v in s.shift_calibration.items():
        print("shift", d, {k: v.get(k) for k in keys}, flush=True)
    print("irf source:", s.irf_source, flush=True)
    # fit every burst (Next), then the shots
    mle.run_step()
    wait(lambda: not mle.pending and mle.model.burst_results, "fit")
    print("fit:", mle.model.status_text, round(time.time() - t0), "s", flush=True)
    s = mle.model.session
    for det in list(s.detectors):
        mle.model.current_detector = det
        drv.draw(4)
        mle.docks.focus("controls"); shot(f"mle_simple_fit_parameters_{det.replace('|', '')}")
        rows = {r["name"]: (r["start"], r["fixed"], r["result"]) for r in mle.model.shift_records()}
        print("rows", det, rows, "tau", mle.model.tau_result, flush=True)
        print("tip", det, mle.model.shift_tooltip("shift_sp").replace("\n", " | "), flush=True)
    mle.model.current_detector = "R|G"; drv.draw(3)
    mle.docks.focus("irf"); shot("mle_simple_irf_tab_RG")
    mle.model.current_detector = "G|G"; drv.draw(3)
    mle.docks.focus("irf"); shot("mle_simple_irf_tab_GG")
    # the reference fits, from the calibration record
    import numpy as np
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    dets = [d for d in s.detectors if d in s.shift_calibration]
    fig, axes = plt.subplots(2, len(dets), figsize=(5 * len(dets), 6), sharex=False, gridspec_kw={"height_ratios": [3, 1]})
    for i, d in enumerate(dets):
        e = s.shift_calibration[d]
        data_, model, res = (np.asarray(e[k], float) for k in ("fit_data", "fit_model", "fit_residuals"))
        n = data_.size // 2; lo, hi = e["fit_window"]
        x = np.arange(n)
        ax = axes[0, i]; ax.semilogy(x, data_[:n], ".", ms=2, color="0.3", label="VV"); ax.semilogy(x, data_[n:], ".", ms=2, color="tab:blue", label="VH")
        ax.semilogy(x, model[:n], "-", color="tab:red", lw=1); ax.semilogy(x, model[n:], "-", color="tab:orange", lw=1)
        ax.set_xlim(lo - 5, hi + 5); ax.set_ylim(max(1, data_[lo:hi].min() * 0.5), data_.max() * 2)
        ax.set_title(f"{d}: {e['dye']} on {e.get('calibrated_on', d)}, τ {e['tau_ns']:.2f} ns, ρ {e['rho_ns'] or 0:.2f} ns, r0 {e.get('r0') or 0.38:.2f}\nG {e['fit_g']:.3f}, VV {e['shift_vv']:+.2f}, VH {e['shift_vh']:+.2f} bins, χ²ᵣ {e['fit_chi2r']:.2f}", fontsize=9)
        ax.legend(fontsize=7)
        axes[1, i].plot(x, res[:n], lw=0.6, color="0.3"); axes[1, i].plot(x, res[n:], lw=0.6, color="tab:blue")
        axes[1, i].set_xlim(lo - 5, hi + 5); axes[1, i].axhline(0, color="k", lw=0.5); axes[1, i].set_xlabel("micro-time bin")
    fig.tight_layout(); fig.savefig(f"{OUT}/reference_fits.png", dpi=120)
    print("done", round(time.time() - t0), "s", flush=True)
    hub.close()


if __name__ == "__main__":
    main()
