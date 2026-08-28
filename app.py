"""
GNSS Positioning Quality Analyzer - Streamlit Dashboard

Phase 4 - Complete UX implementation with:
- RINEX 2 / RINEX 3 compatibility
- Septentrio RINEX cleaning fallback
- Safer observation field detection
- SNR + CMC signal quality analysis
- SPP positioning accuracy reporting
- Plotly interactive charts
- PDF report download
"""

from __future__ import annotations

import os
import tempfile
import threading
from pathlib import Path

import georinex as gr
import numpy as np
import plotly.graph_objects as go
import requests
import streamlit as st
import streamlit.components.v1 as components

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
from src.gnss_pipeline.pdf_report import build_pdf_report
from src.gnss_pipeline.rinex_cleaner import clean_rinex_obs_file
from src.gnss_pipeline.snr_analysis import analyse_session_snr, get_epoch_weights
from src.gnss_pipeline.spp_solver import geodetic_to_ecef, solve_spp_epoch


SPEED_OF_LIGHT = 299_792_458.0
GPS_EPOCH = np.datetime64("1980-01-06T00:00:00", "s")

FLAG_COLORS = {
    "clean":     "#00ff88",
    "suspect":   "#ffaa00",
    "multipath": "#ff4444",
}

# Unified dark neon Plotly theme (mission control aesthetic)
NEON_GREEN = "#00ff88"
NEON_CYAN  = "#00d4ff"
NEON_AMBER = "#ffaa00"
NEON_RED   = "#ff4444"
NEON_PAPER_BG = "#000000"
NEON_PLOT_BG  = "#000000"
NEON_GRID     = "#111111"

st.set_page_config(
    page_title="GNSS Quality Analyzer",
    page_icon=":satellite:",
    layout="wide",
)


# Keep-alive thread

def _keep_alive():
    import time
    while True:
        time.sleep(270)
        try:
            requests.get(
                "https://gnss-saha.streamlit.app",
                timeout=10,
                headers={"User-Agent": "KeepAlive/1.0"},
            )
        except Exception:
            pass


if "keep_alive_started" not in st.session_state:
    st.session_state["keep_alive_started"] = True
    t = threading.Thread(target=_keep_alive, daemon=True)
    t.start()


# Google Font (Space Mono) - loaded via a plain <link> tag rather than a
# CSS @import inside <style>, since some Streamlit deployments block @import.
st.markdown(
    '<link href="https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&display=swap" '
    'rel="stylesheet">',
    unsafe_allow_html=True,
)

# Global CSS - unchanged from the original app, except .quality-banner-*,
# .metric-card-*, and .rinex-badge now use the neon glow colour palette.
# Nothing here touches Streamlit's own classes (.stApp, .stSidebar,
# .block-container, or any st-prefixed selector).

st.markdown("""
<style>
.quality-banner-good {
    background:#000000;border-left:4px solid #00ff88;
    padding:12px 16px;border-radius:6px;margin-bottom:16px;
    color:#8affc0;font-size:15px;line-height:1.6;
    font-family:'Space Mono',monospace;
}
.quality-banner-ok {
    background:#000000;border-left:4px solid #ffaa00;
    padding:12px 16px;border-radius:6px;margin-bottom:16px;
    color:#ffd98a;font-size:15px;line-height:1.6;
    font-family:'Space Mono',monospace;
}
.quality-banner-poor {
    background:#000000;border-left:4px solid #ff4444;
    padding:12px 16px;border-radius:6px;margin-bottom:16px;
    color:#ff9a8a;font-size:15px;line-height:1.6;
    font-family:'Space Mono',monospace;
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
    background:#000000;border:1px solid #00ff88;border-radius:8px;
    padding:14px 16px;margin-bottom:8px;
    box-shadow:0 0 8px #00ff8899, 0 0 16px #00ff8833;
    font-family:'Space Mono',monospace;
}
.metric-card-amber {
    background:#000000;border:1px solid #ffaa00;border-radius:8px;
    padding:14px 16px;margin-bottom:8px;
    box-shadow:0 0 8px #ffaa0099, 0 0 16px #ffaa0033;
    font-family:'Space Mono',monospace;
}
.metric-card-red {
    background:#000000;border:1px solid #ff4444;border-radius:8px;
    padding:14px 16px;margin-bottom:8px;
    box-shadow:0 0 8px #ff444499, 0 0 16px #ff444433;
    font-family:'Space Mono',monospace;
}
.metric-card-neutral {
    background:#000000;border:1px solid #00d4ff;border-radius:8px;
    padding:14px 16px;margin-bottom:8px;
    box-shadow:0 0 8px #00d4ff99, 0 0 16px #00d4ff33;
    font-family:'Space Mono',monospace;
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
    background:#000000;border:1px solid #00ff88;border-radius:4px;
    padding:4px 10px;font-size:11px;color:#00ff88;display:inline-block;
    margin-bottom:8px;font-family:'Space Mono',monospace;
}
</style>
""", unsafe_allow_html=True)


# RINEX loading and field detection

def detect_rinex_fields(obs):
    data_vars = set(obs.data_vars)
    pr_candidates = ["C1C", "C1W", "C1P", "C1", "P1"]
    pr_field = next((f for f in pr_candidates if f in data_vars), None)
    if pr_field is None:
        raise ValueError(
            "No supported L1 pseudorange field found. "
            f"Available: {sorted(data_vars)}. "
            "Expected one of: C1C, C1W, C1P, C1, P1."
        )
    snr_candidates  = ["S1C", "S1W", "S1P", "S1"]
    carr_candidates = ["L1C", "L1W", "L1P", "L1"]
    snr_field  = next((f for f in snr_candidates  if f in data_vars), None)
    carr_field = next((f for f in carr_candidates if f in data_vars), None)
    rinex_version = (
        "RINEX 3" if any(f in data_vars for f in ["C1C", "C1W", "C1P"])
        else "RINEX 2"
    )
    return pr_field, snr_field, carr_field, rinex_version


def load_observation_with_fallback(obs_path, use="G"):
    obs_path = Path(obs_path)
    try:
        obs = gr.load(obs_path, use=use)
        if len(obs.time.values) > 0:
            return obs, obs_path, False
        print("georinex loaded 0 epochs. Trying cleaned RINEX fallback...")
    except Exception as e:
        print(f"Initial georinex load failed: {e}. Trying cleaned RINEX fallback...")
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


