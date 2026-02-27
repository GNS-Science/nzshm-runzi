## Notes on docker, containers & AWS setup


### GNS AWS roles

 - User: toshi_batch_devops - has rights to scedule/manage AWS Batch jobs console & CLI
 - Role: toshi_batch_ECS_TaskExecution - used by Batch/ECS to pull ECR images, Lauch container instances, also passed into task via JobRole (in JobDefinition)

### Commands

```
#Build
$ docker build . -t nzshm22/runzi-opensha 

# to force new git pull etc
$ docker build . --no-cache -t nzshm22/runzi-opensha
```

```
# get credential
$ aws ecr get-login
$ $(aws ecr get-login --no-include-email --region us-east-1)
```

```
# Create ECR repoo
$ aws ecr create-repository --repository-name nzshm22/runzi-opensha # or nzshm22/runzi-runzi-openquake

# push image into AWS ECR
$ export AWS_ACCT=461564345538

## OPENSHA
$ docker tag nzshm22/runzi-opensha ${AWS_ACCT}.dkr.ecr.us-east-1.amazonaws.com/nzshm22/runzi-opensha:latest
$ docker push ${AWS_ACCT}.dkr.ecr.us-east-1.amazonaws.com/nzshm22/runzi-opensha

## OPENQUAKE
$ docker tag nzshm22/runzi-openquake ${AWS_ACCT}.dkr.ecr.us-east-1.amazonaws.com/nzshm22/runzi-openquake:latest
$ docker push ${AWS_ACCT}.dkr.ecr.us-east-1.amazonaws.com/nzshm22/runzi-openquake


#run the job
$ aws batch submit-job --cli-input-json "$(<task-specs/job-submit-002.json)"
```

## New Build (with gitref-tagging)

 - nzshm-opensha
    - push any changes
    - build fatjar
    - get gitrefs
 - runzi
    - push any changes
    - get gitrefs
    - copy fatjar


### Build new container with no tag, forcing git pull etc
make sure Dockerfile has correct runzi branch


```
#EG
export RUNZI_GITREF=8ccbb80
export FATJAR_TAG=bf70d35
export CONTAINER_TAG=runzi-${RUNZI_GITREF}_nz_opensha-${FATJAR_TAG}
docker build  --no-cache \
   -t 461564345538.dkr.ecr.us-east-1.amazonaws.com/nzshm22/runzi-opensha:${CONTAINER_TAG} \
   --build-arg FATJAR_TAG=${FATJAR_TAG} \
   --build-arg RUNZI_GITREF=${RUNZI_GITREF} \
   .
```

### Tag new docker image

```

docker tag ${IMAGE_ID} 461564345538.dkr.ecr.us-east-1.amazonaws.com/nzshm22/runzi:${CONTAINER_TAG}
```

### get credential, push image into AWS ECR

```

$(aws ecr get-login --no-include-email --region us-east-1)
docker push 461564345538.dkr.ecr.us-east-1.amazonaws.com/nzshm22/runzi:${CONTAINER_TAG}

```

### for AWS cli v2
```
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin 461564345538.dkr.ecr.us-east-1.amazonaws.com
docker push 461564345538.dkr.ecr.us-east-1.amazonaws.com/nzshm22/runzi:${CONTAINER_TAG}

```

### Update AWS Job Defintion with ${CONTAINER_TAG}


### RUN ....

This assumes the command is being run from the folder containing `Dockerfile`

```
# setcorrect environment
set_tosh_test_env
```

### Local cli testing

```
wget https://nzshm-opensha-public-jars.s3.ap-southeast-2.amazonaws.com/nzshm-opensha-all-${FATJAR_TAG}.jar -P $(pwd)/nzshm-opensha/build/libs
export NZSHM22_FATJAR=$(pwd)/nzshm-opensha/build/libs/nzshm-opensha-all-${FATJAR_TAG}.jar
AWS_PROFILE=toshi_batch_devops NZSHM22_TOSHI_API_ENABLED=1 NZSHM22_SCRIPT_CLUSTER_MODE=LOCAL python3 ../../runzi/cli/cli.py
```

### AWS or Dockerised run

run the docker container...
 - use LOCAL to run on local docker host
 - use AWS to run on AWS Batch


-v $(pwd)/../../runzi/cli/config/saved_configs:/app/nzshm-runzi/runzi/cli/config/saved_configs \
export NZSHM22_SCRIPT_CLUSTER_MODE=AWS
461564345538.dkr.ecr.us-east-1.amazonaws.com/nzshm22/runzi:${CONTAINER_TAG}
--env-file environ 
```
docker run -it --rm --entrypoint "/bin/bash" \
-v /data/NSHM/DEV/APP/nzshm-runzi/INPUT_FILES:/INPUT_FILES \
-v $HOME/.aws/credentials:/root/.aws/credentials:ro \
-e AWS_PROFILE=toshi_batch_devops \
-e NZSHM22_TOSHI_S3_URL \
-e NZSHM22_TOSHI_API_URL \
-e NZSHM22_TOSHI_API_KEY \
-e NZSHM22_SCRIPT_CLUSTER_MODE \
-e NZSHM22_S3_REPORT_BUCKET \
-e NZSHM22_REPORT_LEVEL=FULL \
-e NZSHM22_TOSHI_API_KEY \
-e NZSHM22_FATJAR=/app/nzshm-opensha/build/libs/nzshm-opensha-all-${FATJAR_TAG}.jar \
146cfb00db9c
```

### Batch setup


### testing docker build

```
# This is how we ran locally, when no AWS access was needed, but it fails now because AWS creds aren't setup
$ docker run -it --rm --env-file environ nzshm22/runzi-opensha -s /app/container_task.sh

# so now we must pass in credentials, then it can use boto to retrieve the ToshiAPI secret

docker run -it --rm --env-file environ \
-v $HOME/.aws/credentials:/root/.aws/credentials:ro
-e AWS_PROFILE=toshi_batch_devops nzshm22/runzi-opensha
-s /app/container_task.sh
```



Note this passing in of credentials is done using Job Definition.jobRoleARN in the ECS environment.


## Running Hazard

There's no cli support yet