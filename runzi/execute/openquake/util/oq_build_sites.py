from typing import List, Tuple

from nzshm_common.geometry.geometry import BACKARC_POLYGON
from nzshm_common.location.location import LOCATION_LISTS, location_by_id
from nzshm_common.grids.region_grid import RegionGrid, load_grid
from nzshm_common.location.code_location import CodedLocation
from shapely.geometry import Point
from openquake.commands.prepare_site_model import calculate_z1pt0, calculate_z2pt5_ngaw2

def coded_location_by_id(id: str) -> str:
    loc = location_by_id(id)
    return CodedLocation(lat=loc['latitude'], lon=loc['longitude'], resolution=0.001).code

def vs30_by_id(id: str) -> str:
    loc = location_by_id(id)
    if vs30 := loc.get('vs30'):
        return str(vs30)
    return 'nan'

def build_site_csv(locations, vs30s=None) -> str:

    def llb(location):
        lat,lon = location.split('~')
        point = Point(float(lon), float(lat))
        backarc_flag = 1 if BACKARC_POLYGON.contains(point)[0] else 0
        return lon, lat, backarc_flag
        

    if vs30s:
        if len(locations) != len(vs30s):
            raise Exception('locations and vs30 lists must be the same length')
        if 'nan' in vs30s:
            raise Exception('location specific vs30 requested, but not all locations have a vs30 value')
        site_csv = 'lon,lat,vs30,z1pt0,z2pt5,vs30measured,backarc\n'
        for location, vs30 in zip(locations, vs30s):
            lon, lat, backarc_flag = llb(location)
            z1pt0 = str(round(calculate_z1pt0(vs30), 0))
            z2pt5 = str(round(calculate_z2pt5_ngaw2(vs30), 1))
            site_csv += f'{lon},{lat},{vs30},{z1pt0},{z2pt5},0,{int(backarc_flag)}\n'
    else:    
        site_csv = 'lon,lat,backarc\n'
        for location in locations:
            lon, lat, backarc_flag = llb(location)
            site_csv += f'{lon},{lat},{int(backarc_flag)}\n'    

    return site_csv

def get_coded_locations(location_list: List[str]) -> Tuple[List[str], List[str]]:
    
    locations: List[str] = []
    vs30s: List[str] = []

    for location_spec in location_list:
        if '~' in location_spec:
            locations.append(location_spec)
            vs30s.append('nan')
        elif location_by_id(location_spec):
            locations.append(coded_location_by_id(location_spec))
            if vs30 := location_by_id(id).get('vs30'):
                vs30s.append(str(vs30))
            else:
                vs30s.append('nan')
        elif location_spec in LOCATION_LISTS:
            location_ids = LOCATION_LISTS[location_spec]["locations"]
            locations += [coded_location_by_id(id) for id in location_ids]
            vs30s += [vs30_by_id(id) for id in location_ids]
        elif location_spec in dir(RegionGrid):
            locations += [CodedLocation(*loc, 0.001).code for loc in load_grid(location_spec)]
            vs30s += ['nan']*len([CodedLocation(*loc, 0.001).code for loc in load_grid(location_spec)]) #region grids don't yet support vs30
        else:
            raise Exception('{0} is not a valid location identifier'.format(location_spec))

    return locations, vs30s


if __name__ == "__main__":

    location_list = ['-34.345~100.000', 'NZ', 'NZ_0_1_NB_1_1', 'srg_1']
    print(build_site_csv(get_coded_locations(location_list)))