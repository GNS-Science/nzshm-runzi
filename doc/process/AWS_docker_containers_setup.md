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


# get credential
$ aws ecr get-login
$ $(aws ecr get-login --no-include-email --region us-east-1)


# Create ECR repoo
$ aws ecr create-repository --repository-name nzshm22/runzi-opensha

# push image into AWS ECR
$ docker tag nzshm22/runzi-opensha ${AWS_ACCT}.dkr.ecr.us-east-1.amazonaws.com/nzshm22/runzi-opensha:latest
$ docker push 461564345538.dkr.ecr.us-east-1.amazonaws.com/nzshm22/runzi-opensha

#run the job
$ aws batch submit-job --cli-input-json "$(<task-specs/job-submit-002.json)"
```


### Batch setup


### testing docker build

```
# This is how we ran locally, when no AWS access was needed, but it fails now because AWS creds aren't setup
$ docker run -it --rm --env-file environ nzshm22/runzi-opensha -s /app/container_task.sh

# so now we must pass in credentials, then it can use boto to retrieve the ToshiAPI secret
$ docker run -it --rm --env-file environ -v $HOME/.aws/credentials:/root/.aws/credentials:ro -e AWS_PROFILE=toshi_batch_devops nzshm22/runzi-opensha -s /app/container_task.sh

```

Note this passing in of credentials is done using Job Definition.jobRoleARN in the ECS environment.


### NEW running Runzi from the Container


This assumes the command is being run from the folder containing `Dockerfile`

```
docker run -it --rm --env-file environ \
-v $HOME/.aws/credentials:/root/.aws/credentials:ro \
-v $(pwd)/../../runzi/cli/config/saved_configs:/app/nzshm-runzi/runzi/cli/config/saved_configs \
-e AWS_PROFILE=toshi_batch_devops \
-e NZSHM22_TOSHI_S3_URL \
-e NZSHM22_TOSHI_API_URL \
nzshm22/runzi-opensha-cli
```