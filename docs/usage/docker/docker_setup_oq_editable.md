# Build a Docker image to run runzi as-is in the working tree
**NB: the built image is NOT for deployment, only local testing, as it is not reproducible**
These instructions will allow you to build an image for testing in which the runzi code can be altered after build including while the container is running.

## build the base docker image
[follow base build](./docker_setup_oq_base.md)

## Build new image on top of the base image
The `WORKING_BURNER` tag indicates that runzi code is from the working directory and the image is not to be used for official calculations as the code is not traceable. The build command must be run from the root directory of the `nzshm-runzi` repo.
```
export WORKING_CONTAINER_TAG=runzi-WORKING-BURNER_nz_openquake-${OQ_VERSION} 
docker build -f docker/runzi-openquake/Dockerfile_WORKING-BURNER --no-cache \
    --build-arg BASE_IMAGE=runzi-openquake:${CONTAINER_TAG} \
    -t runzi-openquake:$WORKING_CONTAINER_TAG .
```

export NZSHM22_RUNZI_ECR_DIGEST="sha256:WORKING_BURNER"

## Set environment variables
Set the locations of the runzi input files
```
export INPUT_FILES_DIR=<path to input files>
```

Set the `NZSHM22_THS_RLZ_DB` to the location of the toshi-hazard-store realization dataset. This can be an S3 bucket or a local path. If running in the cloud, this must be an S3 bucket. For local datasets, the directory and all directories and files below it must allow all users to write to them (i.e. `chmod -R 777 <DATASET DIR>`).

```
export NZSHM22_THS_RLZ_DB=<realization dataset path or S3 URI>
```

Set your AWS profile.
```
export AWS_PROFILE=<your AWS profile name>
```

Set the path to your development runzi directory and the run mode to local.
```
export RUNZI_DIR=<path to your local copy of runzi>
export NZSHM22_SCRIPT_CLUSTER_MODE=LOCAL
```
The directories we mount as volumes in the docker container must have write access for all users in order for the process in the running container to be able to write to them.

## Run

Notice that when we run, we mount the `nzshm-runzi` directory that we can modify the code without re-building the container.
```
docker run -it --rm --env-file docker/runzi-openquake/environ \
--entrypoint "/bin/bash" \
-v $HOME/.aws/credentials:/home/openquake/.aws/credentials:ro \
-v $INPUT_FILES_DIR:/home/openquake/input_files \
-v $RUNZI_DIR:/app/nzshm-runzi \
-v $NZSHM22_THS_RLZ_DB:/THS \
-e AWS_PROFILE \
-e NZSHM22_TOSHI_S3_URL \
-e NZSHM22_TOSHI_API_URL \
-e NZSHM22_TOSHI_API_KEY \
-e NZSHM22_SCRIPT_CLUSTER_MODE \
-e NZSHM22_RUNZI_ECR_DIGEST \
runzi-openquake:${WORKING_CONTAINER_TAG}
```
