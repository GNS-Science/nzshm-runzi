# Calculating Hazard Curves

Hazard curves can be calculated via OpenQuake with the `hazard oq-hazard` sub command.

```console
$ runzi hazard oq-hazard [OPTIONS] INPUT_FILEPATH
```

This will split the SRM logic tree into component branches and spawn an OpenQuake job for each branch. The realizations can then be re-assembled and the full logic tree calculated using `toshi-hazard-post`. The full GMCM logic tree is used for each OpenQuake job (i.e. no decomposition of the GMCM logic tree is performed). Results are stored as hdf5, csv, and, optionally, in the realization database using `toshi-hazard-store`.

## Environment Variables
- `SPOOF_HAZARD`: if set to true will not spawn an OpenQuake job. All OpenQuake input files will be generated, but OpenQuake will not be run.
- `NZSHM22_RUNZI_ECR_DIGEST`: the digest (sha256 hash) of the docker image used to run hazard. This is used to uniquely identify the code used to calculate hazard curves for reproducibility and bug tracking.
- `NZSHM22_THS_RLZ_DB`: folder or S3 bucket where the toshi-hazard-store realizations will be stored. For local storage, must be a valid path; for cloud storage, must be a valid S3 URI.

## Configuration File
The configuration file is in toml format. The following tables and variables are used to specify the hazard job. [A sample configuration file can be found here](example_hazard_config_file.md). All list entries can optionally be given as a single value without brackets.

### `[general]`
- `title`: a string title for the model
- `description`: a string description of the model

### `[hazard_model]`
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
- `vs30s`: a list of ints specifying a uniform vs30 value (in m/s) for all sites.

Provide one of the following for the sites at which to calculate hazard
- `locations`: a list of strings specifying locations by location list, id, or lat~lon string. See the `nzshm-common` documentation for details.
- `locations_file`: a csv file with lat lon and optionally site-specific vs30 values. If vs30 is provided, the uniform `vs30` cannot be provided.


# Post Processing

Once all hazard jobs are completed, you can compact the realization dataset using the toshi-hazard-store defrag script. This allows for faster dataset lookup. Standard partition keys are `vs30` and `nloc_0`
```
$ ths_ds_defrag -v -p vs30,nloc_0 SOURCE_PATH DESTINATION_PATH
```