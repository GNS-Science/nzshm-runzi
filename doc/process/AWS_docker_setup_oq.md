## Build new container with no tag, forcing git pull etc
```
docker build . --no-cache
```

## Tag new docker image
```

export IMAGE_ID=44919313c889
export RUNZI_GITREF=97fbd17
export OQ_TAG=gmm_lt_final_ee_ba #deaggs 
export CONTAINER_TAG=runzi-${RUNZI_GITREF}_nz_openquake-${OQ_TAG}
docker tag ${IMAGE_ID} 461564345538.dkr.ecr.us-east-1.amazonaws.com/nzshm22/runzi-openquake:${CONTAINER_TAG}
```

## get credential, push image into AWS ECR

```

$(aws ecr get-login --no-include-email --region us-east-1)
docker push 461564345538.dkr.ecr.us-east-1.amazonaws.com/nzshm22/runzi-openquake:${CONTAINER_TAG}

```

### for AWS cli v2
```
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin 461564345538.dkr.ecr.us-east-1.amazonaws.com
docker push 461564345538.dkr.ecr.us-east-1.amazonaws.com/nzshm22/runzi-openquake:${CONTAINER_TAG}
```

Update AWS Job Defintion with ${CONTAINER_TAG}