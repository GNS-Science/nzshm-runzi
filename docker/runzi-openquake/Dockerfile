# Dockerfile
# Extend base image
# needs openquake/engine >= 3.13.0
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

# AND for now we're mapping in the code like so `docker run  -it --rm -v $(pwd)/../../../ucerf:/app/ucerf`
# AND then running pip install -e . in the ucerf folder to test

#USER openquake

# Install Runzi TODO:is this only for these test configs ??
WORKDIR /app
RUN git clone https://github.com/GNS-Science/nzshm-runzi.git
WORKDIR /app/nzshm-runzi

RUN git fetch
RUN git checkout feature/89-integrate-openquake-and-toshiapi
RUN pip3 install -r requirements.txt
RUN pip3 install -e .

## Install Kirans grin2oq.py script
# WORKDIR /app
# ADD src/grin2oq.py .

RUN chown openquake /WORKING

# Install Marcos Converter
# git@gitlab.openquake.org:hazard/converters/ucerf.git
# we'll use ADD for now as the repo is not public
ADD ucerf3-updates /app/ucerf
WORKDIR /app/ucerf
RUN pip install -e .

USER openquake

CMD ["python3 /app/nzshm-runzi/runzi/cli/cli.py"]
ENTRYPOINT ["/bin/bash", "-c"]
