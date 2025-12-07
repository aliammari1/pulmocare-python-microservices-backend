#!/bin/bash

# Enhanced Build and Push Script with Auto-Tagging
# This script implements best practices for container image tagging and registry management

set -e

# Configuration - UPDATE THESE VALUES
REGISTRY_TYPE="${REGISTRY_TYPE:-local}"  # Options: local, harbor, docker-hub, acr, ecr, gcr
REGISTRY_URL="${REGISTRY_URL:-registry.medapp.local:5000}"
PROJECT_NAME="${PROJECT_NAME:-medapp}"
PROJECT_ROOT="${PROJECT_ROOT:-/home/azureuser/medapp-backend}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
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

print_header() {
    echo -e "${BLUE}[BUILD]${NC} $1"
}

# Function to generate tags based on Git context and best practices
generate_tags() {
    local service_name=$1
    local tags=()
    
    # Get Git information
    local git_branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")
    local git_commit=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
    local git_tag=$(git describe --tags --exact-match 2>/dev/null || echo "")
    local timestamp=$(date +%Y%m%d-%H%M%S)
    
    # Environment based tagging
    local environment="${ENVIRONMENT:-dev}"
    
    # Base image name
    local base_image="${REGISTRY_URL}/${PROJECT_NAME}/${service_name}"
    
    # 1. Latest tag (for main/master branch)
    if [[ "$git_branch" == "main" || "$git_branch" == "master" ]]; then
        tags+=("${base_image}:latest")
    fi
    
    # 2. Semantic version tag (if git tag exists)
    if [[ -n "$git_tag" ]]; then
        tags+=("${base_image}:${git_tag}")
        # Also create major.minor tag
        if [[ "$git_tag" =~ ^v?([0-9]+\.[0-9]+)\.[0-9]+$ ]]; then
            tags+=("${base_image}:v${BASH_REMATCH[1]}")
        fi
    fi
    
    # 3. Commit-based tag (always)
    tags+=("${base_image}:commit-${git_commit}")
    
    # 4. Branch-based tag (for feature branches)
    if [[ "$git_branch" != "main" && "$git_branch" != "master" ]]; then
        local clean_branch=$(echo "$git_branch" | sed 's/[^a-zA-Z0-9.-]/-/g' | tr '[:upper:]' '[:lower:]')
        tags+=("${base_image}:branch-${clean_branch}")
    fi
    
    # 5. Environment tag
    tags+=("${base_image}:${environment}")
    
    # 6. Timestamp tag (for uniqueness)
    tags+=("${base_image}:${timestamp}")
    
    # 7. PR-based tag (if PR number is available)
    if [[ -n "${PR_NUMBER}" ]]; then
        tags+=("${base_image}:pr-${PR_NUMBER}")
    fi
    
    # 8. Build number tag (if CI build number is available)
    if [[ -n "${BUILD_NUMBER}" ]]; then
        tags+=("${base_image}:build-${BUILD_NUMBER}")
    fi
    
    printf '%s\n' "${tags[@]}"
}

# Function to login to different registry types
registry_login() {
    case "$REGISTRY_TYPE" in
        "local")
            print_status "Using local registry - no authentication needed"
            ;;
        "harbor")
            print_status "Logging into Harbor registry..."
            docker login "$REGISTRY_URL" -u "${HARBOR_USERNAME:-admin}" -p "${HARBOR_PASSWORD:-HarborAdmin123!}"
            ;;
        "docker-hub")
            print_status "Logging into Docker Hub..."
            docker login -u "${DOCKER_USERNAME}" -p "${DOCKER_PASSWORD}"
            ;;
        "acr")
            print_status "Logging into Azure Container Registry..."
            az acr login --name "${ACR_NAME}"
            ;;
        "ecr")
            print_status "Logging into Amazon ECR..."
            aws ecr get-login-password --region "${AWS_REGION}" | docker login --username AWS --password-stdin "${REGISTRY_URL}"
            ;;
        "gcr")
            print_status "Logging into Google Container Registry..."
            docker login -u _json_key -p "$(cat ${GOOGLE_APPLICATION_CREDENTIALS})" https://gcr.io
            ;;
        *)
            print_error "Unknown registry type: $REGISTRY_TYPE"
            exit 1
            ;;
    esac
}

