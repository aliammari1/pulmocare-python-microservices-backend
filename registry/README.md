# Container Registry Setup for MedApp

This directory contains a comprehensive container registry solution for the MedApp Kubernetes deployment with enterprise-grade features, automated tagging strategies, and CI/CD integration.

## 🏗️ Registry Options

### 1. Local Registry (Development)

- **Pros**: Fast, no external dependencies, secure with TLS and authentication
- **Cons**: Not suitable for production clustering
- **Best for**: Local development, testing, offline environments
- **Features**: SSL/TLS encryption, HTTP authentication, persistent storage

### 2. Harbor (Enterprise Self-hosted)

- **Pros**: Enterprise features, vulnerability scanning, RBAC, image signing
- **Cons**: Infrastructure overhead, maintenance required
- **Best for**: Enterprise, on-premise deployments, compliance requirements
- **Features**: Content trust, vulnerability scanning, replication, audit logs

### 3. Cloud Registries

- **Azure Container Registry (ACR)**: Native Azure integration, geo-replication
- **Amazon Elastic Container Registry (ECR)**: AWS native, lifecycle policies
- **Google Container Registry (GCR)**: GCP native, build triggers
- **Best for**: Cloud-native applications, managed infrastructure

### 4. Docker Hub (Public/Private)

- **Pros**: Easy setup, integrated with Docker CLI, large community
- **Cons**: Rate limiting, costs for private repos, limited enterprise features
- **Best for**: Open source projects, small teams, getting started

## 📁 Enhanced Structure

```
registry/
├── README.md                    # This comprehensive guide
├── local-registry.yaml          # Secure local registry with TLS
├── harbor/                      # Harbor enterprise registry
│   ├── docker-compose.yml       # Harbor deployment
│   └── harbor.yml               # Harbor configuration
├── scripts/                     # Advanced automation scripts
│   ├── build-and-push.sh       # Enhanced build with auto-tagging
│   ├── tag-manager.sh           # Tag lifecycle management
│   ├── registry-setup.sh       # Automated registry setup
│   └── ci-cd-integration.sh    # CI/CD pipeline integration
└── configs/                     # Registry configurations
    ├── docker-config.json       # Docker daemon configuration
    └── registry-mirror.yml      # Registry mirror setup
```

## 🏷️ Advanced Tagging Strategy

Our intelligent tagging strategy implements GitOps best practices with automatic tag generation:

### Core Tags

- `latest` - Latest stable release (main/master branch only)
- `stable` - Manually promoted stable releases
- `v1.2.3` - Semantic versioning tags from Git tags

### Development Tags

- `commit-a1b2c3d` - Specific commit references
- `branch-feature-auth` - Feature branch builds
- `pr-123` - Pull request builds
- `build-456` - CI/CD build numbers

### Environment Tags

- `dev` - Development environment
- `staging` - Staging environment
- `prod` - Production environment

### Timestamp Tags

- `20240115-143022` - Build timestamp for uniqueness

### Example Tag Set

````
registry.medapp.local:5000/medapp/auth:latest
registry.medapp.local:5000/medapp/auth:v1.2.3
registry.medapp.local:5000/medapp/auth:commit-a1b2c3d
registry.medapp.local:5000/medapp/auth:prod
registry.medapp.local:5000/medapp/auth:20240115-143022

## 🚀 Quick Start

### 1. Setup Local Registry (Recommended for Development)
```bash
# Set environment variables
export REGISTRY_TYPE=local
export PROJECT_NAME=medapp

# Run setup script
cd registry/scripts
chmod +x *.sh
./registry-setup.sh setup

# Test the registry
./registry-setup.sh test
````

### 2. Build and Push Images

```bash
# Build all services with auto-tagging
./build-and-push.sh

# Build specific services
./build-and-push.sh auth medecins patients

