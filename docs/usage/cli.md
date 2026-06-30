The primary way of interacting with runzi is via the command line interface (CLI). The top level command is `runzi`. Similar operations are grouped under sub commands (e.g. `hazard`, `inversion`, etc.). Under each sub command are the operations that runzi can perform. Use the <nobr>`--help`</nobr> flag to get more information on available commands, arguments, and options.

Most job types require an [input file](input/index.md) to define arguments.

**Usage**:

```console
$ runzi [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--cluster-mode [LOCAL|CLUSTER|AWS]`: Execution target: LOCAL machine, HPC CLUSTER, or AWS cloud.  [default: LOCAL]
* `--install-completion`: Install completion for the current shell.
* `--show-completion`: Show completion for the current shell, to copy it or customize the installation.
* `--help`: Show this message and exit.

**Commands**:

* `inversion`: inversion
* `hazard`: hazard calculations
* `ipp`: inversion post processing
* `rupset`: create rupture sets
* `reports`: create inversion and rupture set reports
* `utils`: utilities

## `inversion`

inversion

**Usage**:

```console
$ runzi inversion [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `crustal`: Run crustal inversions.
* `subduction`: Run subduction inversions.

### `inversion crustal`

Run crustal inversions.

**Usage**:

```console
$ runzi inversion crustal [OPTIONS] INPUT_FILEPATH
```

**Arguments**:

* `INPUT_FILEPATH`: [required]

**Options**:

* `--help`: Show this message and exit.

### `inversion subduction`

Run subduction inversions.

**Usage**:

```console
$ runzi inversion subduction [OPTIONS] INPUT_FILEPATH
```

**Arguments**:

* `INPUT_FILEPATH`: [required]

**Options**:

* `--help`: Show this message and exit.

## `hazard`

hazard calculations

**Usage**:

```console
$ runzi hazard [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `oq-hazard`: Calculate hazard realizations using the...
* `oq-disagg`: Calculate hazard disaggregation...

### `hazard oq-hazard`

Calculate hazard realizations using the OpenQuake engine.

**Usage**:

```console
$ runzi hazard oq-hazard [OPTIONS] INPUT_FILEPATH
```

**Arguments**:

* `INPUT_FILEPATH`: [required]

**Options**:

* `--help`: Show this message and exit.

### `hazard oq-disagg`

Calculate hazard disaggregation realizations using the OpenQuake engine.

**Usage**:

```console
$ runzi hazard oq-disagg [OPTIONS] INPUT_FILEPATH
```

**Arguments**:

* `INPUT_FILEPATH`: [required]

**Options**:

* `--help`: Show this message and exit.

## `ipp`

inversion post processing

**Usage**:

```console
$ runzi ipp [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `avg-sol`: Average multiple solutions by taking the...
* `time-dependent`: Create time dependent inversion solutions...
* `scale`: Scale rupture rates of inversion solutions.
* `oq-convert`: Convert OpenSHA inversion solutions to...

### `ipp avg-sol`

Average multiple solutions by taking the mean rate of all ruptures.

**Usage**:

```console
$ runzi ipp avg-sol [OPTIONS] INPUT_FILEPATH
```

**Arguments**:

* `INPUT_FILEPATH`: [required]

**Options**:

* `--help`: Show this message and exit.

### `ipp time-dependent`

Create time dependent inversion solutions by modifying rupture rates.

**Usage**:

```console
$ runzi ipp time-dependent [OPTIONS] INPUT_FILEPATH
```

**Arguments**:

* `INPUT_FILEPATH`: [required]

**Options**:

* `--help`: Show this message and exit.

### `ipp scale`

Scale rupture rates of inversion solutions.

**Usage**:

```console
$ runzi ipp scale [OPTIONS] INPUT_FILEPATH
```

**Arguments**:

* `INPUT_FILEPATH`: [required]

**Options**:

* `--help`: Show this message and exit.

### `ipp oq-convert`

Convert OpenSHA inversion solutions to OpenQuake source input files.

**Usage**:

```console
$ runzi ipp oq-convert [OPTIONS] INPUT_FILEPATH
```

**Arguments**:

* `INPUT_FILEPATH`: [required]

**Options**:

* `--help`: Show this message and exit.

## `rupset`

create rupture sets

**Usage**:

```console
$ runzi rupset [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `coulomb`: Create Coulomb (crustal) rupture sets.
* `subduction`: Create subduction rupture sets.

### `rupset coulomb`

Create Coulomb (crustal) rupture sets.

**Usage**:

```console
$ runzi rupset coulomb [OPTIONS] INPUT_FILEPATH
```

**Arguments**:

* `INPUT_FILEPATH`: [required]

**Options**:

* `--help`: Show this message and exit.

### `rupset subduction`

Create subduction rupture sets.

**Usage**:

```console
$ runzi rupset subduction [OPTIONS] INPUT_FILEPATH
```

**Arguments**:

* `INPUT_FILEPATH`: [required]

**Options**:

* `--help`: Show this message and exit.

## `reports`

create inversion and rupture set reports

**Usage**:

```console
$ runzi reports [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `rupset`: Create diagnostic reports for rupture sets.
* `inversion`: Create diagnostic reports for inversion.

### `reports rupset`

Create diagnostic reports for rupture sets.

**Usage**:

```console
$ runzi reports rupset [OPTIONS] TOSHI_ID
```

**Arguments**:

* `TOSHI_ID`: id of rupture set or general task used to create rupture sets  [required]

**Options**:

* `--help`: Show this message and exit.

### `reports inversion`

Create diagnostic reports for inversion.

**Usage**:

```console
$ runzi reports inversion [OPTIONS] GENERAL_TASK_ID
```

**Arguments**:

* `GENERAL_TASK_ID`: [required]

**Options**:

* `--help`: Show this message and exit.

## `utils`

utilities

**Usage**:

```console
$ runzi utils [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `docker-build`: Build the runzi image, push it to ECR,...
* `promote`: Promote an already-published image to :prod...
* `save-file`: Zip a file and save as a ToshiAPI File...
* `index-inv`: Add inversions to the index (static web...

### `utils docker-build`

Build the runzi image, push it to ECR, and move the :experimental tag onto it. Does not touch the prod job definition; use `runzi utils promote` to publish to prod.

**Usage**:

```console
$ runzi utils docker-build [OPTIONS]
```

**Options**:

* `--fatjar-tag TEXT`: OpenSHA fatjar tag
* `--runzi-gitref TEXT`: Git branch, tag, or commit to build  [default: main]
* `--python-version TEXT`: Python version  [default: 3.11]
* `--oq-version TEXT`: OpenQuake version  [default: 3.23.4]
* `--install-converter / --no-install-converter`: Set to install UCERF converter  [default: no-install-converter]
* `--dev / --no-dev`: Build dev image (editable install, local-only; skips ECR push)  [default: no-dev]
* `--region TEXT`: AWS region  [default: us-east-1]
* `--aws-account-id TEXT`: AWS account ID  [default: 461564345538]
* `--ecr-repo TEXT`: ECR repository  [default: nzshm22/runzi]
* `--dockerfile TEXT`: Path to Dockerfile  [default: docker/Dockerfile]
* `--skip-build / --no-skip-build`: Skip Docker build  [default: no-skip-build]
* `--skip-push / --no-skip-push`: Skip ECR push  [default: no-skip-push]
* `--help`: Show this message and exit.

### `utils promote`

Promote an already-published image to :prod — changing the shared prod job definition's image. Moves the :prod tag onto an existing image manifest in ECR (no rebuild).

**Usage**:

```console
$ runzi utils promote [OPTIONS]
```

**Options**:

* `--source TEXT`: Source tag to promote to :prod — the current :experimental image, or a specific runzi-<hash>... version tag.  [default: experimental]
* `--region TEXT`: AWS region  [default: us-east-1]
* `--ecr-repo TEXT`: ECR repository  [default: nzshm22/runzi]
* `--yes / --no-yes`, `-y`: Skip the confirmation prompt  [default: no-yes]
* `--help`: Show this message and exit.

### `utils save-file`

Zip a file and save as a ToshiAPI File object.

Can provide single target file
run_save_file_archive(target, tag, input_csv_file, output_csv_file, dry_run)

**Usage**:

```console
$ runzi utils save-file [OPTIONS] TARGET
```

**Arguments**:

* `TARGET`: path of file to be archived  [required]

**Options**:

* `--tag TEXT`: add tag to metadata
* `--input-csv-file / --no-input-csv-file`: target is CSV list of files to archive; must have header: [&#x27;fullpath&#x27;, &#x27;grandparent&#x27;, &#x27;parent&#x27;, &#x27;filename&#x27;]  [default: no-input-csv-file]
* `--output-csv-file PATH`: write CSV of archived files with assigned toshi IDs
* `--dry-run / --no-dry-run`: mock run  [default: no-dry-run]
* `--help`: Show this message and exit.

### `utils index-inv`

Add inversions to the index (static web page).

**Usage**:

```console
$ runzi utils index-inv [OPTIONS] GT_IDS...
```

**Arguments**:

* `GT_IDS...`: whitespace seprated list of inversion genarl task IDs  [required]

**Options**:

* `--help`: Show this message and exit.

