#!/bin/bash
set -e

# Get Consul's IP and add to hosts file
CONSUL_IP=$(getent hosts consul | awk '{ print $1 }')
if [ ! -z "$CONSUL_IP" ]; then
  echo "$CONSUL_IP consul" >> /etc/hosts
fi

# Start Kong
kong start