"""
GNSS Positioning Quality Analyzer — Streamlit Dashboard
Phase 4 Milestone 1

Upload a RINEX observation file and navigation file to receive
a complete signal quality and positioning accuracy report.
"""
import streamlit as st
import georinex as gr
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import tempfile
import os
from pathlib import Path

from src.gnss_pipeline.ephemeris import compute_satellite_position, get_first_valid_ephemeris
from src.gnss_pipeline.az_el import compute_az_el
from src.gnss_pipeline.spp_solver import solve_spp_epoch, geodetic_to_ecef
from src.gnss_pipeline.dop import compute_dop
from src.gnss_pipeline.accuracy import compute_position_error, compute_accuracy_statistics
from src.gnss_pipeline.nav_header_utils import get_nav_header_from_file
from src.gnss_pipeline.snr_analysis import analyse_session_snr, get_epoch_weights
from src.gnss_pipeline.cmc_analysis import analyse_session_cmc, combine_snr_cmc_flags
from src.gnss_pipeline.corrections import klobuchar_iono_correction

SPEED_OF_LIGHT = 299_792_458.0
GPS_EPOCH      = np.datetime64("1980-01-06T00:00:00", "s")

FLAG_COLORS = {"clean": "#1D9E75", "suspect": "#BA7517", "multipath": "#D85A30"}

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="GNSS Quality Analyzer",
    page_icon="🛰️",
    layout="wide",
)

st.title("GNSS Positioning Quality Analyzer")
st.caption(
    "Upload a RINEX 3 observation file and navigation file. "
    "Receive a complete signal quality and positioning accuracy report."
)

# ── Sidebar — inputs ──────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Session configuration")

    obs_file = st.file_uploader(
        "RINEX observation file (.rnx / .obs)",
        type=["rnx", "obs", "25o", "24o", "23o"],
        help="The file containing pseudorange and carrier phase measurements."
    )
    nav_file = st.file_uploader(
        "RINEX navigation file (.rnx)",
        type=["rnx", "25n", "24n", "23n"],
        help="The file containing satellite orbit and clock parameters."
    )

    st.divider()

    ref_lat = st.number_input(
        "Reference latitude (deg)",
        value=45.933497, format="%.6f",
        help="Known true position of the receiver — from NRCan or IGS."
    )
    ref_lon = st.number_input(
        "Reference longitude (deg)",
        value=-66.659879, format="%.6f"
    )
    ref_h = st.number_input(
        "Reference height (m)",
        value=95.960, format="%.3f"
    )

    st.divider()

    max_epochs = st.slider(
        "Maximum epochs to process",
        min_value=10, max_value=300, value=120, step=10,
        help="Fewer epochs = faster processing. 120 = 1 hour at 30-second sampling."
    )

    run_button = st.button("Analyze session", type="primary", use_container_width=True)

# ── Helper functions ──────────────────────────────────────────────────────────

def save_upload(uploaded_file) -> str:
    """Save a Streamlit uploaded file to a temp file and return the path."""
    suffix = Path(uploaded_file.name).suffix
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as f:
        f.write(uploaded_file.read())
        return f.name


