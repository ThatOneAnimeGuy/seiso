#!/bin/bash

source config.sh;
vars="$(printf '$%s ' $(compgen -A variable SEISO_))"
envsubst "$vars" < nginx.conf.tpl > nginx.conf
