#!/bin/bash
# Security scanning script for registry images

REGISTRY_URL="registry.medapp.local:5000"
CONFIG_FILE="config/security/trivy-config.yaml"
RESULTS_DIR="logs/security"

mkdir -p "$RESULTS_DIR"

# Function to scan image
scan_image() {
    local image="$1"
    local output_file="$RESULTS_DIR/$(echo "$image" | tr '/' '_' | tr ':' '_').json"
    
    echo "Scanning $image..."
    
    if command -v trivy &> /dev/null; then
        trivy image --config "$CONFIG_FILE" --output "$output_file" "$image"
        echo "Results saved to: $output_file"
    else
        echo "Trivy not available, skipping scan of $image"
    fi
}

# Scan registry images
if [[ $# -eq 0 ]]; then
    echo "Usage: $0 <image> [image2] [image3] ..."
    echo "Example: $0 registry.medapp.local:5000/myapp:latest"
    exit 1
fi

for image in "$@"; do
    scan_image "$image"
done

echo "Security scanning completed"