# Build with custom environment
ENVIRONMENT=staging ./build-and-push.sh
```

### 3. Manage Tags

```bash
# List tags for a service
./tag-manager.sh list auth

# Promote a development build to staging
./tag-manager.sh promote auth commit-a1b2c3d staging

# Clean up old tags (keep last 10)
./tag-manager.sh cleanup auth 10

# Show tag statistics
./tag-manager.sh stats auth
```

## 🔧 Configuration

### Environment Variables

#### Global Configuration

```bash
export REGISTRY_TYPE=local          # local, harbor, acr, ecr, gcr, docker-hub
export REGISTRY_URL=registry.medapp.local:5000
export PROJECT_NAME=medapp
export ENVIRONMENT=development      # development, staging, production
```

#### Registry-Specific Configuration

##### Harbor Registry

```bash
export HARBOR_USERNAME=admin
export HARBOR_PASSWORD=HarborAdmin123!
export HARBOR_URL=harbor.medapp.local
```

##### Azure Container Registry

```bash
export ACR_NAME=medappregistry
export ACR_RESOURCE_GROUP=medapp-rg
export ACR_LOCATION=eastus
```

##### AWS Elastic Container Registry

```bash
export AWS_REGION=us-east-1
export ECR_REPOSITORY_URI=123456789012.dkr.ecr.us-east-1.amazonaws.com
```

### CI/CD Integration

#### GitHub Actions

```yaml
name: Build and Push
on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Build and Push Images
        env:
          REGISTRY_TYPE: harbor
          REGISTRY_URL: harbor.medapp.local
          HARBOR_USERNAME: ${{ secrets.HARBOR_USERNAME }}
          HARBOR_PASSWORD: ${{ secrets.HARBOR_PASSWORD }}
        run: |
          cd registry/scripts
          ./ci-cd-integration.sh build
```

#### Jenkins Pipeline

```groovy
pipeline {
    agent any

    environment {
        REGISTRY_TYPE = 'harbor'
        REGISTRY_URL = 'harbor.medapp.local'
        PROJECT_NAME = 'medapp'
    }

    stages {
        stage('Build and Push') {
            steps {
                script {
                    sh 'cd registry/scripts && ./ci-cd-integration.sh build'
                }
            }
        }

        stage('Security Scan') {
            steps {
                script {
                    sh 'cd registry/scripts && ./ci-cd-integration.sh scan'
                }
            }
        }

        stage('Deploy') {
            when {
                branch 'main'
            }
            steps {
                script {
                    sh 'cd registry/scripts && ./ci-cd-integration.sh deploy'
                }
            }
        }
    }
}
```

#### GitLab CI

```yaml
stages:
  - build
  - scan
  - deploy

variables:
  REGISTRY_TYPE: harbor
  REGISTRY_URL: harbor.medapp.local
  PROJECT_NAME: medapp

build:
  stage: build
  script:
    - cd registry/scripts
    - ./ci-cd-integration.sh build
  artifacts:
    reports:
      junit: build-report.json

security_scan:
  stage: scan
  script:
    - cd registry/scripts
    - ./ci-cd-integration.sh scan
  artifacts:
    reports:
      container_scanning: scan-results.json

deploy:
  stage: deploy
  script:
    - cd registry/scripts
    - ./ci-cd-integration.sh deploy
  only:
    - main
```

## 🔒 Security Best Practices

### 1. Registry Security

- **TLS Encryption**: All registries configured with SSL/TLS
- **Authentication**: HTTP Basic Auth or token-based authentication
- **RBAC**: Role-based access control for Harbor
- **Content Trust**: Image signing and verification
- **Vulnerability Scanning**: Automated security scanning

### 2. Image Security

- **Multi-stage Builds**: Minimize attack surface
- **Non-root Users**: Run containers as non-root
- **Minimal Base Images**: Use distroless or alpine images
- **Security Labels**: OCI-compliant labels for traceability

### 3. Access Control

```bash
# Create registry secret for Kubernetes
kubectl create secret docker-registry medapp-registry-secret \
  --docker-server=harbor.medapp.local \
  --docker-username=medapp \
  --docker-password=medapp123! \
  --namespace=medapp

