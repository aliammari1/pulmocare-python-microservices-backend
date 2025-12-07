#!/bin/bash

# CI/CD Pipeline Integration Script for Container Registry
# Provides seamless integration with various CI/CD platforms

set -e

# Configuration
CI_PLATFORM="${CI_PLATFORM:-generic}"  # Options: jenkins, github-actions, gitlab-ci, azure-devops, generic
REGISTRY_URL="${REGISTRY_URL:-registry.medapp.local:5000}"
PROJECT_NAME="${PROJECT_NAME:-medapp}"
BRANCH_NAME="${BRANCH_NAME:-$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo 'unknown')}"
BUILD_NUMBER="${BUILD_NUMBER:-$(date +%Y%m%d%H%M%S)}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_status() {
    echo -e "${GREEN}[CI/CD]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_header() {
    echo -e "${BLUE}[PIPELINE]${NC} $1"
}

# Function to detect CI/CD platform
detect_ci_platform() {
    if [[ -n "$JENKINS_URL" ]]; then
        echo "jenkins"
    elif [[ -n "$GITHUB_ACTIONS" ]]; then
        echo "github-actions"
    elif [[ -n "$GITLAB_CI" ]]; then
        echo "gitlab-ci"
    elif [[ -n "$AZURE_HTTP_USER_AGENT" ]]; then
        echo "azure-devops"
    else
        echo "generic"
    fi
}

# Function to get environment variables based on CI platform
get_ci_variables() {
    local platform=$(detect_ci_platform)
    
    case "$platform" in
        "jenkins")
            export CI_COMMIT_SHA="${GIT_COMMIT:-$(git rev-parse HEAD)}"
            export CI_BRANCH="${GIT_BRANCH:-$BRANCH_NAME}"
            export CI_BUILD_NUMBER="${BUILD_NUMBER}"
            export CI_PROJECT_NAME="${JOB_NAME:-$PROJECT_NAME}"
            export CI_PIPELINE_URL="${BUILD_URL}"
            ;;
        "github-actions")
            export CI_COMMIT_SHA="${GITHUB_SHA}"
            export CI_BRANCH="${GITHUB_REF_NAME}"
            export CI_BUILD_NUMBER="${GITHUB_RUN_NUMBER}"
            export CI_PROJECT_NAME="${GITHUB_REPOSITORY##*/}"
            export CI_PIPELINE_URL="${GITHUB_SERVER_URL}/${GITHUB_REPOSITORY}/actions/runs/${GITHUB_RUN_ID}"
            export CI_PR_NUMBER="${GITHUB_PR_NUMBER}"
            ;;
        "gitlab-ci")
            export CI_COMMIT_SHA="${CI_COMMIT_SHA}"
            export CI_BRANCH="${CI_COMMIT_REF_NAME}"
            export CI_BUILD_NUMBER="${CI_PIPELINE_IID}"
            export CI_PROJECT_NAME="${CI_PROJECT_NAME}"
            export CI_PIPELINE_URL="${CI_PIPELINE_URL}"
            export CI_PR_NUMBER="${CI_MERGE_REQUEST_IID}"
            ;;
        "azure-devops")
            export CI_COMMIT_SHA="${BUILD_SOURCEVERSION}"
            export CI_BRANCH="${BUILD_SOURCEBRANCHNAME}"
            export CI_BUILD_NUMBER="${BUILD_BUILDNUMBER}"
            export CI_PROJECT_NAME="${BUILD_REPOSITORY_NAME}"
            export CI_PIPELINE_URL="${SYSTEM_TEAMFOUNDATIONSERVERURI}${SYSTEM_TEAMPROJECT}/_build/results?buildId=${BUILD_BUILDID}"
            ;;
        *)
            export CI_COMMIT_SHA="$(git rev-parse HEAD 2>/dev/null || echo 'unknown')"
            export CI_BRANCH="$BRANCH_NAME"
            export CI_BUILD_NUMBER="$BUILD_NUMBER"
            export CI_PROJECT_NAME="$PROJECT_NAME"
            export CI_PIPELINE_URL="unknown"
            ;;
    esac
    
    print_status "Detected CI platform: $platform"
    print_status "Commit SHA: ${CI_COMMIT_SHA:0:8}"
    print_status "Branch: $CI_BRANCH"
    print_status "Build Number: $CI_BUILD_NUMBER"
}

