import warnings
import georinex as gr

warnings.filterwarnings("ignore", category=FutureWarning)

nav = gr.load("data/raw/extracted/ALGO00CAN_R_20251520000_01D_MN.rnx")

sat = "G02"
sat_data = nav.sel(sv=sat)

required_vars = [
    "sqrtA",
    "Eccentricity",
    "M0",
    "DeltaN",
    "Omega0",
    "omega",
    "Io",
    "Toe",
]

print("\nSatellite:", sat)
print("\nSearching for first valid ephemeris record...")

for i, epoch in enumerate(sat_data.time.values):
    values = [sat_data[var].values[i] for var in required_vars]

    if all(value == value for value in values):  # skips NaN values
        print("\nFirst valid epoch:")
        print(epoch)

        print("\nFirst valid ephemeris record:")
        for var, value in zip(required_vars, values):
            print(var, value)

        break
else:
    print("No valid ephemeris record found for this satellite.")