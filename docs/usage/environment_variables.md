This section describes the environment variables that apply to all types of jobs launched by `runzi`. Job specific env vars are described in the relevant section.

# Boolean
`"1"`, `"Y"`, `"YES"`, `"TRUE"` evaluate as true. They are not case sensitive.

# Env Vars
Defaults are given in brackets.

- `NZSHM22_TOSHI_API_ENABLED` [false]: if set to true will log general task and children with `ToshiAPI` and store realizations in database using `toshi-hazard-store`
- `NZSHM22_SCRIPT_WORKER_POOL_SIZE` [2]: number of jobs to run simultaneously on local hardware.
- `NZSHM22_TOSHI_API_URL` [`http://127.0.0.1:5000/graphql`]
- `NZSHM22_TOSHI_S3_URL` [`http://localhost:4569`]
- `NZSHM22_RUNZI_ECR_DIGEST`
- `NZSHM22_THS_RLZ_DB`
- `NZSHM22_SCRIPT_CLUSTER_MODE` [`LOCAL`]: can be `LOCAL`, `CLUSTER`, `AWS`
- `NZSHM22_SCRIPT_JVM_HEAP_START` [4]: Startup JAVA Memory (per worker)
- `NZSHM22_OPENSHA_ROOT` [`~/DEV/GNS/opensha-modular`]
- `NZSHM22_OPENSHA_JRE` [`/usr/lib/jvm/java-11-openjdk-amd64/bin/java`]
- `NZSHM22_FATJAR` [`OPENSHA_ROOT`]
- `NZSHM22_SCRIPT_WORK_PATH` [`cwd / "tmp"`]
- `NZSHM22_BUILD_PLOTS`
- `NZSHM22_REPORT_LEVEL`:  `LIGHT`, `DEFAULT`, `FULL`
- `NZSHM22_HACK_FAULT_MODEL`
- `NZSHM22_S3_REPORT_BUCKET`
- `NZSHM22_S3_UPLOAD_WORKERS`
- `SPOOF`: if true do not run calculations, just perform setup (and API queries/mutations)