def estimate_epoch_interval_seconds(obs):
    times = obs.time.values
    if len(times) < 2:
        return 30.0
    dt = (times[1] - times[0]) / np.timedelta64(1, "s")
    if not np.isfinite(dt) or dt <= 0:
        return 30.0
    return float(dt)


# UI helpers

def generate_session_summary(cep50, n_clean, n_suspect, n_multipath, mean_hdop):
    total = n_clean + n_suspect + n_multipath
    if total == 0:
        return (
            "The session processed positions, but no satellite quality flags were available.",
            "quality-banner-ok",
        )
    if cep50 < 20:
        acc_text   = "excellent horizontal accuracy"
        banner_cls = "quality-banner-good"
    elif cep50 < 60:
        acc_text   = "good horizontal accuracy"
        banner_cls = "quality-banner-good"
    elif cep50 < 150:
        acc_text   = "moderate horizontal accuracy"
        banner_cls = "quality-banner-ok"
    else:
        acc_text   = "poor horizontal accuracy - check your reference coordinates and data quality"
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
        sig_text   = f"{n_multipath} satellite(s) showed reflected signal contamination and were heavily discounted."
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
        return f'<span class="badge-green">Excellent - {cep50:.1f} m</span>'
    if cep50 < 150:
        return f'<span class="badge-amber">Good - {cep50:.1f} m</span>'
    return f'<span class="badge-red">Poor - {cep50:.1f} m</span>'


def metric_card(title, value, description,
                card_class="metric-card-neutral",
                value_class="metric-value-large"):
    return f"""
    <div class="{card_class}">
        <div class="metric-title">{title}</div>
        <div class="{value_class}">{value}</div>
        <div class="metric-desc">{description}</div>
    </div>"""


def build_animated_metrics_html(cep50, cep95, rmse_h, rmse_v, mean_hdop, n_processed):
    """Build a self-contained mission-control panel (Anime.js count-up) for
    st.components.v1.html(). Values are interpolated from Python; the JS/CSS
    wrapper is a plain string so none of its braces need escaping."""
    metrics = [
        ("CEP50",           cep50,               1, " M"),
        ("CEP95",           cep95,               1, " M"),
        ("RMSE HORIZONTAL", rmse_h,              1, " M"),
        ("RMSE VERTICAL",   rmse_v,              1, " M"),
        ("MEAN HDOP",       mean_hdop,           2, ""),
        ("OBSERVATIONS",    float(n_processed),  0, ""),
    ]
    cards = ""
    for label, value, decimals, suffix in metrics:
        safe_value = value if np.isfinite(value) else 0.0
        cards += f"""
        <div class="amc-card">
            <div class="amc-label">{label}</div>
            <div class="amc-value" data-target="{safe_value:.4f}"
                 data-decimals="{decimals}" data-suffix="{suffix}">0</div>
        </div>"""

    template = """
    <div class="amc-panel">
        <div class="amc-scanlines"></div>
        <div class="amc-grid">__CARDS__</div>
    </div>
    <style>
        html, body { margin:0; padding:0; background:#000000; }
        .amc-panel {
            font-family: 'Space Mono', 'Courier New', monospace;
            background:#000000; border:1px solid #00ff88; border-radius:2px;
            box-shadow: 0 0 8px #00ff8866, 0 0 20px #00ff8822;
            padding:16px; position:relative; overflow:hidden;
            height:240px; box-sizing:border-box;
        }
        .amc-scanlines {
            position:absolute; top:0; left:0; right:0; bottom:0;
            pointer-events:none;
            background: repeating-linear-gradient(
                to bottom,
                rgba(0,255,136,0.1) 0px, rgba(0,255,136,0.1) 1px,
                transparent 1px, transparent 2px
            );
        }
        .amc-grid {
            position:relative; z-index:1;
            display:grid;
            grid-template-columns: repeat(3, 1fr);
            grid-template-rows: repeat(2, 1fr);
            gap:12px; height:100%;
        }
        .amc-card {
            border:1px solid #0d2018; border-radius:2px;
            background:#000000;
            display:flex; flex-direction:column;
            align-items:center; justify-content:center;
            padding:8px; text-align:center;
            transition: box-shadow 0.2s ease;
        }
        .amc-card.amc-pulse {
            animation: amc-pulse-anim 0.9s ease-out;
        }
        @keyframes amc-pulse-anim {
            0%   { box-shadow: 0 0 0px #00ff8800; }
            35%  { box-shadow: 0 0 18px #00ff88cc, 0 0 32px #00ff8866; }
            100% { box-shadow: 0 0 0px #00ff8800; }
        }
        .amc-label {
            font-size:11px; text-transform:uppercase; letter-spacing:0.12em;
            color:#5fae86; margin-bottom:6px;
        }
        .amc-value {
            font-size:26px; font-weight:700; color:#00ff88;
            text-shadow: 0 0 10px #00ff8899;
        }
    </style>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/animejs/3.2.1/anime.min.js"></script>
    <script>
        document.querySelectorAll('.amc-value').forEach(function (el) {
            var target   = parseFloat(el.getAttribute('data-target'));
            var decimals = parseInt(el.getAttribute('data-decimals'), 10);
            var suffix   = el.getAttribute('data-suffix') || '';
            var counter  = { val: 0 };
            anime({
                targets: counter,
                val: target,
                duration: 1500,
                easing: 'easeOutExpo',
                update: function () {
                    el.innerHTML = counter.val.toFixed(decimals) + suffix;
                },
                complete: function () {
                    el.innerHTML = target.toFixed(decimals) + suffix;
                    var card = el.closest('.amc-card');
                    card.classList.add('amc-pulse');
                    setTimeout(function () {
                        card.classList.remove('amc-pulse');
                    }, 900);
                },
            });
        });
    </script>
    """
    return template.replace("__CARDS__", cards)


def hdop_card_class(hdop):
    if hdop < 1.5: return "metric-card-green"
    if hdop < 2.0: return "metric-card-amber"
    return "metric-card-red"


def cep50_card_class(cep50):
    if cep50 < 50:  return "metric-card-green"
    if cep50 < 150: return "metric-card-amber"
    return "metric-card-red"


def signal_summary_card(n_clean, n_suspect, n_multipath):
    total = n_clean + n_suspect + n_multipath
    if total == 0:
        return metric_card(
            "Signal quality", "Unavailable",
            "No SNR or CMC quality flags were available for this file.",
            "metric-card-neutral",
        )
    if n_multipath > 0:
        cls  = "metric-card-red"
        desc = f"{n_multipath} satellite(s) had reflected signals - heavily discounted"
    elif n_suspect > 2:
        cls  = "metric-card-amber"
        desc = f"{n_suspect} satellites showed minor signal issues - used with reduced weight"
    else:
        cls  = "metric-card-green"
        desc = "All or most satellites had reliable signals"
    return metric_card("Signal quality", f"{n_clean}/{total} clean", desc, cls)