# Function to determine if this is a release build
is_release_build() {
    local branch="$CI_BRANCH"
    local tag="$(git describe --tags --exact-match 2>/dev/null || echo '')"
    
    if [[ -n "$tag" ]]; then
        return 0
    elif [[ "$branch" == "main" || "$branch" == "master" ]]; then
        return 0
    elif [[ "$branch" == "release/"* ]]; then
        return 0
    else
        return 1
    fi
}

# Function to determine deployment environment
get_deployment_environment() {
    local branch="$CI_BRANCH"
    
    if [[ "$branch" == "main" || "$branch" == "master" ]]; then
        echo "production"
    elif [[ "$branch" == "staging" ]]; then
        echo "staging"
    elif [[ "$branch" == "develop" ]]; then
        echo "development"
    elif [[ "$branch" == "release/"* ]]; then
        echo "staging"
    else
        echo "feature"
    fi
}

# Function to generate pipeline-specific tags
generate_pipeline_tags() {
    local service_name=$1
    local environment=$(get_deployment_environment)
    local base_image="${REGISTRY_URL}/${PROJECT_NAME}/${service_name}"
    local tags=()
    
    # Core tags
    tags+=("${base_image}:${CI_BUILD_NUMBER}")
    tags+=("${base_image}:commit-${CI_COMMIT_SHA:0:8}")
    tags+=("${base_image}:${environment}")
    
    # Branch-specific tags
    if [[ "$CI_BRANCH" != "main" && "$CI_BRANCH" != "master" ]]; then
        local clean_branch=$(echo "$CI_BRANCH" | sed 's/[^a-zA-Z0-9.-]/-/g' | tr '[:upper:]' '[:lower:]')
        tags+=("${base_image}:branch-${clean_branch}")
    fi
    
    # Release tags
    if is_release_build; then
        tags+=("${base_image}:latest")
        
        # If there's a git tag, use it
        local git_tag=$(git describe --tags --exact-match 2>/dev/null || echo '')
        if [[ -n "$git_tag" ]]; then
            tags+=("${base_image}:${git_tag}")
        fi
    fi
    
    # PR-specific tags
    if [[ -n "$CI_PR_NUMBER" ]]; then
        tags+=("${base_image}:pr-${CI_PR_NUMBER}")
    fi
    
    printf '%s\n' "${tags[@]}"
}

# Function to build and push with pipeline integration
pipeline_build_and_push() {
    local service_name=$1
    local service_path=$2
    local dockerfile_path="$service_path/Dockerfile"
    
    print_header "Pipeline build: $service_name"
    
    if [[ ! -f "$dockerfile_path" ]]; then
        print_error "Dockerfile not found: $dockerfile_path"
        return 1
    fi
    
    # Generate tags
    local tags=($(generate_pipeline_tags "$service_name"))
    local primary_tag="${tags[0]}"
    
    print_status "Generated tags:"
    for tag in "${tags[@]}"; do
        echo "  - $tag"
    done
    
    # Build with build arguments
    local build_args=(
        --build-arg "BUILD_DATE=$(date -u +'%Y-%m-%dT%H:%M:%SZ')"
        --build-arg "VCS_REF=${CI_COMMIT_SHA}"
        --build-arg "VERSION=${CI_BUILD_NUMBER}"
        --build-arg "BUILD_NUMBER=${CI_BUILD_NUMBER}"
        --build-arg "BRANCH=${CI_BRANCH}"
    )
    
    # Build with labels
    local labels=(
        --label "org.opencontainers.image.created=$(date -u +'%Y-%m-%dT%H:%M:%SZ')"
        --label "org.opencontainers.image.revision=${CI_COMMIT_SHA}"
        --label "org.opencontainers.image.version=${CI_BUILD_NUMBER}"
        --label "org.opencontainers.image.title=${service_name}"
        --label "org.opencontainers.image.description=MedApp ${service_name} service"
        --label "org.opencontainers.image.source=${CI_PIPELINE_URL}"
        --label "ci.build.number=${CI_BUILD_NUMBER}"
        --label "ci.branch=${CI_BRANCH}"
        --label "ci.commit=${CI_COMMIT_SHA}"
    )
    
    print_status "Building $service_name..."
    docker build \
        "${build_args[@]}" \
        "${labels[@]}" \
        --tag "$primary_tag" \
        --file "$dockerfile_path" \
        "$service_path"
    
    # Tag with all additional tags
    for tag in "${tags[@]:1}"; do
        docker tag "$primary_tag" "$tag"
    done
    
    # Push all tags
    print_status "Pushing $service_name images..."
    for tag in "${tags[@]}"; do
        print_status "Pushing: $tag"
        docker push "$tag"
    done
    
    # Output variables for downstream jobs
    output_pipeline_variables "$service_name" "${tags[@]}"
    
    return 0
}