def process_session(obs_path, nav_path, ref_lat, ref_lon, ref_h, max_epochs):
    """Run the full pipeline and return results dict."""
    results = {
        "errors_h": [], "errors_v": [],
        "north_errors": [], "east_errors": [],
        "dop_list": [], "n_processed": 0,
        "snr_results": {}, "cmc_results": {},
        "combined_flags": {},
    }

    obs = gr.load(obs_path, use="G")
    nav = gr.load(nav_path, use="G")

    # Limit epochs
    epochs = obs.time.values[:max_epochs]

    # Signal quality analysis
    obs_limited = obs.sel(time=epochs)
    results["snr_results"]     = analyse_session_snr(obs_limited, snr_field="S1C")
    results["cmc_results"]     = analyse_session_cmc(obs_limited)
    results["combined_flags"]  = combine_snr_cmc_flags(
        results["snr_results"], results["cmc_results"]
    )
    sat_weights = get_epoch_weights(results["combined_flags"])
    nav_header  = get_nav_header_from_file(nav)

    for epoch in epochs:
        epoch_s           = epoch.astype("datetime64[s]")
        total_gps_seconds = float((epoch_s - GPS_EPOCH).astype(float))
        gps_time_of_week  = total_gps_seconds % 604800.0

        gps_sats = [s for s in obs.sv.values if str(s).startswith("G")]

        pseudoranges        = {}
        sat_positions       = {}
        elevations          = {}
        azimuths            = {}
        ephemerides         = {}
        eccentric_anomalies = {}

        for sat in gps_sats:
            try:
                pr = float(obs.sel(sv=sat, time=epoch)["C1C"].values)
                if np.isnan(pr) or pr < 1e6:
                    continue
                ep_time, eph = get_first_valid_ephemeris(nav, sat, gps_time_of_week)
                toe          = float(eph.get("Toe", 0.0))
                travel_time  = pr / SPEED_OF_LIGHT
                transmit_raw = gps_time_of_week - travel_time
                dt_raw       = transmit_raw - toe
                if dt_raw < -302400:
                    transmit_time = transmit_raw + 604800.0
                elif dt_raw > 302400:
                    transmit_time = transmit_raw - 604800.0
                else:
                    transmit_time = transmit_raw
                x, y, z   = compute_satellite_position(eph, transmit_time_seconds=transmit_time)
                az, el, _ = compute_az_el(x, y, z, ref_lat, ref_lon, ref_h)
                pseudoranges[str(sat)]        = pr
                sat_positions[str(sat)]       = (x, y, z)
                elevations[str(sat)]          = np.radians(el)
                azimuths[str(sat)]            = np.radians(az)
                ephemerides[str(sat)]         = eph
                eccentric_anomalies[str(sat)] = 0.0
            except Exception:
                continue

        if len(pseudoranges) < 4:
            continue

        toes = [float(ephemerides[s].get("Toe", 0.0)) for s in ephemerides]
        median_toe = float(np.median(toes))
        dt_check   = gps_time_of_week - median_toe
        if dt_check < -302400:
            solver_gps_time = gps_time_of_week + 604800.0
        elif dt_check > 302400:
            solver_gps_time = gps_time_of_week - 604800.0
        else:
            solver_gps_time = gps_time_of_week

        x0_xyz = geodetic_to_ecef(ref_lat, ref_lon, ref_h)
        x0     = np.array([x0_xyz[0], x0_xyz[1], x0_xyz[2], 0.0])

        result = solve_spp_epoch(
            pseudoranges, sat_positions, ephemerides,
            eccentric_anomalies, elevations, azimuths,
            nav_header, gps_time=solver_gps_time,
            x0=x0, weights=sat_weights
        )

        if not result["converged"]:
            continue

        error = compute_position_error(
            result["lat"], result["lon"], result["height"],
            ref_lat, ref_lon, ref_h
        )
        dop = compute_dop(result["H"])

        results["errors_h"].append(error["horizontal_m"])
        results["errors_v"].append(error["vertical_m"])
        results["north_errors"].append(error["north_m"])
        results["east_errors"].append(error["east_m"])
        results["dop_list"].append(dop)
        results["n_processed"] += 1

    return results


def make_scatter_plot(north_errors, east_errors, errors_h, errors_v):
    """Generate position scatter plot."""
    cep50 = float(np.percentile(errors_h, 50))
    cep95 = float(np.percentile(errors_h, 95))
    theta = np.linspace(0, 2*np.pi, 300)

    fig, ax = plt.subplots(figsize=(6, 6))
    ax.scatter(east_errors, north_errors, s=5, alpha=0.5, color="#534AB7")
    ax.plot(0, 0, "r+", markersize=14, markeredgewidth=2.5, label="True position")
    ax.plot(cep50*np.cos(theta), cep50*np.sin(theta),
            color="#1D9E75", linewidth=1.8, linestyle="--",
            label=f"CEP50 = {cep50:.1f} m")
    ax.plot(cep95*np.cos(theta), cep95*np.sin(theta),
            color="#D85A30", linewidth=1.8, linestyle="--",
            label=f"CEP95 = {cep95:.1f} m")
    ax.set_xlabel("East error (m)")
    ax.set_ylabel("North error (m)")
    ax.set_title("Position scatter")
    ax.legend(fontsize=8)
    ax.set_aspect("equal")
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    return fig


