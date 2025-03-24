FROM kong:latest

USER root

# Install basic utilities
RUN apt-get update && \
    apt-get install -y curl wget vim procps net-tools && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Create necessary directories
RUN mkdir -p /usr/local/kong/logs && \
    mkdir -p /usr/local/share/lua/5.1/kong/plugins/body-inspector

# Copy plugin files - make these copies before setting permissions
COPY plugins/body-inspector/handler.lua /usr/local/share/lua/5.1/kong/plugins/body-inspector/
COPY plugins/body-inspector/schema.lua /usr/local/share/lua/5.1/kong/plugins/body-inspector/

# Copy configuration files
COPY kong.yml /usr/local/kong/declarative/kong.yml
COPY start-kong.sh /usr/local/bin/start-kong.sh

# Set proper permissions - avoid changing directory permissions that might be mounted
RUN chmod +x /usr/local/bin/start-kong.sh && \
    chown -R kong:kong /usr/local/kong/logs && \
    chmod -R 777 /usr/local/kong/logs && \
    chmod 644 /usr/local/kong/declarative/kong.yml && \
    chown -R kong:kong /usr/local/share/lua/5.1/kong/plugins/body-inspector && \
    chmod -R 755 /usr/local/share/lua/5.1/kong/plugins/body-inspector

# Environment variables configuration
ENV KONG_DATABASE="off"
ENV KONG_DECLARATIVE_CONFIG="/usr/local/kong/declarative/kong.yml"
ENV KONG_PLUGINS="bundled,prometheus,cors,http-log,body-inspector"
ENV KONG_LOG_LEVEL="debug"
ENV KONG_PROXY_ACCESS_LOG="/dev/stdout"
ENV KONG_ADMIN_ACCESS_LOG="/dev/stdout"
ENV KONG_PROXY_ERROR_LOG="/dev/stderr"
ENV KONG_ADMIN_ERROR_LOG="/dev/stderr"
ENV KONG_ADMIN_LISTEN="0.0.0.0:8001"
ENV KONG_PROXY_LISTEN="0.0.0.0:8000"
ENV KONG_NGINX_DAEMON="off"

# Switch to kong user
USER kong

EXPOSE 8000 8001 8002

# Use the custom entrypoint script 
ENTRYPOINT ["/usr/local/bin/start-kong.sh"]
