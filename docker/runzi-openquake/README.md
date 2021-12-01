
# BUILD

docker build . -t nzshm22/runzi-openquake


# RUN
```
docker run -it --rm \
-e NZSHM22_TOSHI_S3_URL \
-e NZSHM22_TOSHI_API_URL \
-e NZSHM22_SCRIPT_CLUSTER_MODE \
nzshm22/runzi-openquake
```