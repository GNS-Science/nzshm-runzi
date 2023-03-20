from typing import List

from nzshm_common.geometry.geometry import BACKARC_POLYGON
from nzshm_common.location.location import LOCATION_LISTS, location_by_id
from nzshm_common.grids.region_grid import RegionGrid, load_grid
from nzshm_common.location.code_location import CodedLocation
from shapely.geometry import Point

def coded_location_by_id(id):
    loc = location_by_id(id)
    return CodedLocation(lat=loc['latitude'], lon=loc['longitude'], resolution=0.001).code

def build_site_csv(locations) -> str:

    site_csv = 'lon,lat,backarc\n'
    for location in locations:
        lat,lon = location.split('~')
        point = Point(float(lon), float(lat))
        backarc_flag = 1 if BACKARC_POLYGON.contains(point)[0] else 0
        site_csv += f'{lon},{lat},{int(backarc_flag)}\n'    

    return site_csv

def get_coded_locations(location_list: List[str]) -> List[str]:
    
    locations: List[str] = []

    for location_spec in location_list:
        if '~' in location_spec:
            locations.append(location_spec)
        elif location_by_id(location_spec):
            locations.append(coded_location_by_id(location_spec))
        elif location_spec in LOCATION_LISTS:
            location_ids = LOCATION_LISTS[location_spec]["locations"]
            locations += [coded_location_by_id(id) for id in location_ids]
        elif location_spec in dir(RegionGrid):
            locations += [CodedLocation(*loc, 0.001).code for loc in load_grid(location_spec)]
        else:
            raise Exception('{0} is not a valid location identifier'.format(location_spec))

    return locations


if __name__ == "__main__":

    location_list = ['-34.345~100.000', 'NZ', 'NZ_0_1_NB_1_1', 'srg_1']
    print(build_site_csv(get_coded_locations(location_list)))