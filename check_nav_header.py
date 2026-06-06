import georinex as gr

nav = gr.load('data/raw/extracted/FRDN00CAN_R_20251520000_01D_MN.rnx', use='G')

print('Nav header keys:')
for key in nav.attrs.keys():
    print(f'  {key}: {nav.attrs[key]}')

print()
if 'GPSA' in nav.attrs:
    print('GPSA (alpha):', nav.attrs['GPSA'])
else:
    print('GPSA not found')

if 'GPSB' in nav.attrs:
    print('GPSB (beta):', nav.attrs['GPSB'])
else:
    print('GPSB not found')