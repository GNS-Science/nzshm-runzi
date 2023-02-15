# Dockerfile
# Extend base image
# needs openquake/engine >= 3.15.0
#nightly
FROM openquake/engine:3.15

USER root

RUN apt-get update
RUN apt-get install git -y
RUN apt-get install nano
RUN apt-get install wget

WORKDIR /WORKING

RUN /opt/openquake/bin/python3 -m pip install --upgrade pip
RUN pip install lxml
RUN pip install tqdm
RUN pip install numba
# RUN pip uninstall -y numba
RUN pip install pytest

#TEMP until this is in GEM repo
ADD gsim /opt/openquake/lib/python3.9/site-packages/openquake/hazardlib/gsim

#Disagg bins modification
RUN wget https://raw.githubusercontent.com/chrisdicaprio/oq-engine/756435096fda41a24f49e8e64adc150cf629e0b2/openquake/hazardlib/calc/disagg.py\
 -O /opt/openquake/lib/python3.9/site-packages/openquake/hazardlib/calc/disagg.py
RUN wget https://raw.githubusercontent.com/chrisdicaprio/oq-engine/756435096fda41a24f49e8e64adc150cf629e0b2/openquake/commonlib/oqvalidation.py\
 -O /opt/openquake/lib/python3.9/site-packages/openquake/commonlib/oqvalidation.py


# Install Runzi TODO:is this only for these test configs ??
WORKDIR /app
COPY script/container_task.sh .
RUN chmod +x container_task.sh

WORKDIR /app
RUN git clone https://github.com/GNS-Science/nzshm-runzi.git

WORKDIR /app/nzshm-runzi
RUN git fetch
RUN git checkout feature/grid-srwg214
RUN pip3 install -r requirements.txt
RUN pip3 install -e .


# The AWS hazard store script ...
RUN pip install git+https://github.com/GNS-Science/toshi-hazard-store@031e336e5988f0ce717f7f4ceede7be63b90bfcc#egg=toshi-hazard-store
#RUN pip install toshi_hazard_store
RUN pip install -U numba

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
