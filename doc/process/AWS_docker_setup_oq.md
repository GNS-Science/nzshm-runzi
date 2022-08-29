## Build new container with no tag, forcing git pull etc
```
docker build . --no-cache
```

## Tag new docker image
```

export IMAGE_ID=b7e9c2e7af5e
export RUNZI_GITREF=6868efe
export OQ_TAG=deaggs #gmm_lt_v2 
export CONTAINER_TAG=runzi-${RUNZI_GITREF}_nz_openquake-${OQ_TAG} 
docker tag ${IMAGE_ID} 461564345538.dkr.ecr.us-east-1.amazonaws.com/nzshm22/runzi-openquake:${CONTAINER_TAG}
#docker tag ${IMAGE_ID} 461564345538.dkr.ecr.ap-southeast-2.amazonaws.com/nzshm22/runzi-openquake:${CONTAINER_TAG}
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

#aws ecr get-login-password --region ap-southeast-2 | docker login --username AWS --password-stdin 461564345538.dkr.ecr.ap-southeast-2.amazonaws.com
#docker push 461564345538.dkr.ecr.ap-southeast-2.amazonaws.com/nzshm22/runzi-openquake:${CONTAINER_TAG}
```




Update AWS Job Defintion with ${CONTAINER_TAG}
