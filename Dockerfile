FROM python:3.6-slim

MAINTAINER Ronan Delacroix <ronan.delacroix@gmail.com>

# psutil requires gcc, so we'll install build-essential. evenlet also requires netbase.
RUN apt-get update -y -q && \
    apt-get install --no-install-recommends -y -q \
        build-essential && \
    apt-get -o Dpkg::Options::="--force-confmiss" install -y -q --no-install-recommends --reinstall netbase && \
    apt-get clean && \
    rm /var/lib/apt/lists/*_*

COPY ./requirements.txt /opt/app/
WORKDIR /opt/app

RUN pip3 install --no-cache-dir -r requirements.txt

RUN mkdir /opt/current_folder
VOLUME /opt/current_folder

ENV PYTHONPATH=$PYTHONPATH:/opt/app:/opt/current_folder

COPY . /opt/app

ENTRYPOINT ["python3", "/opt/app/bin/jobmanager-builder"]
