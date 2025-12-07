#!/bin/bash

# Registry Setup and Initialization Script
# Automates the setup of different registry types with security best practices

set -e

# Configuration
REGISTRY_TYPE="${REGISTRY_TYPE:-local}"
PROJECT_NAME="${PROJECT_NAME:-medapp}"
ENVIRONMENT="${ENVIRONMENT:-development}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
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

print_header() {
    echo -e "${BLUE}[SETUP]${NC} $1"
}

# Function to check prerequisites
check_prerequisites() {
    print_header "Checking prerequisites..."
    
    local missing_tools=()
    
    # Check for Docker
    if ! command -v docker &> /dev/null; then
        missing_tools+=("docker")
    fi
    
    # Check for kubectl
    if ! command -v kubectl &> /dev/null; then
        missing_tools+=("kubectl")
    fi
    
    # Check for specific tools based on registry type
    case "$REGISTRY_TYPE" in
        "acr")
            if ! command -v az &> /dev/null; then
                missing_tools+=("azure-cli")
            fi
            ;;
        "ecr")
            if ! command -v aws &> /dev/null; then
                missing_tools+=("aws-cli")
            fi
            ;;
        "gcr")
            if ! command -v gcloud &> /dev/null; then
                missing_tools+=("gcloud")
            fi
            ;;
    esac
    
    if [[ ${#missing_tools[@]} -gt 0 ]]; then
        print_error "Missing required tools: ${missing_tools[*]}"
        print_status "Please install the missing tools and run again"
        exit 1
    fi
    
    print_status "All prerequisites satisfied"
}

# Function to setup local registry with security
setup_local_registry() {
    print_header "Setting up local registry..."
    
    local registry_dir="/tmp/registry"
    local certs_dir="$registry_dir/certs"
    local auth_dir="$registry_dir/auth"
    local data_dir="$registry_dir/data"
    
    # Create directories
    mkdir -p "$certs_dir" "$auth_dir" "$data_dir"
    
    # Generate self-signed certificate
    print_status "Generating SSL certificate..."
    openssl req -newkey rsa:4096 -nodes -sha256 -keyout "$certs_dir/domain.key" \
        -x509 -days 365 -out "$certs_dir/domain.crt" -subj "/CN=registry.medapp.local"
    
    # Create htpasswd file for authentication
    print_status "Setting up authentication..."
    docker run --rm --entrypoint htpasswd registry:2 \
        -Bbn "medapp" "medapp123!" > "$auth_dir/htpasswd"
    
    # Deploy registry using Kubernetes
    kubectl apply -f - <<EOF
apiVersion: v1
kind: Namespace
metadata:
  name: registry
---
apiVersion: v1
kind: Secret
metadata:
  name: registry-certs
  namespace: registry
type: Opaque
data:
  domain.crt: $(base64 -w 0 < "$certs_dir/domain.crt")
  domain.key: $(base64 -w 0 < "$certs_dir/domain.key")
---
apiVersion: v1
kind: Secret
metadata:
  name: registry-auth
  namespace: registry
type: Opaque
data:
  htpasswd: $(base64 -w 0 < "$auth_dir/htpasswd")
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: registry-data
  namespace: registry
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 10Gi
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: registry
  namespace: registry
spec:
  replicas: 1
  selector:
    matchLabels:
      app: registry
  template:
    metadata:
      labels:
        app: registry
    spec:
      containers:
      - name: registry
        image: registry:2
        ports:
        - containerPort: 5000
        env:
        - name: REGISTRY_HTTP_TLS_CERTIFICATE
          value: /certs/domain.crt
        - name: REGISTRY_HTTP_TLS_KEY
          value: /certs/domain.key
        - name: REGISTRY_AUTH_HTPASSWD_REALM
          value: "Registry Realm"
        - name: REGISTRY_AUTH_HTPASSWD_PATH
          value: /auth/htpasswd
        - name: REGISTRY_STORAGE_FILESYSTEM_ROOTDIRECTORY
          value: /var/lib/registry
        volumeMounts:
        - name: certs
          mountPath: /certs
        - name: auth
          mountPath: /auth
        - name: data
          mountPath: /var/lib/registry
        resources:
          requests:
            memory: "64Mi"
            cpu: "50m"
          limits:
            memory: "128Mi"
            cpu: "100m"
      volumes:
      - name: certs
        secret:
          secretName: registry-certs
      - name: auth
        secret:
          secretName: registry-auth
      - name: data
        persistentVolumeClaim:
          claimName: registry-data
---
apiVersion: v1
kind: Service
metadata:
  name: registry
  namespace: registry
spec:
  selector:
    app: registry
  ports:
  - port: 5000
    targetPort: 5000
  type: NodePort
EOF
    
    print_status "Local registry deployed successfully"
    print_status "Registry URL: https://registry.medapp.local:5000"
    print_status "Username: medapp"
    print_status "Password: medapp123!"
    
    # Add to /etc/hosts
    print_warning "Add the following to your /etc/hosts file:"
    echo "127.0.0.1 registry.medapp.local"
}

# Function to setup Harbor registry
setup_harbor_registry() {
    print_header "Setting up Harbor registry..."
    
    local harbor_dir="$(dirname "$0")/../harbor"
    
    if [[ ! -f "$harbor_dir/docker-compose.yml" ]]; then
        print_error "Harbor docker-compose.yml not found"
        exit 1
    fi
    
    cd "$harbor_dir"
    
    # Generate certificates
    print_status "Generating Harbor certificates..."
    mkdir -p certs
    
    # Create CA private key
    openssl genrsa -out certs/ca.key 4096
    
    # Create CA certificate
    openssl req -new -x509 -days 365 -key certs/ca.key -out certs/ca.crt \
        -subj "/CN=Harbor-CA"
    
    # Create server private key
    openssl genrsa -out certs/harbor.key 4096
    
    # Create certificate signing request
    openssl req -new -key certs/harbor.key -out certs/harbor.csr \
        -subj "/CN=harbor.medapp.local"
    
    # Create server certificate
    openssl x509 -req -days 365 -in certs/harbor.csr -CA certs/ca.crt \
        -CAkey certs/ca.key -CAcreateserial -out certs/harbor.crt
    
    # Start Harbor
    print_status "Starting Harbor..."
    docker-compose up -d
    
    # Wait for Harbor to be ready
    print_status "Waiting for Harbor to be ready..."
    local max_attempts=60
    local attempt=1
    
    while [[ $attempt -le $max_attempts ]]; do
        if curl -k -s -o /dev/null -w "%{http_code}" https://harbor.medapp.local | grep -q "200\|302"; then
            break
        fi
        print_status "Attempt $attempt/$max_attempts - Harbor not ready yet..."
        sleep 10
        ((attempt++))
    done
    
    if [[ $attempt -gt $max_attempts ]]; then
        print_error "Harbor failed to start within timeout"
        exit 1
    fi
    
    # Create project
    print_status "Creating Harbor project..."
    create_harbor_project
    
    print_status "Harbor registry deployed successfully"
    print_status "Harbor URL: https://harbor.medapp.local"
    print_status "Username: admin"
    print_status "Password: HarborAdmin123!"
}

# Function to create Harbor project via API
create_harbor_project() {
    local project_data=$(cat <<EOF
{
  "project_name": "$PROJECT_NAME",
  "public": false,
  "metadata": {
    "public": "false",
    "enable_content_trust": "true",
    "auto_scan": "true",
    "severity": "low",
    "reuse_sys_cve_allowlist": "true"
  }
}
EOF
)
    
    curl -k -X POST \
        -H "Content-Type: application/json" \
        -u "admin:HarborAdmin123!" \
        -d "$project_data" \
        "https://harbor.medapp.local/api/v2.0/projects" || true
}

# Function to setup cloud registry (ACR example)
setup_acr_registry() {
    print_header "Setting up Azure Container Registry..."
    
    local resource_group="${ACR_RESOURCE_GROUP:-medapp-rg}"
    local registry_name="${ACR_NAME:-medappregistry}"
    local location="${ACR_LOCATION:-eastus}"
    
    # Check if logged in to Azure
    if ! az account show &> /dev/null; then
        print_status "Logging in to Azure..."
        az login
    fi
    
    # Create resource group if it doesn't exist
    if ! az group show --name "$resource_group" &> /dev/null; then
        print_status "Creating resource group..."
        az group create --name "$resource_group" --location "$location"
    fi
    
    # Create ACR
    print_status "Creating Azure Container Registry..."
    az acr create \
        --resource-group "$resource_group" \
        --name "$registry_name" \
        --sku Standard \
        --admin-enabled true
    
    # Get credentials
    local acr_server=$(az acr show --name "$registry_name" --resource-group "$resource_group" --query loginServer -o tsv)
    local acr_username=$(az acr credential show --name "$registry_name" --resource-group "$resource_group" --query username -o tsv)
    local acr_password=$(az acr credential show --name "$registry_name" --resource-group "$resource_group" --query passwords[0].value -o tsv)
    
    print_status "ACR created successfully"
    print_status "Registry URL: $acr_server"
    print_status "Username: $acr_username"
    print_status "Password: $acr_password"
    
    # Create Kubernetes secret
    create_registry_secret "$acr_server" "$acr_username" "$acr_password"
}

# Function to create Kubernetes registry secret
create_registry_secret() {
    local registry_url=$1
    local username=$2
    local password=$3
    local secret_name="${PROJECT_NAME}-registry-secret"
    
    print_status "Creating Kubernetes registry secret..."
    
    kubectl create secret docker-registry "$secret_name" \
        --docker-server="$registry_url" \
        --docker-username="$username" \
        --docker-password="$password" \
        --namespace="$PROJECT_NAME" \
        --dry-run=client -o yaml | kubectl apply -f -
    
    print_status "Registry secret created: $secret_name"
}

# Function to configure Docker daemon for insecure registries
configure_docker_daemon() {
    local registry_url=$1
    
    print_header "Configuring Docker daemon for registry: $registry_url"
    
    local daemon_config="/etc/docker/daemon.json"
    local backup_config="/etc/docker/daemon.json.backup"
    
    # Backup existing config
    if [[ -f "$daemon_config" ]]; then
        sudo cp "$daemon_config" "$backup_config"
    fi
    
    # Create or update daemon.json
    local config_content=$(cat <<EOF
{
  "insecure-registries": ["$registry_url"],
  "registry-mirrors": [],
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  }
}
EOF
)
    
    echo "$config_content" | sudo tee "$daemon_config" > /dev/null
    
    # Restart Docker daemon
    print_status "Restarting Docker daemon..."
    sudo systemctl restart docker
    
    print_status "Docker daemon configured successfully"
}

# Function to test registry connectivity
test_registry() {
    local registry_url=$1
    local username=$2
    local password=$3
    
    print_header "Testing registry connectivity: $registry_url"
    
    # Login to registry
    if [[ -n "$username" && -n "$password" ]]; then
        echo "$password" | docker login "$registry_url" -u "$username" --password-stdin
    fi
    
    # Push a test image
    local test_image="$registry_url/test:latest"
    
    docker pull hello-world:latest
    docker tag hello-world:latest "$test_image"
    
    if docker push "$test_image"; then
        print_status "Registry test successful"
        docker rmi "$test_image" || true
        return 0
    else
        print_error "Registry test failed"
        return 1
    fi
}

# Function to display setup summary
show_setup_summary() {
    print_header "Setup Summary"
    
    case "$REGISTRY_TYPE" in
        "local")
            echo "Registry Type: Local Registry"
            echo "Registry URL: https://registry.medapp.local:5000"
            echo "Username: medapp"
            echo "Password: medapp123!"
            ;;
        "harbor")
            echo "Registry Type: Harbor"
            echo "Registry URL: https://harbor.medapp.local"
            echo "Username: admin"
            echo "Password: HarborAdmin123!"
            ;;
        "acr")
            echo "Registry Type: Azure Container Registry"
            echo "Registry URL: $ACR_NAME.azurecr.io"
            ;;
    esac
    
    echo ""
    echo "Next steps:"
    echo "1. Update your build scripts with the registry URL"
    echo "2. Configure your CI/CD pipeline to use the registry"
    echo "3. Update Kubernetes manifests with imagePullSecrets"
    echo "4. Test the registry with: ./tag-manager.sh test"
}

