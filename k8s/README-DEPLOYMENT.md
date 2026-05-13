# Kubernetes Deployment Guide

This guide covers deploying the banking system to Kubernetes via Jenkins or manually.

## Prerequisites

- A running Kubernetes cluster (1.24+)
- `kubectl` configured with access to your cluster
- Docker images built and available (either locally or in a registry)
- NGINX Ingress Controller installed (for ingress routing)
- Helm 3+ for optional Prometheus/Grafana monitoring

## Manual Deployment (Local Testing)

### 1. Verify kubectl connection

```bash
kubectl cluster-info
```

### 2. Apply the base manifests

```bash
# Create the banking namespace and deploy all resources
kubectl apply -k k8s/

# Or if using a specific namespace
kubectl apply -k k8s/ -n banking
```

### 3. Verify deployments

```bash
# Check pod status
kubectl get pods -n banking

# Check services
kubectl get svc -n banking

# Check ingress
kubectl get ingress -n banking
```

### 4. Access the application

```bash
# Forward the frontend port locally
kubectl port-forward -n banking svc/frontend 3000:80

# Then visit http://localhost:3000
```

## Prometheus + Grafana Monitoring

The base `k8s/` deployment does not require Prometheus CRDs. Install monitoring as an add-on after the application is deployed.

### 1. Install kube-prometheus-stack

Current kube-prometheus-stack releases may require Kubernetes 1.25+. If your cluster is 1.24, install an older compatible chart version.

```bash
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update

helm upgrade --install prometheus prometheus-community/kube-prometheus-stack \
  --namespace monitoring \
  --create-namespace \
  --values k8s/monitoring/prometheus-values.yaml
```

This installs Prometheus, Grafana, Alertmanager, kube-state-metrics, and node-exporter.

### 2. Apply banking monitoring resources

```bash
kubectl apply -k k8s/monitoring
```

This creates:

- `ServiceMonitor` for `transaction-service`, `fraud-detection-service`, and `notification-service`
- `PrometheusRule` alerts for pod readiness, restarts, CPU/memory pressure, scrape failures, HTTP 5xxs, and p95 latency
- A Grafana dashboard ConfigMap named `banking-grafana-dashboard`

### 3. Verify Prometheus discovery

```bash
kubectl get servicemonitor,prometheusrule -n banking
kubectl port-forward -n monitoring svc/prometheus-operated 9090:9090
```

Open `http://localhost:9090/targets` and confirm the three banking backend targets are `UP`.

### 4. Open Grafana

```bash
kubectl port-forward -n monitoring svc/prometheus-grafana 3000:80

kubectl get secret -n monitoring prometheus-grafana \
  -o jsonpath="{.data.admin-user}" | base64 -d

kubectl get secret -n monitoring prometheus-grafana \
  -o jsonpath="{.data.admin-password}" | base64 -d
```

Open `http://localhost:3000`, log in with the decoded credentials, then open the `Banking Kubernetes Overview` dashboard. The built-in Kubernetes dashboards from kube-prometheus-stack will also show pod CPU, memory, restarts, deployments, nodes, and cluster health.

## Jenkins-Triggered Deployment

The `Deploy to Kubernetes` stage is available when `DEPLOY_TO_K8S` parameter is set to `true`.

### Build parameters

- `DEPLOY_TO_K8S`: Enable Kubernetes deployment
- `K8S_NAMESPACE`: Target namespace (default: `banking`)
- `K8S_IMAGE_TAG`: Image tag for all services (default: `latest`)

### Example Jenkins trigger

```bash
curl -X POST \
  -u user:token \
  "http://jenkins/job/banking-devsecops-pipeline/buildWithParameters?DEPLOY_TO_K8S=true&K8S_IMAGE_TAG=v1.2.3"
```

## Production Hardening Checklist

- [ ] Replace image names with your private registry
- [ ] Use `ImagePullSecrets` for private registry auth
- [ ] Set appropriate resource requests/limits on all containers
- [ ] Enable Pod Disruption Budgets for high availability
- [ ] Add NetworkPolicies to restrict inter-pod traffic
- [ ] Use persistent volume snapshots for database backups
- [ ] Configure RBAC for service accounts and role bindings
- [ ] Move Vault from dev mode to production setup
- [ ] Add monitoring/alerting (Prometheus/Grafana)
- [ ] Set up log aggregation (ELK/Loki)

## Troubleshooting

### Pods not starting

```bash
# Check pod logs
kubectl logs -n banking -l app=transaction-service --tail=50
kubectl describe pod -n banking <pod-name>
```

### Ingress not routing traffic

Ensure NGINX Ingress Controller is installed:

```bash
kubectl get ingressclass
# Should show 'nginx' class

# If missing, install:
helm repo add ingress-nginx https://kubernetes.github.io/ingress-nginx
helm install ingress-nginx ingress-nginx/ingress-nginx --namespace ingress-nginx --create-namespace
```

### Database initialization issues

```bash
# Check postgres pod logs
kubectl logs -n banking postgres-0

# If data is corrupted, delete the PVC and let it re-initialize
kubectl delete pvc pgdata-postgres-0 -n banking
```

## Cleanup

```bash
# Delete all resources in the namespace
kubectl delete namespace banking

# Or just the deployments
kubectl delete -k k8s/ -n banking
```
