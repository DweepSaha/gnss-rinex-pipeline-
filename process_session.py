"""
Full session processor — runs SPP on every epoch in a RINEX file
and computes positioning accuracy statistics against NRCan reference.
Includes ionospheric correction, signal quality weighting, and DOP.
Uses improved ephemeris selection (closest Toe to observation time).
Run from project root.
"""
import georinex as gr
import numpy as np
from pathlib import Path
from src.gnss_pipeline.ephemeris import compute_satellite_position, get_first_valid_ephemeris
from src.gnss_pipeline.az_el import compute_az_el
from src.gnss_pipeline.spp_solver import solve_spp_epoch, geodetic_to_ecef, ecef_to_geodetic
from src.gnss_pipeline.dop import compute_dop
from src.gnss_pipeline.accuracy import load_reference_coords, compute_position_error, compute_accuracy_statistics
from src.gnss_pipeline.nav_header_utils import get_nav_header_from_file
from src.gnss_pipeline.snr_analysis import analyse_session_snr, get_epoch_weights
from src.gnss_pipeline.cmc_analysis import analyse_session_cmc, combine_snr_cmc_flags

SPEED_OF_LIGHT = 299_792_458.0

# --- Configuration ---
STATION    = "FRDN"
OBS_FILE   = "data/raw/extracted/FRDN00CAN_R_20251520000_01D_30S_MO.rnx"
NAV_FILE   = "data/raw/extracted/FRDN00CAN_R_20251520000_01D_MN.rnx"
REF_FILE   = "data/reference/nrcan_reference_coords.json"
TLIM_START = "2025-06-01T00:00:30"
TLIM_END   = "2025-06-01T02:00:00"

# --- Load files ---
print(f"Loading RINEX files for {STATION}...")
obs = gr.load(OBS_FILE, use="G", tlim=[TLIM_START, TLIM_END])
nav = gr.load(NAV_FILE, use="G")
ref = load_reference_coords(REF_FILE)[STATION]

print(f"Reference position: lat={ref['lat']:.6f} lon={ref['lon']:.6f} h={ref['height']:.3f} m")
print(f"Epochs to process:  {len(obs.time.values)}")
print()

# --- Ionospheric correction header ---
print("Loading ionospheric correction coefficients...")
nav_header = get_nav_header_from_file(nav)
print()

# --- Signal quality analysis ---
print("Running signal quality analysis...")
snr_results     = analyse_session_snr(obs, snr_field="S1C")
cmc_results     = analyse_session_cmc(obs)
combined_flags  = combine_snr_cmc_flags(snr_results, cmc_results)
sat_weights     = get_epoch_weights(combined_flags)

n_clean     = sum(1 for f in combined_flags.values() if f == "clean")
n_suspect   = sum(1 for f in combined_flags.values() if f == "suspect")
n_multipath = sum(1 for f in combined_flags.values() if f == "multipath")
print(f"Quality flags: {n_clean} clean, {n_suspect} suspect, {n_multipath} multipath")
print()

# --- GPS epoch reference ---
gps_epoch = np.datetime64("1980-01-06T00:00:00", "s")

# --- Storage ---
errors_h     = []
errors_v     = []
north_errors = []
east_errors  = []
dop_list     = []
epoch_list   = []
results      = []

