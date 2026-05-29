This section describes the environment variables that apply to jobs launched by `runzi`.

# Boolean
`"1"`, `"Y"`, `"YES"`, `"TRUE"` evaluate as true. They are not case sensitive.

# Local machine env vars
Set these in your `.env` file. Defaults are given in brackets.

- `NZSHM22_TOSHI_API_ENABLED` [false]: if set to true will log general task and children with `ToshiAPI` and store realizations in database using `toshi-hazard-store`
- `NZSHM22_SCRIPT_WORKER_POOL_SIZE` [2]: number of jobs to run simultaneously on local hardware.
- `NZSHM22_TOSHI_API_URL` [`http://127.0.0.1:5000/graphql`]
- `NZSHM22_TOSHI_S3_URL` [`http://localhost:4569`]
- `NZSHM22_TOSHI_COGNITO_DOMAIN`: Cognito domain used for Scientist (interactive) login and AWS credential federation.
- `NZSHM22_TOSHI_COGNITO_SCIENTIST_CLIENT_ID`: Cognito app client ID for Scientist login.
- `NZSHM22_TOSHI_COGNITO_USER_POOL_ID`: Cognito user pool ID.
- `NZSHM22_TOSHI_COGNITO_IDENTITY_POOL_ID`: Cognito identity pool ID; used to federate AWS credentials via the identity pool.
- `NZSHM22_RUNZI_ECR_DIGEST`: used by `toshi-hazard-store` to record the Docker image digest used to generate hazard cruves.
- `NZSHM22_THS_RLZ_DB`: path to location of parquet files where hazard realizations are stored by `toshi-hazard-store`. Can be local directory or s3 bucket (`s3://`)
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
- `THS_DATASET_AGGR_URI`: location of hazard aggregate datasets; can be local path or s3 URI. Used to lookup hazard curve to find target level at which to calculate disaggregations.
- `NZSHM22_OQ_VENV`: path to the OpenQuake virtual environment root (e.g. `/opt/oq-venv`); required for OQ tasks.
- `NZSHM22_OQ_DATADIR`: directory where `oq engine` writes HDF5 calc datastores (e.g. `/oqdata`); required for OQ tasks.

# AWS Batch job definition env vars
These must be configured in the AWS Batch **job definition** (infrastructure). They are not forwarded from the local machine — local job submission always uses Scientist (interactive) credentials instead.

- `NZSHM22_TOSHI_M2M_SECRET_ARN`: ARN of the Secrets Manager secret holding the M2M (machine-to-machine) Cognito client credentials (`client_id` and `client_secret`). When set alongside `NZSHM22_TOSHI_COGNITO_DOMAIN`, the container authenticates to the Toshi API using M2M JWT tokens rather than interactive login.
- `NZSHM22_TOSHI_COGNITO_DOMAIN`: Cognito domain used for M2M token exchange inside the Batch container.
