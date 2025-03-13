# Build a docker image for use in AWS EC2
This will build an "official" image that is tagged with a git-ref and OQ version

## build the base docker image
follow docs/usage/base_docker_setup_oq.md

## retag the base docker image for AWS Elastic Container Service
export IMAGE_ID=5f9b487631b5
docker tag ${IMAGE_ID} 461564345538.dkr.ecr.us-east-1.amazonaws.com/nzshm22/runzi-openquake:${CONTAINER_TAG}

## get credential, push image into AWS ECR

```
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin 461564345538.dkr.ecr.us-east-1.amazonaws.com
docker push 461564345538.dkr.ecr.us-east-1.amazonaws.com/nzshm22/runzi-openquake:${CONTAINER_TAG}
```

## Update Job Definition
Update AWS Job Definition with ${CONTAINER_TAG}

## run
if running in docker:
```
export NZSHM22_SCRIPT_CLUSTER_MODE=LOCAL
docker run -it --rm --env-file environ \
--entrypoint "/bin/bash" \
-v $HOME/.aws/credentials:/home/openquake/.aws/credentials:ro \
-v /home/chrisdc/NSHM/oqruns/runzi_config_test:/app/nzshm-runzi/demo \
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
461564345538.dkr.ecr.us-east-1.amazonaws.com/nzshm22/runzi-openquake:${CONTAINER_TAG}
```
