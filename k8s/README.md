# MedApp Kubernetes Migration Guide

## 🚀 From Docker Compose to Kubernetes

This guide explains how to migrate your MedApp from Docker Compose to Kubernetes and provides a comprehensive introduction to Kubernetes concepts.

## 📚 Kubernetes Fundamentals

### What is Kubernetes?

Kubernetes (K8s) is a container orchestration platform that automates deployment, scaling, and management of containerized applications. Think of it as a "cluster operating system" that manages containers across multiple machines.

### Key Differences from Docker Compose

| Aspect                | Docker Compose  | Kubernetes                  |
| --------------------- | --------------- | --------------------------- |
| **Scope**             | Single machine  | Multiple machines (cluster) |
| **Scaling**           | Manual          | Automatic                   |
| **High Availability** | Limited         | Built-in                    |
| **Service Discovery** | Built-in        | More advanced               |
| **Load Balancing**    | Basic           | Advanced                    |
| **Storage**           | Local volumes   | Persistent volumes          |
| **Networking**        | Bridge networks | Complex networking          |

### Core Kubernetes Concepts

#### 1. **Cluster Architecture**

```
┌─────────────────────────────────────────────┐
│                 Cluster                     │
│  ┌─────────────┐  ┌─────────────────────┐  │
│  │ Master Node │  │    Worker Nodes     │  │
│  │             │  │  ┌─────┐ ┌─────┐    │  │
│  │ API Server  │  │  │ Pod │ │ Pod │    │  │
│  │ etcd        │  │  └─────┘ └─────┘    │  │
│  │ Scheduler   │  │                     │  │
│  │ Controller  │  │  ┌─────┐ ┌─────┐    │  │
│  └─────────────┘  │  │ Pod │ │ Pod │    │  │
│                   │  └─────┘ └─────┘    │  │
│                   └─────────────────────┘  │
└─────────────────────────────────────────────┘
```

#### 2. **Resource Types**

**Namespace**: Virtual clusters within a physical cluster

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: medapp
```

**Pod**: The smallest deployable unit (usually one container)

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: my-pod
spec:
  containers:
    - name: my-container
      image: nginx
```

**Deployment**: Manages replica sets and rolling updates

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: my-app
spec:
  replicas: 3
  selector:
    matchLabels:
      app: my-app
  template:
    metadata:
      labels:
        app: my-app
    spec:
      containers:
        - name: my-app
          image: my-app:latest
```

**Service**: Provides networking for pods

```yaml
apiVersion: v1
kind: Service
metadata:
  name: my-service
spec:
  selector:
    app: my-app
  ports:
    - port: 80
      targetPort: 8080
```

**ConfigMap**: Stores configuration data

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: my-config
data:
  database_url: "mongodb://mongodb:27017"
```

**Secret**: Stores sensitive data

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: my-secret
type: Opaque
data:
  password: cGFzc3dvcmQ= # base64 encoded
```

## 🏗️ Migration Architecture

### Docker Compose vs Kubernetes Mapping

| Docker Compose | Kubernetes Equivalent                        |
| -------------- | -------------------------------------------- |
| `service`      | `Deployment` + `Service`                     |
| `volumes`      | `PersistentVolume` + `PersistentVolumeClaim` |
| `networks`     | `Service` networking                         |
| `environment`  | `ConfigMap` + `Secret`                       |
| `depends_on`   | `initContainer` or startup probes            |
| `ports`        | `Service` ports                              |
| `restart`      | `restartPolicy`                              |

### MedApp Architecture in Kubernetes

```
┌─────────────────────────────────────────────────────────┐
│                    Ingress Controller                   │
│              (External Traffic Entry)                   │
└─────────────────┬───────────────────────────────────────┘
                  │
