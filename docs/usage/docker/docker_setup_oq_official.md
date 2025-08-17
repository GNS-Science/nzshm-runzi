# Build a docker image for production use
This will build an "official" image that is tagged with a git-ref and OQ version

## build the base docker image
[follow base build](./docker_setup_oq_base.md)

## retag the base docker image for AWS Elastic Container Service
```
export IMAGE_ID=<id of newly created docker image>
docker tag ${IMAGE_ID} 461564345538.dkr.ecr.us-east-1.amazonaws.com/nzshm22/runzi-openquake:${CONTAINER_TAG}
```


## get credential, push image into AWS ECR

```
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin 461564345538.dkr.ecr.us-east-1.amazonaws.com
docker push 461564345538.dkr.ecr.us-east-1.amazonaws.com/nzshm22/runzi-openquake:${CONTAINER_TAG}
```

## Get the container hash digest 
```
docker inspect --format='{{index .RepoDigests 0}}' 461564345538.dkr.ecr.us-east-1.amazonaws.com/nzshm22/runzi-openquake:${CONTAINER_TAG}
```
```
export NZSHM22_RUNZI_ECR_DIGEST=<"sha256:XXX">
```

## Update Job Definition
If running on AWS EC2, update AWS Job Definition with `${CONTAINER_TAG}` on the AWS Console.

## Set environment variables
Set the locations of the runzi input files
```
export RUNZI_DIR=<path to input files>
```

Set the `NZSHM22_THS_RLZ_DB` to the location of the toshi-hazard-store realization dataset. This can be an S3 bucket or a local path. If running in the cloud, this must be an S3 bucket. For local datasets, the directory and all directories and files below it must allow all users to write to them (i.e. `chmod -R 777 <DATASET DIR>`).

```
export NZSHM22_THS_RLZ_DB=<realization dataset path or S3 URI>
```

Set your `AWS_PROFILE` if one other than your default is needed.
```
export AWS_PROFILE=<your AWS profile name>
```

## Run

Set `NZSHM22_SCRIPT_CLUSTER_MODE` to one of `LOCAL`, `AWS`, or `CLUSTER` (`CLUSTER` is not currently supported) and follow the instructions below for the corresponding platform.

### Local

#### If using a local realization dataset
```
docker run -it --rm --env-file environ \
--entrypoint "/bin/bash" \
-v $HOME/.aws/credentials:/home/openquake/.aws/credentials:ro \
-v $RUNZI_DIR:/home/openquake/runzi \
-v $NZSHM22_THS_RLZ_DB:/THS \
-e AWS_PROFILE \
-e NZSHM22_TOSHI_S3_URL \
-e NZSHM22_TOSHI_API_URL \
-e NZSHM22_TOSHI_API_KEY \
-e NZSHM22_SCRIPT_CLUSTER_MODE \
-e NZSHM22_RUNZI_ECR_DIGEST \
461564345538.dkr.ecr.us-east-1.amazonaws.com/nzshm22/runzi-openquake:${CONTAINER_TAG}
```

#### If using an S3 realization dataset
```
docker run -it --rm --env-file environ \
--entrypoint "/bin/bash" \
-v $HOME/.aws/credentials:/home/openquake/.aws/credentials:ro \
-v $RUNZI_DIR:/home/openquake/runzi \
-e AWS_PROFILE \
-e NZSHM22_THS_RLZ_DB \
-e NZSHM22_TOSHI_S3_URL \
-e NZSHM22_TOSHI_API_URL \
-e NZSHM22_TOSHI_API_KEY \
-e NZSHM22_SCRIPT_CLUSTER_MODE \
-e NZSHM22_RUNZI_ECR_DIGEST \
461564345538.dkr.ecr.us-east-1.amazonaws.com/nzshm22/runzi-openquake:${CONTAINER_TAG}
```

### AWS EC2