# Function to build and tag images
build_and_tag() {
    local service_name=$1
    local service_path=$2
    local dockerfile_path="${PROJECT_ROOT}/${service_path}/Dockerfile"
    local context_path="${PROJECT_ROOT}/${service_path}"
    
    print_header "Building $service_name..."
    
    # Check if Dockerfile exists
    if [[ ! -f "$dockerfile_path" ]]; then
        print_error "Dockerfile not found: $dockerfile_path"
        return 1
    fi
    
    # Generate tags
    local tags=($(generate_tags "$service_name"))
    local primary_tag="${tags[0]}"
    
    print_status "Generated tags for $service_name:"
    for tag in "${tags[@]}"; do
        echo "  - $tag"
    done
    
    # Build the image with primary tag
    print_status "Building image with primary tag: $primary_tag"
    docker build \
        --tag "$primary_tag" \
        --label "org.opencontainers.image.source=https://github.com/your-org/medapp" \
        --label "org.opencontainers.image.version=$(git describe --tags --always)" \
        --label "org.opencontainers.image.revision=$(git rev-parse HEAD)" \
        --label "org.opencontainers.image.created=$(date -u +'%Y-%m-%dT%H:%M:%SZ')" \
        --label "org.opencontainers.image.title=$service_name" \
        --label "org.opencontainers.image.description=MedApp $service_name service" \
        --file "$dockerfile_path" \
        "$context_path"
    
    # Tag with all other tags
    for tag in "${tags[@]:1}"; do
        print_status "Tagging: $tag"
        docker tag "$primary_tag" "$tag"
    done
    
    return 0
}

# Function to push images
push_images() {
    local service_name=$1
    local tags=($(generate_tags "$service_name"))
    
    print_header "Pushing $service_name images..."
    
    for tag in "${tags[@]}"; do
        print_status "Pushing: $tag"
        if docker push "$tag"; then
            print_status "Successfully pushed: $tag"
        else
            print_error "Failed to push: $tag"
            return 1
        fi
    done
    
    return 0
}

# Function to cleanup local images (optional)
cleanup_local_images() {
    local service_name=$1
    local tags=($(generate_tags "$service_name"))
    
    if [[ "${CLEANUP_LOCAL:-false}" == "true" ]]; then
        print_header "Cleaning up local images for $service_name..."
        for tag in "${tags[@]}"; do
            docker rmi "$tag" 2>/dev/null || true
        done
    fi
}

# Function to scan image for vulnerabilities (if supported)
scan_image() {
    local service_name=$1
    local primary_tag=$(generate_tags "$service_name" | head -n1)
    
    if command -v trivy &> /dev/null; then
        print_header "Scanning $service_name for vulnerabilities..."
        trivy image --exit-code 0 --severity HIGH,CRITICAL --format table "$primary_tag"
    elif [[ "$REGISTRY_TYPE" == "harbor" ]]; then
        print_status "Harbor will automatically scan the image after push"
    else
        print_warning "No vulnerability scanner available. Consider installing Trivy."
    fi
}

# Function to generate image manifest
generate_manifest() {
    local service_name=$1
    local tags=($(generate_tags "$service_name"))
    local manifest_file="${PROJECT_ROOT}/k8s/manifests/${service_name}-images.json"
    
    mkdir -p "$(dirname "$manifest_file")"
    
    cat > "$manifest_file" << EOF
{
  "service": "$service_name",
  "tags": [
$(printf '    "%s"' "${tags[0]}"; printf ',\n    "%s"' "${tags[@]:1}")
  ],
  "primary_tag": "${tags[0]}",
  "built_at": "$(date -u +'%Y-%m-%dT%H:%M:%SZ')",
  "git_commit": "$(git rev-parse HEAD 2>/dev/null || echo 'unknown')",
  "git_branch": "$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo 'unknown')"
}
EOF
    
    print_status "Generated manifest: $manifest_file"
}

# Function to update Kubernetes manifests with new image tags
update_k8s_manifests() {
    local service_name=$1
    local primary_tag=$(generate_tags "$service_name" | head -n1)
    local k8s_file="${PROJECT_ROOT}/k8s/services/${service_name}-service.yaml"
    
    if [[ -f "$k8s_file" ]]; then
        print_status "Updating Kubernetes manifest: $k8s_file"
        sed -i.bak "s|image: .*/${service_name}:.*|image: ${primary_tag}|g" "$k8s_file"
        rm -f "${k8s_file}.bak"
    fi
}

