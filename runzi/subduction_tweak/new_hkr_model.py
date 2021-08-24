#!pythhon3
"""
script to apply modified slip rates to subduction tiles in short order around east cape.

basically take the slip rate in col22 (for) 30km tiles) and then for each row-wise copy the value to cols 23-30
"""

import csv
from pathlib import Path


folder = Path("/home/chrisbc/DEV/GNS/opensha-new/nshm-nz-opensha/src/main/resources/faultModels")
assert folder.exists()
hkm30_tiles = csv.reader(open(Path(folder, "hk_tile_parameters_10-short.csv"),'r'))

row_rates= {}

# for 30km tiles
COL_START = 22 #22,0,179.16104300015039,-38.60725519281238,178.98387068095758,-38.83818262289971
COL_END = 31 #31,0,-179.31864033251932,-36.50129298882654,-179.49932367926107,-36.72734866102422

# for 10km tiles
COL_START = 67
COL_END = 92


def process(line, col_start, col_end):
    if line[0] == 'along_strike_index':
        pass
    elif int(line[0]) == col_start:
        row_rates[line[1]] = line[9]
        print(line)
    elif (col_start < int(line[0]) < col_end):
        line[9] = row_rates[line[1]]
    return line

def filter_lat(line, lat_min, lat_max):
    # _lat_max = float(line[5])
    try:
        lat1 = float(line[3])
    except:
        return
    if lat_min < lat1 < lat_max:
        if line[1] in '0':
            print(line[0], line[1], lat1, line[9])

#header = hkm30_tiles.next()
# print(header)
# print(header.index("slip_deficit (mm/yr)"))
#
"""
along_strike_index,
down_dip_index,
lon1(deg),
lat1(deg),
lon2(deg),
lat2(deg),
dip (deg),
top_depth (km),
bottom_depth (km),
slip_deficit (mm/yr),
tile_geometry
"""
output = []
for row in hkm30_tiles:
    output.append(process(row, COL_START, COL_END))
    #filter_lat(row, -38.8, -36.7)

outf = csv.writer(open(Path(folder, "hk_tile_parameters_10-short-flat-eastcape.csv"), 'w' ))
outf.writerows(output)

