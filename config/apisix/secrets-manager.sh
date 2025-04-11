#!/bin/bash

# APISIX Secrets Manager Script
# This script manages secrets and environment variables for APISIX in a secure way

# Function to generate a random string for keys
generate_random_key() {
    openssl rand -base64 32 | tr -d '/+=' | cut -c1-32
}

# Create secrets directory if it doesn't exist
SECRETS_DIR="/opt/apisix/secrets"
mkdir -p "$SECRETS_DIR"
chmod 700 "$SECRETS_DIR"

# Generate admin key if it doesn't exist
ADMIN_KEY_FILE="$SECRETS_DIR/admin_key"
if [ ! -f "$ADMIN_KEY_FILE" ]; then
    generate_random_key > "$ADMIN_KEY_FILE"
    chmod 600 "$ADMIN_KEY_FILE"
fi

# Generate API key if it doesn't exist
API_KEY_FILE="$SECRETS_DIR/api_key"
if [ ! -f "$API_KEY_FILE" ]; then
    generate_random_key > "$API_KEY_FILE"
    chmod 600 "$API_KEY_FILE"
fi

# Create certificates directory
CERTS_DIR="/opt/apisix/certs"
mkdir -p "$CERTS_DIR"
chmod 700 "$CERTS_DIR"

# Export environment variables
export ADMIN_KEY=$(cat "$ADMIN_KEY_FILE")
export API_KEY=$(cat "$API_KEY_FILE")
export ALLOWED_ORIGINS=${ALLOWED_ORIGINS:-"http://localhost:*"}
export KEYCLOAK_CLIENT_ID=${KEYCLOAK_CLIENT_ID:-"medapp-api"}
export KEYCLOAK_CLIENT_SECRET=${KEYCLOAK_CLIENT_SECRET:-"default-secret"}
export KEYCLOAK_DISCOVERY_URL=${KEYCLOAK_DISCOVERY_URL:-"http://keycloak:8080/realms/medapp/.well-known/openid-configuration"}

# Generate self-signed certificates if they don't exist
if [ ! -f "$CERTS_DIR/admin.key" ]; then
    # Generate CA key and certificate
    openssl genrsa -out "$CERTS_DIR/ca.key" 4096
    openssl req -x509 -new -nodes -key "$CERTS_DIR/ca.key" -sha256 -days 365 -out "$CERTS_DIR/ca.crt" \
        -subj "/CN=APISIX CA/O=APISIX/C=CN"

    # Generate admin certificate
    openssl genrsa -out "$CERTS_DIR/admin.key" 2048
    openssl req -new -key "$CERTS_DIR/admin.key" \
        -subj "/CN=admin.apisix/O=APISIX/C=CN" \
        -out "$CERTS_DIR/admin.csr"
    openssl x509 -req -in "$CERTS_DIR/admin.csr" \
        -CA "$CERTS_DIR/ca.crt" \
        -CAkey "$CERTS_DIR/ca.key" \
        -CAcreateserial \
        -out "$CERTS_DIR/admin.crt" \
        -days 365 -sha256

    # Generate etcd client certificate
    openssl genrsa -out "$CERTS_DIR/etcd_client.key" 2048
    openssl req -new -key "$CERTS_DIR/etcd_client.key" \
        -subj "/CN=etcd.local/O=APISIX/C=CN" \
        -out "$CERTS_DIR/etcd_client.csr"
    openssl x509 -req -in "$CERTS_DIR/etcd_client.csr" \
        -CA "$CERTS_DIR/ca.crt" \
        -CAkey "$CERTS_DIR/ca.key" \
        -CAcreateserial \
        -out "$CERTS_DIR/etcd_client.crt" \
        -days 365 -sha256

    # Set proper permissions
    chmod 600 "$CERTS_DIR"/*.key
    chmod 644 "$CERTS_DIR"/*.crt
    chmod 644 "$CERTS_DIR"/*.csr
fi

# Output status
echo "Secrets and certificates have been configured:"
echo "- Admin key: ${ADMIN_KEY:0:8}... (truncated)"
echo "- API key: ${API_KEY:0:8}... (truncated)"
echo "- Certificates generated in: $CERTS_DIR"
echo "- Environment variables exported"