def satellite_table_html(flags, snr_results, cmc_results, advanced_mode):
    rows = ""
    for sat in sorted(flags.keys()):
        flag     = flags[sat]
        snr_r    = snr_results.get(sat, {}).get("result", {})
        cmc_r    = cmc_results.get(sat, {}).get("result", {})
        mean_snr = snr_r.get("mean_snr", None)
        cmc_std  = cmc_r.get("std", None)
        snr_flag = snr_r.get("flag", "-")
        cmc_flag = cmc_r.get("flag", "-")
        if flag == "clean":
            row_bg    = "#0d2018"
            flag_html = '<span style="color:#1D9E75;font-weight:500">+ Clean</span>'
            flag_desc = "Reliable - full weight in position calculation"
        elif flag == "suspect":
            row_bg    = "#2a1f08"
            flag_html = '<span style="color:#BA7517;font-weight:500">! Suspect</span>'
            flag_desc = "Minor issues - 30% weight in position calculation"
        else:
            row_bg    = "#2a0d0d"
            flag_html = '<span style="color:#D85A30;font-weight:500">x Multipath</span>'
            flag_desc = "Signal reflected - 5% weight (nearly excluded)"
        snr_str   = f"{mean_snr:.1f} dB-Hz" if mean_snr else "-"
        cmc_str   = f"{cmc_std:.4f} m"      if cmc_std  else "-"
        snr_color = (
            "#1D9E75" if mean_snr and mean_snr > 40
            else "#BA7517" if mean_snr and mean_snr > 30
            else "#D85A30"
        ) if mean_snr else "#888"
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


# Processing

def process_session(obs_path, nav_path, ref_lat, ref_lon, ref_h, max_epochs):
    results = {
        "errors_h": [], "errors_v": [],
        "north_errors": [], "east_errors": [],
        "dop_list": [], "n_processed": 0,
        "snr_results": {}, "cmc_results": {},
        "combined_flags": {},
        "sat_sky_track": {},
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
    epochs      = obs.time.values[:max_epochs]
    obs_limited = obs.sel(time=epochs)
    interval = estimate_epoch_interval_seconds(obs)
    results["epoch_interval_seconds"] = interval
    results["obs_was_cleaned"]        = was_cleaned
    results["actual_obs_path"]        = str(actual_obs_path)
    pr_field, snr_field, carr_field, rinex_version = detect_rinex_fields(obs)
    results["rinex_version"] = rinex_version
    gps_sats_all = [s for s in obs.sv.values if str(s).startswith("G")]
    results["n_sats_total"] = len(gps_sats_all)
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
        results["snr_results"], results["cmc_results"],
    )
    if not results["combined_flags"]:
        results["combined_flags"] = {str(sat): "clean" for sat in gps_sats_all}
    sat_weights = get_epoch_weights(results["combined_flags"])
    nav_header  = get_nav_header_from_file(nav)
    for epoch in epochs:
        epoch_s           = epoch.astype("datetime64[s]")
        total_gps_seconds = float((epoch_s - GPS_EPOCH).astype(float))
        gps_time_of_week  = total_gps_seconds % 604800.0
        gps_sats          = [s for s in obs.sv.values if str(s).startswith("G")]
        pseudoranges = {}; sat_positions = {}; elevations = {}
        azimuths = {}; ephemerides = {}; eccentric_anomalies = {}
        for sat in gps_sats:
            try:
                pr = float(obs.sel(sv=sat, time=epoch)[pr_field].values)
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
                sat_str = str(sat)
                pseudoranges[sat_str]        = pr
                sat_positions[sat_str]       = (x, y, z)
                elevations[sat_str]          = np.radians(el)
                azimuths[sat_str]            = np.radians(az)
                ephemerides[sat_str]         = eph
                eccentric_anomalies[sat_str] = 0.0
                sky_track = results["sat_sky_track"].setdefault(
                    sat_str, {"az": [], "el": []}
                )
                sky_track["az"].append(float(az))
                sky_track["el"].append(float(el))
            except Exception:
                continue
        if len(pseudoranges) < 4:
            continue
        toes       = [float(ephemerides[s].get("Toe", 0.0)) for s in ephemerides]
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
            x0=x0, weights=sat_weights,
        )
        if not result["converged"]:
            continue
        error = compute_position_error(
            result["lat"], result["lon"], result["height"],
            ref_lat, ref_lon, ref_h,
        )
        dop = compute_dop(result["H"])
        results["errors_h"].append(error["horizontal_m"])
        results["errors_v"].append(error["vertical_m"])
        results["north_errors"].append(error["north_m"])
        results["east_errors"].append(error["east_m"])
        results["dop_list"].append(dop)
        results["n_processed"] += 1
    return results


def save_upload(uploaded_file):
    suffix = Path(uploaded_file.name).suffix
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as f:
        f.write(uploaded_file.read())
        return f.name


# Plotly charts

def _axis(title_text, title_color=NEON_CYAN, **kwargs):
    """Helper: build a clean Plotly axis dict with correct title syntax."""
    return dict(
        title=dict(text=title_text, font=dict(color=title_color)),
        tickfont=dict(color=NEON_GREEN),
        **kwargs,
    )


