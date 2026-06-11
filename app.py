"""
GNSS Positioning Quality Analyzer — Streamlit Dashboard

Phase 4 — Complete UX implementation with:
- RINEX 2 / RINEX 3 compatibility
- Septentrio RINEX cleaning fallback
- Safer observation field detection
- SNR + CMC signal quality analysis
- SPP positioning accuracy reporting
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
import threading
import requests
import georinex as gr
import matplotlib.pyplot as plt
import numpy as np
import streamlit as st

from src.gnss_pipeline.accuracy import (
    compute_accuracy_statistics,
    compute_position_error,
)
from src.gnss_pipeline.az_el import compute_az_el
from src.gnss_pipeline.cmc_analysis import (
    analyse_session_cmc,
    combine_snr_cmc_flags,
)
from src.gnss_pipeline.dop import compute_dop
from src.gnss_pipeline.ephemeris import (
    compute_satellite_position,
    get_first_valid_ephemeris,
)
from src.gnss_pipeline.nav_header_utils import get_nav_header_from_file
from src.gnss_pipeline.rinex_cleaner import clean_rinex_obs_file
from src.gnss_pipeline.snr_analysis import analyse_session_snr, get_epoch_weights
from src.gnss_pipeline.spp_solver import geodetic_to_ecef, solve_spp_epoch


SPEED_OF_LIGHT = 299_792_458.0
GPS_EPOCH = np.datetime64("1980-01-06T00:00:00", "s")

FLAG_COLORS = {
    "clean": "#1D9E75",
    "suspect": "#BA7517",
    "multipath": "#D85A30",
}


st.set_page_config(
    page_title="GNSS Quality Analyzer",
    page_icon="🛰️",
    layout="wide",
)

def _keep_alive():
    """Ping this app every 5 minutes to prevent Streamlit Cloud sleep."""
    import time
    while True:
        time.sleep(270)  # 4.5 minutes
        try:
            requests.get(
                "https://gnss-saha.streamlit.app",
                timeout=10,
                headers={"User-Agent": "KeepAlive/1.0"}
            )
        except Exception:
            pass

# Start keep-alive thread once per session
if "keep_alive_started" not in st.session_state:
    st.session_state["keep_alive_started"] = True
    t = threading.Thread(target=_keep_alive, daemon=True)
    t.start()

st.markdown(
    """
