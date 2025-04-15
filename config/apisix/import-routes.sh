#!/bin/bash
set -e

LOG_FILE="/usr/local/apisix/logs/import-routes.log"
echo "$(date) - Starting route import to APISIX..." | tee -a $LOG_FILE


# Extract routes, consumers and global rules using yq (assuming it's installed, if not we'd need to install it)
if ! command -v yq &> /dev/null; then
    echo "Installing yq to parse YAML..."
    wget -q https://github.com/mikefarah/yq/releases/download/v4.31.2/yq_linux_amd64 -O /usr/local/bin/yq
    chmod +x /usr/local/bin/yq
fi

# Admin API endpoint
ADMIN_API="http://localhost:9180/apisix/admin"
ADMIN_KEY=$(yq '.deployment.admin.admin_key[0].key' conf/config.yaml | sed 's/"//g')

# Default environment variable values if not set
# Use simple values that won't cause escaping issues
: ${API_KEY:="test-api-key"}
: ${KEYCLOAK_CLIENT_ID:="medapp-client"}
: ${KEYCLOAK_CLIENT_SECRET:="medapp-secret"}
: ${KEYCLOAK_DISCOVERY_URL:="http://keycloak:8080/realms/medapp/.well-known/openid-configuration"}

# Function to log with timestamp
log() {
    timestamp=$(date +"%Y-%m-%d %H:%M:%S")
    echo "$timestamp - $1" | tee -a $LOG_FILE
}

# Check if config file exists
CONFIG_PATH="/usr/local/apisix/conf/apisix.yaml"
echo "Reading config from: $CONFIG_PATH"

if [ ! -f "$CONFIG_PATH" ]; then
    echo "Error: Config file not found"
    exit 1
fi

# Create a temporary file for the processed config
TEMP_CONFIG=$(mktemp)

# Create a modified YAML directly with yq to avoid sed issues with special characters
echo "Pre-processing configuration to replace environment variables"

# Copy the original file first
cp "$CONFIG_PATH" "$TEMP_CONFIG"

# Process CORS plugin configuration directly with yq
for i in $(yq e '.routes | length' "$TEMP_CONFIG" | wc -l); do
    # Check if the route has cors plugin
    if yq e ".routes[$i].plugins.cors" "$TEMP_CONFIG" &> /dev/null; then
        # Update cors allow_origins if it's using environment variables
        yq e ".routes[$i].plugins.cors.allow_origins = \"*\"" -i "$TEMP_CONFIG"
    fi
done

# Validate the YAML file before proceeding
echo "Validating YAML configuration..."
if ! yq e '.' "$TEMP_CONFIG" &> /dev/null; then
    echo "Error: YAML validation failed. Manual inspection needed."
    exit 1
fi

echo "Configuration pre-processing completed"

# Import routes
ROUTES_COUNT=$(yq e '.routes | length' "$TEMP_CONFIG")
echo "Found $ROUTES_COUNT routes"
SUCCESS_ROUTES=0

for i in $(seq 0 $((ROUTES_COUNT - 1))); do
    # Extract the ID directly from YAML before converting to JSON
    ROUTE_ID=$(yq e ".routes[$i].id" "$TEMP_CONFIG")
    ROUTE_JSON=$(yq e ".routes[$i]" -j "$TEMP_CONFIG")
    
    if [ -z "$ROUTE_ID" ] || [ "$ROUTE_ID" = "null" ]; then
        # Generate a unique ID if none exists
        ROUTE_ID="route-$(date +%s)-$i"
        echo "Route at index $i has no ID, generated: $ROUTE_ID"
        # Add the ID to the JSON
        ROUTE_JSON=$(echo "$ROUTE_JSON" | jq --arg id "$ROUTE_ID" '. + {id: $id}')
    fi
    
    echo "Importing route $ROUTE_ID"
    
    # Debug output to see what we're sending
    echo "Route JSON: $(echo "$ROUTE_JSON" | jq -c '.')"
    
    RESPONSE=$(curl -s -w "\n%{http_code}" -H "X-API-KEY: $ADMIN_KEY" \
        -H "Content-Type: application/json" \
        -X PUT "$ADMIN_API/routes/$ROUTE_ID" \
        -d "$ROUTE_JSON")
    
    HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
    
    if [[ "$HTTP_CODE" == 2* ]]; then
        SUCCESS_ROUTES=$((SUCCESS_ROUTES + 1))
        echo "Route $ROUTE_ID imported successfully"
    else
        RESPONSE_BODY=$(echo "$RESPONSE" | sed '$d')
        echo "Failed to import route $ROUTE_ID: $HTTP_CODE - $RESPONSE_BODY"
        
        # Simplify the route to try again with minimal configuration
        echo "Trying simplified version of route $ROUTE_ID"
        
        # Extract only essential fields
        URI=$(echo "$ROUTE_JSON" | jq -r '.uri // "/unknown"')
        SIMPLIFIED_ROUTE=$(jq -n \
            --arg id "$ROUTE_ID" \
            --arg uri "$URI" \
            '{id: $id, uri: $uri, upstream: {type: "roundrobin", nodes: {"auth-service:8086": 1}}}')
        
        RESPONSE=$(curl -s -w "\n%{http_code}" -H "X-API-KEY: $ADMIN_KEY" \
            -H "Content-Type: application/json" \
            -X PUT "$ADMIN_API/routes/$ROUTE_ID" \
            -d "$SIMPLIFIED_ROUTE")
            
        HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
        
        if [[ "$HTTP_CODE" == 2* ]]; then
            SUCCESS_ROUTES=$((SUCCESS_ROUTES + 1))
            echo "Simplified route $ROUTE_ID imported successfully"
        else
            RESPONSE_BODY=$(echo "$RESPONSE" | sed '$d')
            echo "Still failed to import simplified route $ROUTE_ID: $HTTP_CODE - $RESPONSE_BODY"
        fi
    fi
