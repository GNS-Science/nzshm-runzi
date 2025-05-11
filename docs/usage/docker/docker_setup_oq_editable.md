# Build a Docker image to run runzi as-is in the working tree
**NB: the built image is NOT for deployment, only local testing, as it is not reproducible**
These instructions will allow you to build an image for testing in which the runzi code can be altered after build including while the container is running.

## build the base docker image
follow docs/usage/base_docker_setup_oq.md

## Build new image on top of the base image
The `WORKING_BURNER` tag indicates that runzi code is from the working directory and the image is not to be used for official calculations as the code is not traceable. The build command must be run from the root directory of the `nzshm-runzi` repo.
```
export WORKING_CONTAINER_TAG=runzi-WORKING-BURNER_nz_openquake-${OQ_VERSION} 
docker build -f docker/runzi-openquake/Dockerfile_WORKING-BURNER --no-cache \
    --build-arg BASE_IMAGE=runzi-openquake:${CONTAINER_TAG} \
    -t runzi-openquake:$WORKING_CONTAINER_TAG .
```

export NZSHM22_RUNZI_ECR_DIGEST="sha256:WORKING_BURNER"

## run
Set the path to your toshi-hazard-store DB (local folder or S3 URI) and set your AWS profile.
```
$ export AWS_PROFILE="chrisdc"
```

Notice that when we run, we mount the `nzshm-runzi` directory that we can modify the code without re-building the container. The directories we mount as volumes in the docker container must have write access for all users in order for the process in the running container to be able to write to them. The THS datastore files will be written to `$NZSHM22_SCRIPT_WORK_PATH/DOCKER/THS` on the host.
```
export RUNZI_DIR=/home/chrisdc/NSHM/DEV/APP/nzshm-runzi
export NZSHM22_SCRIPT_CLUSTER_MODE=LOCAL
docker run -it --rm --env-file docker/runzi-openquake/environ \
--entrypoint "/bin/bash" \
-v $HOME/.aws/credentials:/home/openquake/.aws/credentials:ro \
-v $RUNZI_DIR:/app/nzshm-runzi \
-v $NZSHM22_SCRIPT_WORK_PATH/DOCKER:/WORKING \
-e AWS_PROFILE=${AWS_PROFILE} \
-e NZSHM22_TOSHI_S3_URL \
-e NZSHM22_TOSHI_API_URL \
-e NZSHM22_TOSHI_API_KEY \
-e NZSHM22_SCRIPT_CLUSTER_MODE \
-e NZSHM22_S3_REPORT_BUCKET \
-e NZSHM22_RUNZI_ECR_DIGEST \
-e NZSHM22_THS_RLZ_DB=/WORKING/THS \
runzi-openquake:${WORKING_CONTAINER_TAG}
```