# Function to build and push a single service
build_and_push_service() {
    local service_name=$1
    local service_path=$2
    
    print_header "=== Processing $service_name ==="
    
    # Build and tag
    if ! build_and_tag "$service_name" "$service_path"; then
        print_error "Failed to build $service_name"
        return 1
    fi
    
    # Scan for vulnerabilities
    if [[ "${ENABLE_SCANNING:-true}" == "true" ]]; then
        scan_image "$service_name"
    fi
    
    # Push images
    if ! push_images "$service_name"; then
        print_error "Failed to push $service_name"
        return 1
    fi
    
    # Generate manifest
    generate_manifest "$service_name"
    
    # Update K8s manifests
    if [[ "${UPDATE_K8S_MANIFESTS:-true}" == "true" ]]; then
        update_k8s_manifests "$service_name"
    fi
    
    # Cleanup local images
    cleanup_local_images "$service_name"
    
    print_status "✅ Successfully processed $service_name"
    return 0
}

# Main function
main() {
    print_header "🏗️ Starting Enhanced Build and Push Process"
    print_status "Registry: $REGISTRY_URL"
    print_status "Project: $PROJECT_NAME"
    print_status "Registry Type: $REGISTRY_TYPE"
    
    # Check prerequisites
    if ! command -v docker &> /dev/null; then
        print_error "Docker is not installed"
        exit 1
    fi
    
    if ! docker info &> /dev/null; then
        print_error "Docker daemon is not running"
        exit 1
    fi
    
    # Login to registry
    registry_login
    
    # Services to build
    local services=(
        "auth:services/auth"
        "medecins:services/medecins"
        "patients:services/patients"
        "ordonnances:services/ordonnances"
        "radiologues:services/radiologues"
        "reports:services/reports"
        "appointments:services/appointments"
        "medfiles:services/medfiles"
    )
    
    # Add medagent if requested
    if [[ "${INCLUDE_MEDAGENT:-false}" == "true" ]]; then
        services+=("medagent:services/medagent")
    fi
    
    local failed_services=()
    local successful_services=()
    
    # Process each service
    for service_info in "${services[@]}"; do
        IFS=':' read -r service_name service_path <<< "$service_info"
        
        if build_and_push_service "$service_name" "$service_path"; then
            successful_services+=("$service_name")
        else
            failed_services+=("$service_name")
        fi
    done
    
    # Summary
    print_header "📊 Build Summary"
    print_status "Successful builds: ${#successful_services[@]}"
    for service in "${successful_services[@]}"; do
        echo "  ✅ $service"
    done
    
    if [[ ${#failed_services[@]} -gt 0 ]]; then
        print_error "Failed builds: ${#failed_services[@]}"
        for service in "${failed_services[@]}"; do
            echo "  ❌ $service"
        done
        exit 1
    fi
    
    print_status "🎉 All services built and pushed successfully!"
    
    # Display access information
    print_header "📋 Registry Access Information"
    case "$REGISTRY_TYPE" in
        "local")
            echo "Registry UI: https://registry.medapp.local"
            echo "Docker commands: docker pull ${REGISTRY_URL}/${PROJECT_NAME}/service-name:tag"
            ;;
        "harbor")
            echo "Harbor UI: https://${REGISTRY_URL}"
            echo "Username: admin / Password: HarborAdmin123!"
            ;;
        *)
            echo "Registry: ${REGISTRY_URL}"
            ;;
    esac
}

# Handle command line arguments
case "${1:-}" in
    "help"|"-h"|"--help")
        cat << 'EOF'
Enhanced Build and Push Script for MedApp

Usage: ./build-and-push.sh [options]

Environment Variables:
  REGISTRY_TYPE          Registry type (local, harbor, docker-hub, acr, ecr, gcr)
  REGISTRY_URL           Registry URL
  PROJECT_NAME           Project name (default: medapp)
  ENVIRONMENT           Environment (dev, staging, prod)
  INCLUDE_MEDAGENT      Include medagent service (true/false)
  ENABLE_SCANNING       Enable vulnerability scanning (true/false)
  UPDATE_K8S_MANIFESTS  Update Kubernetes manifests (true/false)
  CLEANUP_LOCAL         Cleanup local images after push (true/false)

Examples:
  # Build for local registry
  REGISTRY_TYPE=local ./build-and-push.sh

  # Build for Harbor
  REGISTRY_TYPE=harbor REGISTRY_URL=harbor.company.com ./build-and-push.sh

  # Build for production
  ENVIRONMENT=prod REGISTRY_TYPE=harbor ./build-and-push.sh

  # Build with medagent included
  INCLUDE_MEDAGENT=true ./build-and-push.sh
EOF
        exit 0
        ;;
    *)
        main "$@"
        ;;
esac
