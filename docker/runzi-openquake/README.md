
# About

a docker image tha integrates Openquake, the opensha converter, and RUnzi


# BUILD

```
## previous builds: be0d236ec1b7, be4454febbb1
docker pull openquake/engine:nightly
docker build . --no-cache -t nzshm22/runzi-openquake
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


### TEST EXAMPLE

```
docker run -u root -it --rm \
-v $(pwd)/examples:/WORKING/examples \
-v $(pwd)/../../../ucerf:/app/ucerf \
{IMAGEID}
-s bash
```

### for linux only - with localstack ...

```
docker run -it --rm -u root \
--net=host \
-v $HOME/.aws/credentials:/home/openquake/.aws/credentials:ro \
-v $(pwd)/../../runzi/cli/config/saved_configs:/app/nzshm-runzi/runzi/cli/config/saved_configs \
-v $(pwd)/examples:/WORKING/examples \
-e AWS_PROFILE=toshi_batch_devops \
-e NZSHM22_TOSHI_API_ENABLED=Yes \
-e NZSHM22_TOSHI_S3_URL \
-e NZSHM22_TOSHI_API_URL \
-e NZSHM22_SCRIPT_CLUSTER_MODE \
nzshm22/runzi-openquake:latest \
-s bash
```

## In container: Manual conversion

```
python3 nzshm-runzi/runzi/execute/prepare_inputs.py SW52ZXJzaW9uU29sdXRpb246NTYyNC4wUnZKeFg=
python3 nzshm-runzi/runzi/automation/run_oq_convert_solution.py

#/WORKING/task_1.sh
cat /WORKING/python_script.1.log
```


## In container: run openquake ...

in /app

```
#TODO run configuration_setup

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
NZSHM22_TOSHI_API_KEY=never_push_to_github
NZSHM22_TOSHI_S3_URL=https://nzshm22-toshi-api-prod.s3.amazonaws.com
NZSHM22_S3_REPORT_BUCKET=nzshm22-static-reports
NZSHM22_SCRIPT_WORK_PATH=/home/chrisbc/DEV/GNS/AWS_S3_DATA/WORKING
NZSHM22_TOSHI_API_URL=https://aihssdkef5.execute-api.ap-southeast-2.amazonaws.com/prod/graphql
NZSHM22_SOLVIS_API_URL=https://mmbzw56f1h.execute-api.ap-southeast-2.amazonaws.com/prod
NZSHM22_SOLVIS_API_KEY=5krfgPtC7P9Ghp8S04PS05oTpoofeL664rjnMWJM
```


## TEST log

```
openquake@tryharder-ubuntu:/app$ history
    1  time oq engine --run /WORKING/examples/16_SRWG_TEST/oq_inputs/4-sites_many-periods_vs30-475.ini
    2  oq engine --export-outputs 1 /WORKING/examples/output/TEST/4-sites-many
    3  ls -lath /home/openquake/oqdata/
    4  cp /home/openquake/oqdata/calc_1.hdf5 /WORKING/examples/output/TEST/4-sites-many.hdf5
    5  time oq engine --run /WORKING/examples/16_SRWG_TEST/oq_inputs/many-sites_3-periods_vs30-475.ini
    6  cp /home/openquake/oqdata/calc_2.hdf5 /WORKING/examples/output/TEST/34-sites-few.hdf5
    7  oq engine --export-outputs 2 /WORKING/examples/output/TEST/34-sites-few
    8  pwd
    9  ls
   10  cd /opt/openquake/
   11  ls
   12  cd lib
   13  ls
   14  cd python3.8/
   15  ls
   16  cd site-packages/
   17  ls
   18  oq --version
   19  cd /app
   20  time oq engine --run /WORKING/examples/16_SRWG_TEST/oq_inputs/test-disagg.ini
   21  oq engine --export-outputs 3 /WORKING/examples/output/TEST/test-disagg
   22  cp /home/openquake/oqdata/calc_3.hdf5 /WORKING/examples/output/TEST/test-disagg.hdf5
   23  history
```
