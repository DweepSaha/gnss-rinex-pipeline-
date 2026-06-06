"""
Phase 3 Milestone 3 — Weighted SPP comparison test.
Runs SPP with uniform weights vs quality-based weights
and compares accuracy for FRDN.
Run from project root.
"""
import math
import georinex as gr
import numpy as np
from pathlib import Path

from src.gnss_pipeline.ephemeris import compute_satellite_position, get_first_valid_ephemeris
from src.gnss_pipeline.az_el import compute_az_el
from src.gnss_pipeline.spp_solver import solve_spp_epoch, geodetic_to_ecef, ecef_to_geodetic
from src.gnss_pipeline.dop import compute_dop
from src.gnss_pipeline.accuracy import load_reference_coords, compute_position_error, compute_accuracy_statistics
from src.gnss_pipeline.snr_analysis import analyse_session_snr, get_epoch_weights
from src.gnss_pipeline.cmc_analysis import analyse_session_cmc, combine_snr_cmc_flags

SPEED_OF_LIGHT = 299_792_458.0

OBS_FILE = "data/raw/extracted/FRDN00CAN_R_20251520000_01D_30S_MO.rnx"
NAV_FILE = "data/raw/extracted/FRDN00CAN_R_20251520000_01D_MN.rnx"
REF_FILE = "data/reference/nrcan_reference_coords.json"

TLIM_START = "2025-06-01T00:00:30"
TLIM_END   = "2025-06-01T02:00:00"

print("Loading files...")
obs = gr.load(OBS_FILE, use="G", tlim=[TLIM_START, TLIM_END])
nav = gr.load(NAV_FILE, use="G")
ref = load_reference_coords(REF_FILE)["FRDN"]

print(f"Epochs: {len(obs.time.values)}")
print()

# Run signal quality analysis once for the whole session
print("Running signal quality analysis...")
snr_results  = analyse_session_snr(obs, snr_field="S1C")
cmc_results  = analyse_session_cmc(obs)
combined_flags = combine_snr_cmc_flags(snr_results, cmc_results)
weights        = get_epoch_weights(combined_flags)

print("Quality-based weights:")
for sat in sorted(weights.keys()):
    flag = combined_flags.get(sat, "unknown")
    print(f"  {sat}: weight={weights[sat]:.2f}  ({flag})")
print()

gps_epoch = np.datetime64("1980-01-06T00:00:00", "s")

# Storage for both runs
unweighted_errors_h = []
unweighted_errors_v = []
weighted_errors_h   = []
weighted_errors_v   = []

print("Processing epochs...")

for epoch_idx, epoch in enumerate(obs.time.values):
    if epoch_idx % 20 == 0:
        print(f"  Epoch {epoch_idx+1}/{len(obs.time.values)}...", end="\r")

    epoch_s           = epoch.astype("datetime64[s]")
    total_gps_seconds = float((epoch_s - gps_epoch).astype(float))
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

            ep_time, eph = get_first_valid_ephemeris(nav, sat)
            toe          = float(eph.get("Toe", 0.0))
            travel_time  = pr / SPEED_OF_LIGHT

            if toe > 302400 and gps_time_of_week < 302400:
                transmit_time = gps_time_of_week + 604800.0 - travel_time
            else:
                transmit_time = gps_time_of_week - travel_time

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

    first_toe = float(list(ephemerides.values())[0].get("Toe", 0.0))
    solver_gps_time = (
        gps_time_of_week + 604800.0
        if first_toe > 302400 and gps_time_of_week < 302400
        else gps_time_of_week
    )

    x0_xyz = geodetic_to_ecef(ref["lat"], ref["lon"], ref["height"])
    x0     = np.array([x0_xyz[0], x0_xyz[1], x0_xyz[2], 0.0])

    # Run 1 — unweighted (uniform weights, same as Phase 2)
    result_uw = solve_spp_epoch(
        pseudoranges, sat_positions, ephemerides,
        eccentric_anomalies, elevations, azimuths,
        {}, gps_time=solver_gps_time, x0=x0,
        weights=None
    )

    # Run 2 — weighted (quality-based weights)
    result_w = solve_spp_epoch(
        pseudoranges, sat_positions, ephemerides,
        eccentric_anomalies, elevations, azimuths,
        {}, gps_time=solver_gps_time, x0=x0,
        weights=weights
    )

    if result_uw["converged"]:
        err = compute_position_error(
            result_uw["lat"], result_uw["lon"], result_uw["height"],
            ref["lat"],       ref["lon"],       ref["height"]
        )
        unweighted_errors_h.append(err["horizontal_m"])
        unweighted_errors_v.append(err["vertical_m"])

    if result_w["converged"]:
        err = compute_position_error(
            result_w["lat"], result_w["lon"], result_w["height"],
            ref["lat"],      ref["lon"],      ref["height"]
        )
        weighted_errors_h.append(err["horizontal_m"])
        weighted_errors_v.append(err["vertical_m"])

print(f"\nProcessed successfully.")
print()

# Compute statistics
stats_uw = compute_accuracy_statistics(unweighted_errors_h, unweighted_errors_v)
stats_w  = compute_accuracy_statistics(weighted_errors_h,   weighted_errors_v)

print("=" * 55)
print("Accuracy Comparison — FRDN")
print("=" * 55)
print(f"{'Metric':<20} {'Unweighted':>12} {'Weighted':>12} {'Change':>10}")
print("-" * 55)

metrics = ["CEP50", "CEP95", "RMSE_H", "RMSE_V", "2DRMS"]
for m in metrics:
    uw  = stats_uw.get(m, float("nan"))
    w   = stats_w.get(m, float("nan"))
    chg = w - uw
    arrow = "↓" if chg < 0 else ("↑" if chg > 0 else "—")
    print(f"  {m:<18} {uw:>10.1f} m {w:>10.1f} m {arrow}{abs(chg):>7.1f} m")

print("=" * 55)
print()

if stats_w["CEP50"] < stats_uw["CEP50"]:
    improvement = (1 - stats_w["CEP50"] / stats_uw["CEP50"]) * 100
    print(f"Weighted SPP improved CEP50 by {improvement:.1f}%")
else:
    print("Note: minimal difference expected — FRDN is a clean site.")
    print("Weighting will show larger improvement on urban canyon data.")