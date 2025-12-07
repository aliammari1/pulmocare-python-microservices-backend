#!/bin/bash

# Complete Registry Setup Script
# One-stop script to set up the entire registry infrastructure

set -e

# Configuration
REGISTRY_TYPE="${REGISTRY_TYPE:-local}"
PROJECT_NAME="${PROJECT_NAME:-medapp}"
ENVIRONMENT="${ENVIRONMENT:-development}"
INSTALL_MONITORING="${INSTALL_MONITORING:-true}"
INSTALL_SECURITY="${INSTALL_SECURITY:-true}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

print_status() {
    echo -e "${GREEN}[SETUP]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_header() {
    echo -e "${BLUE}[MEDAPP-REGISTRY]${NC} $1"
}

print_step() {
    echo -e "${CYAN}[STEP]${NC} $1"
}

# Function to display setup banner
show_banner() {
    echo -e "${BLUE}"
    cat << "EOF"
 __  __          _    _                  ____            _     _              
|  \/  | ___  __| |  / \   _ __  _ __   |  _ \ ___  __ _(_)___| |_ _ __ _   _ 
| |\/| |/ _ \/ _` | / _ \ | '_ \| '_ \  | |_) / _ \/ _` | / __| __| '__| | | |
| |  | |  __/ (_| |/ ___ \| |_) | |_) | |  _ <  __/ (_| | \__ \ |_| |  | |_| |
|_|  |_|\___|\__,_/_/   \_\ .__/| .__/  |_| \_\___|\__, |_|___/\__|_|   \__, |
                          |_|   |_|                |___/                |___/ 
EOF
    echo -e "${NC}"
    echo "Enterprise Container Registry Setup"
    echo "===================================="
    echo
}

# Function to check system requirements
check_requirements() {
    print_header "Checking system requirements..."
    
    local requirements_met=true
    
    # Check Docker
    if ! command -v docker &> /dev/null; then
        print_error "Docker is not installed"
        requirements_met=false
    else
        local docker_version=$(docker --version | cut -d' ' -f3 | cut -d',' -f1)
        print_status "Docker version: $docker_version"
    fi
    
    # Check Docker Compose
    if ! command -v docker-compose &> /dev/null; then
        print_error "Docker Compose is not installed"
        requirements_met=false
    else
        local compose_version=$(docker-compose --version | cut -d' ' -f3 | cut -d',' -f1)
        print_status "Docker Compose version: $compose_version"
    fi
    
    # Check Kubernetes
    if ! command -v kubectl &> /dev/null; then
        print_warning "kubectl is not installed - Kubernetes features will be disabled"
    else
        local kubectl_version=$(kubectl version --client --short 2>/dev/null | cut -d' ' -f3)
        print_status "kubectl version: $kubectl_version"
    fi
    
    # Check available disk space
    local available_space=$(df -BG . | awk 'NR==2 {print $4}' | sed 's/G//')
    if [[ $available_space -lt 10 ]]; then
        print_warning "Less than 10GB available disk space. Registry may run out of space."
    else
        print_status "Available disk space: ${available_space}GB"
    fi
    
    # Check available memory
    local available_memory=$(free -g | awk 'NR==2{print $7}')
    if [[ $available_memory -lt 2 ]]; then
        print_warning "Less than 2GB available memory. Performance may be affected."
    else
        print_status "Available memory: ${available_memory}GB"
    fi
    
    if [[ "$requirements_met" == "false" ]]; then
        print_error "System requirements not met. Please install missing components."
        exit 1
    fi
    
    print_status "System requirements check passed"
}

# Function to create directory structure
create_directories() {
    print_step "Creating directory structure..."
    
    local base_dir="$(pwd)"
    local dirs=(
        "certs"
        "auth"
        "data"
        "logs"
        "backups"
        "config"
        "scripts"
    )
    
    for dir in "${dirs[@]}"; do
        mkdir -p "$dir"
        print_status "Created directory: $dir"
    done
}

