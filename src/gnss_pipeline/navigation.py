from pathlib import Path
import warnings
import georinex as gr

warnings.filterwarnings("ignore", category=FutureWarning)


def parse_navigation_file(nav_file_path: str) -> None:
    nav_path = Path(nav_file_path)

    if not nav_path.exists():
        raise FileNotFoundError(f"File not found: {nav_path}")

    print("Loading RINEX navigation file...")
    nav = gr.load(nav_path)

    print("\nNavigation file loaded successfully.")

    print("\nNavigation variables:")
    print(list(nav.data_vars))

    print("\nSatellite list:")
    print(nav.sv.values)

    print("\nEpoch count:")
    print(len(nav.time.values))

    print("\nFirst epoch:")
    print(nav.time.values[0])

    print("\nLast epoch:")
    print(nav.time.values[-1])


if __name__ == "__main__":
    nav_file = "data/raw/extracted/ALGO00CAN_R_20251520000_01D_MN.rnx"
    parse_navigation_file(nav_file)