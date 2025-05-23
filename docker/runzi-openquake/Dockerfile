# Dockerfile
# Extend base image
ARG OQ_VERSION
FROM openquake/engine:${OQ_VERSION}
ARG RUNZI_BRANCH

RUN echo $RUNZI_BRANCH

USER root

RUN apt-get update
RUN apt-get install git -y
RUN apt-get install nano

WORKDIR /WORKING

RUN /opt/openquake/bin/python3 -m pip install --upgrade pip

# Install runzi from GH repo
WORKDIR /app
COPY script/container_task.sh .
RUN chmod +x container_task.sh

WORKDIR /app

RUN git clone https://github.com/GNS-Science/nzshm-runzi.git
WORKDIR /app/nzshm-runzi
RUN git fetch
RUN git switch $RUNZI_BRANCH
RUN pip3 install -e .


# default settings for toshi-hazard-store
WORKDIR /app
COPY pynamodb_settings.py .
ENV PYNAMODB_CONFIG=/app/pynamodb_settings.py
ENV NZSHM22_HAZARD_STORE_NUM_WORKERS=4
ENV NZSHM22_HAZARD_STORE_STAGE=PROD
ENV NZSHM22_HAZARD_STORE_REGION=ap-southeast-2

RUN chown openquake /WORKING

# Install Marcos Converter
# git@gitlab.openquake.org:hazard/converters/ucerf.git
# we'll use ADD for now as the repo is not public
# AND for now we're mapping in the code like so `docker run  -it --rm -v $(pwd)/../../../ucerf:/app/ucerf`
# AND then running pip install -e . in the ucerf folder to test
# https://stackoverflow.com/questions/31528384/conditional-copy-add-in-dockerfile
ADD ucerf3-update[s] /app/ucerf
WORKDIR /app/ucerf
RUN if [[ -f pyproject.toml || -f setup.py ]]; then pip install -e .; fi

USER openquake

ENV NZSHM22_TOSHI_API_ENABLED=1
ENV NZSHM22_SCRIPT_WORK_PATH=/WORKING

CMD ["python3 /app/nzshm-runzi/runzi/cli/cli.py"]
ENTRYPOINT ["/bin/bash", "-c"]
