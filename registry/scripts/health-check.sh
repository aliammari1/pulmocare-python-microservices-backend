#!/bin/bash
# Registry health check script

REGISTRY_URL="https://registry.medapp.local:5000"

# Check registry health
if curl -k -f "$REGISTRY_URL/v2/" > /dev/null 2>&1; then
    echo "Registry is healthy"
    exit 0
else
    echo "Registry is unhealthy"
    exit 1
fi