# --- Main processing loop ---
print("Processing epochs...")
for epoch_idx, epoch in enumerate(obs.time.values):

    if epoch_idx % 20 == 0:
        print(f"  Epoch {epoch_idx+1}/{len(obs.time.values)}...", end="\r")

    # GPS time of week
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

            # Use closest ephemeris to observation time — key Phase 3 improvement
            ep_time, eph = get_first_valid_ephemeris(nav, sat, gps_time_of_week)
            toe          = float(eph.get("Toe", 0.0))
            travel_time  = pr / SPEED_OF_LIGHT

            # Robust transmit time alignment handles all week boundary cases
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

    # Align solver GPS time to median Toe across visible satellites
    toes = [float(ephemerides[s].get("Toe", 0.0)) for s in ephemerides]
    median_toe = float(np.median(toes))
    dt_check   = gps_time_of_week - median_toe
    if dt_check < -302400:
        solver_gps_time = gps_time_of_week + 604800.0
    elif dt_check > 302400:
        solver_gps_time = gps_time_of_week - 604800.0
    else:
        solver_gps_time = gps_time_of_week

    # Initial position guess from reference
    x0_xyz = geodetic_to_ecef(ref["lat"], ref["lon"], ref["height"])
    x0     = np.array([x0_xyz[0], x0_xyz[1], x0_xyz[2], 0.0])

    # Solve SPP with ionospheric correction and quality weights
    result = solve_spp_epoch(
        pseudoranges, sat_positions, ephemerides,
        eccentric_anomalies, elevations, azimuths,
        nav_header, gps_time=solver_gps_time, x0=x0,
        weights=sat_weights
    )

    if not result["converged"]:
        continue

    # Position error vs NRCan reference
    error = compute_position_error(
        result["lat"], result["lon"], result["height"],
        ref["lat"],    ref["lon"],    ref["height"]
    )

    # DOP values
    dop = compute_dop(result["H"])

    errors_h.append(error["horizontal_m"])
    errors_v.append(error["vertical_m"])
    north_errors.append(error["north_m"])
    east_errors.append(error["east_m"])
    dop_list.append(dop)
    epoch_list.append(epoch)
    results.append(result)

print(f"\nProcessed {len(results)} epochs successfully.")
print()

# --- Accuracy statistics ---
stats     = compute_accuracy_statistics(errors_h, errors_v)
mean_hdop = np.nanmean([d["HDOP"] for d in dop_list])
mean_pdop = np.nanmean([d["PDOP"] for d in dop_list])

print("=" * 55)
print(f"SPP Accuracy Report — {STATION} (Phase 3 final)")
print("=" * 55)
print(f"  Epochs processed:       {stats['n_epochs']}")
print(f"  Ionospheric correction: Klobuchar (enabled)")
print(f"  Satellite weighting:    quality-based")
print(f"  Ephemeris selection:    closest Toe to observation")
print()
print(f"  CEP50  (horiz):         {stats['CEP50']:.1f} m")
print(f"  CEP95  (horiz):         {stats['CEP95']:.1f} m")
print(f"  RMSE   horizontal:      {stats['RMSE_H']:.1f} m")
print(f"  RMSE   vertical:        {stats['RMSE_V']:.1f} m")
print(f"  2DRMS:                  {stats['2DRMS']:.1f} m")
print(f"  Mean horiz error:       {stats['mean_H']:.1f} m")
print()
print(f"  Mean HDOP:              {mean_hdop:.2f}")
print(f"  Mean PDOP:              {mean_pdop:.2f}")
print("=" * 55)
print()
print("Comparison vs Phase 2 baseline:")
print("  Phase 2: CEP50=72.8 m  RMSE_H=82.4 m  (no iono, no weighting, first ephemeris)")
improvement_cep = (1 - stats["CEP50"] / 72.8) * 100
improvement_rms = (1 - stats["RMSE_H"] / 82.4) * 100
print(f"  Phase 3: CEP50={stats['CEP50']:.1f} m  RMSE_H={stats['RMSE_H']:.1f} m")
print()
if improvement_cep > 0:
    print(f"  CEP50 improved by {improvement_cep:.1f}%")
    print(f"  RMSE_H improved by {improvement_rms:.1f}%")
else:
    print(f"  CEP50 change: {improvement_cep:.1f}%")

# --- Save results ---
Path("data/processed").mkdir(parents=True, exist_ok=True)
np.save("data/processed/errors_h.npy",     np.array(errors_h))
np.save("data/processed/errors_v.npy",     np.array(errors_v))
np.save("data/processed/north_errors.npy", np.array(north_errors))
np.save("data/processed/east_errors.npy",  np.array(east_errors))
print("Results saved to data/processed/")
print("Run plot_results.py to regenerate visualizations.")