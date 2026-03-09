# Running the docker container locally

Users may want to run the docker container locally so that all dependencies (OpenSHA and OpenQuake) are available. If you are not running jobs locally, only spawning them from your local machine, it is not necessary to run runzi in the container.

In the following commands, replace the docker image (e.g., `461564345538.dkr.ecr.us-east-1.amazonaws.com/nzshm22/runzi-openquake:latest`) with the image use wish to use. In these examples we have mapped a directory containing input JSON files to `/INPUT_FILES` in the container.

Replace `[COMMAND] [COMMAND] [OPTIONS]` with the `runzi` commands you wish to run, e.g. `inversion crustal /INPUT_FILES/crustal_inversion.json`.

## If using a local realization dataset for OpenQuake

You must map `NZSHM22_THS_RLZ_DB` to the `/THS` directory in the docker so that data can be written to it.

```console
docker run \
-v $HOME/.aws/credentials:/home/openquake/.aws/credentials:ro \
-v <path to input files>:/INPUT_FILES
-v $NZSHM22_THS_RLZ_DB:/THS \
-e AWS_PROFILE \
-e NZSHM22_TOSHI_S3_URL \
-e NZSHM22_TOSHI_API_URL \
-e NZSHM22_TOSHI_API_KEY \
-e NZSHM22_SCRIPT_CLUSTER_MODE \
-e NZSHM22_RUNZI_ECR_DIGEST \
461564345538.dkr.ecr.us-east-1.amazonaws.com/nzshm22/runzi-openquake:latest [COMMAND] [COMMAND] [OPTIONS]
```

## If using an S3 realization dataset for OpenQuake

In this case you must set `NZSHM22_THS_RLZ_DB` to the S3 URI.

```console
docker run \
-v $HOME/.aws/credentials:/home/openquake/.aws/credentials:ro \
-v $NZSHM22_THS_RLZ_DB:/THS \
-e NZSHM22_THS_RLZ_DB \
-e AWS_PROFILE \
-e NZSHM22_TOSHI_S3_URL \
-e NZSHM22_TOSHI_API_URL \
-e NZSHM22_TOSHI_API_KEY \
-e NZSHM22_SCRIPT_CLUSTER_MODE \
-e NZSHM22_RUNZI_ECR_DIGEST \
461564345538.dkr.ecr.us-east-1.amazonaws.com/nzshm22/runzi-openquake:latest [COMMAND] [COMMAND] [OPTIONS]
```
