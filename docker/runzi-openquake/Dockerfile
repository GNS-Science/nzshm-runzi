# Dockerfile
# Extend base image
# needs openquake/engine >= 3.13.0
#nightly
FROM openquake/engine:nightly

USER root

RUN apt-get update
RUN apt-get install git -y
RUN apt-get install nano

WORKDIR /WORKING

RUN /opt/openquake/bin/python3 -m pip install --upgrade pip
RUN pip install lxml
RUN pip install tqdm
RUN pip install numba
RUN pip install pytest

#TEMP until this is in GEM repo
ADD gsim /usr/src/oq-engine/openquake/hazardlib/gsim
ADD tom.py /usr/src/oq-engine/openquake/hazardlib

#TEMP UNTIL GEM ACCEPTS ANNES mods
RUN wget https://raw.githubusercontent.com/annehulsey/oq-engine/59bf0b51ae4e614bb4963532250429137bca4817/openquake/hazardlib/calc/disagg.py\
 -O /usr/src/oq-engine/openquake/hazardlib/calc/disagg.py
RUN wget https://raw.githubusercontent.com/annehulsey/oq-engine/59bf0b51ae4e614bb4963532250429137bca4817/openquake/calculators/disaggregation.py\
 -O /usr/src/oq-engine/openquake/calculators/disaggregation.py


# Install Runzi TODO:is this only for these test configs ??
WORKDIR /app
COPY script/container_task.sh .
RUN chmod +x container_task.sh

WORKDIR /app
RUN git clone https://github.com/GNS-Science/nzshm-runzi.git

WORKDIR /app/nzshm-runzi
RUN git fetch
RUN git checkout feature/144-multiple-disaggs
RUN pip3 install -r requirements.txt
RUN pip3 install -e .


# The AWS hazard store script ...
RUN pip install git+https://github.com/GNS-Science/toshi-hazard-store@f96c85a886d28f0d40afdaef675a55cdaa01ad4f#egg=toshi-hazard-store
#RUN pip install toshi_hazard_store

# settings for toshi-hazard-store
WORKDIR /app
COPY pynamodb_settings.py .
ENV PYNAMODB_CONFIG=/app/pynamodb_settings.py
ENV NZSHM22_HAZARD_STORE_NUM_WORKERS=4
ENV NZSHM22_HAZARD_STORE_STAGE=PROD
ENV NZSHM22_HAZARD_STORE_REGION=ap-southeast-2
# ENV NZSHM22_HAZARD_STORE_REGION=us-east-1 not sure this matters as I think it's overridden in oq_hazard.py

RUN chown openquake /WORKING

# Install Marcos Converter
# git@gitlab.openquake.org:hazard/converters/ucerf.git
# we'll use ADD for now as the repo is not public
# AND for now we're mapping in the code like so `docker run  -it --rm -v $(pwd)/../../../ucerf:/app/ucerf`
# AND then running pip install -e . in the ucerf folder to test
ADD ucerf3-updates /app/ucerf
WORKDIR /app/ucerf
RUN pip install -e .

USER openquake

ENV NZSHM22_TOSHI_API_ENABLED=1
ENV NZSHM22_SCRIPT_WORK_PATH=/WORKING

CMD ["python3 /app/nzshm-runzi/runzi/cli/cli.py"]
ENTRYPOINT ["/bin/bash", "-c"]
