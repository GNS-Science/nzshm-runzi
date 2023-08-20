# General

A few things you'll want to setup for all types of jobs.

## AWS Profile

## Environment Variables

Set environment variables

### TEST
If you're running in the TEST environment:

* `NZSHM22_TOSHI_API_KEY`: _secret_
* `NZSHM22_TOSHI_API_URL`: https://i7gz6msaa2.execute-api.ap-southeast-2.amazonaws.com/test/graphql
* `NZSHM22_TOSHI_S3_URL`: https://nzshm22-toshi-api-test.s3.amazonaws.com
* `NZSHM22_S3_REPORT_BUCKET`: nzshm22-static-reports-test
* `NZSHM22_SOLVIS_API_URL`: https://fcx7tkv322.execute-api.ap-southeast-2.amazonaws.com/test
* `NZSHM22_SOLVIS_API_KEY`: _secret_
* `NZSHM22_SCRIPT_WORK_PATH`: convenient directory on large disk, could be on `/tmp` (**DIFFERENT FROM PROD PATH***)
* `NZSHM22_HAZARD_STORE_STAGE`: TEST
* `NZSHM22_HAZARD_STORE_REGION`: ap-southeast-2

### Prod
If you're running in the PROD environment:

* `NZSHM22_TOSHI_API_KEY`: _secret_
* `NZSHM22_TOSHI_API_URL`: https://aihssdkef5.execute-api.ap-southeast-2.amazonaws.com/prod/graphql
* `NZSHM22_TOSHI_S3_URL`: https://nzshm22-toshi-api-prod.s3.amazonaws.com
* `NZSHM22_S3_REPORT_BUCKET`: nzshm22-static-reports
* `NZSHM22_SOLVIS_API_URL`: https://mmbzw56f1h.execute-api.ap-southeast-2.amazonaws.com/prod
* `NZSHM22_SOLVIS_API_KEY`: _secret_
* `NZSHM22_SCRIPT_WORK_PATH`: convenient directory on large disk, could be on `/tmp` (**DIFFERENT FROM TEST PATH**)
* `NZSHM22_HAZARD_STORE_STAGE`: PROD
* `NZSHM22_HAZARD_STORE_REGION`: ap-southeast-2

## Running Variables
These are variables that you may want to change at run-time -- they are not necessarilly kept as envars:

* `AWS_PROFILE`: the name of the AWS profile to use, if you have multiple
* `NZSHM22_TOSHI_API_ENABLED` set to `1` if you want to store results using toshiAPI, otherwise results will remain as local files
* `NZSHM22_SCRIPT_CLUSTER_MODE` set to `LOCAL` to run locally or `AWS` to run on AWS.

# Job Types

 * [Inversion](user_guide/inversion.md)