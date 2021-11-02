FROM adoptopenjdk/openjdk11:alpine-jre
LABEL Chris Chamberlain <chrisbc@artisan.co.nz>
RUN apk add --no-cache curl tar bash procps \
	python3 py3-pip git

WORKDIR /nzshm-opensha/build/libs
COPY nzshm-opensha/build/libs/nzshm-opensha-all.jar .

WORKDIR /app
RUN git clone https://github.com/GNS-Science/nzshm-runzi.git

WORKDIR /app/nzshm-runzi
RUN git checkout feature/AWS_containerised_inversion_task
RUN pip3 install -e .

CMD [""]
ENTRYPOINT ["/bin/bash", "-c"]