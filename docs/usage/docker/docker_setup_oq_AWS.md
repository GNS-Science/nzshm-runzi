# Build a docker image for use in AWS EC2
This will build an "official" image that is tagged with a git-ref and OQ version

## build the base docker image
[follow base build](./docker_setup_oq_base.md)

## retag the base docker image for AWS Elastic Container Service
```
export IMAGE_ID=5f9b487631b5
docker tag ${IMAGE_ID} 461564345538.dkr.ecr.us-east-1.amazonaws.com/nzshm22/runzi-openquake:${CONTAINER_TAG}
```

## get credential, push image into AWS ECR

```
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin 461564345538.dkr.ecr.us-east-1.amazonaws.com
docker push 461564345538.dkr.ecr.us-east-1.amazonaws.com/nzshm22/runzi-openquake:${CONTAINER_TAG}
```

## Update Job Definition
Update AWS Job Definition with `${CONTAINER_TAG}`

## run
To run locally:
```
export NZSHM22_SCRIPT_CLUSTER_MODE=LOCAL
export RUNZI_HAZARD_DIR=/home/chrisdc/NSHM/DEV/APP/nzshm-runzi/demo
docker run -it --rm --env-file environ \
--entrypoint "/bin/bash" \
-v $HOME/.aws/credentials:/home/openquake/.aws/credentials:ro \
-v RUNZI_HAZARD_DIR:/app/nzshm-runzi/demo \
-e AWS_PROFILE=toshi_batch_devops \
-e NZSHM22_TOSHI_S3_URL \
-e NZSHM22_TOSHI_API_URL \
-e NZSHM22_TOSHI_API_KEY \
-e NZSHM22_SCRIPT_CLUSTER_MODE \
-e NZSHM22_S3_REPORT_BUCKET \
-e NZSHM22_REPORT_LEVEL=FULL \
461564345538.dkr.ecr.us-east-1.amazonaws.com/nzshm22/runzi-openquake:${CONTAINER_TAG}
```
