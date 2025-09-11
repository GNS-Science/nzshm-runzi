The primary way of interacting with runzi is via the command line interface (CLI). The top level command is `runzi`. Similar operations are grouped under sub commands (e.g. `hazard`, `inversion`, etc.). Under each sub command are the operations that runzi can perform. Use the <nobr>`--help`</nobr> flag to get more information on available commands, arguments, and options.

**Usage**:

```console
$ runzi [OPTIONS] COMMAND [ARGS]...
```

**Options**:

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
$ runzi ipp oq-convert [OPTIONS] TITLE DESCRIPTION IDS...
```

**Arguments**:

* `TITLE`: [required]
* `DESCRIPTION`: [required]
* `IDS...`: Whitespace seperated list of IDs of objects to convert. Can be individual InversionSolutions or GeneralTask.  [required]

**Options**:

* `--num-workers INTEGER`
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

* `coulomb-rupset`: Create Coulomb (crustal) rupture sets.
* `sub-rupset`: Create subduction rupture sets.

### `rupset coulomb-rupset`

Create Coulomb (crustal) rupture sets.

**Usage**:

```console
$ runzi rupset coulomb-rupset [OPTIONS] INPUT_FILEPATH
```

**Arguments**:

* `INPUT_FILEPATH`: [required]

**Options**:

* `--help`: Show this message and exit.

### `rupset sub-rupset`

Create subduction rupture sets.

**Usage**:

```console
$ runzi rupset sub-rupset [OPTIONS] INPUT_FILEPATH
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

* `rupture-set`: Create diagnostic reports for rupture sets.
* `inversion`: Create diagnostic reports for inversion.

### `reports rupture-set`

Create diagnostic reports for rupture sets.

**Usage**:

```console
$ runzi reports rupture-set [OPTIONS] FILE_OR_TASK_ID NUM_WORKERS
```

**Arguments**:

* `FILE_OR_TASK_ID`: [required]
* `NUM_WORKERS`: [required]

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

* `save-file`: Zip a file and save as a ToshiAPI File...
* `index-inv`: Add inversions to the index (static web...

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