┌─────────────────▼───────────────────────────────────────┐
│                  API Gateway (APISIX)                   │
│              (Internal Routing & Auth)                  │
└─────┬─────┬─────┬─────┬─────┬─────┬─────┬─────┬─────────┘
      │     │     │     │     │     │     │     │
      ▼     ▼     ▼     ▼     ▼     ▼     ▼     ▼
   ┌──────┐ ┌────┐ ┌────┐ ┌────┐ ┌────┐ ┌────┐ ┌────┐ ┌────┐
   │ Auth │ │Med │ │Pat │ │Ord │ │Rad │ │Rep │ │App │ │File│
   │ Svc  │ │Svc │ │Svc │ │Svc │ │Svc │ │Svc │ │Svc │ │Svc │
   └──┬───┘ └─┬──┘ └─┬──┘ └─┬──┘ └─┬──┘ └─┬──┘ └─┬──┘ └─┬──┘
      │       │      │      │      │      │      │      │
      └───────┼──────┼──────┼──────┼──────┼──────┼──────┘
              │      │      │      │      │      │
              ▼      ▼      ▼      ▼      ▼      ▼
        ┌─────────────────────────────────────────────┐
        │          Shared Infrastructure              │
        │  ┌────────┐ ┌────────┐ ┌────────────────┐  │
        │  │MongoDB │ │ Redis  │ │    RabbitMQ    │  │
        │  └────────┘ └────────┘ └────────────────┘  │
        │  ┌────────┐ ┌────────┐ ┌────────────────┐  │
        │  │ MinIO  │ │ Vault  │ │   Keycloak     │  │
        │  └────────┘ └────────┘ └────────────────┘  │
        └─────────────────────────────────────────────┘
```

## 📁 Project Structure

```
k8s/
├── namespace.yaml              # Namespace definitions
├── configmap.yaml             # Application configuration
├── secrets.yaml               # Sensitive data
├── ingress.yaml               # External access rules
├── deploy.sh                  # Deployment script
├── cleanup.sh                 # Cleanup script
├── build-images.sh           # Docker image build script
├── infrastructure/           # Infrastructure components
│   ├── mongodb.yaml
│   ├── redis.yaml
│   ├── postgres.yaml
│   ├── rabbitmq.yaml
│   ├── etcd.yaml
│   ├── consul.yaml
│   ├── minio.yaml
│   ├── vault.yaml
│   ├── keycloak.yaml
│   └── apisix.yaml
├── services/                 # Microservices
│   ├── auth-service.yaml
│   ├── medecins-service.yaml
│   ├── patients-service.yaml
│   ├── ordonnances-service.yaml
│   ├── radiologues-service.yaml
│   ├── reports-service.yaml
│   ├── appointments-service.yaml
│   └── medfiles-service.yaml
└── monitoring/              # Monitoring stack
    ├── prometheus.yaml
    ├── grafana.yaml
    ├── tempo.yaml
    ├── loki.yaml
    └── otel-collector.yaml
```

## 🚀 Deployment Steps

### Prerequisites

1. **Kubernetes Cluster**: You need a running Kubernetes cluster

   - **Local Development**: minikube, kind, or Docker Desktop
   - **Cloud**: AKS, EKS, GKE
   - **On-Premise**: kubeadm, k3s, or enterprise distributions

2. **kubectl**: Kubernetes command-line tool

   ```bash
   # Install kubectl
   curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
   chmod +x kubectl
   sudo mv kubectl /usr/local/bin/
   ```

3. **Docker Registry**: For storing your application images
   - Docker Hub
   - Azure Container Registry (ACR)
   - Amazon ECR
   - Google Container Registry (GCR)
   - Private registry

### Step 1: Prepare Docker Images

1. **Update the build script**:

   ```bash
   # Edit k8s/build-images.sh
   REGISTRY="your-registry.com"  # Change this
   ```

2. **Build and push images**:

   ```bash
   cd k8s
   ./build-images.sh
   ```

3. **Update Kubernetes manifests**:
   - Replace `your-registry/medapp-*:latest` with your actual image URLs
   - Update all service YAML files in `k8s/services/`

### Step 2: Configure Cluster Access

```bash
# Verify cluster access
kubectl cluster-info

