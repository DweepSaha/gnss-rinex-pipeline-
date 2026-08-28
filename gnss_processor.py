"""
Shared GNSS session-processing module.

This module holds the exact SPP processing logic (and the Plotly chart
builders it feeds) that originally live in app.py, copied here unchanged so
that both the Streamlit dashboard (app.py) and the FastAPI backend (api.py)
can call the same code without api.py importing Streamlit.

app.py is left completely untouched - it keeps its own copy of this logic
and keeps working standalone as a fallback UI. This module exists purely so
api.py has something importable that has no Streamlit dependency.
"""

from __future__ import annotations

from pathlib import Path

import georinex as gr
import numpy as np
import plotly.graph_objects as go

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


def compute_summary(results):
    """Compute the accuracy statistics and mean DOP values that the UI
    layers (app.py's main script, api.py's /analyze endpoint) derive from
    process_session()'s raw results dict."""
    eh = results["errors_h"]
    ev = results["errors_v"]
    stats = compute_accuracy_statistics(list(eh), list(ev))
    dops = results["dop_list"]
    mean_hdop = float(np.nanmean([d.get("HDOP", np.nan) for d in dops])) if dops else float("nan")
    mean_pdop = float(np.nanmean([d.get("PDOP", np.nan) for d in dops])) if dops else float("nan")
    return stats, mean_hdop, mean_pdop


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
