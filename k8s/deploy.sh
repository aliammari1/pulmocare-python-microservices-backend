#!/bin/bash

# Kubernetes Deployment Script for MedApp
# This script deploys the entire MedApp stack to Kubernetes

set -e

echo "🚀 Starting MedApp Kubernetes Deployment"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if kubectl is installed
if ! command -v kubectl &> /dev/null; then
    print_error "kubectl is not installed. Please install kubectl first."
    exit 1
fi

# Check if cluster is accessible
if ! kubectl cluster-info &> /dev/null; then
    print_error "Cannot access Kubernetes cluster. Please check your kubeconfig."
    exit 1
fi

print_status "Kubernetes cluster is accessible"

# Create namespaces
print_status "Creating namespaces..."
kubectl apply -f namespace.yaml

# Apply configuration and secrets
print_status "Applying configuration and secrets..."
kubectl apply -f configmap.yaml
kubectl apply -f secrets.yaml

# Deploy infrastructure components
print_status "Deploying infrastructure components..."

# Deploy databases and storage
print_status "Deploying databases..."
kubectl apply -f infrastructure/mongodb.yaml
kubectl apply -f infrastructure/postgres.yaml
kubectl apply -f infrastructure/redis.yaml

# Deploy message queue
print_status "Deploying message queue..."
kubectl apply -f infrastructure/rabbitmq.yaml

# Deploy service discovery and coordination
print_status "Deploying service discovery..."
kubectl apply -f infrastructure/etcd.yaml
kubectl apply -f infrastructure/consul.yaml

# Deploy object storage and secrets management
print_status "Deploying storage and secrets..."
kubectl apply -f infrastructure/minio.yaml
kubectl apply -f infrastructure/vault.yaml

# Deploy authentication
print_status "Deploying authentication..."
kubectl apply -f infrastructure/keycloak.yaml

# Wait for infrastructure to be ready
print_status "Waiting for infrastructure to be ready..."
kubectl wait --for=condition=ready pod -l app=mongodb -n medapp --timeout=300s
kubectl wait --for=condition=ready pod -l app=redis -n medapp --timeout=300s
kubectl wait --for=condition=ready pod -l app=rabbitmq -n medapp --timeout=300s
kubectl wait --for=condition=ready pod -l app=etcd -n medapp --timeout=300s
kubectl wait --for=condition=ready pod -l app=keycloak-db -n medapp --timeout=300s

print_status "Infrastructure is ready!"

# Deploy monitoring stack
print_status "Deploying monitoring stack..."
kubectl apply -f monitoring/prometheus.yaml
kubectl apply -f monitoring/grafana.yaml
kubectl apply -f monitoring/tempo.yaml
kubectl apply -f monitoring/loki.yaml
kubectl apply -f monitoring/otel-collector.yaml

# Deploy API Gateway
print_status "Deploying API Gateway..."
kubectl apply -f infrastructure/apisix.yaml

# Deploy microservices
print_status "Deploying microservices..."
kubectl apply -f services/auth-service.yaml
kubectl apply -f services/medecins-service.yaml
kubectl apply -f services/patients-service.yaml
kubectl apply -f services/ordonnances-service.yaml
kubectl apply -f services/radiologues-service.yaml
kubectl apply -f services/reports-service.yaml
kubectl apply -f services/appointments-service.yaml
kubectl apply -f services/medfiles-service.yaml

# Deploy ingress
print_status "Deploying ingress..."
kubectl apply -f ingress.yaml

print_status "🎉 MedApp deployment completed!"

# Print access information
echo ""
echo "📋 Access Information:"
echo "================================"
echo "API Gateway: http://api.medapp.local"
echo "Keycloak: http://auth.medapp.local"
echo "Grafana: http://grafana.medapp.local (admin/admin)"
echo "Prometheus: http://prometheus.medapp.local"
echo "MinIO: http://minio.medapp.local"
echo "MinIO Console: http://minio-console.medapp.local"
echo ""
echo "📝 Note: Make sure to add these domains to your /etc/hosts file:"
echo "127.0.0.1 api.medapp.local auth.medapp.local grafana.medapp.local prometheus.medapp.local minio.medapp.local minio-console.medapp.local"
echo ""
echo "🔧 To check the status of your deployment:"
echo "kubectl get pods -n medapp"
echo "kubectl get pods -n medapp-monitoring"
echo ""
echo "🔗 To get service URLs:"
echo "kubectl get ingress -n medapp"
echo "kubectl get ingress -n medapp-monitoring"
