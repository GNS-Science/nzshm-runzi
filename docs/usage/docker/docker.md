# Building and using Docker to run runzi

The docker build process for runzi with openquake is done in two stages. In the first stage the base image is created using the end of a branch in the remote repo. This is done so that runzi code is traceable to a git commit that can be found on GitHub and therefore results are reproducible. In the second phase, the built docker image is either tagged and pushed to AWS ECS to be used as an "official" build (run either in the cloud locally) or the local runzi code in the users working tree is used to overwrite the ruzni installation from the first stage (editable build). This is can then be used for local testing and debugging. **Note that the test build is not to be used in production because the results are not guaranteed to be reproducible.**

## Base Build (do this first)
[Base build instructions](docker_setup_oq_base.md)

## Official Build
[Official build instructions](./docker_setup_oq_official.md)

## Editable Build
[Editable build instructions](./docker_setup_oq_editable.md)
