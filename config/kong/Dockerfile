FROM kong/kong-gateway:latest

USER root

RUN apt-get update && apt-get install -y apt-utils dnsutils

COPY start-kong.sh /start-kong.sh

RUN chmod +x /start-kong.sh

COPY kong.yml /usr/local/kong/declarative/kong.yml

RUN apt-get clean && rm -rf /var/lib/apt/lists/*

EXPOSE 8000 8001 8002 8443 8444

CMD ["/start-kong.sh"]



ENV KONG_DNS_RESOLVER=127.0.0.11:53
