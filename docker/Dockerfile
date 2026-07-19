# syntax=docker/dockerfile:1
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

# Build-only tooling. Fonts are installed in the runtime stage directly, not dragged
# across from here — see the runtime stage for why.
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends git curl
RUN --mount=type=cache,target=/root/.cache/pip pip install --upgrade pip

WORKDIR /app
COPY ucerf* /app/ucerf

# Install java (JRE only — OpenSHA runs via the py4j gateway and we never compile, so the
# ~180 MB of extra JDK tooling is dead weight). --strip-components makes the extract
# independent of the archive's top-level directory name.
RUN mkdir -p /opt/java \
    && curl -sSL -o /tmp/jre.tar.gz \
    "https://github.com/adoptium/temurin11-binaries/releases/download/jdk-11.0.25%2B9/OpenJDK11U-jre_x64_linux_hotspot_11.0.25_9.tar.gz" \
    && tar -xzf /tmp/jre.tar.gz -C /opt/java --strip-components=1 \
    && rm /tmp/jre.tar.gz

# Install OpenSHA
WORKDIR /opt/nzshm-opensha/build/libs
RUN curl -sSL -o nzshm-opensha-all-${FATJAR_TAG}.jar \
    https://nzshm-opensha-public-jars.s3.ap-southeast-2.amazonaws.com/nzshm-opensha-all-${FATJAR_TAG}.jar

# oq-venv: OpenQuake (pinned requirements) — cached aggressively, rarely changes.
# The pip cache mount keeps the heavy dependency stack (numpy/scipy/pandas/h5py…) off
# the image layer while avoiding re-downloads on rebuilds.
RUN python -m venv /opt/oq-venv
RUN --mount=type=cache,target=/root/.cache/pip \
    export PY_NO_DOT=$(echo $PYTHON_VERSION | tr -d '.') && \
    /opt/oq-venv/bin/pip install \
        -r https://raw.githubusercontent.com/gem/oq-engine/refs/tags/v${OQ_VERSION}/requirements-py${PY_NO_DOT}-linux64.txt \
        openquake.engine==${OQ_VERSION}

# Optional UCERF converter into oq-venv (INSTALL_CONVERTER=Y to enable)
RUN --mount=type=cache,target=/root/.cache/pip \
    if [ "$INSTALL_CONVERTER" = "Y" ] ; then \
    cd /app/ucerf && /opt/oq-venv/bin/pip install . ; \
    fi

# runzi-venv: runzi only — changes frequently, so comes after oq-venv. Installed straight
# from git: pip performs the clone/checkout (accepting a branch, tag, or the full commit SHA
# the build CLI passes) and hatch-vcs derives the version from the tag history pip's clone
# brings along — no separate working tree to manage or copy.
WORKDIR /app
RUN python -m venv /opt/runzi-venv
RUN --mount=type=cache,target=/root/.cache/pip \
    /opt/runzi-venv/bin/pip install "runzi @ git+https://github.com/GNS-Science/nzshm-runzi.git@${RUNZI_GITREF}"

FROM python:${PYTHON_VERSION}-slim-bookworm AS runtime
ARG FATJAR_TAG

# Runtime system deps, installed directly rather than by copying the entire build-stage
# /usr across: the venvs in /opt were built against this same base image's Python, so only
# /opt is a real artifact — copying /usr would also drag in curl and a duplicate interpreter.
#   - fonts: OpenSHA report / matplotlib rendering
#   - git: several inversion/rupset tasks use GitPython (git.Repo) at runtime, which shells
#     out to the git binary.
RUN apt-get update \
    && apt-get install -y --no-install-recommends git fontconfig libfreetype6 fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*
ENV FONTCONFIG_PATH=/etc/fonts

# venvs + java + fatjar — the only artifacts the runtime needs from the build stage.
COPY --from=build /opt /opt

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
