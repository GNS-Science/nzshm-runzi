import os
import sys
import toml
from pathlib import Path

from openquake.baselib import sap
from openquake.hazardlib.sourcewriter import write_source_model
from openquake.converters.ucerf.parsers.sections_geojson import (
    get_multi_fault_source)

folder = './SW52ZXJzaW9uU29sdXRpb246MTU2NjcuMHpxc1dM'
out_folder = "/WORKDIR"

TOML = """
type = 'geojson'
source_id = 'SW52ZXJzaW9uU29sdXRpb246MTU2NjcuMHpxc1dM'
source_name = 'nzshm-opensha Crustal demo'

# Unit of measure for the rupture sampling: km
rupture_sampling_distance = 0.5

# The `tectonic_region_type` label must be consistent with what you use in the
# logic tree for the ground-motion characterisation
# Use "Subduction Interface" or "Active Shallow Crust"
tectonic_region_type = "Active Shallow Crust"

# Unit of measure for the `investigation_time`: years
investigation_time = 1.0
"""

fpath = Path(folder)
config = toml.loads(TOML)

## print(config)

dip_sd = config['rupture_sampling_distance']
strike_sd = dip_sd
source_id = config['source_id']
source_name = config['source_name']
tectonic_region_type = config['tectonic_region_type']
investigation_time = config['investigation_time']
#data_folder = config['data_folder']
#output_folder = config['output_folder']

computed = get_multi_fault_source(folder, dip_sd, strike_sd, source_id,
                                          source_name, tectonic_region_type,
                                          investigation_time)

print(computed)
Path(out_folder).mkdir(parents=True, exist_ok=True)
out_file = os.path.join(out_folder, f'{source_id}-ruptures.xml')
write_source_model(out_file, [computed], name=source_name, investigation_time=investigation_time)
print('Created output in: {:s}'.format(out_folder))