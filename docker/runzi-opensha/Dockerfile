FROM adoptopenjdk/openjdk11:alpine-jre
LABEL Chris Chamberlain <chrisbc@artisan.co.nz>
RUN apk add --no-cache curl tar bash procps \
	python3 py3-pip git

WORKDIR /app/nzshm-opensha/build/libs
COPY nzshm-opensha/build/libs/nzshm-opensha-all.jar .

WORKDIR /WORKING
WORKDIR /app

COPY script/container_task.sh .
RUN chmod +x container_task.sh
RUN git clone https://github.com/GNS-Science/nzshm-runzi.git

WORKDIR /app/nzshm-runzi
RUN git fetch
RUN git checkout origin/feature/AWS_containerised_inversion_task
RUN pip3 install -r headless_requirements.txt
RUN pip3 install -e .

CMD [""]
ENTRYPOINT ["/bin/bash", "-c"]