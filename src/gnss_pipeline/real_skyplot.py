import math
from pathlib import Path
import warnings

import georinex as gr
import matplotlib.pyplot as plt
import numpy as np
import pymap3d as pm

from ephemeris import compute_satellite_position, get_first_valid_ephemeris

warnings.filterwarnings("ignore", category=FutureWarning)


RECEIVER_LAT = 45.9555
RECEIVER_LON = -78.0714
RECEIVER_HEIGHT = 200.0


def get_gps_satellites(nav):
    return [str(sv) for sv in nav.sv.values if str(sv).startswith("G")]


def compute_az_el_for_satellite(nav, sat, times_seconds):
    epoch, eph = get_first_valid_ephemeris(nav, sat)

    az_values = []
    el_values = []

    for transmit_time_seconds in times_seconds:
        x, y, z = compute_satellite_position(eph, transmit_time_seconds)

        az, el, slant_range = pm.ecef2aer(
            x,
            y,
            z,
            RECEIVER_LAT,
            RECEIVER_LON,
            RECEIVER_HEIGHT,
            deg=True,
        )

        if el > 0:
            az_values.append(az)
            el_values.append(el)

    return az_values, el_values


def make_real_skyplot_tracks():
    nav_file = "data/raw/extracted/ALGO00CAN_R_20251520000_01D_MN.rnx"

    print("Loading navigation file...")
    nav = gr.load(nav_file)
    print("Navigation file loaded.")

    gps_sats = get_gps_satellites(nav)

    print("\nGPS satellites found:")
    print(gps_sats)

    # 0 to 2 hours, every 10 minutes
    times_seconds = np.arange(0, 2 * 60 * 60 + 1, 10 * 60)

    fig = plt.figure(figsize=(9, 9))
    ax = plt.subplot(111, polar=True)

    ax.set_theta_zero_location("N")
    ax.set_theta_direction(-1)

    ax.set_rlim(90, 0)
    ax.set_yticks([0, 30, 60, 90])
    ax.set_yticklabels(["90°", "60°", "30°", "0°"])

    plotted_count = 0

    for sat in gps_sats:
        try:
            az_values, el_values = compute_az_el_for_satellite(
                nav,
                sat,
                times_seconds,
            )

            if len(az_values) < 2:
                continue

            theta_values = [math.radians(az) for az in az_values]
            radius_values = [90 - el for el in el_values]

            ax.plot(theta_values, radius_values, marker="o", label=sat)

            # Label the final visible point
            ax.text(
                theta_values[-1],
                radius_values[-1],
                sat,
                fontsize=8,
            )

            plotted_count += 1

            print(f"{sat}: plotted {len(az_values)} visible points")

        except Exception as error:
            print(f"Skipping {sat}: {error}")

    ax.set_title("Real GPS Sky Plot Tracks from Broadcast Ephemeris")

    if plotted_count > 0:
        ax.legend(loc="upper right", bbox_to_anchor=(1.35, 1.1), fontsize=8)

    output_path = Path("outputs/plots/real_skyplot_tracks_gps.png")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    plt.savefig(output_path, dpi=300, bbox_inches="tight")

    print(f"\nPlotted satellites: {plotted_count}")
    print(f"Real sky plot tracks saved to: {output_path}")


if __name__ == "__main__":
    make_real_skyplot_tracks()