# Function to output variables for downstream pipeline jobs
output_pipeline_variables() {
    local service_name=$1
    shift
    local tags=("$@")
    local primary_tag="${tags[0]}"
    
    case "$(detect_ci_platform)" in
        "github-actions")
            echo "::set-output name=${service_name}_image::${primary_tag}"
            echo "::set-output name=${service_name}_tags::${tags[*]}"
            ;;
        "gitlab-ci")
            echo "${service_name^^}_IMAGE=${primary_tag}" >> variables.env
            echo "${service_name^^}_TAGS=${tags[*]}" >> variables.env
            ;;
        "jenkins")
            echo "${service_name^^}_IMAGE=${primary_tag}" > "${service_name}_image.properties"
            echo "${service_name^^}_TAGS=${tags[*]}" >> "${service_name}_image.properties"
            ;;
        "azure-devops")
            echo "##vso[task.setvariable variable=${service_name}_image;isOutput=true]${primary_tag}"
            echo "##vso[task.setvariable variable=${service_name}_tags;isOutput=true]${tags[*]}"
            ;;
    esac
}

# Function to update Kubernetes manifests with new image tags
update_k8s_manifests() {
    local service_name=$1
    local new_tag=$2
    local manifest_path="k8s/services/${service_name}-service.yaml"
    
    if [[ -f "$manifest_path" ]]; then
        print_status "Updating Kubernetes manifest: $manifest_path"
        
        # Use sed to update the image tag
        sed -i "s|image: .*/medapp-${service_name}:.*|image: ${REGISTRY_URL}/${PROJECT_NAME}/${service_name}:${new_tag}|g" "$manifest_path"
        
        print_status "Updated manifest with tag: $new_tag"
    else
        print_warning "Kubernetes manifest not found: $manifest_path"
    fi
}

# Function to run security scanning
security_scan() {
    local image_tag=$1
    
    print_header "Running security scan on: $image_tag"
    
    # Use Trivy for vulnerability scanning
    if command -v trivy &> /dev/null; then
        print_status "Scanning with Trivy..."
        trivy image --severity HIGH,CRITICAL --format json --output scan-results.json "$image_tag"
        
        # Check if there are any HIGH or CRITICAL vulnerabilities
        local critical_count=$(jq '.Results[]?.Vulnerabilities[]? | select(.Severity == "CRITICAL") | length' scan-results.json 2>/dev/null | wc -l)
        local high_count=$(jq '.Results[]?.Vulnerabilities[]? | select(.Severity == "HIGH") | length' scan-results.json 2>/dev/null | wc -l)
        
        if [[ $critical_count -gt 0 ]]; then
            print_error "Found $critical_count CRITICAL vulnerabilities"
            return 1
        elif [[ $high_count -gt 0 ]]; then
            print_warning "Found $high_count HIGH vulnerabilities"
        else
            print_status "No critical vulnerabilities found"
        fi
    else
        print_warning "Trivy not installed, skipping security scan"
    fi
    
    return 0
}

