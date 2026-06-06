"""
Regenerate Phase 2 baseline results for comparison plotting.
Uses original Phase 2 settings: no iono, no weighting, first ephemeris.
Run from project root.
"""
import georinex as gr
import numpy as np
from pathlib import Path
from src.gnss_pipeline.ephemeris import compute_satellite_position, get_first_valid_ephemeris
from src.gnss_pipeline.az_el import compute_az_el
from src.gnss_pipeline.spp_solver import solve_spp_epoch, geodetic_to_ecef
from src.gnss_pipeline.accuracy import load_reference_coords, compute_position_error, compute_accuracy_statistics

SPEED_OF_LIGHT = 299_792_458.0
OBS_FILE   = "data/raw/extracted/FRDN00CAN_R_20251520000_01D_30S_MO.rnx"
NAV_FILE   = "data/raw/extracted/FRDN00CAN_R_20251520000_01D_MN.rnx"
REF_FILE   = "data/reference/nrcan_reference_coords.json"
TLIM_START = "2025-06-01T00:00:30"
TLIM_END   = "2025-06-01T02:00:00"

print("Regenerating Phase 2 baseline results...")
obs = gr.load(OBS_FILE, use="G", tlim=[TLIM_START, TLIM_END])
nav = gr.load(NAV_FILE, use="G")
ref = load_reference_coords(REF_FILE)["FRDN"]

gps_epoch    = np.datetime64("1980-01-06T00:00:00", "s")
errors_h     = []
errors_v     = []
north_errors = []
east_errors  = []

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

            # Phase 2 behaviour: first valid ephemeris, no GPS time passed
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

    # Phase 2: no iono correction, no weights
    result = solve_spp_epoch(
        pseudoranges, sat_positions, ephemerides,
        eccentric_anomalies, elevations, azimuths,
        {}, gps_time=solver_gps_time, x0=x0,
        weights=None
    )

    if not result["converged"]:
        continue

    error = compute_position_error(
        result["lat"], result["lon"], result["height"],
        ref["lat"],    ref["lon"],    ref["height"]
    )
    errors_h.append(error["horizontal_m"])
    errors_v.append(error["vertical_m"])
    north_errors.append(error["north_m"])
    east_errors.append(error["east_m"])

print(f"\nProcessed {len(errors_h)} epochs.")

stats = compute_accuracy_statistics(errors_h, errors_v)
print(f"Phase 2 baseline: CEP50={stats['CEP50']:.1f} m  RMSE_H={stats['RMSE_H']:.1f} m")

Path("data/processed").mkdir(parents=True, exist_ok=True)
np.save("data/processed/p2_errors_h.npy",     np.array(errors_h))
np.save("data/processed/p2_errors_v.npy",     np.array(errors_v))
np.save("data/processed/p2_north_errors.npy", np.array(north_errors))
np.save("data/processed/p2_east_errors.npy",  np.array(east_errors))
print("Phase 2 baseline saved to data/processed/p2_*.npy")