def make_scatter_plot(north_errors, east_errors, errors_h):
    cep50 = float(np.percentile(errors_h, 50))
    cep95 = float(np.percentile(errors_h, 95))
    theta = np.linspace(0, 2 * np.pi, 300)
    east_arr  = np.asarray(east_errors, dtype=float)
    north_arr = np.asarray(north_errors, dtype=float)
    horiz = np.sqrt(north_arr**2 + east_arr**2)
    n = len(east_arr)
    cmin = float(np.min(horiz)) if n else 0.0
    cmax = float(np.max(horiz)) if n else 1.0

    neon_colorscale = [[0.0, NEON_CYAN], [0.5, NEON_AMBER], [1.0, NEON_RED]]

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=cep95 * np.cos(theta), y=cep95 * np.sin(theta),
        mode="lines",
        line=dict(color=NEON_RED, width=1.5, dash="dash"),
        name=f"CEP95 = {cep95:.1f} m",
        hoverinfo="skip",
    ))
    fig.add_trace(go.Scatter(
        x=cep50 * np.cos(theta), y=cep50 * np.sin(theta),
        mode="lines",
        line=dict(color=NEON_GREEN, width=1.8, dash="dash"),
        name=f"CEP50 = {cep50:.1f} m",
        hoverinfo="skip",
    ))
    fig.add_trace(go.Scatter(
        x=east_arr, y=north_arr,
        mode="markers",
        marker=dict(
            color=horiz,
            colorscale=neon_colorscale, cmin=cmin, cmax=cmax,
            size=5, opacity=0.85,
            colorbar=dict(
                title=dict(text="Horiz. error (m)", font=dict(color=NEON_CYAN)),
                tickfont=dict(color=NEON_GREEN),
                thickness=12, len=0.6,
            ),
            showscale=True,
        ),
        name="Position fixes",
        customdata=np.column_stack([north_arr, east_arr, horiz]),
        hovertemplate=(
            "<b>Position fix</b><br>"
            "East error: %{x:.1f} m<br>"
            "North error: %{y:.1f} m<br>"
            "Horizontal error: %{customdata[2]:.1f} m"
            "<extra></extra>"
        ),
    ))
    fig.add_trace(go.Scatter(
        x=[0], y=[0], mode="markers",
        marker=dict(symbol="cross", size=14, color=NEON_RED,
                    line=dict(color=NEON_RED, width=2.5)),
        name="True position",
        hovertemplate="<b>True position</b><extra></extra>",
    ))

    # Animation: position fixes appear one-by-one. The base trace already
    # holds the full set (so static/PDF export is complete); pressing Play
    # replays the progressive reveal via frames.
    frames = []
    for i in range(1, n + 1):
        frames.append(go.Frame(
            name=str(i),
            traces=[2],
            data=[go.Scatter(
                x=east_arr[:i], y=north_arr[:i],
                marker=dict(
                    color=horiz[:i], colorscale=neon_colorscale,
                    cmin=cmin, cmax=cmax, size=5, opacity=0.85,
                ),
            )],
        ))
    fig.frames = frames

    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor=NEON_PAPER_BG, plot_bgcolor=NEON_PLOT_BG,
        title=dict(
            text=f"Position Scatter  |  CEP50 = {cep50:.1f} m  |  CEP95 = {cep95:.1f} m",
            font=dict(size=13, color=NEON_CYAN), x=0.5,
        ),
        xaxis=_axis("East error (m)",
                    showgrid=True, gridcolor=NEON_GRID,
                    zeroline=True, zerolinecolor="#333"),
        yaxis=_axis("North error (m)",
                    showgrid=True, gridcolor=NEON_GRID,
                    zeroline=True, zerolinecolor="#333",
                    scaleanchor="x"),
        legend=dict(bgcolor="#050508", bordercolor="#1a1a1a", borderwidth=1,
                    font=dict(color=NEON_GREEN, size=10)),
        margin=dict(l=50, r=20, t=50, b=50), height=480,
        updatemenus=[dict(
            type="buttons", showactive=False,
            x=0.02, y=1.12, xanchor="left", yanchor="top",
            bgcolor="#000000", bordercolor=NEON_GREEN,
            font=dict(color=NEON_GREEN),
            buttons=[dict(
                label="Play",
                method="animate",
                args=[None, dict(
                    frame=dict(duration=20, redraw=True),
                    transition=dict(duration=20),
                    fromcurrent=False, mode="immediate",
                )],
            )],
        )],
    )
    return fig


def make_error_timeseries(errors_h, errors_v, dop_list,
                          epoch_interval_seconds=30.0):
    epochs_min = np.arange(len(errors_h)) * epoch_interval_seconds / 60.0
    hdop_vals  = [d.get("HDOP", np.nan) for d in dop_list]
    mean_h     = float(np.nanmean(errors_h))
    mean_v     = float(np.nanmean(errors_v))
    cep50      = float(np.percentile(errors_h, 50))

    dim_cyan  = "rgba(0,212,255,0.45)"
    dim_red   = "rgba(255,68,68,0.45)"
    dim_amber = "rgba(255,170,0,0.45)"

    n = len(errors_h)

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=epochs_min, y=errors_h, mode="lines", name="Horizontal error",
        line=dict(color=NEON_CYAN, width=1.5),
        hovertemplate="Time: %{x:.2f} min<br>Horiz. error: %{y:.1f} m<extra></extra>",
        yaxis="y1",
    ))
    fig.add_hline(y=mean_h, line_dash="dash", line_color=dim_cyan, line_width=1,
                  annotation_text=f"Mean {mean_h:.1f} m",
                  annotation_position="top right",
                  annotation_font_color=dim_cyan, yref="y1")
    fig.add_hline(y=cep50, line_dash="dot", line_color=dim_amber, line_width=1,
                  annotation_text=f"CEP50 {cep50:.1f} m",
                  annotation_position="bottom right",
                  annotation_font_color=dim_amber, yref="y1")
    fig.add_trace(go.Scatter(
        x=epochs_min, y=errors_v, mode="lines", name="Vertical error",
        line=dict(color=NEON_RED, width=1.5),
        hovertemplate="Time: %{x:.2f} min<br>Vert. error: %{y:.1f} m<extra></extra>",
        yaxis="y2", visible="legendonly",
    ))
    fig.add_hline(y=mean_v, line_dash="dash", line_color=dim_red, line_width=1,
                  annotation_text=f"Mean V {mean_v:.1f} m",
                  annotation_position="top left",
                  annotation_font_color=dim_red, yref="y2")
    fig.add_trace(go.Scatter(
        x=epochs_min, y=hdop_vals, mode="lines", name="HDOP",
        line=dict(color=NEON_AMBER, width=1.5),
        hovertemplate="Time: %{x:.2f} min<br>HDOP: %{y:.2f}<extra></extra>",
        yaxis="y3",
    ))
    fig.add_hline(y=2.0, line_dash="dash", line_color="#666", line_width=1,
                  annotation_text="HDOP 2.0 threshold",
                  annotation_position="top right",
                  annotation_font_color="#666", yref="y3")

    # Animation: draw the three lines left-to-right, one more point per frame.
    # Base traces already hold the full series (static/PDF export stays
    # complete); Play replays the progressive draw-on.
    frames = []
    for i in range(1, n + 1):
        frames.append(go.Frame(
            name=str(i),
            traces=[0, 1, 2],
            data=[
                go.Scatter(x=epochs_min[:i], y=errors_h[:i]),
                go.Scatter(x=epochs_min[:i], y=errors_v[:i]),
                go.Scatter(x=epochs_min[:i], y=hdop_vals[:i]),
            ],
        ))
    fig.frames = frames

    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor=NEON_PAPER_BG, plot_bgcolor=NEON_PLOT_BG,
        title=dict(
            text="Error and Geometry Over Time",
            font=dict(size=13, color=NEON_CYAN), x=0.5,
        ),
        xaxis=_axis("Time (minutes)",
                    showgrid=True, gridcolor=NEON_GRID,
                    domain=[0, 0.85]),
        yaxis=_axis("Horizontal error (m)", title_color=NEON_CYAN,
                    showgrid=True, gridcolor=NEON_GRID),
        yaxis2=_axis("Vertical error (m)", title_color=NEON_RED,
                     overlaying="y", side="right",
                     position=0.86, showgrid=False),
        yaxis3=_axis("HDOP", title_color=NEON_AMBER,
                     overlaying="y", side="right",
                     position=1.0, showgrid=False),
        legend=dict(
            bgcolor="#050508", bordercolor="#1a1a1a", borderwidth=1,
            font=dict(color=NEON_GREEN, size=10),
            orientation="h", y=-0.18,
        ),
        hovermode="x unified",
        margin=dict(l=60, r=130, t=50, b=70), height=420,
        updatemenus=[dict(
            type="buttons", showactive=False,
            x=0.02, y=1.15, xanchor="left", yanchor="top",
            bgcolor="#000000", bordercolor=NEON_GREEN,
            font=dict(color=NEON_GREEN),
            buttons=[dict(
                label="Play",
                method="animate",
                args=[None, dict(
                    frame=dict(duration=20, redraw=True),
                    transition=dict(duration=20),
                    fromcurrent=False, mode="immediate",
                )],
            )],
        )],
    )
    return fig


