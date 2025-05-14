# Environment Variables
This section describes the environment variables that apply to all types of jobs launched by `runzi`. Job specific env vars are described in the relevant section.

## Boolean
`"1"`, `"Y"`, `"YES"`, `"TRUE"` evaluate as true. They are not case sensitive.

## Env Vars
Defaults are given in brackets.

- `NZSHM22_TOSHI_API_ENABLED` [false]: if set to true will log general task and children with `ToshiAPI` and store realizations in database using `toshi-hazard-store`
- `NZSHM22_SCRIPT_WORKER_POOL_SIZE` [2]: number of jobs to run simultaneously on local hardware.