# Build a docker image for production use
This will build an "official" image that is tagged with a git-ref and OQ version

## build the base docker image
[follow base build](./docker_setup_oq_base.md)

## retag the base docker image for AWS Elastic Container Service
```
export IMAGE_ID=4fd7a8a9583e
docker tag ${IMAGE_ID} 461564345538.dkr.ecr.us-east-1.amazonaws.com/nzshm22/runzi-openquake:${CONTAINER_TAG}
```


## get credential, push image into AWS ECR

```
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin 461564345538.dkr.ecr.us-east-1.amazonaws.com
docker push 461564345538.dkr.ecr.us-east-1.amazonaws.com/nzshm22/runzi-openquake:${CONTAINER_TAG}
```

## Get the container hash digest 
```
$ docker inspect --format='{{index .RepoDigests 0}}' 461564345538.dkr.ecr.us-east-1.amazonaws.com/nzshm22/runzi-openquake:${CONTAINER_TAG}
```
export NZSHM22_RUNZI_ECR_DIGEST="sha256:2fa86a92388c4e09072b9147c3b1c49818e54ee58c8e5cfb66cf9bcfca17b029"

## Update Job Definition
Update AWS Job Definition with `${CONTAINER_TAG}`

## run
Set the path to your toshi-hazard-store DB (local folder or S3 URI) and set your AWS profile.
```
$ export AWS_PROFILE="chrisdc"
```

If running in the cloud this must be an S3 bucket. If running locally in a docker container this must be `/WORKING/THS`. Otherwise it can be a valid path on your local machine.
```
$ export NZSHM22_THS_RLZ_DB=<path to THS datastore>
```

If running locally the directories we mount as volumes in the docker container must have write access for all users in order for the process in the running container to be able to write to them. The THS datastore files will be written to `$NZSHM22_SCRIPT_WORK_PATH/DOCKER/THS` on the host.

```
export RUNZI_DIR=/home/chrisdc/NSHM/DEV/APP/nzshm-runzi
export NZSHM22_SCRIPT_CLUSTER_MODE=LOCAL
docker run -it --rm --env-file environ \
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
-e NZSHM22_THS_RLZ_DB \
461564345538.dkr.ecr.us-east-1.amazonaws.com/nzshm22/runzi-openquake:${CONTAINER_TAG}
```