def make_snr_heatmap(snr_results):
    sats = sorted(snr_results.keys())
    if not sats:
        return None
    max_epochs = max(len(d["snr"]) for d in snr_results.values())
    matrix     = np.full((len(sats), max_epochs), np.nan)
    for i, sat in enumerate(sats):
        snr = snr_results[sat]["snr"]
        matrix[i, :len(snr)] = snr
    ticktext = [
        f'<span style="color:{FLAG_COLORS.get(snr_results[sat]["result"]["flag"], "#888")}">{sat}</span>'
        for sat in sats
    ]
    fig = go.Figure(data=go.Heatmap(
        z=matrix,
        x=list(range(max_epochs)),
        y=sats,
        colorscale=[
            [0.0, NEON_RED],
            [0.5, NEON_AMBER],
            [1.0, NEON_GREEN],
        ],
        zmin=20, zmax=55,
        colorbar=dict(
            title=dict(text="SNR (dB-Hz)", font=dict(color=NEON_GREEN)),
            tickfont=dict(color=NEON_GREEN),
            thickness=14,
        ),
        hovertemplate=(
            "Satellite: %{y}<br>"
            "Epoch: %{x}<br>"
            "SNR: %{z:.1f} dB-Hz"
            "<extra></extra>"
        ),
    ))
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor=NEON_PAPER_BG, plot_bgcolor=NEON_PLOT_BG,
        title=dict(
            text="Signal Strength Over Time (SNR)",
            font=dict(size=13, color=NEON_CYAN), x=0.5,
        ),
        xaxis=_axis("Epoch index", showgrid=False),
        yaxis=dict(
            tickmode="array",
            tickvals=list(range(len(sats))),
            ticktext=ticktext,
            tickfont=dict(color=NEON_GREEN, size=10),
            showgrid=False,
        ),
        margin=dict(l=60, r=20, t=50, b=50),
        height=max(300, len(sats) * 28),
    )
    return fig


