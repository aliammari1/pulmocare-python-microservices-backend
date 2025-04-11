FROM apache/apisix:latest

# Install basic development dependencies
USER root
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libssl-dev \
    libpcre3-dev \
    zlib1g-dev \
    lua5.1-dev \
    curl \
    unzip \
    git \
    wget \
    make \
    jq \
    python3 \
    python3-pip \
    ca-certificates \
    logrotate \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install LuaRocks
RUN wget https://luarocks.org/releases/luarocks-3.9.2.tar.gz \
    && tar -xzvf luarocks-3.9.2.tar.gz \
    && cd luarocks-3.9.2 \
    && ./configure --with-lua-include=/usr/include/lua5.1 \
    && make \
    && make install \
    && cd .. \
    && rm -rf luarocks-3.9.2 \
    && rm luarocks-3.9.2.tar.gz

# Install Lua packages
RUN luarocks install lua-resty-jwt \
    && luarocks install lua-resty-session \
    && luarocks install lua-resty-http \
    && luarocks install lua-resty-openidc

# Install Python packages
RUN pip3 install --no-cache-dir \
    pyyaml \
    requests

# Create necessary directories
RUN mkdir -p /usr/local/apisix/logs \
    && mkdir -p /usr/local/apisix/conf

# Copy configuration files
COPY config.yaml /usr/local/apisix/conf/config.yaml
COPY apisix.yaml /usr/local/apisix/conf/apisix.yaml
COPY import-routes.sh /usr/local/apisix/import-routes.sh
COPY entrypoint.sh /usr/local/apisix/entrypoint.sh

# Set permissions
RUN chmod 755 /usr/local/apisix/entrypoint.sh \
    && chmod 755 /usr/local/apisix/import-routes.sh

# Basic log rotation setup
COPY <<-'EOF' /etc/logrotate.d/apisix
/usr/local/apisix/logs/*.log {
    daily
    missingok
    rotate 7
    compress
    delaycompress
    notifempty
    create 644 root root
}
EOF

# Set environment variables
ENV APISIX_STAND_ALONE=false \
    ETCD_HOST=http://etcd:2379 \
    PATH=$PATH:/usr/local/openresty/luajit/bin:/usr/local/openresty/nginx/sbin:/usr/local/openresty/bin

# Simple healthcheck
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:9080/apisix/admin/health || exit 1

ENTRYPOINT ["/usr/local/apisix/entrypoint.sh"]