# Use in pod specification
spec:
  imagePullSecrets:
  - name: medapp-registry-secret
```

## 📊 Monitoring and Maintenance

### Registry Health Monitoring

```bash
# Check registry health
curl -k https://registry.medapp.local:5000/v2/

# Monitor disk usage
./tag-manager.sh stats auth

# Clean up old images
./tag-manager.sh cleanup auth 10
```

### Automated Cleanup Policy

```bash
# Set up automated cleanup (run daily)
# Keep last 30 builds, protect release tags
0 2 * * * /path/to/registry/scripts/tag-manager.sh cleanup auth 30
```

## 🛠️ Advanced Features

### 1. Registry Mirroring

Deploy registry mirrors for improved performance:

```bash
kubectl apply -f configs/registry-mirror.yml
```

### 2. Multi-Registry Support

Build and push to multiple registries simultaneously:

```bash
export REGISTRY_URLS="harbor.medapp.local,registry.medapp.local:5000"
./build-and-push.sh
```

### 3. Image Promotion Pipeline

Promote images through environments:

```bash
# Promote from dev to staging
./tag-manager.sh promote auth dev staging

# Promote from staging to production
./tag-manager.sh promote auth staging prod
```

### 4. Build Cache Optimization

Enable Docker BuildKit for improved build performance:

```bash
export DOCKER_BUILDKIT=1
export BUILDKIT_PROGRESS=plain
./build-and-push.sh
```

## 🔍 Troubleshooting

### Common Issues

1. **Registry Connection Failed**

   ```bash
   # Check registry connectivity
   curl -k https://registry.medapp.local:5000/v2/

   # Check Docker daemon configuration
   cat /etc/docker/daemon.json
   ```

2. **Authentication Failed**

   ```bash
   # Re-login to registry
   docker login registry.medapp.local:5000

   # Check credentials
   cat ~/.docker/config.json
   ```

3. **Image Push Failed**

   ```bash
   # Check disk space
   df -h

   # Check registry logs
   kubectl logs -n registry deployment/registry
   ```

4. **Tag Validation Failed**

   ```bash
   # Validate tag format
   ./tag-manager.sh validate "v1.2.3"

   # List valid tags
   ./tag-manager.sh list auth
   ```

### Debug Mode

Enable debug logging:

```bash
export DEBUG=true
./build-and-push.sh
```

## 📝 Best Practices Summary

1. **Use Semantic Versioning** for release tags
2. **Implement Image Signing** for production
3. **Run Security Scans** in CI/CD pipeline
4. **Clean Up Old Images** regularly
5. **Monitor Registry Health** continuously
6. **Use Immutable Tags** for releases
7. **Implement RBAC** for access control
8. **Enable Audit Logging** for compliance
9. **Use Multi-stage Builds** for smaller images
10. **Test Registry Connectivity** before deployment

## 📚 Additional Resources

- [Docker Registry Documentation](https://docs.docker.com/registry/)
- [Harbor Documentation](https://goharbor.io/docs/)
- [Kubernetes Image Pull Secrets](https://kubernetes.io/docs/tasks/configure-pod-container/pull-image-private-registry/)
- [Container Image Security Best Practices](https://kubernetes.io/docs/concepts/security/pod-security-standards/)

---

**Need Help?** Check the troubleshooting section or review the script comments for detailed usage instructions.

- `v1.2.3` - Semantic version tags
- `commit-abc123f` - Git commit based tags
- `branch-feature-auth` - Branch based tags
- `pr-123` - Pull request based tags
- `dev`, `staging`, `prod` - Environment based tags

## 🚀 Quick Setup

Choose your preferred registry option and follow the corresponding setup guide.
