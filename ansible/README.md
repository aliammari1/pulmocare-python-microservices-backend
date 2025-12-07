# MedApp Microservices Automation

An Ansible-based automation system for creating, building, and deploying consistent FastAPI microservices in the MedApp platform.

## 🚀 Features

- **🏗️ Automated Service Creation**: Generate complete FastAPI services with consistent structure
- **🐳 Docker Integration**: Automatic Docker image building with optimized configurations
- **☸️ Kubernetes Deployment**: Standard K8s deployments with health checks, monitoring, and scaling
- **🔍 Service Discovery**: Automatic Consul registration with health checks
- **📊 Observability**: Built-in Prometheus metrics, OpenTelemetry tracing, and structured logging
- **🧪 Testing Framework**: Pre-configured pytest setup with comprehensive test templates
- **🔧 Infrastructure Management**: Automated setup of MongoDB, Redis, RabbitMQ, and monitoring stack

## 📋 Prerequisites

- Ansible 2.9+
- Docker 20.0+
- Kubernetes cluster (local or remote)
- kubectl configured
- Python 3.8+

### Quick Install (Ubuntu/Debian)

```bash
make install-deps
```

## 🏁 Quick Start

### 1. Setup Infrastructure

```bash
# Setup the complete MedApp infrastructure
make setup
```

### 2. Create Your First Service

```bash
# Create a new service
make create-service SERVICE_NAME=notifications

# Or with Ansible directly
cd ansible
ansible-playbook playbooks/create-microservice.yml -e service_name=notifications
```

### 3. Build and Deploy

```bash
# Build, push, and deploy in one command
make full-deploy SERVICE_NAME=notifications

# Or step by step
make build-service SERVICE_NAME=notifications
make push-service SERVICE_NAME=notifications
make deploy-service SERVICE_NAME=notifications
```

### 4. Check Status

```bash
# List all services
make list-services

# Show system status
make status
```

## 📁 Generated Service Structure

Each generated service follows this consistent structure:

```
services/your-service/
├── Dockerfile                 # Optimized Docker configuration
├── requirements.txt           # Python dependencies
├── app/
│   ├── app.py                # Main FastAPI application
│   ├── config.py             # Configuration management
│   ├── models/
│   │   ├── __init__.py
│   │   └── base.py           # Pydantic models
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── health.py         # Health check endpoints
│   │   └── main.py           # Main business routes
│   ├── services/
│   │   └── __init__.py       # Business logic services
│   ├── middleware/
│   │   ├── __init__.py
│   │   ├── logging.py        # Logging configuration
│   │   └── tracing.py        # OpenTelemetry setup
│   ├── .env.development      # Development environment
│   ├── .env.production       # Production environment
│   └── logs/                 # Application logs
├── tests/
│   ├── __init__.py
│   ├── conftest.py           # Test configuration
│   └── test_main.py          # Comprehensive tests
└── k8s/
    └── services/
        └── your-service-service.yaml  # Kubernetes deployment
```

## 🎯 Service Features

Each generated service includes:

### 🔧 Core Features

- **FastAPI Framework**: Modern, fast web framework for APIs
- **Pydantic Models**: Data validation and serialization
- **Async Support**: Full async/await support for high performance
- **Environment Configuration**: Separate dev/prod configurations
- **CORS Support**: Configurable CORS policies

### 📊 Observability

- **Health Checks**: `/health`, `/health/live`, `/health/ready` endpoints
- **Prometheus Metrics**: Request counting, duration tracking
- **OpenTelemetry Tracing**: Distributed tracing with OTLP export
- **Structured Logging**: JSON logging with correlation IDs
- **Service Info**: `/info` endpoint with service metadata

### 🗄️ Data & Messaging

- **MongoDB Integration**: Async MongoDB client with connection pooling
- **Redis Caching**: Optional Redis integration for caching
- **RabbitMQ Messaging**: Message queue integration for async processing
- **Connection Management**: Automatic connection pooling and retry logic

### 🔐 Security & Auth

- **JWT Support**: Token-based authentication
- **Keycloak Integration**: Enterprise identity management
- **Security Headers**: Standard security middleware
- **Input Validation**: Pydantic-based request validation

### ☸️ Kubernetes Ready

- **Health Probes**: Liveness and readiness probes
- **Resource Limits**: CPU and memory constraints
- **Auto Scaling**: Horizontal Pod Autoscaler configuration
- **Service Monitoring**: ServiceMonitor for Prometheus
- **Security Context**: Non-root user, read-only filesystem

## 🛠️ Available Commands

### Makefile Commands

```bash
# Service Management
make create-service SERVICE_NAME=my-service    # Create new service
make build-service SERVICE_NAME=my-service     # Build Docker image
make push-service SERVICE_NAME=my-service      # Push to registry
make deploy-service SERVICE_NAME=my-service    # Deploy to Kubernetes
make full-deploy SERVICE_NAME=my-service       # Build, push, and deploy

# Infrastructure
make setup                                     # Setup infrastructure
make list-services                            # List all services
make status                                   # Show system status

# Maintenance
make remove-service SERVICE_NAME=my-service   # Remove service
make clean-service SERVICE_NAME=my-service    # Completely remove service
make test-service SERVICE_NAME=my-service     # Run tests
make logs-service SERVICE_NAME=my-service     # View logs
make port-forward SERVICE_NAME=my-service     # Port forward for local access

# Utilities
make clean                                    # Clean Docker resources
make install-deps                             # Install dependencies
```

### Ansible Commands

