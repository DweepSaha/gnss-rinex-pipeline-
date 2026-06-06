"""
Multi-station comparison — Phase 4 Milestone 2

Runs the full Phase 3 pipeline on FRDN, ALGO, and HLFX stations
and compares accuracy, signal quality, and DOP values.
Run from project root.
"""
import georinex as gr
import numpy as np
from pathlib import Path
from src.gnss_pipeline.ephemeris import compute_satellite_position, get_first_valid_ephemeris
from src.gnss_pipeline.az_el import compute_az_el
from src.gnss_pipeline.spp_solver import solve_spp_epoch, geodetic_to_ecef
from src.gnss_pipeline.dop import compute_dop
from src.gnss_pipeline.accuracy import load_reference_coords, compute_position_error, compute_accuracy_statistics
from src.gnss_pipeline.nav_header_utils import get_nav_header_from_file
from src.gnss_pipeline.snr_analysis import analyse_session_snr, get_epoch_weights
from src.gnss_pipeline.cmc_analysis import analyse_session_cmc, combine_snr_cmc_flags

SPEED_OF_LIGHT = 299_792_458.0
GPS_EPOCH      = np.datetime64("1980-01-06T00:00:00", "s")
REF_FILE       = "data/reference/nrcan_reference_coords.json"

# Three stations — same date, same time window
STATIONS = [
    {
        "name":     "FRDN",
        "location": "Fredericton, NB",
        "obs":      "data/raw/extracted/FRDN00CAN_R_20251520000_01D_30S_MO.rnx",
        "nav":      "data/raw/extracted/FRDN00CAN_R_20251520000_01D_MN.rnx",
    },
    {
        "name":     "ALGO",
        "location": "Algonquin Park, ON",
        "obs":      "data/raw/extracted/ALGO00CAN_R_20251520000_01D_30S_MO.rnx",
        "nav":      "data/raw/extracted/ALGO00CAN_R_20251520000_01D_MN.rnx",
    },
    {
        "name":     "HLFX",
        "location": "Halifax, NS",
        "obs":      "data/raw/extracted/HLFX00CAN_R_20251520000_01D_30S_MO.rnx",
        "nav":      "data/raw/extracted/HLFX00CAN_R_20251520000_01D_MN.rnx",
    },
]

TLIM_START = "2025-06-01T00:00:30"
TLIM_END   = "2025-06-01T02:00:00"


def process_station(station: dict, ref: dict) -> dict:
    """Run full pipeline for one station. Returns statistics dict."""
    name = station["name"]
    print(f"\nProcessing {name} ({station['location']})...")

    obs = gr.load(station["obs"], use="G", tlim=[TLIM_START, TLIM_END])
    nav = gr.load(station["nav"], use="G")

    nav_header = get_nav_header_from_file(nav)

    # Signal quality analysis
    snr_results    = analyse_session_snr(obs, snr_field="S1C")
    cmc_results    = analyse_session_cmc(obs)
    combined_flags = combine_snr_cmc_flags(snr_results, cmc_results)
    sat_weights    = get_epoch_weights(combined_flags)

    n_clean     = sum(1 for f in combined_flags.values() if f == "clean")
    n_suspect   = sum(1 for f in combined_flags.values() if f == "suspect")
    n_multipath = sum(1 for f in combined_flags.values() if f == "multipath")
    print(f"  Quality: {n_clean} clean, {n_suspect} suspect, {n_multipath} multipath")

    errors_h  = []
    errors_v  = []
    north_err = []
    east_err  = []
    dop_list  = []

    for epoch_idx, epoch in enumerate(obs.time.values):
        if epoch_idx % 30 == 0:
            print(f"  Epoch {epoch_idx+1}/{len(obs.time.values)}...", end="\r")

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
                az, el, _ = compute_az_el(x, y, z, ref["lat"], ref["lon"], ref["height"])
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

        x0_xyz = geodetic_to_ecef(ref["lat"], ref["lon"], ref["height"])
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
            ref["lat"],    ref["lon"],    ref["height"]
        )
        dop = compute_dop(result["H"])

        errors_h.append(error["horizontal_m"])
        errors_v.append(error["vertical_m"])
        north_err.append(error["north_m"])
        east_err.append(error["east_m"])
        dop_list.append(dop)

    stats = compute_accuracy_statistics(errors_h, errors_v)
    mean_hdop = float(np.nanmean([d.get("HDOP", np.nan) for d in dop_list]))

    print(f"\n  CEP50={stats['CEP50']:.1f} m  RMSE_H={stats['RMSE_H']:.1f} m  "
          f"HDOP={mean_hdop:.2f}  epochs={stats['n_epochs']}")

    # Save for plotting
    Path("data/processed").mkdir(parents=True, exist_ok=True)
    np.save(f"data/processed/{name}_errors_h.npy",   np.array(errors_h))
    np.save(f"data/processed/{name}_errors_v.npy",   np.array(errors_v))
    np.save(f"data/processed/{name}_north_errors.npy", np.array(north_err))
    np.save(f"data/processed/{name}_east_errors.npy",  np.array(east_err))

    return {
        "name":       name,
        "location":   station["location"],
        "stats":      stats,
        "mean_hdop":  mean_hdop,
        "n_clean":    n_clean,
        "n_suspect":  n_suspect,
        "n_multipath": n_multipath,
        "errors_h":   errors_h,
        "errors_v":   errors_v,
        "north_err":  north_err,
        "east_err":   east_err,
    }


# ── Run all three stations ────────────────────────────────────────────────────
all_refs    = load_reference_coords(REF_FILE)
all_results = []

