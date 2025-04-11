#!/bin/bash
set -e

LOG_FILE="/usr/local/apisix/logs/import-routes.log"
echo "$(date) - Starting route import to APISIX..." | tee -a $LOG_FILE

# Admin API endpoint
ADMIN_API="http://localhost:9180/apisix/admin"
ADMIN_KEY=${APISIX_ADMIN_KEY:-edd1c9f034335f136f87ad84b625c8f1}

# Import routes using Python
python3 << 'EOF'
import yaml
import os
import json
import sys
import requests
import time
from datetime import datetime

def log(msg):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print("{} - {}".format(timestamp, msg))

try:
    config_path = "/usr/local/apisix/conf/apisix.yaml"
    log("Reading config from: " + config_path)
    
    if not os.path.exists(config_path):
        log("Error: Config file not found")
        sys.exit(1)

    with open(config_path) as f:
        config = yaml.safe_load(f)

    headers = {
        "X-API-KEY": os.getenv("APISIX_ADMIN_KEY", "edd1c9f034335f136f87ad84b625c8f1"),
        "Content-Type": "application/json"
    }
    base_url = "http://localhost:9180/apisix/admin"

    # Import routes
    if "routes" in config:
        routes = config["routes"]
        log("Found {} routes".format(len(routes)))
        success = 0
        
        for route in routes:
            try:
                route_id = route.get("id", "unknown")
                url = base_url + "/routes/" + str(route_id)
                response = requests.put(url, headers=headers, json=route)
                
                if response.status_code in [200, 201]:
                    success += 1
                    log("Route {} imported successfully".format(route_id))
                else:
                    log("Failed to import route {}: {}".format(route_id, response.status_code))
            except Exception as e:
                log("Error importing route: " + str(e))
        
        log("Routes imported: {}/{}".format(success, len(routes)))

    # Import consumers
    if "consumers" in config:
        consumers = config["consumers"]
        log("Found {} consumers".format(len(consumers)))
        success = 0
        
        for consumer in consumers:
            try:
                username = consumer.get("username", "unknown")
                url = base_url + "/consumers/" + str(username)
                response = requests.put(url, headers=headers, json=consumer)
                
                if response.status_code in [200, 201]:
                    success += 1
                    log("Consumer {} imported successfully".format(username))
                else:
                    log("Failed to import consumer {}: {}".format(username, response.status_code))
            except Exception as e:
                log("Error importing consumer: " + str(e))
        
        log("Consumers imported: {}/{}".format(success, len(consumers)))

    # Import global rules
    if "global_rules" in config:
        rules = config["global_rules"]
        log("Found {} global rules".format(len(rules)))
        success = 0
        
        for rule in rules:
            try:
                rule_id = rule.get("id", "unknown")
                url = base_url + "/global_rules/" + str(rule_id)
                response = requests.put(url, headers=headers, json=rule)
                
                if response.status_code in [200, 201]:
                    success += 1
                    log("Global rule {} imported successfully".format(rule_id))
                else:
                    log("Failed to import global rule {}: {}".format(rule_id, response.status_code))
            except Exception as e:
                log("Error importing global rule: " + str(e))
        
        log("Global rules imported: {}/{}".format(success, len(rules)))

except Exception as e:
    log("Critical error: " + str(e))
    sys.exit(1)
EOF

# Verify routes were imported
echo "$(date) - Verifying routes..." | tee -a $LOG_FILE
sleep 2
ROUTES_COUNT=$(curl -s -H "X-API-KEY: $ADMIN_KEY" $ADMIN_API/routes | grep -o '"total":[0-9]*' | grep -o '[0-9]*')

if [ -n "$ROUTES_COUNT" ] && [ "$ROUTES_COUNT" -gt 0 ]; then
    echo "$(date) - Verification successful: $ROUTES_COUNT routes found." | tee -a $LOG_FILE
    exit 0
else
    echo "$(date) - Warning: No routes found after import." | tee -a $LOG_FILE
    exit 1
fi
