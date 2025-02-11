# Calculating Hazard Curves

Hazard curves can be calculated via OpenQuake with the `oq-hazard` command
```
runzi-hazard oq-hazard CONFIGURATION_FILE
```

This will split the SRM logic tree into component branches and spawn an OpenQuake job for each branch. The realizations can then be re-assembled and the full logic tree calculated using `toshi-hazard-post`. The full GMCM logic tree is used for each OpenQuake job (i.e. no decomposition of the GMCM logic tree is performed). Results are stored as hdf5, csv, and, optionally, in the realization database using `toshi-hazard-store`.

## Environment Variables
- `SPOOF_HAZARD`: if set to true will not spawn an OpenQuake job. All OpenQuake input files will be generated, but OpenQuake will not be run.

## Configuration File
The configuration file is in toml format. The following tables and variables are used to specify the hazard job. [A sample configuration file can be found here](example_hazard_config_file.md).

### `[general]`
- `title`: a string title for the model
- `description`: a string description of the model

### `[model]`
A model can be specified by a model version available from the `nzshm-model` package, logic tree and config files, or a combination of both. 

- `nshm_model_version`: a string specifying a model version available from the `nzshm-model` package (e.g. `"NSHM_v1.0.4"`)
- `gmcm_logic_tree`: a string specifying the path to a ground motion characterization model json file
- `srm_logic_tree`: a string specifying the path to a seismicity rate model json file
- `hazard_config`: a string specifying the path to a hazard config json file

A valid model requires all three of a ground motion characterization model, seismicity rate model, and a hazard config. Any logic tree or config files specified will overwrite the defaults provided by the `nshm_model_version`. See the `nzshm-model` documentation for the format of the logic tree and hazard config json files. Non-absolute paths are taken relative to the configuration file.

### `[calculation]`
- `num_workers`: the number of jobs to run simultaneously if running on local hardware. This will overwrite the default or the number specified by the env var `NZSHM22_SCRIPT_WORKER_POOL_SIZE`

### `[hazard_curve]`
- `imts`: A list of intensity measure type strings at which to calculate hazard
- `imtls`: A list of intensity measure type level floats at which to calculate hazard

### `[site_params]`
- `vs30`: an int specifying a uniform vs30 value (in m/s) for all sites.

Provide one of the following for the sites at which to calculate hazard
- `locations`: a list of strings specifying locations by location list, id, or lat~lon string. See the `nzshm-common` documentation for details.
- `locations_file`: a csv file with lat lon and optionally site-specific vs30 values. If vs30 is provided, the uniform `vs30` cannot be provided.