def make_sky_plot(sat_sky_track, combined_flags, snr_results):
    """Polar sky plot: r = 90 - elevation (deg), theta = azimuth (deg, compass)."""
    if not sat_sky_track:
        return None

    fig = go.Figure()

    for flag_name in ["clean", "suspect", "multipath"]:
        fig.add_trace(go.Scatterpolar(
            r=[np.nan], theta=[np.nan], mode="lines",
            line=dict(color=FLAG_COLORS[flag_name], width=2.5),
            name=flag_name.capitalize(),
            legendgroup=flag_name, showlegend=True,
            hoverinfo="skip",
        ))

    sat_trace_indices = {}
    sat_r_theta = {}

    for sat in sorted(sat_sky_track.keys()):
        track = sat_sky_track[sat]
        az_list = track.get("az", [])
        el_list = track.get("el", [])
        n = len(az_list)
        if n == 0:
            continue

        flag  = combined_flags.get(sat, "clean")
        color = FLAG_COLORS.get(flag, "#00ff88")
        r_vals = [90.0 - el for el in el_list]

        snr_arr = np.full(n, np.nan)
        raw_snr = snr_results.get(sat, {}).get("snr") if snr_results else None
        if raw_snr is not None:
            raw_snr = np.asarray(raw_snr, dtype=float)
            k = min(n, len(raw_snr))
            snr_arr[:k] = raw_snr[:k]

        hovertext = []
        for i in range(n):
            if np.isnan(snr_arr[i]):
                snr_str = "N/A"
            else:
                snr_str = f"{snr_arr[i]:.1f} dB-Hz"
            hovertext.append(
                f"Satellite: {sat}<br>"
                f"Azimuth: {az_list[i]:.1f} deg<br>"
                f"Elevation: {el_list[i]:.1f} deg<br>"
                f"SNR: {snr_str}"
            )

        line_idx = len(fig.data)
        fig.add_trace(go.Scatterpolar(
            r=r_vals, theta=az_list, mode="lines",
            line=dict(color=color, width=1.8),
            name=flag.capitalize(),
            legendgroup=flag,
            showlegend=False,
            hovertext=hovertext, hoverinfo="text",
        ))
        marker_idx = len(fig.data)
        fig.add_trace(go.Scatterpolar(
            r=[r_vals[-1]], theta=[az_list[-1]], mode="markers",
            marker=dict(color=color, size=10, line=dict(color="#000", width=1)),
            legendgroup=flag, showlegend=False,
            hovertext=[hovertext[-1]], hoverinfo="text",
        ))
        mid = n // 2
        text_idx = len(fig.data)
        fig.add_trace(go.Scatterpolar(
            r=[r_vals[mid]], theta=[az_list[mid]], mode="text",
            text=[sat], textposition="top center",
            textfont=dict(color=color, size=10),
            legendgroup=flag, showlegend=False,
            hoverinfo="skip",
        ))

        sat_trace_indices[sat] = (line_idx, marker_idx, text_idx)
        sat_r_theta[sat] = (r_vals, az_list, mid)

    mask_theta = np.linspace(0, 360, 181)
    fig.add_trace(go.Scatterpolar(
        r=[75.0] * len(mask_theta), theta=mask_theta, mode="lines",
        line=dict(color="#444", width=1, dash="dash"),
        name="15 deg elevation mask",
        showlegend=False, hoverinfo="skip",
    ))

    # Animation: reveal each satellite arc progressively, one full arc per
    # frame. Base traces already hold the complete tracks (static/PDF export
    # stays complete); Play replays the progressive draw-on.
    valid_sats = list(sat_trace_indices.keys())
    n_sats = len(valid_sats)
    frames = []
    for k in range(0, n_sats + 1):
        frame_data = []
        frame_traces = []
        for idx, sat in enumerate(valid_sats):
            line_idx, marker_idx, text_idx = sat_trace_indices[sat]
            r_vals, az_list, mid = sat_r_theta[sat]
            if idx < k:
                frame_data.append(go.Scatterpolar(r=r_vals, theta=az_list))
                frame_data.append(go.Scatterpolar(r=[r_vals[-1]], theta=[az_list[-1]]))
                frame_data.append(go.Scatterpolar(r=[r_vals[mid]], theta=[az_list[mid]]))
            else:
                frame_data.append(go.Scatterpolar(r=[], theta=[]))
                frame_data.append(go.Scatterpolar(r=[], theta=[]))
                frame_data.append(go.Scatterpolar(r=[], theta=[]))
            frame_traces.extend([line_idx, marker_idx, text_idx])
        frames.append(go.Frame(name=str(k), data=frame_data, traces=frame_traces))
    fig.frames = frames

    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor=NEON_PAPER_BG, plot_bgcolor=NEON_PLOT_BG,
        title=dict(
            text="Satellite Sky Plot",
            font=dict(size=13, color=NEON_CYAN), x=0.5,
        ),
        polar=dict(
            bgcolor="#000000",
            radialaxis=dict(
                range=[0, 90],
                tickvals=[0, 15, 30, 45, 60, 75, 90],
                ticktext=["90", "75", "60", "45", "30", "15", "0"],
                tickfont=dict(color=NEON_GREEN, size=9),
                gridcolor=NEON_GREEN, linecolor=NEON_GREEN,
                gridwidth=0.4,
            ),
            angularaxis=dict(
                rotation=90, direction="clockwise",
                tickfont=dict(color=NEON_GREEN, size=9),
                gridcolor=NEON_GREEN, linecolor=NEON_GREEN,
                gridwidth=0.4,
            ),
        ),
        legend=dict(bgcolor="#050508", bordercolor="#1a1a1a", borderwidth=1,
                    font=dict(color=NEON_GREEN, size=10)),
        margin=dict(l=30, r=30, t=50, b=30),
        width=500, height=500,
        updatemenus=[dict(
            type="buttons", showactive=False,
            x=0.02, y=1.12, xanchor="left", yanchor="top",
            bgcolor="#000000", bordercolor=NEON_GREEN,
            font=dict(color=NEON_GREEN),
            buttons=[dict(
                label="Play",
                method="animate",
                args=[None, dict(
                    frame=dict(duration=300, redraw=True),
                    transition=dict(duration=100),
                    fromcurrent=False, mode="immediate",
                )],
            )],
        )],
    )
    return fig


# Sidebar

