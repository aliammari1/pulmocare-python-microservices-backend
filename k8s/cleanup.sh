#!/bin/bash

# Kubernetes Cleanup Script for MedApp
# This script removes the entire MedApp stack from Kubernetes

set -e

echo "🧹 Starting MedApp Kubernetes Cleanup"

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

# Remove ingress
print_status "Removing ingress..."
kubectl delete -f ingress.yaml --ignore-not-found=true

# Remove microservices
print_status "Removing microservices..."
kubectl delete -f services/ --ignore-not-found=true

# Remove API Gateway
print_status "Removing API Gateway..."
kubectl delete -f infrastructure/apisix.yaml --ignore-not-found=true

# Remove monitoring stack
print_status "Removing monitoring stack..."
kubectl delete -f monitoring/ --ignore-not-found=true

# Remove infrastructure
print_status "Removing infrastructure..."
kubectl delete -f infrastructure/ --ignore-not-found=true

# Remove configuration and secrets
print_status "Removing configuration and secrets..."
kubectl delete -f configmap.yaml --ignore-not-found=true
kubectl delete -f secrets.yaml --ignore-not-found=true

# Remove namespaces (this will also remove any remaining resources)
print_status "Removing namespaces..."
kubectl delete -f namespace.yaml --ignore-not-found=true

# Remove persistent volumes (optional - uncomment if you want to delete data)
# print_warning "Removing persistent volumes and data..."
# kubectl delete pv --all

print_status "🎉 MedApp cleanup completed!"

echo ""
echo "📝 Note: Persistent volumes may still exist and contain data."
echo "If you want to completely remove all data, run:"
echo "kubectl delete pv --all"
