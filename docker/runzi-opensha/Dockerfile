ARG PYTHON_VERSION
FROM python:${PYTHON_VERSION}-slim-bookworm

ARG PYTHON_VERSION
ARG FATJAR_TAG
ARG RUNZI_GITREF
ARG OQ_VERSION

RUN test -n "$PYTHON_VERSION" || (echo "PYTHON_VERSION is required" && exit 1)
RUN test -n "$FATJAR_TAG" || (echo "FATJAR_TAG is required" && exit 1)
RUN test -n "$RUNZI_GITREF" || (echo "RUNZI_GITREF is required" && exit 1)
RUN test -n "$OQ_VERSION" || (echo "OQ_VERSION is required" && exit 1)

RUN pip install --upgrade pip
RUN apt update
RUN apt install -y git curl


# Install java
RUN curl -sSL -o /tmp/jdk.tar.gz \
    "https://github.com/adoptium/temurin11-binaries/releases/download/jdk-11.0.25%2B9/OpenJDK11U-jdk_x64_linux_hotspot_11.0.25_9.tar.gz" \
    && tar -xzf /tmp/jdk.tar.gz -C /opt/ \
    && mv /opt/jdk-11.0.25+9 /opt/java \
    && rm /tmp/jdk.tar.gz

# Install OpenSHA
WORKDIR /app/nzshm-opensha/build/libs
RUN curl -sSL -o nzshm-opensha-all-${FATJAR_TAG}.jar \
    https://nzshm-opensha-public-jars.s3.ap-southeast-2.amazonaws.com/nzshm-opensha-all-${FATJAR_TAG}.jar

# Install OpenQuake
RUN export PY_NO_DOT=$(echo $PYTHON_VERSION | tr -d '.') && \
  pip install -r https://raw.githubusercontent.com/gem/oq-engine/refs/tags/v${OQ_VERSION}/requirements-py${PY_NO_DOT}-linux64.txt openquake.engine==${OQ_VERSION}

# Install runzi
WORKDIR /app
COPY script/java_container_task.sh .
COPY script/python_container_task.sh .
RUN chmod +x java_container_task.sh
RUN chmod +x python_container_task.sh
RUN git clone https://github.com/GNS-Science/nzshm-runzi.git
WORKDIR /app/nzshm-runzi
RUN git fetch
RUN git checkout ${RUNZI_GITREF}
RUN pip install .

# Create working directory and set env vars
WORKDIR /WORKING
RUN mkdir -p /WORKING
ENV NZSHM22_TOSHI_API_ENABLED=1
ENV NZSHM22_SCRIPT_WORK_PATH=/WORKING
ENV NZSHM22_OPENSHA_JRE=/opt/java/bin
ENV NZSHM22_FATJAR=/app/nzshm-opensha/build/libs/nzshm-opensha-all-${FATJAR_TAG}.jar
ENV NZSHM22_OPENSHA_ROOT=/app
ENV NZSHM22_S3_UPLOAD_WORKERS=25
ENV NZSHM22_BUILD_PLOTS=TRUE

ENV PYTHON_PREP_MODULE=SET_AT_RUNTIME
ENV PYTHON_TASK_MODULE=SET_AT_RUNTIME

CMD ["runzi"]
ENTRYPOINT ["/bin/bash", "-c"]