# Function to generate build report
generate_build_report() {
    local services=("$@")
    local report_file="build-report.json"
    
    print_header "Generating build report..."
    
    local report_data=$(cat <<EOF
{
  "build": {
    "number": "$CI_BUILD_NUMBER",
    "branch": "$CI_BRANCH",
    "commit": "$CI_COMMIT_SHA",
    "timestamp": "$(date -u +'%Y-%m-%dT%H:%M:%SZ')",
    "pipeline_url": "$CI_PIPELINE_URL",
    "environment": "$(get_deployment_environment)"
  },
  "registry": {
    "url": "$REGISTRY_URL",
    "project": "$PROJECT_NAME"
  },
  "services": [
EOF
)
    
    local first=true
    for service in "${services[@]}"; do
        if [[ "$first" == "true" ]]; then
            first=false
        else
            report_data+=","
        fi
        
        local tags=($(generate_pipeline_tags "$service"))
        local tags_json=$(printf '"%s",' "${tags[@]}" | sed 's/,$//')
        
        report_data+=$(cat <<EOF

    {
      "name": "$service",
      "tags": [$tags_json]
    }
EOF
)
    done
    
    report_data+=$(cat <<EOF

  ]
}
EOF
)
    
    echo "$report_data" > "$report_file"
    print_status "Build report generated: $report_file"
}

# Function to cleanup old images in registry
cleanup_old_images() {
    local max_age_days=${1:-30}
    
    print_header "Cleaning up images older than $max_age_days days"
    
    # This would need to be implemented based on the registry type
    # For now, just log the action
    print_status "Cleanup would remove images older than $max_age_days days"
    print_warning "Cleanup implementation depends on registry type"
}

# Main pipeline function
run_pipeline() {
    local action=$1
    shift
    local services=("$@")
    
    # Set up CI environment
    get_ci_variables
    
    case "$action" in
        "build")
            if [[ ${#services[@]} -eq 0 ]]; then
                # Default services
                services=("auth" "medecins" "patients" "ordonnances" "radiologues" "reports" "appointments" "medfiles")
            fi
            
            print_header "Building ${#services[@]} services"
            
            local failed_services=()
            for service in "${services[@]}"; do
                local service_path="services/$service"
                
                if [[ -d "$service_path" ]]; then
                    if pipeline_build_and_push "$service" "$service_path"; then
                        print_status "✅ $service build completed"
                    else
                        print_error "❌ $service build failed"
                        failed_services+=("$service")
                    fi
                else
                    print_warning "Service directory not found: $service_path"
                fi
            done
            
            # Generate build report
            generate_build_report "${services[@]}"
            
            if [[ ${#failed_services[@]} -gt 0 ]]; then
                print_error "Failed services: ${failed_services[*]}"
                exit 1
            fi
            
            print_status "All services built successfully"
            ;;
        "scan")
            print_header "Scanning images for vulnerabilities"
            for service in "${services[@]}"; do
                local tags=($(generate_pipeline_tags "$service"))
                security_scan "${tags[0]}"
            done
            ;;
        "deploy")
            print_header "Updating Kubernetes manifests"
            for service in "${services[@]}"; do
                local tags=($(generate_pipeline_tags "$service"))
                local primary_tag=$(echo "${tags[0]}" | cut -d: -f2)
                update_k8s_manifests "$service" "$primary_tag"
            done
            ;;
        "cleanup")
            cleanup_old_images "${1:-30}"
            ;;
        *)
            echo "Usage: $0 {build|scan|deploy|cleanup} [services...]"
            echo ""
            echo "Commands:"
            echo "  build [services...]    - Build and push container images"
            echo "  scan [services...]     - Scan images for vulnerabilities"
            echo "  deploy [services...]   - Update Kubernetes manifests"
            echo "  cleanup [days]         - Cleanup old images"
            echo ""
            echo "Examples:"
            echo "  $0 build auth medecins"
            echo "  $0 scan"
            echo "  $0 deploy"
            echo "  $0 cleanup 30"
            exit 1
            ;;
    esac
}

# Check if script is being sourced or executed
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    run_pipeline "$@"
fi
