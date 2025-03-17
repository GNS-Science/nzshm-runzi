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

## run
Notice that when we run, we mount the `nzshm-runzi` directory that we can modify the code without re-building the container.
```
export RUNZI_DIR=/home/chrisdc/NSHM/DEV/APP/nzshm-runzi
export NZSHM22_SCRIPT_CLUSTER_MODE=LOCAL
docker run -it --rm --env-file docker/runzi-openquake/environ \
--entrypoint "/bin/bash" \
-v $HOME/.aws/credentials:/home/openquake/.aws/credentials:ro \
-v $RUNZI_DIR:/app/nzshm-runzi \
-v $NZSHM22_SCRIPT_WORK_PATH/DOCKER:/WORKING \
-e AWS_PROFILE=toshi_batch_devops \
-e NZSHM22_TOSHI_S3_URL \
-e NZSHM22_TOSHI_API_URL \
-e NZSHM22_TOSHI_API_KEY \
-e NZSHM22_SCRIPT_CLUSTER_MODE \
-e NZSHM22_S3_REPORT_BUCKET \
-e NZSHM22_REPORT_LEVEL=FULL \
-e NZSHM22_TOSHI_API_KEY \
-e NZSHM22_HAZARD_STORE_STAGE \
-e NZSHM22_HAZARD_STORE_REGION=ap-southeast-2 \
runzi-openquake:${WORKING_CONTAINER_TAG}
```
