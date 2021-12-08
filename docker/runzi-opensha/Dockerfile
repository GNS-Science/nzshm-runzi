FROM adoptopenjdk/openjdk11:alpine-jre
LABEL Chris Chamberlain <chrisbc@artisan.co.nz>
RUN apk add --no-cache curl tar bash procps \
	python3 py3-pip git ttf-dejavu

WORKDIR /app/nzshm-opensha/build/libs
COPY nzshm-opensha/build/libs/nzshm-opensha-all.jar .

WORKDIR /WORKING
WORKDIR /app

COPY script/container_task.sh .
RUN chmod +x container_task.sh
RUN git clone https://github.com/GNS-Science/nzshm-runzi.git

WORKDIR /app/nzshm-runzi
RUN git fetch
# RUN git checkout feature/41_task_index_list_input
RUN pip3 install -r requirements.txt
RUN pip3 install -e .

ENV NZSHM22_TOSHI_API_ENABLED=1
ENV NZSHM22_SCRIPT_WORK_PATH=/WORKING
ENV NZSHM22_OPENSHA_JRE=/opt/java/openjdk/bin/java
ENV NZSHM22_FATJAR=/app/nzshm-opensha/build/libs/nzshm-opensha-all.jar
ENV NZSHM22_OPENSHA_ROOT=/app
ENV NZSHM22_S3_UPLOAD_WORKERS=25
ENV NZSHM22_BUILD_PLOTS=TRUE

ENV PYTHON_PREP_MODULE=SET_AT_RUNTIME
ENV PYTHON_TASK_MODULE=SET_AT_RUNTIME

CMD ["python3 /app/nzshm-runzi/runzi/cli/cli.py"]
ENTRYPOINT ["/bin/bash", "-c"]
