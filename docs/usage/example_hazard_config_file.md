```
[general]
title = "OpenQuake Hazard Calcs"
description = "hazard demo"

[hazard_model]
nshm_model_version = "NSHM_v1.0.4"

# these entries will overwrite anything in the nshm_model_version.
# all 3 are required if a nshm_model_version is not specified
# gmcm_logic_tree = "gmcm_small.json"
srm_logic_tree = "srm_small.json"
# hazard_config = "hazard_config.json"

[calculation]
num_workers = 1

[hazard_curve]
imts = ['PGA', 'SA(0.5)', 'SA(1.5)', 'SA(3.0)']
imtls = [
    0.0001, 0.0002, 0.0004, 0.0006, 0.0008,
    0.001, 0.002, 0.004, 0.006, 0.008,
    0.01, 0.02, 0.04, 0.06, 0.08,
    0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9,
    1.0, 1.2, 1.4, 1.6, 1.8, 2.0, 2.2, 2.4, 2.6, 2.8, 3.0, 3.5, 4.0, 4.5, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0
    ]

[site_params]

# do not use if locations file has site-specific vs30 values
vs30 = 400

# can provide locations or locations_file, not both
# locations = ['WLG','AKL','DUD','CHC']

locations_file = 'sites.csv'

# locations_file can have site-specific vs30. In this case, do not provide vs30 variable
# locations_file = 'demo/sites_vs30.csv'
```