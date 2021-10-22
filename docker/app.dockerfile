FROM ubuntu:20.04

RUN apt-get update
RUN DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends build-essential python3 python3-dev python3-pip nginx libpq-dev curl libmagic1
RUN pip3 install uwsgi

WORKDIR /app
COPY . /app

RUN pip3 install -r requirements.txt
RUN pip3 install -r src/vendor/PixivUtil2/requirements.txt

ENV DB_ROOT=/storage
ENV LANG=C.UTF-8
CMD uwsgi --ini ./uwsgi.ini
