"""
Geomagnetic storm ionospheric validation test.
Compares SPP accuracy with and without Klobuchar correction
on May 10 2024 (Kp=9 geomagnetic storm) vs June 1 2025 (quiet day).
Run from project root.
"""
import georinex as gr
import numpy as np
from src.gnss_pipeline.ephemeris import compute_satellite_position, get_first_valid_ephemeris
from src.gnss_pipeline.az_el import compute_az_el
from src.gnss_pipeline.spp_solver import solve_spp_epoch, geodetic_to_ecef
from src.gnss_pipeline.accuracy import load_reference_coords, compute_position_error, compute_accuracy_statistics
from src.gnss_pipeline.nav_header_utils import get_nav_header
from src.gnss_pipeline.corrections import klobuchar_iono_correction

from src.gnss_pipeline.nav_header_utils import get_nav_header
quiet = get_nav_header(storm=False)
storm = get_nav_header(storm=True)
print("DEBUG quiet GPSA:", quiet["GPSA"])
print("DEBUG storm GPSA:", storm["GPSA"])
print()

SPEED_OF_LIGHT = 299_792_458.0
REF_FILE       = "data/reference/nrcan_reference_coords.json"

ref        = load_reference_coords(REF_FILE)["FRDN"]
nav_header = get_nav_header()
gps_epoch  = np.datetime64("1980-01-06T00:00:00", "s")

# Two datasets — storm day vs quiet day, same station, same time window
datasets = [
    {
        "label":    "Quiet day  (2025-06-01 14:00-16:00 UTC)",
        "obs_file": "data/raw/extracted/FRDN00CAN_R_20251520000_01D_30S_MO.rnx",
        "nav_file": "data/raw/extracted/FRDN00CAN_R_20251520000_01D_MN.rnx",
        "tlim_start": "2025-06-01T14:00:00",
        "tlim_end":   "2025-06-01T16:00:00",
    },
    {
        "label":    "Storm day  (2024-05-10 14:00-16:00 UTC, Kp=9)",
        "obs_file": "data/raw/extracted/FRDN00CAN_R_20241310000_01D_30S_MO.rnx",
        "nav_file": "data/raw/extracted/FRDN00CAN_R_20241310000_01D_MN.rnx",
        "tlim_start": "2024-05-10T14:00:00",
        "tlim_end":   "2024-05-10T16:00:00",
    },
]


def process_epoch(obs, nav, epoch, use_iono: bool) -> dict:
    """Process a single epoch. Returns error dict or None if failed."""
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
        return None

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
    header = nav_header if use_iono else {}

    result = solve_spp_epoch(
        pseudoranges, sat_positions, ephemerides,
        eccentric_anomalies, elevations, azimuths,
        header, gps_time=solver_gps_time, x0=x0
    )

    if not result["converged"]:
        return None

    return compute_position_error(
        result["lat"], result["lon"], result["height"],
        ref["lat"],    ref["lon"],    ref["height"]
    )


def run_session(obs, nav, use_iono: bool) -> tuple:
    """Process all epochs in a session."""
    errors_h = []
    errors_v = []
    for epoch_idx, epoch in enumerate(obs.time.values):
        if epoch_idx % 30 == 0:
            print(f"    Epoch {epoch_idx+1}/{len(obs.time.values)}...", end="\r")
        error = process_epoch(obs, nav, epoch, use_iono)
        if error is not None:
            errors_h.append(error["horizontal_m"])
            errors_v.append(error["vertical_m"])
    return compute_accuracy_statistics(errors_h, errors_v), len(errors_h)


print("Geomagnetic Storm Ionospheric Validation")
print("=" * 72)
print(f"{'Dataset + metric':<42} {'No iono':>10} {'With iono':>10} {'Change':>8}")
print("-" * 72)

for ds in datasets:
    print(f"\nLoading: {ds['label']}")

    try:
        obs = gr.load(ds["obs_file"], use="G",
                      tlim=[ds["tlim_start"], ds["tlim_end"]])
        nav = gr.load(ds["nav_file"], use="G")
    except Exception as e:
        print(f"  ERROR loading files: {e}")
        print(f"  Make sure {ds['obs_file']} exists.")
        continue

    print(f"  Epochs loaded: {len(obs.time.values)}")

    # Sample iono corrections for this session
    epoch_s = obs.time.values[0].astype("datetime64[s]")
    total   = float((epoch_s - gps_epoch).astype(float))
    tow     = total % 604800.0
    lat_r   = np.radians(ref["lat"])
    lon_r   = np.radians(ref["lon"])
    i_45    = klobuchar_iono_correction(
        nav_header, np.radians(45), np.radians(180), lat_r, lon_r, tow
    )
    i_20    = klobuchar_iono_correction(
        nav_header, np.radians(20), np.radians(180), lat_r, lon_r, tow
    )
    print(f"  Klobuchar: {i_45:.2f} m at 45 deg,  {i_20:.2f} m at 20 deg elevation")

    print(f"  Running without iono...")
    stats_no, n_no = run_session(obs, nav, use_iono=False)

    print(f"\n  Running with iono...")
    stats_wi, n_wi = run_session(obs, nav, use_iono=True)

    print(f"\n  Epochs processed: {n_wi}")

    for metric in ["CEP50", "CEP95", "RMSE_H", "RMSE_V"]:
        no_i  = stats_no.get(metric, float("nan"))
        w_i   = stats_wi.get(metric, float("nan"))
        chg   = w_i - no_i
        arrow = "↓" if chg < -0.5 else ("↑" if chg > 0.5 else " ")
        pct   = abs(chg) / no_i * 100 if no_i > 0 else 0
        label = f"  {ds['label'][:38]} {metric}"
        print(f"{label:<42} {no_i:>8.1f} m  {w_i:>8.1f} m  "
              f"{arrow}{abs(chg):>5.1f} m ({pct:.0f}%)")

print()
print("=" * 72)
print()
print("Validation conclusion:")
print("  If storm day shows larger iono correction AND larger improvement")
print("  than quiet day → Klobuchar model is validated and working correctly.")