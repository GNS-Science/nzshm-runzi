## Build new container with no tag, forcing git pull etc
```
docker build . --no-cache
```

## Tag new docker image
```

export IMAGE_ID=5f9b487631b5
export RUNZI_GITREF=HEAD
export OQ_TAG=3.20.1
export CONTAINER_TAG=runzi-${RUNZI_GITREF}_nz_openquake-${OQ_TAG} 
docker tag ${IMAGE_ID} runzi-openquake:${CONTAINER_TAG}
#docker tag ${IMAGE_ID} 461564345538.dkr.ecr.us-east-1.amazonaws.com/nzshm22/runzi-openquake:${CONTAINER_TAG}
```

## get credential, push image into AWS ECR

```
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin 461564345538.dkr.ecr.us-east-1.amazonaws.com
docker push 461564345538.dkr.ecr.us-east-1.amazonaws.com/nzshm22/runzi-openquake:${CONTAINER_TAG}

```

### for AWS cli v2
```
docker push 461564345538.dkr.ecr.us-east-1.amazonaws.com/nzshm22/runzi-openquake:${CONTAINER_TAG}

#aws ecr get-login-password --region ap-southeast-2 | docker login --username AWS --password-stdin 461564345538.dkr.ecr.ap-southeast-2.amazonaws.com
#docker push 461564345538.dkr.ecr.ap-southeast-2.amazonaws.com/nzshm22/runzi-openquake:${CONTAINER_TAG}
```

Update AWS Job Definition with ${CONTAINER_TAG}

## run
if running in docker:
```
export NZSHM22_SCRIPT_CLUSTER_MODE=LOCAL
docker run -it --rm --env-file docker/runzi-openquake/environ \
--entrypoint "/bin/bash" \
-v $HOME/.aws/credentials:/home/openquake/.aws/credentials:ro \
-v /home/chrisdc/NSHM/DEV/APP/nzshm-runzi/demo:/app/nzshm-runzi/demo \
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
runzi-openquake:${CONTAINER_TAG}
```

