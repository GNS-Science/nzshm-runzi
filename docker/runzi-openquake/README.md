
# About

a docker image tha integrates Openquake, the opensha converter, and RUnzi


# BUILD

```
## previous build be4454febbb1
docker pull openquake/engine:nightly
docker build . -t nzshm22/runzi-openquake
```

# ENV OPTIONS

NZSHM22_SCRIPT_CLUSTER_MODE #one of LOCAL, CLUSTER, AWS
NZSHM22_TOSHI_API_ENABLED
NZSHM22_TOSHI_API_URL 		#default http://127.0.0.1:5000/graphql")  http://host.docker.internal/5000/graphql etc
NZSHM22_TOSHI_S3_URL 		#default http://localhost:4569")

# RUN

## Minimum local only...

```
docker run -it --rm \
-e NZSHM22_TOSHI_S3_URL \
-e NZSHM22_TOSHI_API_URL \
-e NZSHM22_SCRIPT_CLUSTER_MODE \
nzshm22/runzi-openquake
```

## With AWS + TOSHI


```
docker run -it --rm \
-v $HOME/.aws/credentials:/home/openquake/.aws/credentials:ro \
-v $(pwd)/../../runzi/cli/config/saved_configs:/app/nzshm-runzi/runzi/cli/config/saved_configs \

-e AWS_PROFILE=toshi_batch_devops \
-e NZSHM22_TOSHI_API_ENABLED=Yes \
-e NZSHM22_TOSHI_S3_URL \
-e NZSHM22_TOSHI_API_URL \
-e NZSHM22_SCRIPT_CLUSTER_MODE \
-e NZSHM22_S3_REPORT_BUCKET=BLAH \

```

### TEST EXAMPLE

```
docker run -u root -it --rm \
-v $(pwd)/examples:/WORKING/examples \
-v $(pwd)/../../../ucerf:/app/ucerf \
{IMAGEID}
-s bash
```

in the container ...

in /app

```
oq db start &
oq engine --run /WORKING/examples/01_point_era_oq/job-WLG.ini
oq engine --export-outputs 1 /WORKING/output
```

```
python3 convert.py
```

## New Runzi commands (Ben)

runziCLI/hazard>
runziCLI/hazard/run

prompt for folder in /WORKING

user selects file
...>run y/N
...>export y/N


```
NZSHM22_FATJAR=/home/chrisbc/DEV/GNS/opensha-modular/nzshm-runzi/docker/runzi-opensha/nzshm-opensha/build/libs/nzshm-opensha-all-reportpagegen-rupset.jar
NZSHM22_TOSHI_API_KEY=8o9XVIVrOh6J9qfp0hW3d3c1S7WyT2U69YzRtgIE
NZSHM22_TOSHI_S3_URL=https://nzshm22-toshi-api-prod.s3.amazonaws.com
NZSHM22_S3_REPORT_BUCKET=nzshm22-static-reports
NZSHM22_SCRIPT_WORK_PATH=/home/chrisbc/DEV/GNS/AWS_S3_DATA/WORKING
NZSHM22_TOSHI_API_URL=https://aihssdkef5.execute-api.ap-southeast-2.amazonaws.com/prod/graphql
NZSHM22_SOLVIS_API_URL=https://mmbzw56f1h.execute-api.ap-southeast-2.amazonaws.com/prod
NZSHM22_SOLVIS_API_KEY=5krfgPtC7P9Ghp8S04PS05oTpoofeL664rjnMWJM
```
