#!/bin/bash

# Tag Management Script for Container Images
# Provides advanced tagging strategies and tag cleanup capabilities

set -e

# Configuration
REGISTRY_URL="${REGISTRY_URL:-registry.medapp.local:5000}"
PROJECT_NAME="${PROJECT_NAME:-medapp}"
DRY_RUN="${DRY_RUN:-false}"

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
    echo -e "${BLUE}[TAG-MGR]${NC} $1"
}

# Function to list all tags for a service
list_tags() {
    local service_name=$1
    local image_name="${REGISTRY_URL}/${PROJECT_NAME}/${service_name}"
    
    print_header "Listing tags for $service_name"
    
    # For Docker Hub
    if [[ "$REGISTRY_URL" == *"docker.io"* ]]; then
        curl -s "https://registry.hub.docker.com/v2/repositories/${PROJECT_NAME}/${service_name}/tags/" | \
        jq -r '.results[].name' | sort -V
    # For Harbor
    elif command -v curl &> /dev/null; then
        # Try to use Harbor API
        local harbor_url=$(echo "$REGISTRY_URL" | sed 's/:5000//')
        curl -s -k -u "${HARBOR_USERNAME:-admin}:${HARBOR_PASSWORD:-HarborAdmin123!}" \
            "${harbor_url}/api/v2.0/projects/${PROJECT_NAME}/repositories/${service_name}/artifacts" | \
        jq -r '.[].tags[]?.name // empty' | sort -V
    else
        print_warning "Cannot list tags - API not available for this registry type"
    fi
}

# Function to promote a tag (e.g., dev -> staging -> prod)
promote_tag() {
    local service_name=$1
    local source_tag=$2
    local target_tag=$3
    
    print_header "Promoting $service_name:$source_tag to $target_tag"
    
    local image_name="${REGISTRY_URL}/${PROJECT_NAME}/${service_name}"
    
    if [[ "$DRY_RUN" == "true" ]]; then
        print_warning "DRY RUN: Would promote $image_name:$source_tag to $image_name:$target_tag"
        return 0
    fi
    
    # Pull source image
    docker pull "$image_name:$source_tag"
    
    # Tag as target
    docker tag "$image_name:$source_tag" "$image_name:$target_tag"
    
    # Push target tag
    docker push "$image_name:$target_tag"
    
    print_status "Successfully promoted $service_name:$source_tag to $target_tag"
}

