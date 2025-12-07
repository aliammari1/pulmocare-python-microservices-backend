# MedApp Kubernetes Quick Start Guide

## 🚀 Quick Deployment (5 Minutes)

### Prerequisites Checklist

- [ ] Kubernetes cluster running (minikube, kind, or cloud)
- [ ] kubectl installed and configured
- [ ] Docker installed (for building images)
- [ ] Access to a Docker registry

### Step 1: Clone and Navigate

```bash
cd /home/azureuser/medapp-backend/k8s
```

### Step 2: Configure Registry (IMPORTANT!)

Edit the image references in all service files:

```bash
# Replace 'your-registry' with your actual registry
find services/ -name "*.yaml" -exec sed -i 's/your-registry/your-actual-registry.com/g' {} +
```

### Step 3: Build and Push Images (Optional - Skip if using pre-built images)

```bash
# Update registry URL in build script
vim build-images.sh  # Change REGISTRY variable

# Build and push
./build-images.sh
```

### Step 4: Deploy Everything

```bash
./deploy.sh
```

### Step 5: Check Status

```bash
# Check pods
kubectl get pods -n medapp
kubectl get pods -n medapp-monitoring

# Check services
kubectl get svc -n medapp

# Check ingress
kubectl get ingress -n medapp
```

### Step 6: Access Applications

**Option A: Port Forwarding (Immediate Access)**

```bash
# API Gateway
kubectl port-forward -n medapp svc/apisix-service 9080:9080 &

# Keycloak
kubectl port-forward -n medapp svc/keycloak-service 8080:8080 &

# Grafana
kubectl port-forward -n medapp-monitoring svc/grafana-service 3000:3000 &

# Access at:
# API: http://localhost:9080
# Auth: http://localhost:8080
# Monitoring: http://localhost:3000
```

**Option B: Ingress (Domain Access)**

```bash
# Add to /etc/hosts
echo "127.0.0.1 api.medapp.local auth.medapp.local grafana.medapp.local" | sudo tee -a /etc/hosts

# Access at:
# API: http://api.medapp.local
# Auth: http://auth.medapp.local
# Monitoring: http://grafana.medapp.local
```

## 🔧 Common Issues & Solutions

### Issue: Pods stuck in "Pending"

```bash
kubectl describe pod -n medapp <pod-name>
# Usually: insufficient resources or storage issues
```

### Issue: "ImagePullBackOff"

```bash
# Check image names and registry access
kubectl get events -n medapp --sort-by='.lastTimestamp'
```

### Issue: Services not accessible

```bash
# Check service endpoints
kubectl get endpoints -n medapp
```

## 🧹 Clean Up

```bash
./cleanup.sh
```

## 📊 Monitoring Access

Default credentials:

- **Grafana**: admin/admin
- **Keycloak**: admin/admin

## 🎯 What's Deployed

### Core Services (medapp namespace)

- Authentication Service (Port 8086)
- Doctors Service (Port 8081)
- Patients Service (Port 8083)
- Prescriptions Service (Port 8082)
- Radiologists Service (Port 8084)
- Reports Service (Port 8085)
- Appointments Service (Port 8087)
- Medical Files Service (Port 8088)

### Infrastructure (medapp namespace)

- MongoDB (Database)
- Redis (Cache)
- RabbitMQ (Message Queue)
- PostgreSQL (Keycloak DB)
- MinIO (Object Storage)
- Keycloak (Identity Management)
- APISIX (API Gateway)
- Consul (Service Discovery)
- Vault (Secrets Management)

### Monitoring (medapp-monitoring namespace)

- Prometheus (Metrics)
- Grafana (Dashboards)
- Tempo (Tracing)
- Loki (Logs)
- OpenTelemetry Collector

## 📝 Next Steps

1. **Configure DNS or use port-forwarding for access**
2. **Update default passwords in production**
3. **Configure proper TLS certificates**
4. **Set up backup strategies**
5. **Implement CI/CD pipelines**

## 🆘 Need Help?

```bash
# Check everything
kubectl get all -n medapp
kubectl get all -n medapp-monitoring

# View logs
kubectl logs -n medapp deployment/auth-service

# Get into a pod
kubectl exec -it -n medapp deployment/auth-service -- bash
```

## 🔗 Useful Commands

```bash
# Scale a service
kubectl scale deployment auth-service --replicas=3 -n medapp

# Update an image
kubectl set image deployment/auth-service auth-service=new-image:tag -n medapp

# Restart a deployment
kubectl rollout restart deployment/auth-service -n medapp

# View resource usage
kubectl top pods -n medapp
```

Happy Kubernetes journey! 🎉