def make_error_timeseries(errors_h, errors_v, dop_list):
    """Generate error time series plot."""
    epochs_min = np.arange(len(errors_h)) * 30 / 60
    hdop_vals  = [d.get("HDOP", np.nan) for d in dop_list]

    fig, axes = plt.subplots(3, 1, figsize=(10, 7), sharex=True)
    axes[0].plot(epochs_min, errors_h, color="#534AB7", linewidth=0.9)
    axes[0].axhline(np.nanmean(errors_h), color="#1D9E75",
                    linestyle="--", linewidth=0.8,
                    label=f"Mean = {np.nanmean(errors_h):.1f} m")
    axes[0].set_ylabel("Horizontal error (m)")
    axes[0].legend(fontsize=8)
    axes[0].grid(True, alpha=0.3)

    axes[1].plot(epochs_min, errors_v, color="#D85A30", linewidth=0.9)
    axes[1].axhline(np.nanmean(errors_v), color="#993C1D",
                    linestyle="--", linewidth=0.8,
                    label=f"Mean = {np.nanmean(errors_v):.1f} m")
    axes[1].set_ylabel("Vertical error (m)")
    axes[1].legend(fontsize=8)
    axes[1].grid(True, alpha=0.3)

    axes[2].plot(epochs_min, hdop_vals, color="#BA7517", linewidth=0.9)
    axes[2].axhline(2.0, color="#854F0B", linestyle="--",
                    linewidth=0.8, alpha=0.6, label="HDOP = 2.0")
    axes[2].set_ylabel("HDOP")
    axes[2].set_xlabel("Time (minutes)")
    axes[2].legend(fontsize=8)
    axes[2].grid(True, alpha=0.3)

    plt.tight_layout()
    return fig


def make_snr_heatmap(snr_results):
    """Generate SNR heatmap."""
    sats      = sorted(snr_results.keys())
    max_epochs = max(len(d["snr"]) for d in snr_results.values())
    matrix    = np.full((len(sats), max_epochs), np.nan)
    for i, sat in enumerate(sats):
        snr = snr_results[sat]["snr"]
        matrix[i, :len(snr)] = snr

    fig, ax = plt.subplots(figsize=(12, 4))
    im = ax.imshow(matrix, aspect="auto", interpolation="nearest",
                   cmap="RdYlGn", vmin=20, vmax=55)
    plt.colorbar(im, ax=ax, label="SNR (dB-Hz)", shrink=0.8)
    ax.set_yticks(range(len(sats)))
    ax.set_yticklabels(sats, fontsize=9)
    for i, sat in enumerate(sats):
        flag  = snr_results[sat]["result"]["flag"]
        color = FLAG_COLORS.get(flag, "gray")
        ax.get_yticklabels()[i].set_color(color)
    ax.set_xlabel("Epoch index")
    ax.set_title("SNR heatmap (satellite label color = quality flag)")
    plt.tight_layout()
    return fig


# ── Main panel ────────────────────────────────────────────────────────────────

if not run_button:
    st.info(
        "Upload a RINEX observation file and navigation file in the sidebar, "
        "set the known reference position, then click **Analyze session**."
    )
    st.subheader("How to use this tool")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown("**Step 1**\n\nDownload RINEX files from NRCan CORS network or any IGS station.")
    with col2:
        st.markdown("**Step 2**\n\nUpload both files and enter the station's known coordinates.")
    with col3:
        st.markdown("**Step 3**\n\nClick Analyze. Receive complete signal quality and accuracy report.")

elif obs_file is None or nav_file is None:
    st.error("Please upload both the observation file and the navigation file.")