for station in STATIONS:
    ref    = all_refs[station["name"]]
    result = process_station(station, ref)
    all_results.append(result)

# ── Print comparison table ────────────────────────────────────────────────────
print()
print("=" * 72)
print("Multi-Station Accuracy Comparison — 2025-06-01 00:00–02:00 UTC")
print("=" * 72)
print(f"{'Station':<8} {'Location':<22} {'CEP50':>8} {'CEP95':>8} "
      f"{'RMSE_H':>8} {'RMSE_V':>8} {'HDOP':>6} {'Clean':>6}")
print("-" * 72)
for r in all_results:
    s = r["stats"]
    print(f"  {r['name']:<6} {r['location']:<22} "
          f"{s['CEP50']:>6.1f} m {s['CEP95']:>6.1f} m "
          f"{s['RMSE_H']:>6.1f} m {s['RMSE_V']:>6.1f} m "
          f"{r['mean_hdop']:>5.2f} {r['n_clean']:>5}/{r['n_clean']+r['n_suspect']+r['n_multipath']}")
print("=" * 72)

# ── Generate comparison plots ─────────────────────────────────────────────────
import matplotlib.pyplot as plt

Path("outputs/plots").mkdir(parents=True, exist_ok=True)

colors = ["#534AB7", "#1D9E75", "#D85A30"]
theta  = np.linspace(0, 2*np.pi, 300)

# Plot 1: Three scatter plots side by side
fig, axes = plt.subplots(1, 3, figsize=(18, 6))
fig.suptitle(
    "SPP Position Scatter — Three NRCan Stations\n2025-06-01 00:00–02:00 UTC",
    fontsize=13
)

all_errors = [r["errors_h"] for r in all_results]
max_err    = max(np.percentile(e, 99) for e in all_errors) * 1.2

for ax, r, color in zip(axes, all_results, colors):
    ne  = np.array(r["north_err"])
    ee  = np.array(r["east_err"])
    eh  = np.array(r["errors_h"])
    s   = r["stats"]

    ax.scatter(ee, ne, s=4, alpha=0.4, color=color)
    ax.plot(0, 0, "r+", markersize=12, markeredgewidth=2)
    ax.plot(s["CEP50"]*np.cos(theta), s["CEP50"]*np.sin(theta),
            color="#1D9E75", linewidth=1.5, linestyle="--",
            label=f"CEP50={s['CEP50']:.1f} m")
    ax.plot(s["CEP95"]*np.cos(theta), s["CEP95"]*np.sin(theta),
            color="#D85A30", linewidth=1.5, linestyle="--",
            label=f"CEP95={s['CEP95']:.1f} m")
    ax.set_title(f"{r['name']} — {r['location']}", fontsize=10)
    ax.set_xlabel("East error (m)", fontsize=9)
    ax.set_ylabel("North error (m)", fontsize=9)
    ax.legend(fontsize=8)
    ax.set_aspect("equal")
    ax.grid(True, alpha=0.3)
    ax.set_xlim(-max_err, max_err)
    ax.set_ylim(-max_err, max_err)

plt.tight_layout()
out = "outputs/plots/multistation_scatter.png"
plt.savefig(out, dpi=150, bbox_inches="tight")
plt.close()
print(f"Saved: {out}")

# Plot 2: Bar chart comparison
metrics   = ["CEP50", "CEP95", "RMSE_H", "RMSE_V"]
x         = np.arange(len(metrics))
w         = 0.25

fig, axes = plt.subplots(1, 2, figsize=(14, 5))
fig.suptitle("Multi-Station Accuracy Comparison — FRDN, ALGO, HLFX", fontsize=13)

for i, (r, color) in enumerate(zip(all_results, colors)):
    s    = r["stats"]
    vals = [s["CEP50"], s["CEP95"], s["RMSE_H"], s["RMSE_V"]]
    bars = axes[0].bar(x + i*w - w, vals, w,
                       label=f"{r['name']} ({r['location']})",
                       color=color, alpha=0.85, edgecolor="white")
    for bar, val in zip(bars, vals):
        axes[0].text(bar.get_x() + bar.get_width()/2,
                    bar.get_height() + 0.5,
                    f"{val:.0f}", ha="center", fontsize=7, color=color)

axes[0].set_xticks(x)
axes[0].set_xticklabels(metrics)
axes[0].set_ylabel("Error (m)", fontsize=11)
axes[0].set_title("Accuracy metrics by station", fontsize=11)
axes[0].legend(fontsize=8)
axes[0].grid(True, alpha=0.3, axis="y")

# HDOP comparison
hdop_vals = [r["mean_hdop"] for r in all_results]
names     = [r["name"] for r in all_results]
bar_hdop  = axes[1].bar(names, hdop_vals, color=colors,
                        alpha=0.85, edgecolor="white", width=0.4)
for bar, val in zip(bar_hdop, hdop_vals):
    axes[1].text(bar.get_x() + bar.get_width()/2,
                bar.get_height() + 0.01,
                f"{val:.2f}", ha="center", fontsize=10)
axes[1].set_ylabel("Mean HDOP", fontsize=11)
axes[1].set_title("Mean HDOP by station\n(lower = better satellite geometry)", fontsize=11)
axes[1].axhline(2.0, color="gray", linestyle="--", linewidth=0.8, alpha=0.6)
axes[1].grid(True, alpha=0.3, axis="y")

plt.tight_layout()
out = "outputs/plots/multistation_accuracy.png"
plt.savefig(out, dpi=150, bbox_inches="tight")
plt.close()
print(f"Saved: {out}")

print()
print("Milestone 2 complete.")
print("Two plots saved to outputs/plots/")