# Check nodes
kubectl get nodes

# Create kubeconfig if needed
kubectl config set-cluster my-cluster --server=https://your-cluster-endpoint
kubectl config set-credentials my-user --token=your-token
kubectl config set-context my-context --cluster=my-cluster --user=my-user
kubectl config use-context my-context
```

### Step 3: Deploy the Application

```bash
cd k8s
./deploy.sh
```

This script will:

1. Create namespaces
2. Apply configuration and secrets
3. Deploy infrastructure components
4. Deploy monitoring stack
5. Deploy API gateway
6. Deploy microservices
7. Configure ingress

### Step 4: Verify Deployment

```bash
# Check all pods
kubectl get pods -n medapp
kubectl get pods -n medapp-monitoring

# Check services
kubectl get services -n medapp

# Check ingress
kubectl get ingress -n medapp

# View logs
kubectl logs -n medapp deployment/auth-service

# Get pod details
kubectl describe pod -n medapp <pod-name>
```

## 🔧 Configuration Management

### Environment Variables

In Docker Compose:

```yaml
environment:
  - DATABASE_URL=mongodb://mongodb:27017
  - REDIS_URL=redis://redis:6379
```

In Kubernetes:

```yaml
env:
  - name: DATABASE_URL
    valueFrom:
      configMapKeyRef:
        name: medapp-config
        key: MONGODB_URI
  - name: REDIS_PASSWORD
    valueFrom:
      secretKeyRef:
        name: medapp-secrets
        key: REDIS_PASSWORD
```

### Secrets Management

**Create secrets securely**:

```bash
# Create secret from literal
kubectl create secret generic my-secret --from-literal=password=mypassword

# Create secret from file
kubectl create secret generic my-secret --from-file=config.json

# Use external secret management (recommended for production)
# - HashiCorp Vault
# - Azure Key Vault
# - AWS Secrets Manager
# - Google Secret Manager
```

## 📊 Monitoring and Observability

### Monitoring Stack Components

1. **Prometheus**: Metrics collection and alerting
2. **Grafana**: Visualization and dashboards
3. **Tempo**: Distributed tracing
4. **Loki**: Log aggregation
5. **OpenTelemetry Collector**: Telemetry data processing

### Access Monitoring

```bash
# Port-forward to access services locally
kubectl port-forward -n medapp-monitoring svc/grafana-service 3000:3000
kubectl port-forward -n medapp-monitoring svc/prometheus-service 9090:9090

# Or use ingress (update /etc/hosts)
echo "127.0.0.1 grafana.medapp.local prometheus.medapp.local" >> /etc/hosts
```

## 🔒 Security Considerations

### Network Policies

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: deny-all
  namespace: medapp
spec:
  podSelector: {}
  policyTypes:
    - Ingress
    - Egress
```

### Pod Security Standards

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: secure-pod
spec:
  securityContext:
    runAsNonRoot: true
    runAsUser: 1000
    fsGroup: 2000
  containers:
    - name: app
      image: my-app
      securityContext:
        allowPrivilegeEscalation: false
        readOnlyRootFilesystem: true
        capabilities:
          drop:
            - ALL
```

### RBAC (Role-Based Access Control)

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  namespace: medapp
  name: medapp-reader
rules:
  - apiGroups: [""]
    resources: ["pods", "services"]
    verbs: ["get", "list", "watch"]
```

## 📈 Scaling and Performance

### Horizontal Pod Autoscaler

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: auth-service-hpa
  namespace: medapp
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: auth-service
  minReplicas: 2
  maxReplicas: 10
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 70
```

### Resource Management

```yaml
resources:
  requests:
    memory: "256Mi"
    cpu: "250m"
  limits:
    memory: "512Mi"
    cpu: "500m"
