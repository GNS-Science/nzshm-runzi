This section describes the environment variables that apply to jobs launched by `runzi`.

# Boolean
`"1"`, `"Y"`, `"YES"`, `"TRUE"` evaluate as true. They are not case sensitive.

# Env Vars
Defaults are given in brackets.

- `NZSHM22_TOSHI_API_ENABLED` [false]: if set to true will log general task and children with `ToshiAPI` and store realizations in database using `toshi-hazard-store`
- `NZSHM22_SCRIPT_WORKER_POOL_SIZE` [2]: number of jobs to run simultaneously on local hardware.
- `NZSHM22_TOSHI_API_URL` [`http://127.0.0.1:5000/graphql`]
- `NZSHM22_TOSHI_S3_URL` [`http://localhost:4569`]
- `NZSHM22_RUNZI_ECR_DIGEST`: used by `toshi-hazard-store` to record the Docker image digest used to generate hazard cruves.
- `NZSHM22_THS_RLZ_DB`: path to location of parquet files where hazard realizations are stored by `toshi-hazard-store`. Can be local directory or s3 bucket (`s3://`)
- `NZSHM22_SCRIPT_CLUSTER_MODE` [`LOCAL`]: can be `LOCAL`, `CLUSTER`, `AWS`
- `NZSHM22_SCRIPT_JVM_HEAP_START` [4]: Startup JAVA Memory (per worker)
- `NZSHM22_OPENSHA_ROOT` [`~/DEV/GNS/opensha-modular`]: path to root directory for OpenSHA
- `NZSHM22_OPENSHA_JRE` [`/usr/lib/jvm/java-11-openjdk-amd64/bin/java`]: location of java executable
- `NZSHM22_FATJAR` [`OPENSHA_ROOT`]: location of OpenSHA fat jar
- `NZSHM22_SCRIPT_WORK_PATH` [`cwd / "tmp"`]: path to working directory for scripts, configurations, etc
- `NZSHM22_BUILD_PLOTS`: if true, inversion reports will build MFD plots
- `NZSHM22_REPORT_LEVEL`:  `LIGHT`, `DEFAULT`, `FULL`: the level of detail for inversion reports
- `NZSHM22_HACK_FAULT_MODEL`
- `NZSHM22_S3_REPORT_BUCKET`: location of inversion and rupture set reports
- `NZSHM22_S3_UPLOAD_WORKERS`: number of simultaneous workers for uploading to s3
- `SPOOF`: if true do not run calculations, just perform setup (and API queries/mutations)
