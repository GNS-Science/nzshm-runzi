ARG PYTHON_VERSION
FROM python:${PYTHON_VERSION}-slim-bookworm AS build

ARG PYTHON_VERSION
ARG FATJAR_TAG
ARG RUNZI_GITREF
ARG OQ_VERSION
ARG INSTALL_CONVERTER="N"

RUN test -n "$PYTHON_VERSION" || (echo "PYTHON_VERSION is required" && exit 1)
RUN test -n "$FATJAR_TAG" || (echo "FATJAR_TAG is required" && exit 1)
RUN test -n "$RUNZI_GITREF" || (echo "RUNZI_GITREF is required" && exit 1)
RUN test -n "$OQ_VERSION" || (echo "OQ_VERSION is required" && exit 1)

RUN pip install --upgrade pip
RUN apt update
RUN apt install -y git curl

# Install fonts needed for OpenSHA reports (config/env are propagated to the runtime stage)
RUN apt-get install -y fontconfig libfreetype6 fonts-dejavu-core && rm -rf /var/lib/apt/lists/*


WORKDIR /app
COPY ucerf* /app/ucerf

# Install java
RUN curl -sSL -o /tmp/jdk.tar.gz \
    "https://github.com/adoptium/temurin11-binaries/releases/download/jdk-11.0.25%2B9/OpenJDK11U-jdk_x64_linux_hotspot_11.0.25_9.tar.gz" \
    && tar -xzf /tmp/jdk.tar.gz -C /opt/ \
    && mv /opt/jdk-11.0.25+9 /opt/java \
    && rm /tmp/jdk.tar.gz

# Install OpenSHA
WORKDIR /opt/nzshm-opensha/build/libs
RUN curl -sSL -o nzshm-opensha-all-${FATJAR_TAG}.jar \
    https://nzshm-opensha-public-jars.s3.ap-southeast-2.amazonaws.com/nzshm-opensha-all-${FATJAR_TAG}.jar

# oq-venv: OpenQuake (pinned requirements) — cached aggressively, rarely changes
RUN python -m venv /opt/oq-venv
RUN export PY_NO_DOT=$(echo $PYTHON_VERSION | tr -d '.') && \
    /opt/oq-venv/bin/pip install \
        -r https://raw.githubusercontent.com/gem/oq-engine/refs/tags/v${OQ_VERSION}/requirements-py${PY_NO_DOT}-linux64.txt \
        openquake.engine==${OQ_VERSION}

# Optional UCERF converter into oq-venv (INSTALL_CONVERTER=Y to enable)
RUN if [ "$INSTALL_CONVERTER" = "Y" ] ; then \
    cd /app/ucerf && /opt/oq-venv/bin/pip install . ; \
    fi

# runzi-venv: runzi only — changes frequently, so comes after oq-venv
WORKDIR /app
RUN git clone https://github.com/GNS-Science/nzshm-runzi.git
WORKDIR /app/nzshm-runzi
RUN git fetch
RUN git checkout ${RUNZI_GITREF}
RUN python -m venv /opt/runzi-venv
RUN /opt/runzi-venv/bin/pip install .

# RUN rm -r /app
FROM python:${PYTHON_VERSION}-slim-bookworm AS runtime
ARG FATJAR_TAG
COPY --from=build /usr /usr
COPY --from=build /opt /opt
# Fonts for OpenSHA report / matplotlib rendering: libs+faces arrive via /usr, but
# fontconfig's config dir lives in /etc and ENV does not cross stages, so bring both across.
COPY --from=build /etc/fonts /etc/fonts
ENV FONTCONFIG_PATH=/etc/fonts
COPY java_container_task.sh /usr/local/bin/java_container_task.sh
COPY python_container_task.sh /usr/local/bin/python_container_task.sh
RUN chmod +x /usr/local/bin/java_container_task.sh
RUN chmod +x /usr/local/bin/python_container_task.sh

# create the toshi-hazard-store dataset directories to store realizations locally
WORKDIR /THS
ENV NZSHM22_THS_RLZ_DB=/THS/HAZARD
ENV NZSHM22_THS_DISAGG_RLZ_DB=/THS/DISAGG

# Create working directory and set env vars
WORKDIR /WORKING
RUN mkdir -p /WORKING /THS/HAZARD /THS/DISAGG && chmod 0777 /WORKING /THS/HAZARD /THS/DISAGG
ENV NZSHM22_SCRIPT_WORK_PATH=/WORKING
ENV NZSHM22_OPENSHA_JRE=/opt/java/bin
ENV NZSHM22_FATJAR=/opt/nzshm-opensha/build/libs/nzshm-opensha-all-${FATJAR_TAG}.jar
ENV NZSHM22_OPENSHA_ROOT=/app
ENV NZSHM22_S3_UPLOAD_WORKERS=25
ENV NZSHM22_BUILD_PLOTS=TRUE

ENV PYTHON_PREP_MODULE=SET_AT_RUNTIME
ENV PYTHON_TASK_MODULE=SET_AT_RUNTIME

# OpenQuake venv isolation
ENV NZSHM22_OQ_VENV=/opt/oq-venv
ENV NZSHM22_OQ_DATADIR=/oqdata
ENV PATH=/opt/runzi-venv/bin:$PATH
ENV NUMBA_CACHE_DIR=/tmp/numba_cache
ENV MPLCONFIGDIR=/tmp/matplotlib
RUN mkdir -p /oqdata && chmod 777 /oqdata && mkdir -p /tmp/numba_cache && chmod 777 /tmp/numba_cache && mkdir -p /tmp/matplotlib && chmod 777 /tmp/matplotlib

ENTRYPOINT ["/bin/bash", "-c"]

FROM runtime AS dev
COPY --from=build /app/nzshm-runzi /app/nzshm-runzi
WORKDIR /app/nzshm-runzi
RUN /opt/runzi-venv/bin/pip install -e .
WORKDIR /WORKING
ENV PYTHONDONTWRITEBYTECODE=1