```

## 🚦 Health Checks

### Liveness and Readiness Probes

```yaml
livenessProbe:
  httpGet:
    path: /health
    port: 8080
  initialDelaySeconds: 30
  periodSeconds: 10

readinessProbe:
  httpGet:
    path: /ready
    port: 8080
  initialDelaySeconds: 5
  periodSeconds: 5
```

## 🔄 Rolling Updates and Rollbacks

### Rolling Update Strategy

```yaml
spec:
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxUnavailable: 1
      maxSurge: 1
```

### Deployment Commands

```bash
# Update deployment
kubectl set image deployment/auth-service auth-service=my-registry/auth:v2 -n medapp

# Check rollout status
kubectl rollout status deployment/auth-service -n medapp

# Rollback to previous version
kubectl rollout undo deployment/auth-service -n medapp

# View rollout history
kubectl rollout history deployment/auth-service -n medapp
```

## 💾 Storage Management

### Persistent Volumes

```yaml
apiVersion: v1
kind: PersistentVolume
metadata:
  name: mongodb-pv
spec:
  capacity:
    storage: 10Gi
  accessModes:
    - ReadWriteOnce
  persistentVolumeReclaimPolicy: Retain
  storageClassName: fast-ssd
  hostPath:
    path: /data/mongodb
```

### Storage Classes

```yaml
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: fast-ssd
provisioner: kubernetes.io/aws-ebs
parameters:
  type: gp3
  fsType: ext4
allowVolumeExpansion: true
```

## 🔧 Troubleshooting

### Common Issues and Solutions

1. **Pods stuck in Pending state**:

   ```bash
   kubectl describe pod <pod-name> -n medapp
   # Check for resource constraints or scheduling issues
   ```

2. **Image pull errors**:

   ```bash
   # Check image name and registry access
   kubectl get events -n medapp --sort-by='.lastTimestamp'
   ```

3. **Service connectivity issues**:

   ```bash
   # Test service connectivity
   kubectl exec -it <pod-name> -n medapp -- curl http://service-name:port
   ```

4. **Configuration issues**:
   ```bash
   # Check ConfigMaps and Secrets
   kubectl get configmap -n medapp
   kubectl get secrets -n medapp
   ```

### Useful Commands

```bash
# Get all resources in namespace
kubectl get all -n medapp

# View resource usage
kubectl top pods -n medapp
kubectl top nodes

# Access pod shell
kubectl exec -it <pod-name> -n medapp -- /bin/bash

# Copy files to/from pod
kubectl cp local-file pod-name:/path/to/file -n medapp

# Port forwarding
kubectl port-forward -n medapp svc/service-name 8080:80

# View cluster events
kubectl get events --sort-by='.lastTimestamp' -n medapp
```

## 🔗 Next Steps

1. **Production Readiness**:

   - Implement proper RBAC
   - Set up network policies
   - Configure backup strategies
   - Implement monitoring and alerting

2. **CI/CD Integration**:

   - Set up automated deployments
   - Implement GitOps with ArgoCD or Flux
   - Add quality gates and testing

3. **Advanced Features**:

   - Service mesh (Istio/Linkerd)
   - Advanced networking (Calico/Cilium)
   - Policy engines (OPA Gatekeeper)
   - Multi-cluster deployments

4. **Cost Optimization**:
   - Right-size resources
   - Implement cluster autoscaling
   - Use spot instances
   - Implement resource quotas

## 📚 Additional Resources

- [Kubernetes Documentation](https://kubernetes.io/docs/)
- [Kubernetes Best Practices](https://kubernetes.io/docs/concepts/configuration/overview/)
- [CNCF Landscape](https://landscape.cncf.io/)
- [Kubernetes Patterns](https://k8spatterns.io/)
- [Troubleshooting Guide](https://kubernetes.io/docs/tasks/debug-application-cluster/)

This migration provides a solid foundation for running your MedApp on Kubernetes with improved scalability, reliability, and operational capabilities.
