# Dockerfile
# Extend base image
FROM openquake/engine

USER root
RUN apt-get update
RUN apt-get install git -y

WORKDIR /WORKING
WORKDIR /app
RUN git clone https://github.com/GNS-Science/nzshm-runzi.git

WORKDIR /app/nzshm-runzi

RUN git fetch
RUN git checkout feature/48_runzi-openquake_docker_build
RUN pip3 install -r requirements.txt
RUN pip3 install -e .

RUN chown openquake /WORKING
USER openquake

CMD ["python3 /app/nzshm-runzi/runzi/cli/cli.py"]
ENTRYPOINT ["/bin/bash", "-c"]