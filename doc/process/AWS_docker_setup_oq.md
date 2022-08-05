
## Build and tag new docker image
```
docker build . --no-cache
export IMAGE_ID=a08a4dad9eca
export RUNZI_GITREF=d379d83
export OQ_TAG=gmm_lt_final_v0
export CONTAINER_TAG=runzi-${RUNZI_GITREF}_nz_openquake-${OQ_TAG}
docker tag ${IMAGE_ID} 461564345538.dkr.ecr.us-east-1.amazonaws.com/nzshm22/runzi-openquake:${CONTAINER_TAG}
```

## get credential, push image into AWS ECR

```

$(aws ecr get-login --no-include-email --region us-east-1)
docker push 461564345538.dkr.ecr.us-east-1.amazonaws.com/nzshm22/runzi-opensha:${CONTAINER_TAG}

```

### for AWS cli v2
```
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin 461564345538.dkr.ecr.us-east-1.amazonaws.com
docker push 461564345538.dkr.ecr.us-east-1.amazonaws.com/nzshm22/runzi-openquake:${CONTAINER_TAG}
```

Update AWS Job Defintion with ${CONTAINER_TAG}