```bash
cd ansible

# Create service with custom options
ansible-playbook playbooks/create-microservice.yml \
  -e service_name=my-service \
  -e service_description="My Custom Service" \
  -e service_port=8090 \
  -e metrics_port=9090

# Build and deploy with options
ansible-playbook playbooks/build-and-deploy.yml \
  -e service_name=my-service \
  -e build_image=true \
  -e push_image=true \
  -e deploy_k8s=true

# Setup infrastructure with custom options
ansible-playbook playbooks/setup-infrastructure.yml \
  -e setup_consul=true \
  -e setup_mongodb=true \
  -e setup_monitoring=true
```

## 📊 Service Registry

All services are tracked in `ansible/vars/services.yml`:

```yaml
services:
  my-service:
    name: "my-service"
    description: "My Custom Service"
    port: 8090
    metrics_port: 9090
    tags: ["api", "my-service"]
    created: "2025-01-01T10:00:00Z"
```

## 🔧 Configuration

### Environment Variables

Each service supports these environment variables:

```bash
# Service Configuration
ENV=production
HOST=0.0.0.0
PORT=8080
METRICS_PORT=9080

# Database
MONGODB_HOST=mongodb
MONGODB_PORT=27017
MONGODB_USERNAME=admin
MONGODB_PASSWORD=password

# Cache
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_PASSWORD=password

# Message Queue
RABBITMQ_HOST=rabbitmq
RABBITMQ_PORT=5672
RABBITMQ_USERNAME=admin
RABBITMQ_PASSWORD=password

# Service Discovery
CONSUL_HOST=consul
CONSUL_PORT=8500

# Observability
OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318
ENABLE_METRICS=true
ENABLE_TRACING=true
```

### Customization

You can customize the templates in `ansible/templates/`:

- `fastapi/`: FastAPI application templates
- `docker/`: Docker-related templates
- `kubernetes/`: Kubernetes deployment templates
- `consul/`: Consul service registration templates

## 📋 Playbook Reference

### `create-microservice.yml`

Creates a new microservice with complete structure.

**Parameters:**

- `service_name` (required): Name of the service
- `service_description`: Service description
- `service_port`: HTTP port (default: auto-assigned)
- `metrics_port`: Metrics port (default: auto-assigned)
- `service_tags`: List of tags

### `build-and-deploy.yml`

Builds Docker image and deploys to Kubernetes.

**Parameters:**

- `service_name` (required): Name of the service
- `build_image`: Build Docker image (default: true)
- `push_image`: Push to registry (default: false)
- `deploy_k8s`: Deploy to Kubernetes (default: true)
- `register_consul`: Register with Consul (default: true)

### `setup-infrastructure.yml`

Sets up the complete infrastructure stack.

**Parameters:**

- `setup_consul`: Deploy Consul (default: true)
- `setup_mongodb`: Deploy MongoDB (default: true)
- `setup_redis`: Deploy Redis (default: true)
- `setup_rabbitmq`: Deploy RabbitMQ (default: true)
- `setup_monitoring`: Deploy monitoring stack (default: true)

## 🧪 Testing

Each service includes comprehensive tests:

```bash
# Run tests for a specific service
make test-service SERVICE_NAME=my-service

# Run tests manually
cd services/my-service
python -m pytest tests/ -v --cov=app
```

Test categories:

- **Health checks**: Liveness, readiness, and health endpoints
- **CRUD operations**: Create, read, update, delete functionality
- **Pagination**: List endpoints with pagination
- **Search**: Filtering and search functionality
- **Error handling**: Invalid input and error scenarios
- **Metrics**: Prometheus metrics endpoint

## 📈 Monitoring

### Prometheus Metrics

Each service exposes metrics at `/metrics`:

- `http_requests_total`: Total HTTP requests
- `http_request_duration_seconds`: Request duration histogram

### OpenTelemetry Tracing

Distributed tracing with automatic instrumentation for:

- HTTP requests
- Database operations
- External service calls

### Health Checks

Three health check endpoints:

- `/api/v1/health`: Overall health with dependency checks
- `/api/v1/health/live`: Kubernetes liveness probe
- `/api/v1/health/ready`: Kubernetes readiness probe

## 🚀 Production Deployment

### 1. Configure Registry

Update `ansible/inventory.yml`:

```yaml
docker_registry: "your-registry.com"
```

### 2. Setup Secrets

```bash
# Create production secrets
kubectl create secret generic mongodb-secret \
  --from-literal=username=$MONGO_USER \
  --from-literal=password=$MONGO_PASS \
  -n medapp
```

### 3. Deploy Services

```bash
# Deploy all infrastructure
make setup

# Create and deploy your services
make create-service SERVICE_NAME=users
make full-deploy SERVICE_NAME=users
```

## 🔍 Troubleshooting

### Common Issues

**Service won't start:**

```bash
# Check logs
make logs-service SERVICE_NAME=my-service

# Check pod status
kubectl describe pod -l app=my-service-service -n medapp
```

**Database connection issues:**

```bash
# Check if MongoDB is running
kubectl get pods -l app=mongodb -n medapp

# Test connection
kubectl exec -it deployment/my-service-service -n medapp -- curl localhost:8080/api/v1/health
```

**Port conflicts:**

```bash
# Check port allocation
make list-services

# Update service port in ansible/vars/services.yml if needed
```

## 📝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes to the templates
4. Test with a new service creation
5. Submit a pull request

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🤝 Support

For issues and questions:

1. Check the troubleshooting section
2. Review the logs with `make logs-service SERVICE_NAME=your-service`
3. Create an issue in the repository

---

**Happy microservice building! 🎉**
