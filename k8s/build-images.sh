#!/bin/bash

# Build and Push Docker Images Script
# This script builds all the microservice Docker images and pushes them to a registry

set -e

# Configuration - UPDATE THESE VALUES
REGISTRY="your-registry.com"  # Change this to your Docker registry
TAG="latest"
PROJECT_ROOT="/home/azureuser/medapp-backend"

echo "🏗️ Building and pushing MedApp Docker images"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to build and push a service
build_and_push() {
    local service_name=$1
    local service_path=$2
    
    print_status "Building $service_name..."
    
    cd "$PROJECT_ROOT/$service_path"
    
    # Build the image
    docker build -t "$REGISTRY/medapp-$service_name:$TAG" .
    
    # Push the image
    print_status "Pushing $service_name to registry..."
    docker push "$REGISTRY/medapp-$service_name:$TAG"
    
    print_status "$service_name build and push completed"
    cd "$PROJECT_ROOT"
}

# Check if Docker is installed and running
if ! command -v docker &> /dev/null; then
    print_error "Docker is not installed. Please install Docker first."
    exit 1
fi

if ! docker info &> /dev/null; then
    print_error "Docker daemon is not running. Please start Docker."
    exit 1
fi

# Login to registry (uncomment and modify as needed)
# print_status "Logging in to Docker registry..."
# docker login $REGISTRY

print_warning "Make sure you're logged in to your Docker registry: $REGISTRY"
print_warning "Update the REGISTRY variable in this script with your actual registry URL"

# Build and push all services
build_and_push "auth" "services/auth"
build_and_push "medecins" "services/medecins"
build_and_push "patients" "services/patients"
build_and_push "ordonnances" "services/ordonnances"
build_and_push "radiologues" "services/radiologues"
build_and_push "reports" "services/reports"
build_and_push "appointments" "services/appointments"
build_and_push "medfiles" "services/medfiles"

print_status "🎉 All images built and pushed successfully!"

echo ""
echo "📝 Built images:"
echo "- $REGISTRY/medapp-auth:$TAG"
echo "- $REGISTRY/medapp-medecins:$TAG"
echo "- $REGISTRY/medapp-patients:$TAG"
echo "- $REGISTRY/medapp-ordonnances:$TAG"
echo "- $REGISTRY/medapp-radiologues:$TAG"
echo "- $REGISTRY/medapp-reports:$TAG"
echo "- $REGISTRY/medapp-appointments:$TAG"
echo "- $REGISTRY/medapp-medfiles:$TAG"
echo ""
echo "🔧 Next steps:"
echo "1. Update the image references in your Kubernetes YAML files"
echo "2. Run ./deploy.sh to deploy to Kubernetes"
