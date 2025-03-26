FROM kong:latest

USER root

RUN apt-get update && apt-get upgrade -y && apt-get install curl -y

USER kong

COPY kong.yaml /kong.yaml

