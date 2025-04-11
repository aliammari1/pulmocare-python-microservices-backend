#!/bin/bash
set -e

LOG_FILE="/usr/local/apisix/logs/startup.log"

log() {
    local message=$1
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $message" | tee -a $LOG_FILE
}

# Create logs directory if it doesn't exist
mkdir -p /usr/local/apisix/logs

# Clean up any existing socket files
log "Cleaning up any existing socket files..."
rm -f /usr/local/apisix/logs/worker_events.sock

# Validate configuration files
log "Validating APISIX configuration..."
if ! /usr/bin/apisix test; then
    log "ERROR: APISIX configuration validation failed. Exiting."
    exit 1
fi
log "APISIX configuration validation successful."

# Initialize and start APISIX
log "Initializing and starting APISIX..."
/usr/bin/apisix init
sleep 2
/usr/bin/apisix start &

# Wait for APISIX to be ready
log "Waiting for APISIX to be ready..."
max_retries=30
retry_count=0
backoff=1

while [ $retry_count -lt $max_retries ]; do
    if curl -s -m 1 -o /dev/null http://localhost:9180/apisix/admin/server_info -H "X-API-KEY: ${APISIX_ADMIN_KEY:-edd1c9f034335f136f87ad84b625c8f1}"; then
        log "APISIX is ready!"
        break
    fi
    retry_count=$((retry_count + 1))
    if [ $retry_count -eq $max_retries ]; then
        log "APISIX health check failed after ${max_retries} attempts."
        break
    fi
    log "APISIX is not ready yet. Waiting... (Attempt ${retry_count}/${max_retries})"
    sleep $backoff
    backoff=$((backoff * 2 > 10 ? 10 : backoff * 2))
done

# Wait for etcd
log "Waiting for etcd to be ready..."
max_retries=30
retry_count=0
backoff=1

while [ $retry_count -lt $max_retries ]; do
    if curl -s -m 2 -o /dev/null http://etcd:2379/health; then
        log "etcd is ready!"
        break
    fi
    retry_count=$((retry_count + 1))
    if [ $retry_count -eq $max_retries ]; then
        log "etcd health check failed after ${max_retries} attempts."
        break
    fi
    log "etcd is not ready yet. Waiting... (Attempt ${retry_count}/${max_retries})"
    sleep $backoff
    backoff=$((backoff * 2 > 10 ? 10 : backoff * 2))
done

# Import routes
log "Importing routes..."
if [ -f "/usr/local/apisix/import-routes.sh" ]; then
    chmod +x /usr/local/apisix/import-routes.sh
    if ! /usr/local/apisix/import-routes.sh; then
        log "WARNING: Route import failed"
    fi
fi

log "APISIX setup completed"

# Keep container running and follow logs
tail -f /usr/local/apisix/logs/error.log /usr/local/apisix/logs/access.log