# Main function
main() {
    local action=${1:-"setup"}
    
    case "$action" in
        "setup")
            check_prerequisites
            
            case "$REGISTRY_TYPE" in
                "local")
                    setup_local_registry
                    ;;
                "harbor")
                    setup_harbor_registry
                    ;;
                "acr")
                    setup_acr_registry
                    ;;
                *)
                    print_error "Unsupported registry type: $REGISTRY_TYPE"
                    print_status "Supported types: local, harbor, acr"
                    exit 1
                    ;;
            esac
            
            show_setup_summary
            ;;
        "test")
            case "$REGISTRY_TYPE" in
                "local")
                    test_registry "registry.medapp.local:5000" "medapp" "medapp123!"
                    ;;
                "harbor")
                    test_registry "harbor.medapp.local" "admin" "HarborAdmin123!"
                    ;;
                *)
                    print_warning "Test not implemented for registry type: $REGISTRY_TYPE"
                    ;;
            esac
            ;;
        "configure-docker")
            configure_docker_daemon "${2:-registry.medapp.local:5000}"
            ;;
        *)
            echo "Usage: $0 {setup|test|configure-docker} [registry_url]"
            echo ""
            echo "Commands:"
            echo "  setup              - Setup the registry"
            echo "  test               - Test registry connectivity"
            echo "  configure-docker   - Configure Docker daemon"
            echo ""
            echo "Environment variables:"
            echo "  REGISTRY_TYPE      - Registry type (local, harbor, acr)"
            echo "  PROJECT_NAME       - Project name"
            echo "  ENVIRONMENT        - Environment name"
            exit 1
            ;;
    esac
}

# Execute main function
main "$@"