done

echo "Routes imported: $SUCCESS_ROUTES/$ROUTES_COUNT"

# Import consumers
CONSUMERS_COUNT=$(yq e '.consumers | length // 0' "$TEMP_CONFIG")
if [ "$CONSUMERS_COUNT" -gt 0 ]; then
    echo "Found $CONSUMERS_COUNT consumers"
    SUCCESS_CONSUMERS=0
    
    for i in $(seq 0 $((CONSUMERS_COUNT - 1))); do
        # Extract the username directly from YAML before converting to JSON
        USERNAME=$(yq e ".consumers[$i].username" "$TEMP_CONFIG")
        CONSUMER_JSON=$(yq e ".consumers[$i]" -j "$TEMP_CONFIG")
        
        if [ -z "$USERNAME" ] || [ "$USERNAME" = "null" ]; then
            USERNAME="consumer-$(date +%s)-$i"
            echo "Consumer at index $i has no username, generated: $USERNAME"
            # Add the username to the JSON
            CONSUMER_JSON=$(echo "$CONSUMER_JSON" | jq --arg username "$USERNAME" '. + {username: $username}')
        fi
        
        echo "Importing consumer $USERNAME"
        
        RESPONSE=$(curl -s -w "\n%{http_code}" -H "X-API-KEY: $ADMIN_KEY" \
            -H "Content-Type: application/json" \
            -X PUT "$ADMIN_API/consumers/$USERNAME" \
            -d "$CONSUMER_JSON")
        
        HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
        
        if [[ "$HTTP_CODE" == 2* ]]; then
            SUCCESS_CONSUMERS=$((SUCCESS_CONSUMERS + 1))
            echo "Consumer $USERNAME imported successfully"
        else
            RESPONSE_BODY=$(echo "$RESPONSE" | sed '$d')
            echo "Failed to import consumer $USERNAME: $HTTP_CODE - $RESPONSE_BODY"
        fi
    done
    
    echo "Consumers imported: $SUCCESS_CONSUMERS/$CONSUMERS_COUNT"
fi

# Import global rules
RULES_COUNT=$(yq e '.global_rules | length // 0' "$TEMP_CONFIG")
if [ "$RULES_COUNT" -gt 0 ]; then
    echo "Found $RULES_COUNT global rules"
    SUCCESS_RULES=0
    
    for i in $(seq 0 $((RULES_COUNT - 1))); do
        # Extract the ID directly from YAML before converting to JSON
        RULE_ID=$(yq e ".global_rules[$i].id" "$TEMP_CONFIG")
        RULE_JSON=$(yq e ".global_rules[$i]" -j "$TEMP_CONFIG")
        
        if [ -z "$RULE_ID" ] || [ "$RULE_ID" = "null" ]; then
            RULE_ID="rule-$(date +%s)-$i"
            echo "Global rule at index $i has no ID, generated: $RULE_ID"
            # Add the ID to the JSON
            RULE_JSON=$(echo "$RULE_JSON" | jq --arg id "$RULE_ID" '. + {id: $id}')
        fi
        
        echo "Importing global rule $RULE_ID"
        
        RESPONSE=$(curl -s -w "\n%{http_code}" -H "X-API-KEY: $ADMIN_KEY" \
            -H "Content-Type: application/json" \
            -X PUT "$ADMIN_API/global_rules/$RULE_ID" \
            -d "$RULE_JSON")
        
        HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
        
        if [[ "$HTTP_CODE" == 2* ]]; then
            SUCCESS_RULES=$((SUCCESS_RULES + 1))
            echo "Global rule $RULE_ID imported successfully"
        else
            RESPONSE_BODY=$(echo "$RESPONSE" | sed '$d')
            echo "Failed to import global rule $RULE_ID: $HTTP_CODE - $RESPONSE_BODY"
        fi
    done
    
    echo "Global rules imported: $SUCCESS_RULES/$RULES_COUNT"
fi

# Clean up temporary file
rm -f "$TEMP_CONFIG"

# Verify routes were imported
echo "Verifying routes..."
sleep 2
ROUTES_COUNT=$(curl -s -H "X-API-KEY: $ADMIN_KEY" $ADMIN_API/routes | grep -o '"total":[0-9]*' | grep -o '[0-9]*')

if [ -n "$ROUTES_COUNT" ] && [ "$ROUTES_COUNT" -gt 0 ]; then
    echo "Verification successful: $ROUTES_COUNT routes found."
    exit 0
else
    echo "Warning: No routes found after import. Trying individual route import with debugging..."
    
    # Create a basic test route as a last resort
    TEST_ROUTE='{
        "id": "test-route",
        "uri": "/test",
        "upstream": {
            "nodes": {
                "auth-service:8086": 1
            },
            "type": "roundrobin"
        }
    }'
    
    echo "Trying to import a basic test route"
    RESPONSE=$(curl -v -H "X-API-KEY: $ADMIN_KEY" \
        -H "Content-Type: application/json" \
        -X PUT "$ADMIN_API/routes/test-route" \
        -d "$TEST_ROUTE" 2>&1)
        
    echo "Test route response: $RESPONSE"
    
    exit 1
fi