<style>
.quality-banner-good {
    background:#1a3d2b;border-left:4px solid #1D9E75;
    padding:12px 16px;border-radius:6px;margin-bottom:16px;
    color:#a8f0c6;font-size:15px;line-height:1.6;
}
.quality-banner-ok {
    background:#3d2e0a;border-left:4px solid #BA7517;
    padding:12px 16px;border-radius:6px;margin-bottom:16px;
    color:#f5d08a;font-size:15px;line-height:1.6;
}
.quality-banner-poor {
    background:#3d1010;border-left:4px solid #D85A30;
    padding:12px 16px;border-radius:6px;margin-bottom:16px;
    color:#f5a58a;font-size:15px;line-height:1.6;
}
.badge-green {
    background:#1D9E75;color:white;padding:4px 12px;
    border-radius:12px;font-size:14px;font-weight:500;
}
.badge-amber {
    background:#BA7517;color:white;padding:4px 12px;
    border-radius:12px;font-size:14px;font-weight:500;
}
.badge-red {
    background:#D85A30;color:white;padding:4px 12px;
    border-radius:12px;font-size:14px;font-weight:500;
}
.metric-card-green {
    background:#0d2018;border:1px solid #1D9E75;border-radius:8px;
    padding:14px 16px;margin-bottom:8px;
}
.metric-card-amber {
    background:#2a1f08;border:1px solid #BA7517;border-radius:8px;
    padding:14px 16px;margin-bottom:8px;
}
.metric-card-red {
    background:#2a0d0d;border:1px solid #D85A30;border-radius:8px;
    padding:14px 16px;margin-bottom:8px;
}
.metric-card-neutral {
    background:#1a1a2e;border:1px solid #444;border-radius:8px;
    padding:14px 16px;margin-bottom:8px;
}
.metric-title {
    font-size:11px;text-transform:uppercase;letter-spacing:0.06em;
    color:#aaa;margin-bottom:4px;
}
.metric-value-large {
    font-size:26px;font-weight:600;color:#fff;margin-bottom:2px;
}
.metric-value-medium {
    font-size:20px;font-weight:500;color:#fff;margin-bottom:2px;
}
.metric-desc {
    font-size:12px;color:#888;line-height:1.4;
}
.mode-beginner {
    background:#0f1b2d;border:1px solid #2d5a8e;border-radius:6px;
    padding:8px 12px;margin-bottom:12px;font-size:12px;color:#7eb8f5;
}
.mode-advanced {
    background:#1a1a2e;border:1px solid #534AB7;border-radius:6px;
    padding:8px 12px;margin-bottom:12px;font-size:12px;color:#a8a0f0;
}
.help-link-box {
    background:#1a1a2e;border:1px solid #444;border-radius:6px;
    padding:10px 12px;margin-top:8px;text-align:center;
}
.rinex-badge {
    background:#1a1a2e;border:1px solid #444;border-radius:4px;
    padding:4px 10px;font-size:11px;color:#888;display:inline-block;
    margin-bottom:8px;
}
</style>
""",
    unsafe_allow_html=True,
)


# ── RINEX loading and field detection ─────────────────────────────────────────

def detect_rinex_fields(obs) -> tuple[str, str | None, str | None, str]:
    """
    Detect pseudorange, SNR, and carrier phase field names.

    RINEX 3 commonly uses:
        C1C, S1C, L1C

    RINEX 2 commonly uses:
        C1 or P1, S1, L1

    Returns:
        pr_field, snr_field, carr_field, rinex_version_str

    Pseudorange is required.
    SNR and carrier phase are optional.
    """
    data_vars = set(obs.data_vars)

    pr_candidates = ["C1C", "C1W", "C1P", "C1", "P1"]
    pr_field = next((field for field in pr_candidates if field in data_vars), None)

    if pr_field is None:
        raise ValueError(
            "No supported L1 pseudorange field found. "
            f"Available observation types: {sorted(data_vars)}. "
            "Expected one of: C1C, C1W, C1P, C1, P1."
        )

    snr_candidates = ["S1C", "S1W", "S1P", "S1"]
    snr_field = next((field for field in snr_candidates if field in data_vars), None)

    carr_candidates = ["L1C", "L1W", "L1P", "L1"]
    carr_field = next((field for field in carr_candidates if field in data_vars), None)

    rinex_version = "RINEX 3" if any(field in data_vars for field in ["C1C", "C1W", "C1P"]) else "RINEX 2"

    return pr_field, snr_field, carr_field, rinex_version


def load_observation_with_fallback(obs_path, use="G"):
    """
    Load a RINEX observation file with georinex.

    First tries normal georinex loading.
    If georinex fails or loads 0 epochs, the file is cleaned using
    rinex_cleaner.py and loaded again.

    This is mainly needed for receiver-exported RINEX 3 files such as
    the Septentrio file we debugged.
    """
    obs_path = Path(obs_path)

    try:
        obs = gr.load(obs_path, use=use)

        if len(obs.time.values) > 0:
            return obs, obs_path, False

        print("georinex loaded 0 epochs. Trying cleaned RINEX fallback...")

    except Exception as e:
        print(f"Initial georinex observation load failed: {e}")
        print("Trying cleaned RINEX fallback...")

    cleaned_path = obs_path.with_name(obs_path.stem + "_cleaned_gps_1hz.rnx")

    clean_rinex_obs_file(
        input_path=obs_path,
        output_path=cleaned_path,
        gps_only=True,
        whole_seconds_only=True,
    )

    obs = gr.load(cleaned_path, use=use)

    if len(obs.time.values) == 0:
        raise ValueError(
            "Observation file still loaded 0 epochs after cleaning. "
            f"Cleaned file saved at: {cleaned_path}"
        )

    return obs, cleaned_path, True


def estimate_epoch_interval_seconds(obs) -> float:
    """
    Estimate the observation interval in seconds.

    Used for plot labels and session duration estimates.
    """
    times = obs.time.values

    if len(times) < 2:
        return 30.0

    dt = (times[1] - times[0]) / np.timedelta64(1, "s")

    if not np.isfinite(dt) or dt <= 0:
        return 30.0

    return float(dt)


# ── UI helpers ────────────────────────────────────────────────────────────────

def generate_session_summary(cep50, n_clean, n_suspect, n_multipath, mean_hdop):
    total = n_clean + n_suspect + n_multipath

    if total == 0:
        return (
            "The session processed positions, but no satellite quality flags were available.",
            "quality-banner-ok",
        )

    if cep50 < 20:
        acc_text = "excellent horizontal accuracy"
        banner_cls = "quality-banner-good"
    elif cep50 < 60:
        acc_text = "good horizontal accuracy"
        banner_cls = "quality-banner-good"
    elif cep50 < 150:
        acc_text = "moderate horizontal accuracy"
        banner_cls = "quality-banner-ok"
    else:
        acc_text = "poor horizontal accuracy — check your reference coordinates and data quality"
        banner_cls = "quality-banner-poor"

    if mean_hdop < 1.5:
        geom_text = "excellent satellite geometry"
    elif mean_hdop < 2.0:
        geom_text = "good satellite geometry"
    else:
        geom_text = "marginal satellite geometry"
        if banner_cls == "quality-banner-good":
            banner_cls = "quality-banner-ok"

    if n_multipath > 0:
        sig_text = f"{n_multipath} satellite(s) showed reflected signal contamination and were heavily discounted."
        banner_cls = "quality-banner-ok" if n_multipath <= 2 else "quality-banner-poor"
    elif n_suspect > total / 2:
        sig_text = "Several satellites showed minor signal quality issues."
    else:
        sig_text = f"{n_clean} of {total} satellites had fully reliable signals."

    return (
        f"This session produced <b>{acc_text}</b> with <b>{geom_text}</b>. {sig_text}",
        banner_cls,
    )


def cep50_badge(cep50):
    if cep50 < 50:
        return f'<span class="badge-green">Excellent — {cep50:.1f} m</span>'
    if cep50 < 150:
        return f'<span class="badge-amber">Good — {cep50:.1f} m</span>'
    return f'<span class="badge-red">Poor — {cep50:.1f} m</span>'


def metric_card(
    title,
    value,
    description,
    card_class="metric-card-neutral",
    value_class="metric-value-large",
):
    return f"""
    <div class="{card_class}">
        <div class="metric-title">{title}</div>
        <div class="{value_class}">{value}</div>
        <div class="metric-desc">{description}</div>
    </div>"""


def hdop_card_class(hdop):
    if hdop < 1.5:
        return "metric-card-green"
    if hdop < 2.0:
        return "metric-card-amber"
    return "metric-card-red"


def cep50_card_class(cep50):
    if cep50 < 50:
        return "metric-card-green"
    if cep50 < 150:
        return "metric-card-amber"
    return "metric-card-red"


def signal_summary_card(n_clean, n_suspect, n_multipath):
    total = n_clean + n_suspect + n_multipath

    if total == 0:
        return metric_card(
            "Signal quality",
            "Unavailable",
            "No SNR or CMC quality flags were available for this file.",
            "metric-card-neutral",
        )

    if n_multipath > 0:
        cls = "metric-card-red"
        desc = f"{n_multipath} satellite(s) had reflected signals — heavily discounted"
    elif n_suspect > 2:
        cls = "metric-card-amber"
        desc = f"{n_suspect} satellites showed minor signal issues — used with reduced weight"
    else:
        cls = "metric-card-green"
        desc = "All or most satellites had reliable signals"

    return metric_card("Signal quality", f"{n_clean}/{total} clean", desc, cls)


def satellite_table_html(flags, snr_results, cmc_results, advanced_mode):
    rows = ""

    for sat in sorted(flags.keys()):
        flag = flags[sat]
        snr_r = snr_results.get(sat, {}).get("result", {})
        cmc_r = cmc_results.get(sat, {}).get("result", {})

        mean_snr = snr_r.get("mean_snr", None)
        cmc_std = cmc_r.get("std", None)
        snr_flag = snr_r.get("flag", "—")
        cmc_flag = cmc_r.get("flag", "—")

        if flag == "clean":
            row_bg = "#0d2018"
            flag_html = '<span style="color:#1D9E75;font-weight:500">✓ Clean</span>'
            flag_desc = "Reliable — full weight in position calculation"
        elif flag == "suspect":
            row_bg = "#2a1f08"
            flag_html = '<span style="color:#BA7517;font-weight:500">⚠ Suspect</span>'
            flag_desc = "Minor issues — 30% weight in position calculation"
        else:
            row_bg = "#2a0d0d"
            flag_html = '<span style="color:#D85A30;font-weight:500">✗ Multipath</span>'
            flag_desc = "Signal reflected — 5% weight (nearly excluded)"

        snr_str = f"{mean_snr:.1f} dB-Hz" if mean_snr else "—"
        cmc_str = f"{cmc_std:.4f} m" if cmc_std else "—"

        if mean_snr:
            if mean_snr > 40:
                snr_color = "#1D9E75"
            elif mean_snr > 30:
                snr_color = "#BA7517"
            else:
                snr_color = "#D85A30"
        else:
            snr_color = "#888"

        if advanced_mode:
            rows += f"""
            <tr style="background:{row_bg}">
                <td style="padding:7px 10px;font-weight:500">{sat}</td>
                <td style="padding:7px 10px">{flag_html}</td>
                <td style="padding:7px 10px;color:#aaa;font-size:12px">{flag_desc}</td>
                <td style="padding:7px 10px;color:{snr_color}">{snr_str}</td>
                <td style="padding:7px 10px;color:#aaa;font-size:12px">{snr_flag}</td>
                <td style="padding:7px 10px;color:#aaa">{cmc_str}</td>
                <td style="padding:7px 10px;color:#aaa;font-size:12px">{cmc_flag}</td>
            </tr>"""
        else:
            rows += f"""
            <tr style="background:{row_bg}">
                <td style="padding:7px 10px;font-weight:500">{sat}</td>
                <td style="padding:7px 10px">{flag_html}</td>
                <td style="padding:7px 10px;color:#aaa;font-size:12px">{flag_desc}</td>
                <td style="padding:7px 10px;color:{snr_color}">{snr_str}</td>
            </tr>"""

    if advanced_mode:
        header = """
        <tr style="background:#1a1a2e;font-size:11px;
                   text-transform:uppercase;letter-spacing:0.05em;color:#999">
            <th style="padding:8px 10px;text-align:left">Satellite</th>
            <th style="padding:8px 10px;text-align:left">Quality flag</th>
            <th style="padding:8px 10px;text-align:left">What this means</th>
            <th style="padding:8px 10px;text-align:left">Signal strength</th>
            <th style="padding:8px 10px;text-align:left">SNR flag</th>
            <th style="padding:8px 10px;text-align:left">Multipath level (CMC std)</th>
            <th style="padding:8px 10px;text-align:left">CMC flag</th>
        </tr>"""
    else:
        header = """
        <tr style="background:#1a1a2e;font-size:11px;
                   text-transform:uppercase;letter-spacing:0.05em;color:#999">
            <th style="padding:8px 10px;text-align:left">Satellite</th>
            <th style="padding:8px 10px;text-align:left">Quality</th>
            <th style="padding:8px 10px;text-align:left">What this means</th>
            <th style="padding:8px 10px;text-align:left">Signal strength</th>
        </tr>"""

    return f"""
    <table style="width:100%;border-collapse:collapse;font-size:13px">
        <thead>{header}</thead>
        <tbody>{rows}</tbody>
    </table>"""


# ── Processing ────────────────────────────────────────────────────────────────

def process_session(obs_path, nav_path, ref_lat, ref_lon, ref_h, max_epochs):
    results = {
        "errors_h": [],
        "errors_v": [],
        "north_errors": [],
        "east_errors": [],
        "dop_list": [],
        "n_processed": 0,
        "snr_results": {},
        "cmc_results": {},
        "combined_flags": {},
        "rinex_version": "Unknown",
        "n_sats_total": 0,
        "epoch_interval_seconds": 30.0,
        "obs_was_cleaned": False,
        "actual_obs_path": str(obs_path),
    }

    obs, actual_obs_path, was_cleaned = load_observation_with_fallback(obs_path, use="G")
    nav = gr.load(nav_path, use="G")

    if len(obs.time.values) == 0:
        raise ValueError(
            "Observation file loaded successfully, but contains 0 epochs. "
            "Check that this is a valid RINEX observation file."
        )

    epochs = obs.time.values[:max_epochs]
    obs_limited = obs.sel(time=epochs)

    epoch_interval_seconds = estimate_epoch_interval_seconds(obs)

    results["epoch_interval_seconds"] = epoch_interval_seconds
    results["obs_was_cleaned"] = was_cleaned
    results["actual_obs_path"] = str(actual_obs_path)

    pr_field, snr_field, carr_field, rinex_version = detect_rinex_fields(obs)
    results["rinex_version"] = rinex_version

    gps_sats_all = [s for s in obs.sv.values if str(s).startswith("G")]
    results["n_sats_total"] = len(gps_sats_all)

    # Signal quality analysis.
    # SNR and CMC are useful, but not every file contains every needed field.
    if snr_field is not None:
        try:
            results["snr_results"] = analyse_session_snr(obs_limited, snr_field=snr_field)
        except Exception:
            results["snr_results"] = {}
    else:
        results["snr_results"] = {}

    try:
        results["cmc_results"] = analyse_session_cmc(obs_limited)
    except Exception:
        results["cmc_results"] = {}

    results["combined_flags"] = combine_snr_cmc_flags(
        results["snr_results"],
        results["cmc_results"],
    )

    if not results["combined_flags"]:
        results["combined_flags"] = {str(sat): "clean" for sat in gps_sats_all}

    sat_weights = get_epoch_weights(results["combined_flags"])
    nav_header = get_nav_header_from_file(nav)

    for epoch in epochs:
        epoch_s = epoch.astype("datetime64[s]")
        total_gps_seconds = float((epoch_s - GPS_EPOCH).astype(float))
        gps_time_of_week = total_gps_seconds % 604800.0
        gps_sats = [s for s in obs.sv.values if str(s).startswith("G")]

        pseudoranges = {}
        sat_positions = {}
        elevations = {}
        azimuths = {}
        ephemerides = {}
        eccentric_anomalies = {}

        for sat in gps_sats:
            try:
                pr = float(obs.sel(sv=sat, time=epoch)[pr_field].values)

                if np.isnan(pr) or pr < 1e6:
                    continue

                ep_time, eph = get_first_valid_ephemeris(nav, sat, gps_time_of_week)

                toe = float(eph.get("Toe", 0.0))
                travel_time = pr / SPEED_OF_LIGHT
                transmit_raw = gps_time_of_week - travel_time
                dt_raw = transmit_raw - toe

                if dt_raw < -302400:
                    transmit_time = transmit_raw + 604800.0
                elif dt_raw > 302400:
                    transmit_time = transmit_raw - 604800.0
                else:
                    transmit_time = transmit_raw

                x, y, z = compute_satellite_position(
                    eph,
                    transmit_time_seconds=transmit_time,
                )

                az, el, _ = compute_az_el(x, y, z, ref_lat, ref_lon, ref_h)

                sat_str = str(sat)

                pseudoranges[sat_str] = pr
                sat_positions[sat_str] = (x, y, z)
                elevations[sat_str] = np.radians(el)
                azimuths[sat_str] = np.radians(az)
                ephemerides[sat_str] = eph

                # Your current ephemeris function does not return eccentric anomaly,
                # so we keep this placeholder to match solve_spp_epoch().
                eccentric_anomalies[sat_str] = 0.0

            except Exception:
                continue

        if len(pseudoranges) < 4:
            continue

        toes = [float(ephemerides[s].get("Toe", 0.0)) for s in ephemerides]
        median_toe = float(np.median(toes))
        dt_check = gps_time_of_week - median_toe

        if dt_check < -302400:
            solver_gps_time = gps_time_of_week + 604800.0
        elif dt_check > 302400:
            solver_gps_time = gps_time_of_week - 604800.0
        else:
            solver_gps_time = gps_time_of_week

        x0_xyz = geodetic_to_ecef(ref_lat, ref_lon, ref_h)
        x0 = np.array([x0_xyz[0], x0_xyz[1], x0_xyz[2], 0.0])

        result = solve_spp_epoch(
            pseudoranges,
            sat_positions,
            ephemerides,
            eccentric_anomalies,
            elevations,
            azimuths,
            nav_header,
            gps_time=solver_gps_time,
            x0=x0,
            weights=sat_weights,
        )

        if not result["converged"]:
            continue

        error = compute_position_error(
            result["lat"],
            result["lon"],
            result["height"],
            ref_lat,
            ref_lon,
            ref_h,
        )

        dop = compute_dop(result["H"])

        results["errors_h"].append(error["horizontal_m"])
        results["errors_v"].append(error["vertical_m"])
        results["north_errors"].append(error["north_m"])
        results["east_errors"].append(error["east_m"])
        results["dop_list"].append(dop)
        results["n_processed"] += 1

    return results


def save_upload(uploaded_file) -> str:
    suffix = Path(uploaded_file.name).suffix

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as f:
        f.write(uploaded_file.read())
        return f.name


# ── Plotting ──────────────────────────────────────────────────────────────────

def make_scatter_plot(north_errors, east_errors, errors_h):
    cep50 = float(np.percentile(errors_h, 50))
    cep95 = float(np.percentile(errors_h, 95))

    theta = np.linspace(0, 2 * np.pi, 300)

    fig, ax = plt.subplots(figsize=(6, 6))

    ax.scatter(east_errors, north_errors, s=5, alpha=0.5, color="#534AB7")
    ax.plot(0, 0, "r+", markersize=14, markeredgewidth=2.5, label="True position")

    ax.plot(
        cep50 * np.cos(theta),
        cep50 * np.sin(theta),
        color="#1D9E75",
        linewidth=1.8,
        linestyle="--",
        label=f"CEP50 = {cep50:.1f} m",
    )

    ax.plot(
        cep95 * np.cos(theta),
        cep95 * np.sin(theta),
        color="#D85A30",
        linewidth=1.8,
        linestyle="--",
        label=f"CEP95 = {cep95:.1f} m",
    )

    ax.set_xlabel("East error (m)")
    ax.set_ylabel("North error (m)")
    ax.set_title("Position scatter")
    ax.legend(fontsize=8)
    ax.set_aspect("equal")
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    return fig


def make_error_timeseries(errors_h, errors_v, dop_list, epoch_interval_seconds=30.0):
    epochs_min = np.arange(len(errors_h)) * epoch_interval_seconds / 60.0
    hdop_vals = [d.get("HDOP", np.nan) for d in dop_list]

    fig, axes = plt.subplots(3, 1, figsize=(10, 7), sharex=True)

    axes[0].plot(epochs_min, errors_h, color="#534AB7", linewidth=0.9)
    axes[0].axhline(
        np.nanmean(errors_h),
        color="#1D9E75",
        linestyle="--",
        linewidth=0.8,
        label=f"Mean = {np.nanmean(errors_h):.1f} m",
    )
    axes[0].set_ylabel("Horizontal error (m)")
    axes[0].legend(fontsize=8)
    axes[0].grid(True, alpha=0.3)

    axes[1].plot(epochs_min, errors_v, color="#D85A30", linewidth=0.9)
    axes[1].axhline(
        np.nanmean(errors_v),
        color="#993C1D",
        linestyle="--",
        linewidth=0.8,
        label=f"Mean = {np.nanmean(errors_v):.1f} m",
    )
    axes[1].set_ylabel("Vertical error (m)")
    axes[1].legend(fontsize=8)
    axes[1].grid(True, alpha=0.3)

    axes[2].plot(epochs_min, hdop_vals, color="#BA7517", linewidth=0.9)
    axes[2].axhline(
        2.0,
        color="#854F0B",
        linestyle="--",
        linewidth=0.8,
        alpha=0.6,
        label="HDOP = 2.0 threshold",
    )
    axes[2].set_ylabel("HDOP")
    axes[2].set_xlabel("Time (minutes)")
    axes[2].legend(fontsize=8)
    axes[2].grid(True, alpha=0.3)

    plt.tight_layout()
    return fig


def make_snr_heatmap(snr_results):
    sats = sorted(snr_results.keys())

    if not sats:
        return None

    max_epochs = max(len(d["snr"]) for d in snr_results.values())

    matrix = np.full((len(sats), max_epochs), np.nan)

    for i, sat in enumerate(sats):
        snr = snr_results[sat]["snr"]
        matrix[i, : len(snr)] = snr

    fig, ax = plt.subplots(figsize=(12, 4))

    im = ax.imshow(
        matrix,
        aspect="auto",
        interpolation="nearest",
        cmap="RdYlGn",
        vmin=20,
        vmax=55,
    )

    plt.colorbar(im, ax=ax, label="SNR (dB-Hz)", shrink=0.8)

    ax.set_yticks(range(len(sats)))
    ax.set_yticklabels(sats, fontsize=9)

    for i, sat in enumerate(sats):
        flag = snr_results[sat]["result"]["flag"]
        color = FLAG_COLORS.get(flag, "gray")
        ax.get_yticklabels()[i].set_color(color)

    ax.set_xlabel("Epoch index")
    ax.set_title("Signal strength over time — green = strong, red = weak")

    plt.tight_layout()
    return fig


# ── Sidebar ──────────────────────────────────────────────────────────────────

with st.sidebar:
    logo_path = Path("assets/gge_transparent.png")

    if logo_path.exists():
        st.image(str(logo_path), use_container_width=True)
    else:
        st.markdown(
            """
        <div style="text-align:center;padding:8px 0 4px 0;
                    border:1px dashed #333;border-radius:6px;margin-bottom:8px">
            <div style="font-size:11px;color:#666;margin-bottom:2px">Department of</div>
            <div style="font-size:13px;font-weight:500;color:#ccc;line-height:1.4">
                Geodesy & Geomatics Engineering
            </div>
            <div style="font-size:11px;color:#666">University of New Brunswick</div>
        </div>
        """,
            unsafe_allow_html=True,
        )

    st.markdown("---")

    advanced_mode = st.toggle(
        "Advanced mode",
        value=False,
        help=(
            "OFF = Beginner mode: plain-English labels, simplified metrics, plot captions.\n"
            "ON = Advanced mode: full technical details, all metrics, SNR and CMC columns."
        ),
    )

    if advanced_mode:
        st.markdown(
            '<div class="mode-advanced">⚙ Advanced mode — full technical details</div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<div class="mode-beginner">📘 Beginner mode — plain-English summaries</div>',
            unsafe_allow_html=True,
        )

    st.markdown("---")

    obs_file = st.file_uploader(
        "GPS measurement file",
        type=[
            "rnx",
            "obs",
            "25o",
            "24o",
            "23o",
            "22o",
            "21o",
            "20o",
            "19o",
            "18o",
            "17o",
        ],
        help=(
            "The raw measurement file from your GPS session. "
            "Supports RINEX 2 and RINEX 3 formats. "
            "From NRCan: file ending in _MO.rnx. "
            "From Trimble/Leica/Septentrio: export RINEX 3 from the manufacturer software. "
            "From IGS archive: files ending in .21o, .22o etc. are RINEX 2."
        ),
    )

    nav_file = st.file_uploader(
        "Satellite orbit file",
        type=[
            "rnx",
            "25n",
            "24n",
            "23n",
            "22n",
            "21n",
            "20n",
            "19n",
            "18n",
            "17n",
        ],
        help=(
            "Describes where each GPS satellite was in space throughout the day. "
            "Download free from NRCan, IGS, CDDIS, or another GNSS archive for the same date. "
            "Must cover the same date as the observation file."
        ),
    )

    st.markdown("---")
    st.markdown("**Known true position of receiver**")
    st.caption(
        "The published coordinates of where the GPS receiver was located. "
        "Used to measure positioning accuracy."
    )

    ref_lat = st.number_input(
        "Latitude (decimal degrees)",
        value=45.933497,
        format="%.6f",
        help="Positive = North. Example: 45.933497",
    )

    ref_lon = st.number_input(
        "Longitude (decimal degrees)",
        value=-66.659879,
        format="%.6f",
        help="Negative = West. Example: -66.659879",
    )

    ref_h = st.number_input(
        "Ellipsoidal height (metres)",
        value=95.960,
        format="%.3f",
        help=(
            "Height above the WGS84 ellipsoid — not elevation above sea level. "
            "These differ by 10–50 m. Use the value from NRCan or IGS coordinates."
        ),
    )

    st.markdown("---")

    max_epochs = st.slider(
        "Observations to analyze",
        min_value=10,
        max_value=300,
        value=120,
        step=10,
        help=(
            "For 30-second files: 120 ≈ 1 hour. "
            "For 1-second files: 120 ≈ 2 minutes. "
            "More = better statistics but slower."
        ),
    )

    run_button = st.button(
        "Analyze session",
        type="primary",
        use_container_width=True,
    )

    st.markdown("---")

    st.markdown(
        '<div class="help-link-box">'
        '📖 <a href="/1_Understanding_Results" target="_self" '
        'style="color:#7eb8f5;text-decoration:none;font-size:13px">'
        'Understanding your results</a><br>'
        '<span style="font-size:11px;color:#666">'
        'Plain-English guide to every input, output, and GNSS term'
        "</span></div>",
        unsafe_allow_html=True,
    )


# ── Main panel ────────────────────────────────────────────────────────────────

st.title("GNSS Positioning Quality Analyzer")

st.caption(
    "Upload a GPS measurement file and satellite orbit file. "
    "Supports RINEX 2 and RINEX 3 formats. "
    "Receive a complete signal quality and positioning accuracy report."
)


if not run_button:
    st.info(
        "Upload your GPS files in the sidebar and click **Analyze session** to begin. "
        "New to GNSS? Use the **Understanding your results** link in the sidebar for a "
        "plain-English guide to every input and output."
    )

    st.subheader("How to use this tool")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown("**Step 1 — Get your files**")
        st.markdown(
            "Download GPS measurement and orbit files from "
            "[NRCan CORS](https://webapp.csrs-scrs.nrcan.gc.ca/geod/data-donnees/cacs-scca.php) "
            "or any IGS station. Supports RINEX 2 and RINEX 3."
        )

    with col2:
        st.markdown("**Step 2 — Enter your position**")
        st.markdown(
            "Enter the known true coordinates of the GPS receiver location. "
            "For NRCan stations, use the published reference coordinates."
        )

    with col3:
        st.markdown("**Step 3 — Run the analysis**")
        st.markdown(
            "Click Analyze session. Receive a complete quality report — "
            "accuracy statistics, signal quality flags, and position plots."
        )

    if not advanced_mode:
        st.divider()
        st.subheader("Quick guide to key terms")

        qa, qb, qc = st.columns(3)

        with qa:
            st.markdown("**CEP50**")
            st.markdown(
                "Your horizontal accuracy — the radius containing half your positions. "
                "Smaller is better."
            )

        with qb:
            st.markdown("**Signal quality flags**")
            st.markdown(
                "Each satellite rated Clean ✓, Suspect ⚠, or Multipath ✗. "
                "Multipath means signal bounced off a surface."
            )

        with qc:
            st.markdown("**HDOP**")
            st.markdown(
                "Satellite geometry score. Under 1.5 = excellent. "
                "Above 2.0 = satellites clustered — accuracy may be reduced."
            )


elif obs_file is None or nav_file is None:
    st.error(
        "Please upload both the GPS measurement file and the satellite orbit file in the sidebar."
    )


else:
    obs_path = save_upload(obs_file)
    nav_path = save_upload(nav_file)

    with st.spinner("Processing GPS data — this may take 1–3 minutes..."):
        try:
            results = process_session(
                obs_path,
                nav_path,
                ref_lat,
                ref_lon,
                ref_h,
                max_epochs,
            )

        except Exception as e:
            st.error(f"Processing failed: {e}")

            for p in [obs_path, nav_path]:
                try:
                    os.unlink(p)
                except Exception:
                    pass

            st.stop()

        finally:
            for p in [obs_path, nav_path]:
                try:
                    os.unlink(p)
                except Exception:
                    pass

    if results["n_processed"] < 4:
        st.error(
            "Not enough observations processed. "
            "Check that your reference coordinates are correct, "
            "both files cover the same date, and the observation file contains enough GPS data."
        )
        st.stop()

    eh = np.array(results["errors_h"])
    ev = np.array(results["errors_v"])

    stats = compute_accuracy_statistics(list(eh), list(ev))
    flags = results["combined_flags"]

    n_clean = sum(1 for f in flags.values() if f == "clean")
    n_suspect = sum(1 for f in flags.values() if f == "suspect")
    n_multipath = sum(1 for f in flags.values() if f == "multipath")

    dops = results["dop_list"]
    mean_hdop = np.nanmean([d.get("HDOP", np.nan) for d in dops])
    mean_pdop = np.nanmean([d.get("PDOP", np.nan) for d in dops])

    st.markdown(
        f'<div class="rinex-badge">📄 {results["rinex_version"]} · '
        f'{results["n_sats_total"]} GPS satellites in file · '
        f'{results["epoch_interval_seconds"]:.0f}s interval</div>',
        unsafe_allow_html=True,
    )

    if results.get("obs_was_cleaned", False):
        st.info(
            "This observation file needed preprocessing before georinex could read it. "
            "The app normalized RINEX epoch formatting, kept GPS-only observations, "
            "rewrote satellite counts, and removed duplicate satellite IDs."
        )

    summary_text, banner_cls = generate_session_summary(
        stats["CEP50"],
        n_clean,
        n_suspect,
        n_multipath,
        mean_hdop,
    )

    st.markdown(
        f'<div class="{banner_cls}">🛰️ &nbsp; {summary_text}</div>',
        unsafe_allow_html=True,
    )

    # ── Accuracy summary ──────────────────────────────────────────────────────

    st.subheader("Accuracy summary")

    if not advanced_mode:
        st.markdown(
            f"**Overall accuracy rating:** &nbsp; {cep50_badge(stats['CEP50'])}",
            unsafe_allow_html=True,
        )

        st.markdown("")

        r1c1, r1c2, r1c3 = st.columns(3)

        with r1c1:
            st.markdown(
                metric_card(
                    "Horizontal accuracy (CEP50)",
                    f"{stats['CEP50']:.1f} m",
                    "Half your positions were within this distance of the true location. Smaller = better.",
                    cep50_card_class(stats["CEP50"]),
                ),
                unsafe_allow_html=True,
            )

        with r1c2:
            st.markdown(
                metric_card(
                    "Worst-case accuracy (CEP95)",
                    f"{stats['CEP95']:.1f} m",
                    "95% of your positions were within this distance. Only 1 in 20 positions was worse.",
                    cep50_card_class(stats["CEP95"]),
                ),
                unsafe_allow_html=True,
            )

        with r1c3:
            st.markdown(
                signal_summary_card(n_clean, n_suspect, n_multipath),
                unsafe_allow_html=True,
            )

        r2c1, r2c2, r2c3 = st.columns(3)

        with r2c1:
            st.markdown(
                metric_card(
                    "Height accuracy (RMSE vertical)",
                    f"{stats['RMSE_V']:.1f} m",
                    "Average height error. Vertical is usually less accurate than horizontal in GPS "
                    "because satellites are only above the horizon.",
                    "metric-card-amber" if stats["RMSE_V"] < 200 else "metric-card-red",
                ),
                unsafe_allow_html=True,
            )

        with r2c2:
            hdop_label = (
                "Excellent ✓"
                if mean_hdop < 1.5
                else "Good ✓"
                if mean_hdop < 2.0
                else "Marginal ⚠"
            )

            st.markdown(
                metric_card(
                    "Satellite geometry (HDOP)",
                    f"{mean_hdop:.2f} — {hdop_label}",
                    "How well-spread the satellites were across the sky. "
                    "Under 1.5 = excellent. Above 2.0 = clustered, accuracy may be reduced.",
                    hdop_card_class(mean_hdop),
                ),
                unsafe_allow_html=True,
            )

        with r2c3:
            st.markdown(
                metric_card(
                    "Observations analyzed",
                    str(results["n_processed"]),
                    f"Each observation ≈ {results['epoch_interval_seconds']:.0f} second(s). "
                    f"{results['n_processed']} observations ≈ "
                    f"{results['n_processed'] * results['epoch_interval_seconds'] / 60:.1f} minutes of session.",
                    "metric-card-neutral",
                ),
                unsafe_allow_html=True,
            )

    else:
        c1, c2, c3, c4, c5 = st.columns(5)

        c1.metric(
            "Epochs processed",
            results["n_processed"],
            help="Number of observation epochs analyzed.",
        )
        c2.metric(
            "CEP50",
            f"{stats['CEP50']:.1f} m",
            help="Median horizontal error — 50th percentile of all position errors.",
        )
        c3.metric(
            "CEP95",
            f"{stats['CEP95']:.1f} m",
            help="95th percentile horizontal error.",
        )
        c4.metric(
            "RMSE_H",
            f"{stats['RMSE_H']:.1f} m",
            help="Root-mean-square horizontal error.",
        )
        c5.metric(
            "RMSE_V",
            f"{stats['RMSE_V']:.1f} m",
            help="Root-mean-square vertical error.",
        )

        d1, d2, d3, d4 = st.columns(4)

        d1.metric(
            "Mean HDOP",
            f"{mean_hdop:.2f}",
            help="Horizontal dilution of precision. Under 1.5 = excellent.",
        )
        d2.metric(
            "Mean PDOP",
            f"{mean_pdop:.2f}",
            help="3D position dilution of precision. Under 2.5 = good.",
        )
        d3.metric(
            "2DRMS",
            f"{stats.get('2DRMS', 0):.1f} m",
            help="Twice the distance RMS — commonly used as a horizontal accuracy metric.",
        )
        d4.metric(
            "Mean horizontal error",
            f"{stats.get('mean_H', 0):.1f} m",
            help="Simple arithmetic mean of all horizontal errors.",
        )

    st.divider()

    # ── Signal quality ────────────────────────────────────────────────────────

    st.subheader("Signal quality — per satellite")

    if not advanced_mode:
        st.caption(
            "Each GPS satellite is rated based on signal strength and multipath indicators. "
            "Green = clean, amber = suspect, red = multipath."
        )

    st.markdown(
        satellite_table_html(
            flags,
            results["snr_results"],
            results["cmc_results"],
            advanced_mode,
        ),
        unsafe_allow_html=True,
    )

    st.divider()

    # ── Plots ─────────────────────────────────────────────────────────────────

    st.subheader("Position analysis")

    col_scatter, col_snr = st.columns([1, 2])

    with col_scatter:
        fig_scatter = make_scatter_plot(
            results["north_errors"],
            results["east_errors"],
            list(eh),
        )

        st.pyplot(fig_scatter, use_container_width=True)
        plt.close(fig_scatter)

        if not advanced_mode:
            st.caption(
                "Each dot = one GPS position fix. Red cross = true location. "
                "Green circle = CEP50. Tighter clustering = better accuracy."
            )

    with col_snr:
        if results["snr_results"]:
            fig_snr = make_snr_heatmap(results["snr_results"])

            if fig_snr is not None:
                st.pyplot(fig_snr, use_container_width=True)
                plt.close(fig_snr)

                if not advanced_mode:
                    st.caption(
                        "Green = strong signal, red = weak. White gaps = missing data. "
                        "Row label color: green = clean, amber = suspect, red = multipath."
                    )
        else:
            st.info(
                "No SNR data was available in this file, so the signal-strength heatmap was skipped."
            )

    st.subheader("Error over time")

    fig_ts = make_error_timeseries(
        results["errors_h"],
        results["errors_v"],
        results["dop_list"],
        results["epoch_interval_seconds"],
    )

    st.pyplot(fig_ts, use_container_width=True)
    plt.close(fig_ts)

    if not advanced_mode:
        st.caption(
            "Top: horizontal distance from true location at each moment. "
            "Middle: height error. "
            "Bottom: satellite geometry score."
        )

    # ── Footer ────────────────────────────────────────────────────────────────

    st.divider()

    st.markdown(
        '<div style="text-align:center;color:#666;font-size:12px;padding:8px 0">'
        "GNSS Positioning Quality Analyzer · "
        "Dweep Saha · Department of Geodesy & Geomatics Engineering · "
        "University of New Brunswick · "
        '<a href="https://github.com/DweepSaha/gnss-rinex-pipeline-" '
        'style="color:#534AB7">GitHub</a>'
        "</div>",
        unsafe_allow_html=True,
    )