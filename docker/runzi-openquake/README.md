
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
NZSHM22_TOSHI_API_URL 		#default http://127.0.0.1:5000/graphql")
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
nzshm22/runzi-openquake
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




