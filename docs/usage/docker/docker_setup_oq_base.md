## Build new container
The image is build using the GH repo for runzi, so we will tag with the latest commit on the branch from the remote. Set the `RUNZI_BRANCH` variable to the desired branch on the remote to use.
```
cd docker/runzi-openquake
git fetch
export OQ_VERSION=desired OQ version, e.g. "3.20.1"
export RUNZI_BRANCH=desired runzi git branch, e.g. "main"
export RUNZI_GITREF=$(git rev-parse --short origin/${RUNZI_BRANCH})
export CONTAINER_TAG=runzi-${RUNZI_GITREF}_nz_openquake-${OQ_VERSION} 
docker build --no-cache -t runzi-openquake:${CONTAINER_TAG} \
    --build-arg OQ_VERSION=${OQ_VERSION} \
    --build-arg RUNZI_BRANCH=${RUNZI_BRANCH} .
```