# Function to cleanup old tags based on retention policy
cleanup_old_tags() {
    local service_name=$1
    local keep_count=${2:-10}  # Keep last 10 tags by default
    
    print_header "Cleaning up old tags for $service_name (keeping last $keep_count)"
    
    local image_name="${REGISTRY_URL}/${PROJECT_NAME}/${service_name}"
    
    # Get all tags sorted by creation date (newest first)
    local all_tags=($(list_tags "$service_name"))
    
    if [[ ${#all_tags[@]} -le $keep_count ]]; then
        print_status "Only ${#all_tags[@]} tags found, no cleanup needed"
        return 0
    fi
    
    # Skip protected tags
    local protected_tags=("latest" "stable" "prod" "production" "staging")
    local tags_to_delete=()
    
    for tag in "${all_tags[@]:$keep_count}"; do
        local is_protected=false
        for protected in "${protected_tags[@]}"; do
            if [[ "$tag" == "$protected" ]]; then
                is_protected=true
                break
            fi
        done
        
        if [[ "$is_protected" == "false" ]]; then
            tags_to_delete+=("$tag")
        fi
    done
    
    if [[ ${#tags_to_delete[@]} -eq 0 ]]; then
        print_status "No tags to delete"
        return 0
    fi
    
    print_warning "Will delete ${#tags_to_delete[@]} old tags:"
    for tag in "${tags_to_delete[@]}"; do
        echo "  - $tag"
    done
    
    if [[ "$DRY_RUN" == "true" ]]; then
        print_warning "DRY RUN: Would delete the above tags"
        return 0
    fi
    
    # Confirm deletion
    read -p "Are you sure? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        print_status "Cleanup cancelled"
        return 0
    fi
    
    # Delete tags
    for tag in "${tags_to_delete[@]}"; do
        if delete_tag "$service_name" "$tag"; then
            print_status "Deleted: $image_name:$tag"
        else
            print_error "Failed to delete: $image_name:$tag"
        fi
    done
}

# Function to delete a specific tag
delete_tag() {
    local service_name=$1
    local tag=$2
    local image_name="${REGISTRY_URL}/${PROJECT_NAME}/${service_name}"
    
    # For Harbor registry
    if [[ "$REGISTRY_URL" == *"harbor"* ]]; then
        local harbor_url=$(echo "$REGISTRY_URL" | sed 's/:5000//')
        curl -s -k -X DELETE \
            -u "${HARBOR_USERNAME:-admin}:${HARBOR_PASSWORD:-HarborAdmin123!}" \
            "${harbor_url}/api/v2.0/projects/${PROJECT_NAME}/repositories/${service_name}/artifacts/${tag}"
        return $?
    else
        # For other registries, try to use docker commands
        print_warning "Tag deletion not implemented for this registry type"
        return 1
    fi
}

# Function to retag an image with new convention
retag_image() {
    local service_name=$1
    local old_tag=$2
    local new_tag=$3
    
    print_header "Retagging $service_name:$old_tag to $new_tag"
    
    local image_name="${REGISTRY_URL}/${PROJECT_NAME}/${service_name}"
    
    if [[ "$DRY_RUN" == "true" ]]; then
        print_warning "DRY RUN: Would retag $image_name:$old_tag to $image_name:$new_tag"
        return 0
    fi
    
    # Pull old image
    docker pull "$image_name:$old_tag"
    
    # Tag with new name
    docker tag "$image_name:$old_tag" "$image_name:$new_tag"
    
    # Push new tag
    docker push "$image_name:$new_tag"
    
    print_status "Successfully retagged $service_name:$old_tag to $new_tag"
}

# Function to show tag statistics
show_tag_stats() {
    local service_name=$1
    
    print_header "Tag statistics for $service_name"
    
    local tags=($(list_tags "$service_name"))
    local total_tags=${#tags[@]}
    
    echo "Total tags: $total_tags"
    
    # Count by type
    local version_tags=0
    local commit_tags=0
    local branch_tags=0
    local env_tags=0
    local build_tags=0
    
    for tag in "${tags[@]}"; do
        if [[ "$tag" =~ ^v?[0-9]+\.[0-9]+\.[0-9]+ ]]; then
            ((version_tags++))
        elif [[ "$tag" =~ ^commit- ]]; then
            ((commit_tags++))
        elif [[ "$tag" =~ ^branch- ]]; then
            ((branch_tags++))
        elif [[ "$tag" =~ ^(dev|staging|prod|production)$ ]]; then
            ((env_tags++))
        elif [[ "$tag" =~ ^build- ]]; then
            ((build_tags++))
        fi
    done
    
    echo "Version tags: $version_tags"
    echo "Commit tags: $commit_tags"
    echo "Branch tags: $branch_tags"
    echo "Environment tags: $env_tags"
    echo "Build tags: $build_tags"
    
    # Show recent tags
    echo
    echo "Recent tags (last 5):"
    for tag in "${tags[@]:0:5}"; do
        echo "  - $tag"
    done
}

# Function to validate tag naming convention
validate_tag() {
    local tag=$1
    local valid_patterns=(
        '^latest$'
        '^stable$'
        '^v?[0-9]+\.[0-9]+\.[0-9]+(-[a-zA-Z0-9]+)*$'  # Semantic version
        '^commit-[a-f0-9]{7,}$'                        # Commit hash
        '^branch-[a-zA-Z0-9.-]+$'                      # Branch name
        '^(dev|staging|prod|production)$'              # Environment
        '^[0-9]{8}-[0-9]{6}$'                         # Timestamp
        '^pr-[0-9]+$'                                 # Pull request
        '^build-[0-9]+$'                              # Build number
    )
    
    for pattern in "${valid_patterns[@]}"; do
        if [[ "$tag" =~ $pattern ]]; then
            return 0
        fi
    done
    
    return 1
}

# Main function
main() {
    local action=$1
    shift
    
    case "$action" in
        "list")
            if [[ $# -eq 0 ]]; then
                print_error "Usage: $0 list <service_name>"
                exit 1
            fi
            list_tags "$1"
            ;;
        "promote")
            if [[ $# -lt 3 ]]; then
                print_error "Usage: $0 promote <service_name> <source_tag> <target_tag>"
                exit 1
            fi
            promote_tag "$1" "$2" "$3"
            ;;
        "cleanup")
            if [[ $# -eq 0 ]]; then
                print_error "Usage: $0 cleanup <service_name> [keep_count]"
                exit 1
            fi
            cleanup_old_tags "$1" "${2:-10}"
            ;;
        "retag")
            if [[ $# -lt 3 ]]; then
                print_error "Usage: $0 retag <service_name> <old_tag> <new_tag>"
                exit 1
            fi
            retag_image "$1" "$2" "$3"
            ;;
        "stats")
            if [[ $# -eq 0 ]]; then
                print_error "Usage: $0 stats <service_name>"
                exit 1
            fi
            show_tag_stats "$1"
            ;;
        "validate")
            if [[ $# -eq 0 ]]; then
                print_error "Usage: $0 validate <tag>"
                exit 1
            fi
            if validate_tag "$1"; then
                print_status "Tag '$1' is valid"
            else
                print_error "Tag '$1' does not follow naming convention"
                exit 1
            fi
            ;;
        *)
            echo "Usage: $0 {list|promote|cleanup|retag|stats|validate} [options]"
            echo ""
            echo "Commands:"
            echo "  list <service>                     - List all tags for a service"
            echo "  promote <service> <src> <dst>      - Promote a tag"
            echo "  cleanup <service> [keep_count]     - Clean up old tags"
            echo "  retag <service> <old> <new>        - Retag an image"
            echo "  stats <service>                    - Show tag statistics"
            echo "  validate <tag>                     - Validate tag naming"
            echo ""
            echo "Environment variables:"
            echo "  REGISTRY_URL     - Registry URL"
            echo "  PROJECT_NAME     - Project name"
            echo "  DRY_RUN         - Set to 'true' for dry run"
            exit 1
            ;;
    esac
}

# Check if script is being sourced or executed
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi
