# Building and using Docker to run runzi

The docker build process for runzi with openquake is done in two stages. In the first stage the base image is created using the end of a branch in the remote repo. This is done so that runzi code is traceable to a git commit that can be found on GitHub and therefore results are reproducible. In the second phase, the built docker image is either tagged and pushed to AWS ECS to be run in the cloud or the local runzi code in the users working tree is used to overwrite the "official" ruzni installation from the first stage. This is can then be used for local testing and debugging. **Note that a local build is not to be used in production because the results are not guaranteed to be reproducible.**

## Base Build (do this first)
[Base build instructions](docker_setup_oq_base.md)

## AWS Build
[AWS build instructions](./docker_setup_oq_AWS.md)

## Local Build
[Local build instructions](./docker_setup_oq_local.md)
