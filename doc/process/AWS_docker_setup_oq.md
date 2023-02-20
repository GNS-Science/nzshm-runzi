## Build new container with no tag, forcing git pull etc
```
docker build . --no-cache
```

## Tag new docker image
```

export IMAGE_ID=1ab1bcf9fba4
export RUNZI_GITREF=8734fa7
export OQ_TAG=v3p15 #gmm_lt_v2 
export CONTAINER_TAG=runzi-${RUNZI_GITREF}_nz_openquake-${OQ_TAG} 
docker tag ${IMAGE_ID} 461564345538.dkr.ecr.us-east-1.amazonaws.com/nzshm22/runzi-openquake:${CONTAINER_TAG}
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




Update AWS Job Defintion with ${CONTAINER_TAG}