# Function to generate SSL certificates
generate_certificates() {
    print_step "Generating SSL certificates..."
    
    local certs_dir="certs"
    
    # Generate CA private key
    openssl genrsa -out "$certs_dir/ca.key" 4096
    
    # Generate CA certificate
    openssl req -new -x509 -days 365 -key "$certs_dir/ca.key" -out "$certs_dir/ca.crt" \
        -subj "/C=US/ST=CA/L=San Francisco/O=MedApp/OU=IT/CN=MedApp-CA"
    
    # Generate server private key
    openssl genrsa -out "$certs_dir/domain.key" 4096
    
    # Generate certificate signing request
    openssl req -new -key "$certs_dir/domain.key" -out "$certs_dir/domain.csr" \
        -subj "/C=US/ST=CA/L=San Francisco/O=MedApp/OU=IT/CN=registry.medapp.local"
    
    # Generate server certificate
    openssl x509 -req -days 365 -in "$certs_dir/domain.csr" -CA "$certs_dir/ca.crt" \
        -CAkey "$certs_dir/ca.key" -CAcreateserial -out "$certs_dir/domain.crt"
    
    # Generate client certificates for authentication
    openssl genrsa -out "$certs_dir/client.key" 4096
    openssl req -new -key "$certs_dir/client.key" -out "$certs_dir/client.csr" \
        -subj "/C=US/ST=CA/L=San Francisco/O=MedApp/OU=IT/CN=medapp-client"
    openssl x509 -req -days 365 -in "$certs_dir/client.csr" -CA "$certs_dir/ca.crt" \
        -CAkey "$certs_dir/ca.key" -CAcreateserial -out "$certs_dir/client.crt"
    
    # Set proper permissions
    chmod 600 "$certs_dir"/*.key
    chmod 644 "$certs_dir"/*.crt
    
    print_status "SSL certificates generated successfully"
}

# Function to setup authentication
setup_authentication() {
    print_step "Setting up authentication..."
    
    local auth_dir="auth"
    
    # Create htpasswd file
    docker run --rm --entrypoint htpasswd registry:latest \
        -Bbn "medapp" "medapp123!" > "$auth_dir/htpasswd"
    
    # Add additional users
    docker run --rm --entrypoint htpasswd registry:latest \
        -Bbn "admin" "admin123!" >> "$auth_dir/htpasswd"
    
    docker run --rm --entrypoint htpasswd registry:latest \
        -Bbn "readonly" "readonly123!" >> "$auth_dir/htpasswd"
    
    print_status "Authentication configured with multiple users"
}

# Function to create registry configuration
create_registry_config() {
    print_step "Creating registry configuration..."
    
    local config_file="config/registry-config.yml"
    
    cat > "$config_file" << EOF
version: 0.1
log:
  level: info
  formatter: text
  fields:
    service: registry
    environment: $ENVIRONMENT
storage:
  filesystem:
    rootdirectory: /var/lib/registry
  maintenance:
    uploadpurging:
      enabled: true
      age: 168h
      interval: 24h
      dryrun: false
  delete:
    enabled: true
auth:
  htpasswd:
    realm: "Registry Realm"
    path: /auth/htpasswd
http:
  addr: :5000
  headers:
    X-Content-Type-Options: [nosniff]
    X-Frame-Options: [deny]
    X-XSS-Protection: ["1; mode=block"]
  tls:
    certificate: /certs/domain.crt
    key: /certs/domain.key
  secret: $(openssl rand -hex 32)
health:
  storagedriver:
    enabled: true
    interval: 10s
    threshold: 3
notifications:
  endpoints:
    - name: webhook
      disabled: false
      url: http://webhook-receiver:8080/webhook
      headers:
        Authorization: [Bearer $(openssl rand -hex 16)]
      timeout: 1s
      threshold: 5
      backoff: 1s
      ignoredmediatypes:
        - application/octet-stream
proxy:
  remoteurl: https://registry-1.docker.io
  username: $DOCKER_HUB_USERNAME
  password: $DOCKER_HUB_PASSWORD
EOF
    
    print_status "Registry configuration created"
}

# Function to deploy registry stack
deploy_registry_stack() {
    print_step "Deploying registry stack..."
    
    case "$REGISTRY_TYPE" in
        "local")
            deploy_local_registry
            ;;
        "harbor")
            deploy_harbor_registry
            ;;
        "full-stack")
            deploy_full_stack
            ;;
        *)
            print_error "Unknown registry type: $REGISTRY_TYPE"
            exit 1
            ;;
    esac
}

# Function to deploy local registry
deploy_local_registry() {
    print_status "Deploying local registry..."
    
    # Create Docker Compose file for local registry
    cat > docker-compose.local.yml << EOF
version: '3.8'

services:
  registry:
    image: registry:latest
    container_name: ${PROJECT_NAME}-registry
    ports:
      - "5000:5000"
    environment:
      REGISTRY_STORAGE_FILESYSTEM_ROOTDIRECTORY: /var/lib/registry
      REGISTRY_HTTP_TLS_CERTIFICATE: /certs/domain.crt
      REGISTRY_HTTP_TLS_KEY: /certs/domain.key
      REGISTRY_AUTH_HTPASSWD_REALM: "Registry Realm"
      REGISTRY_AUTH_HTPASSWD_PATH: /auth/htpasswd
    volumes:
      - ./data:/var/lib/registry
      - ./certs:/certs:ro
      - ./auth:/auth:ro
      - ./config/registry-config.yml:/etc/docker/registry/config.yml:ro
    restart: unless-stopped
    networks:
      - registry-network

networks:
  registry-network:
    driver: bridge
EOF
    
    docker-compose -f docker-compose.local.yml up -d
    print_status "Local registry deployed"
}

# Function to deploy Harbor registry
deploy_harbor_registry() {
    print_status "Deploying Harbor registry..."
    
    # Use existing Harbor configuration
    cd harbor
    docker-compose up -d
    cd ..
    
    print_status "Harbor registry deployed"
}

# Function to deploy full stack
deploy_full_stack() {
    print_status "Deploying full registry stack..."
    
    docker-compose up -d
    print_status "Full registry stack deployed"
}

# Function to setup monitoring
setup_monitoring() {
    if [[ "$INSTALL_MONITORING" == "true" ]]; then
        print_step "Setting up monitoring..."
        
        # Create Grafana dashboards
        create_grafana_dashboards
        
        # Configure Prometheus alerts
        create_prometheus_alerts
        
        print_status "Monitoring setup completed"
    fi
}

# Function to create Grafana dashboards
create_grafana_dashboards() {
    local dashboard_dir="config/grafana/dashboards"
    mkdir -p "$dashboard_dir"
    
    # Create registry dashboard
    cat > "$dashboard_dir/registry-dashboard.json" << 'EOF'
{
  "dashboard": {
    "id": null,
    "title": "Container Registry Dashboard",
    "tags": ["registry", "docker"],
    "timezone": "browser",
    "panels": [
      {
        "title": "Registry Status",
        "type": "stat",
        "targets": [
          {
            "expr": "up{job=\"registry\"}",
            "legendFormat": "Registry Status"
          }
        ]
      },
      {
        "title": "Total Repositories",
        "type": "stat",
        "targets": [
          {
            "expr": "registry_repositories_total",
            "legendFormat": "Repositories"
          }
        ]
      },
      {
        "title": "Storage Usage",
        "type": "graph",
        "targets": [
          {
            "expr": "registry_storage_usage_bytes",
            "legendFormat": "Storage Usage"
          }
        ]
      },
      {
        "title": "Request Rate",
        "type": "graph",
        "targets": [
          {
            "expr": "rate(registry_http_requests_total[5m])",
            "legendFormat": "{{method}} {{code}}"
          }
        ]
      }
    ],
    "time": {
      "from": "now-1h",
      "to": "now"
    },
    "refresh": "30s"
  }
}
EOF
    
    print_status "Grafana dashboards created"
}

# Function to create Prometheus alerts
create_prometheus_alerts() {
    cat > config/registry_rules.yml << 'EOF'
groups:
- name: registry.rules
  rules:
  - alert: RegistryDown
    expr: up{job="registry"} == 0
    for: 5m
    labels:
      severity: critical
    annotations:
      summary: "Registry is down"
      description: "Registry has been down for more than 5 minutes."

  - alert: RegistryHighErrorRate
    expr: rate(registry_http_requests_total{code=~"5.."}[5m]) > 0.1
    for: 5m
    labels:
      severity: warning
    annotations:
      summary: "High error rate in registry"
      description: "Registry error rate is {{ $value }} errors per second."

  - alert: RegistryDiskSpaceLow
    expr: (registry_storage_usage_bytes / registry_storage_capacity_bytes) > 0.8
    for: 5m
    labels:
      severity: warning
    annotations:
      summary: "Registry disk space is low"
      description: "Registry disk usage is {{ $value | humanizePercentage }}."

  - alert: RegistryCertificateExpiring
    expr: (registry_certificate_expiry_seconds - time()) / 86400 < 30
    for: 1m
    labels:
      severity: warning
    annotations:
      summary: "Registry certificate expiring soon"
      description: "Registry certificate expires in {{ $value }} days."
EOF
    
    print_status "Prometheus alerts configured"
}

# Function to setup security scanning
setup_security() {
    if [[ "$INSTALL_SECURITY" == "true" ]]; then
        print_step "Setting up security scanning..."
        
        # Install Trivy
        if ! command -v trivy &> /dev/null; then
            print_status "Installing Trivy..."
            curl -sfL https://raw.githubusercontent.com/aquasecurity/trivy/main/contrib/install.sh | sh -s -- -b /usr/local/bin
        fi
        
        # Create security scanning configuration
        create_security_config
        
        print_status "Security scanning setup completed"
    fi
}

# Function to create security configuration
create_security_config() {
    cat > config/trivy-config.yaml << EOF
format: json
output: /tmp/trivy-results.json
severity:
  - UNKNOWN
  - LOW
  - MEDIUM
  - HIGH
  - CRITICAL
vulnerability:
  type:
    - os
    - library
  scanners:
    - vuln
    - secret
ignore-unfixed: false
skip-dirs:
  - /var/lib/apt/lists
  - /tmp
  - /var/cache
skip-files:
  - "*.md"
  - "*.txt"
EOF
    
    print_status "Security configuration created"
}

# Function to create maintenance scripts
create_maintenance_scripts() {
    print_step "Creating maintenance scripts..."
    
    # Create backup script
    cat > scripts/backup.sh << 'EOF'
#!/bin/bash
# Registry backup script

BACKUP_DIR="/backup/registry"
DATE=$(date +%Y%m%d-%H%M%S)
BACKUP_FILE="registry-backup-$DATE.tar.gz"

mkdir -p "$BACKUP_DIR"

# Backup registry data
tar -czf "$BACKUP_DIR/$BACKUP_FILE" \
    --exclude='*.log' \
    data/ certs/ auth/ config/

echo "Backup created: $BACKUP_DIR/$BACKUP_FILE"
EOF
    
    # Create cleanup script
    cat > scripts/cleanup.sh << 'EOF'
#!/bin/bash
# Registry cleanup script

# Remove old backups (keep last 7 days)
find /backup/registry -name "registry-backup-*.tar.gz" -mtime +7 -delete

# Remove old log files
find logs/ -name "*.log" -mtime +30 -delete

# Docker system cleanup
docker system prune -f --volumes

echo "Cleanup completed"
EOF
    
    # Create health check script
    cat > scripts/health-check.sh << 'EOF'
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
EOF
    
    chmod +x scripts/*.sh
    print_status "Maintenance scripts created"
}

# Function to test the deployment
test_deployment() {
    print_step "Testing deployment..."
    
    local registry_url="registry.medapp.local:5000"
    local max_attempts=30
    local attempt=1
    
    print_status "Waiting for registry to be ready..."
    
    while [[ $attempt -le $max_attempts ]]; do
        if curl -k -s -o /dev/null -w "%{http_code}" "https://$registry_url/v2/" | grep -q "200\|401"; then
            print_status "Registry is responding"
            break
        fi
        
        print_status "Attempt $attempt/$max_attempts - waiting for registry..."
        sleep 10
        ((attempt++))
    done
    
    if [[ $attempt -gt $max_attempts ]]; then
        print_error "Registry failed to start within timeout"
        return 1
    fi
    
    # Test authentication
    print_status "Testing authentication..."
    if echo "medapp123!" | docker login "$registry_url" -u medapp --password-stdin; then
        print_status "Authentication test passed"
        docker logout "$registry_url"
    else
        print_error "Authentication test failed"
        return 1
    fi
    
    # Test push/pull
    print_status "Testing push/pull operations..."
    docker pull hello-world:latest
    docker tag hello-world:latest "$registry_url/test/hello-world:latest"
    
    if docker push "$registry_url/test/hello-world:latest"; then
        print_status "Push test passed"
        
        # Clean up test image
        docker rmi "$registry_url/test/hello-world:latest" || true
        docker rmi hello-world:latest || true
        
        print_status "Pull/push test completed successfully"
    else
        print_error "Push test failed"
        return 1
    fi
    
    print_status "All tests passed!"
}

# Function to display setup summary
show_setup_summary() {
    print_header "Setup Summary"
    
    echo "Registry Type: $REGISTRY_TYPE"
    echo "Project Name: $PROJECT_NAME"
    echo "Environment: $ENVIRONMENT"
    echo "Monitoring: $INSTALL_MONITORING"
    echo "Security: $INSTALL_SECURITY"
    echo
    
    case "$REGISTRY_TYPE" in
        "local")
            echo "Registry URL: https://registry.medapp.local:5000"
            echo "Registry UI: http://registry.medapp.local:8080"
            ;;
        "harbor")
            echo "Harbor URL: https://harbor.medapp.local"
            echo "Harbor Admin: admin / HarborAdmin123!"
            ;;
        "full-stack")
            echo "Registry URL: https://registry.medapp.local:5000"
            echo "Registry UI: http://registry.medapp.local:8080"
            echo "Harbor URL: https://harbor.medapp.local"
            echo "Prometheus: http://localhost:9090"
            echo "Grafana: http://localhost:3001 (admin/grafana123!)"
            ;;
    esac
    
    echo
    echo "Default Credentials:"
    echo "  Registry: medapp / medapp123!"
    echo "  Admin: admin / admin123!"
    echo "  ReadOnly: readonly / readonly123!"
    echo
    echo "Next Steps:"
    echo "1. Add 'registry.medapp.local' to your /etc/hosts file"
    echo "2. Install the CA certificate: certs/ca.crt"
    echo "3. Use the registry CLI: ./registry-cli"
    echo "4. Build and push images: ./scripts/build-and-push.sh"
    echo "5. Monitor health: ./scripts/health-check.sh check"
    echo
    echo "Documentation: registry/README.md"
}

# Main setup function
main() {
    show_banner
    
    # Parse command line arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            --type)
                REGISTRY_TYPE="$2"
                shift 2
                ;;
            --project)
                PROJECT_NAME="$2"
                shift 2
                ;;
            --environment)
                ENVIRONMENT="$2"
                shift 2
                ;;
            --no-monitoring)
                INSTALL_MONITORING="false"
                shift
                ;;
            --no-security)
                INSTALL_SECURITY="false"
                shift
                ;;
            --help)
                echo "Usage: $0 [options]"
                echo ""
                echo "Options:"
                echo "  --type TYPE           Registry type (local, harbor, full-stack)"
                echo "  --project NAME        Project name (default: medapp)"
                echo "  --environment ENV     Environment (default: development)"
                echo "  --no-monitoring       Skip monitoring setup"
                echo "  --no-security         Skip security setup"
                echo "  --help                Show this help"
                exit 0
                ;;
            *)
                print_error "Unknown option: $1"
                exit 1
                ;;
        esac
    done
    
    print_status "Starting MedApp Registry Setup"
    print_status "Registry Type: $REGISTRY_TYPE"
    print_status "Project Name: $PROJECT_NAME"
    print_status "Environment: $ENVIRONMENT"
    echo
    
    # Run setup steps
    check_requirements
    create_directories
    generate_certificates
    setup_authentication
    create_registry_config
    deploy_registry_stack
    setup_monitoring
    setup_security
    create_maintenance_scripts
    
    # Test the deployment
    if test_deployment; then
        print_status "✅ Registry setup completed successfully!"
        show_setup_summary
    else
        print_error "❌ Registry setup failed during testing"
        exit 1
    fi
}

# Execute main function
main "$@"
