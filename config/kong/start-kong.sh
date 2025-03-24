#!/bin/bash
set -e

echo "Starting Kong initialization..."

# Check if the Kong configuration file exists
if [ ! -f "/usr/local/kong/declarative/kong.yml" ]; then
  echo "Error: Kong configuration file not found at /usr/local/kong/declarative/kong.yml"
  exit 1
fi

# Print plugins
echo "Checking installed plugins..."
kong version

echo "Available plugins:"
ls -la /usr/local/share/lua/5.1/kong/plugins/

# Start Kong in the background
echo "Starting Kong..."
kong start

# Keep the container running
echo "Kong started, now keeping container alive..."
tail -f /dev/null & # Send a background process to keep container running
wait $! # Wait for the background process, which won't terminate