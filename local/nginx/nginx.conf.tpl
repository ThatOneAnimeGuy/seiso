user www-data;
worker_processes auto;
pid /run/nginx.pid;
include /etc/nginx/modules-enabled/*.conf;

events {
    worker_connections  768;
}

http {
    default_type       text/html;
    sendfile           on;
    keepalive_timeout  65;

    server {
        listen 80;
        server_name $SEISO_CDN_SERVER_NAME_1 $SEISO_CDN_SERVER_NAME_2;
        access_log /var/log/cdn.access.log combined;

        if ($http_host = $SEISO_CDN_SERVER_NAME_1) {
            set $bucket $SEISO_STORAGE_BUCKET_URL_1;
        }

        if ($http_host = $SEISO_CDN_SERVER_NAME_2) {
            set $bucket $SEISO_STORAGE_BUCKET_URL_2;
        }

        location / {
            resolver               1.1.1.1;
            proxy_http_version     1.1;
            proxy_redirect         off;
            proxy_set_header       Connection "";
            proxy_set_header       Authorization '';   
            proxy_set_header       Host $bucket;
            proxy_set_header       X-Real-IP $remote_addr;
            proxy_set_header       X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_hide_header      x-amz-id-2;
            proxy_hide_header      x-amz-request-id;
            proxy_hide_header      x-amz-meta-server-side-encryption;
            proxy_hide_header      x-amz-server-side-encryption;
            proxy_hide_header      Set-Cookie;
            proxy_ignore_headers   Set-Cookie;
            proxy_intercept_errors on;
            add_header             Cache-Control max-age=31536000;
            proxy_pass             https://$bucket$request_uri;
        }
    }

    server {
        listen 80;
        client_max_body_size 100m;
        server_name  $SEISO_APP_SERVER_NAME;
        access_log   /var/log/access.log combined;
        include      mime.types;

        location /static {
            root /app;
            try_files $uri _404;
        }

        location /favicon.ico {
            root /app/static;
            try_files $uri _404;
        }

        location / {
            proxy_pass http://seiso-app:8000;
        }
    }
}
