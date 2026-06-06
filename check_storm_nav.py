import georinex as gr

nav = gr.load('data/raw/extracted/FRDN00CAN_R_20241310000_01D_MN.rnx', use='G')

print("Storm day nav header keys:")
for key, val in nav.attrs.items():
    print(f"  {key}: {val}")

print()
if 'GPSA' in nav.attrs:
    print(f"GPSA found: {nav.attrs['GPSA']}")
else:
    print("GPSA not found in storm nav file")

if 'GPSB' in nav.attrs:
    print(f"GPSB found: {nav.attrs['GPSB']}")
else:
    print("GPSB not found in storm nav file")