else:
    # Save uploads to temp files
    obs_path = save_upload(obs_file)
    nav_path = save_upload(nav_file)

    ref = {"lat": ref_lat, "lon": ref_lon, "height": ref_h}

    with st.spinner("Processing RINEX data — this takes 1–3 minutes..."):
        try:
            results = process_session(
                obs_path, nav_path,
                ref_lat, ref_lon, ref_h,
                max_epochs
            )
        except Exception as e:
            st.error(f"Processing failed: {e}")
            os.unlink(obs_path)
            os.unlink(nav_path)
            st.stop()
        finally:
            # Clean up temp files
            for p in [obs_path, nav_path]:
                try:
                    os.unlink(p)
                except Exception:
                    pass

    if results["n_processed"] < 4:
        st.error("Not enough epochs converged. Check your files and reference coordinates.")
        st.stop()

    eh = np.array(results["errors_h"])
    ev = np.array(results["errors_v"])
    stats = compute_accuracy_statistics(list(eh), list(ev))

    # ── Metric cards ──
    st.subheader("Accuracy summary")
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Epochs processed", results["n_processed"])
    c2.metric("CEP50", f"{stats['CEP50']:.1f} m")
    c3.metric("CEP95", f"{stats['CEP95']:.1f} m")
    c4.metric("RMSE horizontal", f"{stats['RMSE_H']:.1f} m")
    c5.metric("RMSE vertical",   f"{stats['RMSE_V']:.1f} m")

    dops     = results["dop_list"]
    mean_hdop = np.nanmean([d.get("HDOP", np.nan) for d in dops])
    mean_pdop = np.nanmean([d.get("PDOP", np.nan) for d in dops])
    d1, d2   = st.columns(2)
    d1.metric("Mean HDOP", f"{mean_hdop:.2f}")
    d2.metric("Mean PDOP", f"{mean_pdop:.2f}")

    st.divider()

    # ── Signal quality summary ──
    st.subheader("Signal quality")
    flags  = results["combined_flags"]
    n_clean     = sum(1 for f in flags.values() if f == "clean")
    n_suspect   = sum(1 for f in flags.values() if f == "suspect")
    n_multipath = sum(1 for f in flags.values() if f == "multipath")

    q1, q2, q3 = st.columns(3)
    q1.metric("Clean satellites",     n_clean)
    q2.metric("Suspect satellites",   n_suspect)
    q3.metric("Multipath satellites", n_multipath)

    # Per-satellite quality table
    sat_rows = []
    for sat in sorted(flags.keys()):
        snr_r = results["snr_results"].get(sat, {}).get("result", {})
        cmc_r = results["cmc_results"].get(sat, {}).get("result", {})
        sat_rows.append({
            "Satellite":       sat,
            "Combined flag":   flags[sat],
            "SNR flag":        snr_r.get("flag", "—"),
            "Mean SNR (dB-Hz)": snr_r.get("mean_snr", "—"),
            "CMC flag":        cmc_r.get("flag", "—"),
            "CMC std (m)":     cmc_r.get("std", "—"),
        })

    import pandas as pd
    df = pd.DataFrame(sat_rows)
    st.dataframe(df, use_container_width=True, hide_index=True)

    st.divider()

    # ── Plots ──
    st.subheader("Position analysis")
    col_scatter, col_snr = st.columns([1, 2])

    with col_scatter:
        fig_scatter = make_scatter_plot(
            results["north_errors"], results["east_errors"], list(eh), list(ev)
        )
        st.pyplot(fig_scatter, use_container_width=True)
        plt.close()

    with col_snr:
        if results["snr_results"]:
            fig_snr = make_snr_heatmap(results["snr_results"])
            st.pyplot(fig_snr, use_container_width=True)
            plt.close()

    st.subheader("Error time series")
    fig_ts = make_error_timeseries(
        results["errors_h"], results["errors_v"], results["dop_list"]
    )
    st.pyplot(fig_ts, use_container_width=True)
    plt.close()

    st.success(
        f"Analysis complete. "
        f"CEP50 = {stats['CEP50']:.1f} m | "
        f"RMSE_H = {stats['RMSE_H']:.1f} m | "
        f"{n_clean} clean satellites, {n_suspect} suspect, {n_multipath} multipath."
    )