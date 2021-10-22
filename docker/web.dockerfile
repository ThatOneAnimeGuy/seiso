FROM nginx:stable

RUN apt-get update
RUN apt-get install -y python3-certbot-nginx

COPY ./nginx /root/nginx
WORKDIR /root/nginx
RUN /bin/bash build_conf.sh && mv nginx.conf /etc/nginx/nginx.conf