with st.sidebar:
    logo_path = Path("assets/gge_transparent.png")
    if logo_path.exists():
        st.image(str(logo_path), use_container_width=True)
    else:
        st.markdown("""
        <div style="text-align:center;padding:8px 0 4px 0;
                    border:1px dashed #333;border-radius:6px;margin-bottom:8px">
            <div style="font-size:11px;color:#666;margin-bottom:2px">Department of</div>
            <div style="font-size:13px;font-weight:500;color:#ccc;line-height:1.4">
                Geodesy & Geomatics Engineering
            </div>
            <div style="font-size:11px;color:#666">University of New Brunswick</div>
        </div>
        """, unsafe_allow_html=True)
    st.markdown("---")
    advanced_mode = st.toggle(
        "Advanced mode", value=False,
        help=(
            "OFF = Beginner mode: plain-English labels, simplified metrics.\n"
            "ON = Advanced mode: full technical details, all metrics, SNR and CMC columns."
        ),
    )
    if advanced_mode:
        st.markdown(
            '<div class="mode-advanced">Advanced mode - full technical details</div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<div class="mode-beginner">Beginner mode - plain-English summaries</div>',
            unsafe_allow_html=True,
        )
    st.markdown("---")
    obs_file = st.file_uploader(
        "GPS measurement file",
        type=[
            "rnx", "obs",
            "25o", "24o", "23o", "22o", "21o", "20o", "19o", "18o", "17o",
            "25O", "24O", "23O", "22O", "21O", "20O", "19O", "18O", "17O",
        ],
        help=(
            "The raw measurement file from your GPS session. "
            "Supports RINEX 2 and RINEX 3. "
            "From NRCan: file ending in _MO.rnx."
        ),
    )
    nav_file = st.file_uploader(
        "Satellite orbit file",
        type=[
            "rnx",
            "25n", "24n", "23n", "22n", "21n", "20n", "19n", "18n", "17n",
            "25N", "24N", "23N", "22N", "21N", "20N", "19N", "18N", "17N",
            "23g", "23G", "23l", "23L", "23c", "23C",
        ],
        help=(
            "Describes where each GPS satellite was in space throughout the day. "
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
        "Latitude (decimal degrees)", value=45.933497, format="%.6f",
        help="Positive = North. Example: 45.933497",
    )
    ref_lon = st.number_input(
        "Longitude (decimal degrees)", value=-66.659879, format="%.6f",
        help="Negative = West. Example: -66.659879",
    )
    ref_h = st.number_input(
        "Ellipsoidal height (metres)", value=95.960, format="%.3f",
        help=(
            "Height above the WGS84 ellipsoid - not elevation above sea level. "
            "These differ by 10-50 m. Use the value from NRCan or IGS coordinates."
        ),
    )
    st.markdown("---")
    max_epochs = st.slider(
        "Observations to analyze",
        min_value=10, max_value=300, value=120, step=10,
        help=(
            "For 30-second files: 120 = 1 hour. "
            "For 1-second files: 120 = 2 minutes. "
            "More = better statistics but slower."
        ),
    )
    run_button = st.button(
        "Analyze session", type="primary", use_container_width=True,
    )
    st.markdown("---")
    st.markdown(
        '<div class="help-link-box">'
        '<a href="/1_Understanding_Results" target="_self" '
        'style="color:#7eb8f5;text-decoration:none;font-size:13px">'
        'Understanding your results</a><br>'
        '<span style="font-size:11px;color:#666">'
        'Plain-English guide to every input, output, and GNSS term'
        '</span></div>',
        unsafe_allow_html=True,
    )


# Main panel

st.title("GNSS Positioning Quality Analyzer")
st.caption(
    "Upload a GPS measurement file and satellite orbit file. "
    "Supports RINEX 2 and RINEX 3 formats. "
    "Receive a complete signal quality and positioning accuracy report."
)

if not run_button:
    st.info(
        "Upload your GPS files in the sidebar and click **Analyze session** to begin. "
        "New to GNSS? Use the **Understanding your results** link in the sidebar."
    )
    st.subheader("How to use this tool")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown("**Step 1 - Get your files**")
        st.markdown(
            "Download GPS measurement and orbit files from "
            "[NRCan CORS](https://webapp.csrs-scrs.nrcan.gc.ca/geod/data-donnees/cacs-scca.php) "
            "or any IGS station. Supports RINEX 2 and RINEX 3."
        )
    with col2:
        st.markdown("**Step 2 - Enter your position**")
        st.markdown(
            "Enter the known true coordinates of the GPS receiver location. "
            "For NRCan stations, use the published reference coordinates."
        )
    with col3:
        st.markdown("**Step 3 - Run the analysis**")
        st.markdown(
            "Click Analyze session. Receive a complete quality report - "
            "accuracy statistics, signal quality flags, and interactive plots."
        )
    if not advanced_mode:
        st.divider()
        st.subheader("Quick guide to key terms")
        qa, qb, qc = st.columns(3)
        with qa:
            st.markdown("**CEP50**")
            st.markdown(
                "Your horizontal accuracy - the radius containing half your positions. "
                "Smaller is better."
            )
        with qb:
            st.markdown("**Signal quality flags**")
            st.markdown(
                "Each satellite rated Clean, Suspect, or Multipath. "
                "Multipath means signal bounced off a surface."
            )
        with qc:
            st.markdown("**HDOP**")
            st.markdown(
                "Satellite geometry score. Under 1.5 = excellent. "
                "Above 2.0 = satellites clustered - accuracy may be reduced."
            )

elif obs_file is None or nav_file is None:
    st.error(
        "Please upload both the GPS measurement file and the satellite orbit file in the sidebar."
    )

else:
    obs_path = save_upload(obs_file)
    nav_path = save_upload(nav_file)

    with st.spinner("Processing GPS data - this may take 1-3 minutes..."):
        try:
            results = process_session(
                obs_path, nav_path, ref_lat, ref_lon, ref_h, max_epochs,
            )
        except Exception as e:
            st.error(f"Processing failed: {e}")
            for p in [obs_path, nav_path]:
                try: os.unlink(p)
                except Exception: pass
            st.stop()
        finally:
            for p in [obs_path, nav_path]:
                try: os.unlink(p)
                except Exception: pass

    if results["n_processed"] < 4:
        st.error(
            "Not enough observations processed. "
            "Check that your reference coordinates are correct, "
            "both files cover the same date, and the observation file contains GPS data."
        )
        st.stop()

    eh    = np.array(results["errors_h"])
    ev    = np.array(results["errors_v"])
    stats = compute_accuracy_statistics(list(eh), list(ev))
    flags = results["combined_flags"]

    n_clean     = sum(1 for f in flags.values() if f == "clean")
    n_suspect   = sum(1 for f in flags.values() if f == "suspect")
    n_multipath = sum(1 for f in flags.values() if f == "multipath")

    dops      = results["dop_list"]
    mean_hdop = np.nanmean([d.get("HDOP", np.nan) for d in dops])
    mean_pdop = np.nanmean([d.get("PDOP", np.nan) for d in dops])

    st.markdown(
        f'<div class="rinex-badge">File: {results["rinex_version"]} | '
        f'{results["n_sats_total"]} GPS satellites | '
        f'{results["epoch_interval_seconds"]:.0f}s interval</div>',
        unsafe_allow_html=True,
    )

    if results.get("obs_was_cleaned", False):
        st.info(
            "This observation file needed preprocessing before georinex could read it. "
            "The app normalised RINEX epoch formatting, kept GPS-only observations, "
            "rewrote satellite counts, and removed duplicate satellite IDs."
        )

    summary_text, banner_cls = generate_session_summary(
        stats["CEP50"], n_clean, n_suspect, n_multipath, mean_hdop,
    )
    status_labels = {
        "quality-banner-good": "NOMINAL",
        "quality-banner-ok":   "CAUTION",
        "quality-banner-poor": "ALERT",
    }
    status_label = status_labels.get(banner_cls, "CAUTION")
    st.markdown(
        f'<div class="{banner_cls}">'
        f'<div style="font-size:11px;letter-spacing:0.15em;text-transform:uppercase;'
        f'opacity:0.8;margin-bottom:6px">MISSION STATUS: {status_label}</div>'
        f'{summary_text}'
        f'</div>',
        unsafe_allow_html=True,
    )

    st.subheader("Accuracy summary")

    components.html(
        build_animated_metrics_html(
            stats["CEP50"], stats["CEP95"], stats["RMSE_H"], stats["RMSE_V"],
            mean_hdop, results["n_processed"],
        ),
        height=280,
    )

    if not advanced_mode:
        st.markdown(
            f"**Overall accuracy rating:** &nbsp; {cep50_badge(stats['CEP50'])}",
            unsafe_allow_html=True,
        )
        st.markdown("")
        r1c1, r1c2, r1c3 = st.columns(3)
        with r1c1:
            st.markdown(metric_card(
                "Horizontal accuracy (CEP50)", f"{stats['CEP50']:.1f} m",
                "Half your positions were within this distance of the true location. Smaller = better.",
                cep50_card_class(stats["CEP50"]),
            ), unsafe_allow_html=True)
        with r1c2:
            st.markdown(metric_card(
                "Worst-case accuracy (CEP95)", f"{stats['CEP95']:.1f} m",
                "95% of your positions were within this distance. Only 1 in 20 positions was worse.",
                cep50_card_class(stats["CEP95"]),
            ), unsafe_allow_html=True)
        with r1c3:
            st.markdown(signal_summary_card(n_clean, n_suspect, n_multipath),
                        unsafe_allow_html=True)
        r2c1, r2c2, r2c3 = st.columns(3)
        with r2c1:
            st.markdown(metric_card(
                "Height accuracy (RMSE vertical)", f"{stats['RMSE_V']:.1f} m",
                "Average height error. Vertical is usually less accurate than horizontal in GPS "
                "because satellites are only above the horizon.",
                "metric-card-amber" if stats["RMSE_V"] < 200 else "metric-card-red",
            ), unsafe_allow_html=True)
        with r2c2:
            hdop_label = (
                "Excellent" if mean_hdop < 1.5
                else "Good" if mean_hdop < 2.0
                else "Marginal"
            )
            st.markdown(metric_card(
                "Satellite geometry (HDOP)",
                f"{mean_hdop:.2f} - {hdop_label}",
                "How well-spread the satellites were across the sky. "
                "Under 1.5 = excellent. Above 2.0 = clustered, accuracy may be reduced.",
                hdop_card_class(mean_hdop),
            ), unsafe_allow_html=True)
        with r2c3:
            st.markdown(metric_card(
                "Observations analyzed", str(results["n_processed"]),
                f"Each observation = {results['epoch_interval_seconds']:.0f} second(s). "
                f"{results['n_processed']} observations = "
                f"{results['n_processed'] * results['epoch_interval_seconds'] / 60:.1f} minutes.",
                "metric-card-neutral",
            ), unsafe_allow_html=True)
    else:
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Epochs processed", results["n_processed"])
        c2.metric("CEP50", f"{stats['CEP50']:.1f} m")
        c3.metric("CEP95", f"{stats['CEP95']:.1f} m")
        c4.metric("RMSE_H", f"{stats['RMSE_H']:.1f} m")
        c5.metric("RMSE_V", f"{stats['RMSE_V']:.1f} m")
        d1, d2, d3, d4 = st.columns(4)
        d1.metric("Mean HDOP", f"{mean_hdop:.2f}")
        d2.metric("Mean PDOP", f"{mean_pdop:.2f}")
        d3.metric("2DRMS", f"{stats.get('2DRMS', 0):.1f} m")
        d4.metric("Mean horizontal error", f"{stats.get('mean_H', 0):.1f} m")

    st.divider()

    st.subheader("Signal quality - per satellite")
    if not advanced_mode:
        st.caption(
            "Each GPS satellite is rated based on signal strength and multipath indicators. "
            "Green = clean, amber = suspect, red = multipath."
        )
    st.markdown(
        satellite_table_html(flags, results["snr_results"],
                             results["cmc_results"], advanced_mode),
        unsafe_allow_html=True,
    )

    st.divider()

    st.subheader("Position analysis")
    col_scatter, col_snr = st.columns([1, 2])

    with col_scatter:
        fig_scatter = make_scatter_plot(
            results["north_errors"], results["east_errors"], list(eh)
        )
        st.plotly_chart(fig_scatter, use_container_width=True)
        if not advanced_mode:
            st.caption(
                "Hover over any point to see exact error values. "
                "Colour shows horizontal error magnitude."
            )

    with col_snr:
        if results["snr_results"]:
            fig_snr = make_snr_heatmap(results["snr_results"])
            if fig_snr is not None:
                st.plotly_chart(fig_snr, use_container_width=True)
                if not advanced_mode:
                    st.caption(
                        "Hover over any cell to see exact SNR value. "
                        "Green = strong signal. Red = weak."
                    )
        else:
            fig_snr = None
            st.info(
                "No SNR data was available in this file. "
                "Signal quality assessed using CMC analysis only."
            )

    st.subheader("Satellite sky tracks")
    fig_sky = make_sky_plot(
        results.get("sat_sky_track", {}),
        results["combined_flags"],
        results["snr_results"],
    )
    if fig_sky is not None:
        st.plotly_chart(fig_sky, use_container_width=True)
        if not advanced_mode:
            st.caption(
                "Each line traces a satellite's path across the sky during the session. "
                "Centre = directly overhead. Edge = horizon. "
                "Dashed circle = 15 degree elevation mask. "
                "Dot = satellite's final tracked position."
            )
    else:
        st.info("No satellite sky track data was available for this session.")

    st.subheader("Error over time")
    fig_ts = make_error_timeseries(
        results["errors_h"], results["errors_v"],
        results["dop_list"], results["epoch_interval_seconds"],
    )
    st.plotly_chart(fig_ts, use_container_width=True)
    if not advanced_mode:
        st.caption(
            "Hover over any point to see exact values. "
            "Toggle Vertical error in the legend to show/hide it."
        )

    st.divider()
    st.subheader("Download report")
    if not advanced_mode:
        st.caption(
            "Download a PDF report containing all accuracy metrics, "
            "signal quality flags, plots, and a plain-English interpretation."
        )
    with st.spinner("Generating PDF report..."):
        try:
            pdf_bytes = build_pdf_report(
                results        = results,
                stats          = stats,
                flags          = flags,
                mean_hdop      = mean_hdop,
                mean_pdop      = mean_pdop,
                ref_lat        = ref_lat,
                ref_lon        = ref_lon,
                ref_h          = ref_h,
                obs_filename   = obs_file.name if obs_file else "",
                nav_filename   = nav_file.name if nav_file else "",
                fig_scatter    = fig_scatter,
                fig_sky        = fig_sky,
                fig_snr        = fig_snr if results["snr_results"] else None,
                fig_timeseries = fig_ts,
            )
            st.download_button(
                label="Download PDF Report",
                data=pdf_bytes,
                file_name="GNSS_Quality_Report.pdf",
                mime="application/pdf",
                use_container_width=True,
                type="primary",
            )
        except Exception as e:
            st.error(f"PDF generation failed: {e}")

    st.divider()
    st.markdown(
        '<div style="text-align:center;color:#666;font-size:12px;padding:8px 0">'
        "GNSS Positioning Quality Analyzer | "
        "Dweep Saha | Department of Geodesy & Geomatics Engineering | "
        "University of New Brunswick | "
        '<a href="https://github.com/DweepSaha/gnss-rinex-pipeline-" '
        'style="color:#534AB7">GitHub</a>'
        "</div>",
        unsafe_allow_html=True,
    )