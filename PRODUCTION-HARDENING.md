# Production Hardening Guide

Complete step-by-step instructions to move from scaffold to production-ready Kubernetes deployment.

---

## Step 1: Replace Placeholder Image Names with Your Registry

### Goal
Push images to a container registry (Docker Hub, ECR, GCR, etc.) and reference them in Kubernetes manifests.

### Implementation

**1a. Configure registry credentials in Jenkins**

1. Navigate to Jenkins → Manage Credentials → System
2. Add new credential type: `Username with password`
   - Username: `your-registry-user`
   - Password: `your-registry-token`
   - ID: `registry-creds`
3. Save

**1b. Update Jenkinsfile to push to registry**

In the `Push to Docker Hub` stage, tag and push images:

```groovy
stage('Push to Registry') {
  when {
    expression { return params.PUSH_IMAGES }
  }
  steps {
    withCredentials([usernamePassword(credentialsId: 'registry-creds', usernameVariable: 'REG_USER', passwordVariable: 'REG_PASS')]) {
      sh '''
        set -e
        REGISTRY="${REGISTRY_ENDPOINT}"  # e.g., docker.io, gcr.io, ecr-url
        
        echo "$REG_PASS" | docker login -u "$REG_USER" --password-stdin "$REGISTRY"
        
        docker tag banking-devsecops-transaction-service:latest "$REGISTRY/banking/transaction-service:${BUILD_NUMBER}"
        docker tag banking-devsecops-fraud-detection-service:latest "$REGISTRY/banking/fraud-detection-service:${BUILD_NUMBER}"
        docker tag banking-devsecops-notification-service:latest "$REGISTRY/banking/notification-service:${BUILD_NUMBER}"
        docker tag banking-devsecops-frontend:latest "$REGISTRY/banking/frontend:${BUILD_NUMBER}"
        
        docker push "$REGISTRY/banking/transaction-service:${BUILD_NUMBER}"
        docker push "$REGISTRY/banking/fraud-detection-service:${BUILD_NUMBER}"
        docker push "$REGISTRY/banking/notification-service:${BUILD_NUMBER}"
        docker push "$REGISTRY/banking/frontend:${BUILD_NUMBER}"
        
        docker logout "$REGISTRY"
      '''
    }
  }
}
```

**1c. Create kustomization overlay for production**

```bash
mkdir -p k8s/overlays/production
```

Create `k8s/overlays/production/kustomization.yaml`:

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

namespace: banking-prod

bases:
  - ../../

namePrefix: prod-

images:
  - name: banking-transaction-service
    newName: your-registry.com/banking/transaction-service
    newTag: v1.0.0
  - name: banking-fraud-detection-service
    newName: your-registry.com/banking/fraud-detection-service
    newTag: v1.0.0
  - name: banking-notification-service
    newName: your-registry.com/banking/notification-service
    newTag: v1.0.0
  - name: banking-frontend
    newName: your-registry.com/banking/frontend
    newTag: v1.0.0

patchesStrategicMerge:
  - image-pull-secrets.yaml
```

Create `k8s/overlays/production/image-pull-secrets.yaml`:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: transaction-service
spec:
  template:
    spec:
      imagePullSecrets:
        - name: registry-credentials
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: fraud-detection-service
spec:
  template:
    spec:
      imagePullSecrets:
        - name: registry-credentials
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: notification-service
spec:
  template:
    spec:
      imagePullSecrets:
        - name: registry-credentials
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: frontend
spec:
  template:
    spec:
      imagePullSecrets:
        - name: registry-credentials
```

**1d. Create registry secret in cluster**

```bash
kubectl create secret docker-registry registry-credentials \
  --docker-server=your-registry.com \
  --docker-username=your-user \
  --docker-password=your-token \
  --docker-email=your-email@example.com \
  -n banking-prod
```

**1e. Deploy using registry overlay**

```bash
kubectl apply -k k8s/overlays/production
```

---

## Step 2: Migrate Vault from Dev to Production Setup

### Goal
Move from Vault dev mode to a production-hardened, HA-ready setup.

### Implementation

**2a. Install Vault Helm chart**

```bash
helm repo add hashicorp https://helm.releases.hashicorp.com
helm repo update

helm install vault hashicorp/vault \
  --namespace vault \
  --create-namespace \
  --values vault-values.yaml
```

Create `vault-values.yaml`:

```yaml
server:
  dataStorage:
    size: 10Gi
  resources:
    requests:
      memory: "256Mi"
      cpu: "250m"
    limits:
      memory: "512Mi"
      cpu: "500m"
  ha:
    enabled: true
    replicas: 3
  serviceAccount:
    create: true
    name: vault
  storage:
    type: file
    file:
      path: /vault/data

ui:
  enabled: true

injector:
  enabled: true
```

**2b. Unseal and initialize production Vault**

```bash
# Port-forward to Vault
kubectl port-forward -n vault svc/vault 8200:8200 &

# Initialize Vault (generates root token + unseal keys)
vault operator init \
  -key-shares=5 \
  -key-threshold=3 \
  -format=json > vault-init.json

# Unseal (requires 3 of 5 keys)
export VAULT_ADDR=http://127.0.0.1:8200
UNSEAL_KEY=$(jq -r '.unseal_keys_b64[0]' vault-init.json)
vault operator unseal "$UNSEAL_KEY"
# Repeat 2 more times with different keys

# Log in with root token
VAULT_TOKEN=$(jq -r '.root_token' vault-init.json)
export VAULT_TOKEN
vault status
```

**⚠️ CRITICAL: Store `vault-init.json` securely (encrypted backup, not in git)**

**2c. Enable and configure KV secrets engine**

```bash
vault secrets enable -path=secret kv-v2

# Create banking secrets
vault kv put secret/banking/transaction-service \
  DB_HOST=postgres.banking-prod.svc.cluster.local \
  DB_PORT=5432 \
  DB_NAME=banking \
  DB_USER=banking_user \
  DB_PASSWORD="$(openssl rand -base64 32)" \
  JWT_SECRET_KEY="$(openssl rand -base64 64)"

vault kv put secret/banking/fraud-detection-service \
  JWT_SECRET_KEY="$(openssl rand -base64 64)"

vault kv put secret/banking/notification-service \
  DB_HOST=postgres.banking-prod.svc.cluster.local \
  DB_PORT=5432 \
  DB_NAME=banking \
  DB_USER=banking_user \
  DB_PASSWORD="$(openssl rand -base64 32)" \
  JWT_SECRET_KEY="$(openssl rand -base64 64)" \
  SMTP_HOST="smtp.gmail.com" \
  SMTP_PORT="587" \
  SMTP_USER="alerts@company.com" \
  SMTP_PASSWORD="your-app-password"
```

**2d. Configure Kubernetes authentication**

```bash
# Enable Kubernetes auth
vault auth enable kubernetes

# Configure Kubernetes auth method
vault write auth/kubernetes/config \
  kubernetes_host="https://$KUBERNETES_SERVICE_HOST:$KUBERNETES_SERVICE_PORT" \
  kubernetes_ca_cert=@/var/run/secrets/kubernetes.io/serviceaccount/ca.crt \
  token_reviewer_jwt=@/var/run/secrets/kubernetes.io/serviceaccount/token

# Create policies for each service
vault policy write banking-transaction - <<EOF
path "secret/data/banking/transaction-service" {
  capabilities = ["read"]
}
EOF

vault policy write banking-fraud - <<EOF
path "secret/data/banking/fraud-detection-service" {
  capabilities = ["read"]
}
EOF

vault policy write banking-notification - <<EOF
path "secret/data/banking/notification-service" {
  capabilities = ["read"]
}
EOF

# Create Kubernetes auth roles
vault write auth/kubernetes/role/banking-transaction \
  bound_service_account_names=transaction-service \
  bound_service_account_namespaces=banking-prod \
  policies=banking-transaction \
  ttl=1h

vault write auth/kubernetes/role/banking-fraud \
  bound_service_account_names=fraud-detection-service \
  bound_service_account_namespaces=banking-prod \
  policies=banking-fraud \
  ttl=1h

vault write auth/kubernetes/role/banking-notification \
  bound_service_account_names=notification-service \
  bound_service_account_namespaces=banking-prod \
  policies=banking-notification \
  ttl=1h
```

**2e. Update Kubernetes manifests to use production Vault**

Create `k8s/overlays/production/vault-integration.yaml`:

```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: transaction-service
---
apiVersion: v1
kind: ServiceAccount
metadata:
  name: fraud-detection-service
---
apiVersion: v1
kind: ServiceAccount
metadata:
  name: notification-service
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: transaction-service
spec:
  template:
    metadata:
      annotations:
        vault.hashicorp.com/agent-inject: "true"
        vault.hashicorp.com/agent-inject-secret-banking: "secret/data/banking/transaction-service"
        vault.hashicorp.com/agent-inject-template-banking: |
          {{- with secret "secret/data/banking/transaction-service" -}}
          export DB_HOST="{{ .Data.data.DB_HOST }}"
          export DB_PORT="{{ .Data.data.DB_PORT }}"
          export DB_NAME="{{ .Data.data.DB_NAME }}"
          export DB_USER="{{ .Data.data.DB_USER }}"
          export DB_PASSWORD="{{ .Data.data.DB_PASSWORD }}"
          export JWT_SECRET_KEY="{{ .Data.data.JWT_SECRET_KEY }}"
          {{- end }}
        vault.hashicorp.com/role: "banking-transaction"
    spec:
      serviceAccountName: transaction-service
```

---

## Step 3: Add Resource Limits/Requests and Autoscaling

### Goal
Ensure fair resource allocation and automatic scaling under load.

### Implementation

**3a. Create resource-limited deployment overlay**

Create `k8s/overlays/production/resources.yaml`:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: transaction-service
spec:
  replicas: 3
  template:
    spec:
      containers:
        - name: transaction-service
          resources:
            requests:
              memory: "256Mi"
              cpu: "250m"
            limits:
              memory: "512Mi"
              cpu: "500m"
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: fraud-detection-service
spec:
  replicas: 2
  template:
    spec:
      containers:
        - name: fraud-detection-service
          resources:
            requests:
              memory: "128Mi"
              cpu: "100m"
            limits:
              memory: "256Mi"
              cpu: "200m"
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: notification-service
spec:
  replicas: 2
  template:
    spec:
      containers:
        - name: notification-service
          resources:
            requests:
              memory: "256Mi"
              cpu: "250m"
            limits:
              memory: "512Mi"
              cpu: "500m"
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: frontend
spec:
  replicas: 2
  template:
    spec:
      containers:
        - name: frontend
          resources:
            requests:
              memory: "64Mi"
              cpu: "100m"
            limits:
              memory: "256Mi"
              cpu: "200m"
---
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: postgres
spec:
  template:
    spec:
      containers:
        - name: postgres
          resources:
            requests:
              memory: "512Mi"
              cpu: "500m"
            limits:
              memory: "1Gi"
              cpu: "1000m"
```

**3b. Set up HorizontalPodAutoscaler**

Create `k8s/overlays/production/autoscaling.yaml`:

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: transaction-service-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: transaction-service
  minReplicas: 3
  maxReplicas: 10
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 70
    - type: Resource
      resource:
        name: memory
        target:
          type: Utilization
          averageUtilization: 80
---
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: fraud-detection-service-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: fraud-detection-service
  minReplicas: 2
  maxReplicas: 8
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 75
---
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: notification-service-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: notification-service
  minReplicas: 2
  maxReplicas: 6
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 70
```

**3c. Verify metrics are available**

```bash
# Requires metrics-server installed
kubectl get deployment metrics-server -n kube-system

# If not present, install it:
kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml

# Check HPA status
kubectl get hpa -n banking-prod
kubectl describe hpa transaction-service-hpa -n banking-prod
```

---

## Step 4: Set Up Monitoring (Prometheus + Grafana)

### Goal
Collect metrics and visualize system health and performance.

### Implementation

**4a. Install Prometheus Operator**

```bash
# Add Prometheus Helm repo
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update

# Install kube-prometheus-stack (includes Prometheus, Grafana, AlertManager)
helm install prometheus prometheus-community/kube-prometheus-stack \
  --namespace monitoring \
  --create-namespace \
  --values prometheus-values.yaml
```

Create `prometheus-values.yaml`:

```yaml
prometheus:
  prometheusSpec:
    retention: 30d
    resources:
      requests:
        memory: "512Mi"
        cpu: "500m"
      limits:
        memory: "1Gi"
        cpu: "1000m"
    serviceMonitorSelectorNilUsesHelmValues: false

grafana:
  adminPassword: "your-secure-password"
  persistence:
    enabled: true
    size: 10Gi
  datasources:
    datasources.yaml:
      apiVersion: 1
      datasources:
        - name: Prometheus
          type: prometheus
          url: http://prometheus-operated:9090
          isDefault: true

alertmanager:
  enabled: true
  alertmanagerSpec:
    storage:
      volumeClaimTemplate:
        spec:
          resources:
            requests:
              storage: 5Gi
```

**4b. Create ServiceMonitor for banking services**

Create `k8s/overlays/production/monitoring.yaml`:

```yaml
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: banking-services
  namespace: banking-prod
spec:
  selector:
    matchLabels:
      app: transaction-service
  endpoints:
    - port: http
      interval: 30s
      path: /metrics
---
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: fraud-detection
  namespace: banking-prod
spec:
  selector:
    matchLabels:
      app: fraud-detection-service
  endpoints:
    - port: http
      interval: 30s
      path: /metrics
---
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: notification-service
  namespace: banking-prod
spec:
  selector:
    matchLabels:
      app: notification-service
  endpoints:
    - port: http
      interval: 30s
      path: /metrics
```

**4c. Create PrometheusRule for alerts**

Create `k8s/overlays/production/alerts.yaml`:

```yaml
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: banking-alerts
  namespace: banking-prod
spec:
  groups:
    - name: banking.rules
      interval: 30s
      rules:
        - alert: HighErrorRate
          expr: 'rate(flask_http_requests_total{status=~"5.."}[5m]) > 0.05'
          for: 5m
          labels:
            severity: critical
          annotations:
            summary: "High error rate detected"
            description: "Service {{ $labels.service }} has error rate > 5%"

        - alert: PodMemoryUsage
          expr: 'container_memory_usage_bytes / container_spec_memory_limit_bytes > 0.9'
          for: 5m
          labels:
            severity: warning
          annotations:
            summary: "Pod memory usage is high"
            description: "Pod {{ $labels.pod }} memory usage > 90%"

        - alert: DatabaseDown
          expr: 'pg_up{job="postgres"} == 0'
          for: 1m
          labels:
            severity: critical
          annotations:
            summary: "PostgreSQL is down"

        - alert: TransactionLatencyHigh
          expr: 'histogram_quantile(0.95, rate(banking_transaction_duration_seconds_bucket[5m])) > 1'
          for: 5m
          labels:
            severity: warning
          annotations:
            summary: "High transaction latency"
            description: "p95 latency > 1 second"
```

**4d. Access Grafana**

```bash
# Port-forward to Grafana
kubectl port-forward -n monitoring svc/prometheus-grafana 3000:80

# Access at http://localhost:3000
# Default credentials: admin / your-secure-password

# Import dashboards from Grafana dashboard library or create custom ones
```

**4e. Add Prometheus to services (Flask metrics)**

Update service requirements to include `prometheus-client`:

```bash
pip install prometheus-client
```

Add metrics collection to each Flask service's `utils.py` or `__init__.py`:

```python
from prometheus_client import Counter, Histogram, generate_latest
import time

REQUEST_COUNT = Counter('flask_requests_total', 'Total requests', ['method', 'endpoint', 'status'])
REQUEST_LATENCY = Histogram('flask_request_duration_seconds', 'Request latency', ['endpoint'])
TRANSACTION_DURATION = Histogram('banking_transaction_duration_seconds', 'Transaction processing time')

@app.before_request
def before_request():
    request.start_time = time.time()

@app.after_request
def after_request(response):
    duration = time.time() - request.start_time
    REQUEST_COUNT.labels(method=request.method, endpoint=request.path, status=response.status_code).inc()
    REQUEST_LATENCY.labels(endpoint=request.path).observe(duration)
    return response

@app.route('/metrics')
def metrics():
    return generate_latest()
```

---

## Step 5: Configure Log Shipping (Filebeat + Logstash + Elasticsearch)

### Goal
Centralize logs for analysis, debugging, and compliance.

### Implementation

**5a. Deploy ELK Stack**

```bash
helm repo add elastic https://helm.elastic.co
helm repo update

# Install Elasticsearch
helm install elasticsearch elastic/elasticsearch \
  --namespace logging \
  --create-namespace \
  --values elasticsearch-values.yaml

# Install Logstash
helm install logstash elastic/logstash \
  --namespace logging \
  --values logstash-values.yaml

# Install Kibana
helm install kibana elastic/kibana \
  --namespace logging \
  --values kibana-values.yaml
```

Create `elasticsearch-values.yaml`:

```yaml
replicas: 3
resources:
  requests:
    memory: "1Gi"
    cpu: "500m"
  limits:
    memory: "2Gi"
    cpu: "1000m"
persistence:
  enabled: true
  size: 30Gi
```

Create `logstash-values.yaml`:

```yaml
replicas: 2
config:
  pipeline.esc: "/usr/share/logstash/pipeline"
  
  logstash.yml: |
    http.host: 0.0.0.0
    xpack.monitoring.enabled: true
    
logstashPipeline:
  logstash.conf: |
    input {
      beats {
        port => 5000
      }
    }
    filter {
      json {
        source => "message"
      }
    }
    output {
      elasticsearch {
        hosts => ["elasticsearch:9200"]
        index => "banking-%{+YYYY.MM.dd}"
      }
    }

resources:
  requests:
    memory: "512Mi"
    cpu: "250m"
  limits:
    memory: "1Gi"
    cpu: "500m"
```

Create `kibana-values.yaml`:

```yaml
replicas: 1
elasticsearchHosts: "http://elasticsearch:9200"
resources:
  requests:
    memory: "256Mi"
    cpu: "100m"
  limits:
    memory: "512Mi"
    cpu: "200m"
```

**5b. Deploy Filebeat to collect logs**

Create `k8s/overlays/production/filebeat.yaml`:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: filebeat-config
  namespace: banking-prod
data:
  filebeat.yml: |
    filebeat.inputs:
    - type: container
      enabled: true
      paths:
        - /var/lib/docker/containers/*/*.log
      processors:
        - decode_json_fields:
            fields: ["message"]
            target: ""
            overwrite_keys: true

    output.elasticsearch:
      enabled: true
      hosts: ["elasticsearch.logging:9200"]
      index: "banking-%{+yyyy.MM.dd}"

    logging.level: info
---
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: filebeat
  namespace: banking-prod
spec:
  selector:
    matchLabels:
      app: filebeat
  template:
    metadata:
      labels:
        app: filebeat
    spec:
      serviceAccountName: filebeat
      terminationGracePeriodSeconds: 30
      dnsPolicy: ClusterFirstWithHostNet
      containers:
      - name: filebeat
        image: docker.elastic.co/beats/filebeat:8.12.0
        env:
        - name: NODE_NAME
          valueFrom:
            fieldRef:
              fieldPath: spec.nodeName
        volumeMounts:
        - name: config
          mountPath: /etc/filebeat.yml
          readOnly: true
          subPath: filebeat.yml
        - name: varlog
          mountPath: /var/log
          readOnly: true
        - name: varlibdockercontainers
          mountPath: /var/lib/docker/containers
          readOnly: true
        resources:
          requests:
            memory: "100Mi"
            cpu: "50m"
          limits:
            memory: "200Mi"
            cpu: "100m"
      volumes:
      - name: config
        configMap:
          name: filebeat-config
      - name: varlog
        hostPath:
          path: /var/log
      - name: varlibdockercontainers
        hostPath:
          path: /var/lib/docker/containers
---
apiVersion: v1
kind: ServiceAccount
metadata:
  name: filebeat
  namespace: banking-prod
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: filebeat
rules:
- apiGroups: [""]
  resources:
  - namespaces
  - pods
  verbs:
  - get
  - list
  - watch
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: filebeat
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: filebeat
subjects:
- kind: ServiceAccount
  name: filebeat
  namespace: banking-prod
```

**5c. Access Kibana and create dashboards**

```bash
# Port-forward to Kibana
kubectl port-forward -n logging svc/kibana 5601:5601

# Access at http://localhost:5601
# Create index pattern: banking-*
# Create visualizations and dashboards
```

---

## Step 6: Add PodDisruptionBudgets and Network Policies

### Goal
Ensure high availability and secure inter-pod communication.

### Implementation

**6a. Create PodDisruptionBudgets**

Create `k8s/overlays/production/pdb.yaml`:

```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: transaction-service-pdb
  namespace: banking-prod
spec:
  minAvailable: 2
  selector:
    matchLabels:
      app: transaction-service
---
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: fraud-detection-service-pdb
  namespace: banking-prod
spec:
  minAvailable: 1
  selector:
    matchLabels:
      app: fraud-detection-service
---
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: notification-service-pdb
  namespace: banking-prod
spec:
  minAvailable: 1
  selector:
    matchLabels:
      app: notification-service
---
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: postgres-pdb
  namespace: banking-prod
spec:
  minAvailable: 1
  selector:
    matchLabels:
      app: postgres
```

**6b. Create NetworkPolicies**

Create `k8s/overlays/production/network-policies.yaml`:

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny-ingress
  namespace: banking-prod
spec:
  podSelector: {}
  policyTypes:
  - Ingress
---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-transaction-service
  namespace: banking-prod
spec:
  podSelector:
    matchLabels:
      app: transaction-service
  policyTypes:
  - Ingress
  ingress:
  - from:
    - podSelector:
        matchLabels:
          app: frontend
    - podSelector:
        matchLabels:
          app: fraud-detection-service
    ports:
    - protocol: TCP
      port: 5001
  - from:
    - namespaceSelector:
        matchLabels:
          name: ingress-nginx
    ports:
    - protocol: TCP
      port: 5001
---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-fraud-detection
  namespace: banking-prod
spec:
  podSelector:
    matchLabels:
      app: fraud-detection-service
  policyTypes:
  - Ingress
  ingress:
  - from:
    - podSelector:
        matchLabels:
          app: transaction-service
    ports:
    - protocol: TCP
      port: 5002
---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-notification-service
  namespace: banking-prod
spec:
  podSelector:
    matchLabels:
      app: notification-service
  policyTypes:
  - Ingress
  ingress:
  - from:
    - podSelector:
        matchLabels:
          app: transaction-service
    - podSelector:
        matchLabels:
          app: fraud-detection-service
    ports:
    - protocol: TCP
      port: 5003
---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-postgres
  namespace: banking-prod
spec:
  podSelector:
    matchLabels:
      app: postgres
  policyTypes:
  - Ingress
  ingress:
  - from:
    - podSelector:
        matchLabels:
          app: transaction-service
    - podSelector:
        matchLabels:
          app: notification-service
    ports:
    - protocol: TCP
      port: 5432
---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-frontend
  namespace: banking-prod
spec:
  podSelector:
    matchLabels:
      app: frontend
  policyTypes:
  - Ingress
  ingress:
  - from:
    - namespaceSelector:
        matchLabels:
          name: ingress-nginx
    ports:
    - protocol: TCP
      port: 80
---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-vault
  namespace: banking-prod
spec:
  podSelector:
    matchLabels:
      app: vault
  policyTypes:
  - Ingress
  ingress:
  - from:
    - podSelector: {}
    ports:
    - protocol: TCP
      port: 8200
---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-postgres-egress
  namespace: banking-prod
spec:
  podSelector:
    matchLabels:
      app: postgres
  policyTypes:
  - Egress
  egress:
  - to:
    - podSelector: {}
```

**6c. Label namespaces for ingress routing**

```bash
kubectl label namespace ingress-nginx name=ingress-nginx
kubectl apply -f k8s/overlays/production/network-policies.yaml
```

---

## Step 7: Document Runbooks and Incident Response

### Goal
Create operational guides for common issues and incident response procedures.

### Implementation

**7a. Create runbook template**

Create `docs/RUNBOOKS.md`:

```markdown
# Banking System Runbooks

## 1. Pod Crash Loop

**Symptoms**: Pod repeatedly restarts, stuck in CrashLoopBackOff

**Diagnosis**:
\`\`\`bash
kubectl logs -n banking-prod <pod-name> --tail=100
kubectl describe pod -n banking-prod <pod-name>
\`\`\`

**Common Causes & Fixes**:

### Database Connection Failed
- Check Postgres is running: `kubectl get pods -n banking-prod postgres-0`
- Verify secrets: `kubectl get secrets -n banking-prod banking-secrets -o yaml`
- Test connection: `kubectl exec -n banking-prod postgres-0 -- pg_isready -U banking_user`

### Out of Memory
- Check resource limits: `kubectl top pod -n banking-prod`
- Increase memory limit in overlay: `k8s/overlays/production/resources.yaml`
- Redeploy: `kubectl apply -k k8s/overlays/production`

### Missing Environment Variables
- Verify Vault is healthy: `kubectl logs -n vault vault-0`
- Reload secrets: `kubectl rollout restart deployment/transaction-service -n banking-prod`

---

## 2. Slow Transaction Processing

**Symptoms**: Transaction endpoint latency > 1s

**Diagnosis**:
\`\`\`bash
# Check Prometheus metrics
kubectl port-forward -n monitoring svc/prometheus-operated 9090:9090
# Query: rate(banking_transaction_duration_seconds_sum[5m]) / rate(banking_transaction_duration_seconds_count[5m])

# Check database queries
kubectl exec -n banking-prod postgres-0 -- psql -U banking_user -d banking -c "SELECT * FROM pg_stat_statements ORDER BY mean_time DESC LIMIT 10;"

# Check resource usage
kubectl top pods -n banking-prod
\`\`\`

**Common Causes & Fixes**:

### Database Bottleneck
- Add indexes: \`CREATE INDEX idx_transactions_account_id ON transactions(from_account_id);\`
- Increase Postgres resources in overlay
- Enable read replicas for reporting queries

### Service Resource Contention
- Check HPA status: `kubectl get hpa -n banking-prod`
- Manually scale up: `kubectl scale deployment transaction-service --replicas=5 -n banking-prod`
- Increase resource requests in overlay if underprovisioned

### Network Latency
- Check ingress: `kubectl get ingress -n banking-prod`
- Verify service discovery: `kubectl get svc -n banking-prod`

---

## 3. High Error Rate

**Symptoms**: Errors appearing in Kibana, Prometheus alerts firing

**Diagnosis**:
\`\`\`bash
# Check pod logs
kubectl logs -n banking-prod -l app=transaction-service --tail=200 | tail -n 50

# Check Elasticsearch for errors
curl -X GET "localhost:9200/banking-*/_search?q=level:ERROR" 2>/dev/null | jq '.hits.hits[].source'

# Check Prometheus alerts
kubectl port-forward -n monitoring svc/prometheus-operated 9090:9090
# Visit http://localhost:9090/alerts
\`\`\`

**Common Causes & Fixes**:

### Vault Authentication Failure
- Check Vault pod: `kubectl logs -n vault vault-0`
- Verify JWT token validity: `vault token lookup`
- Re-authenticate: `kubectl rollout restart deployment/transaction-service -n banking-prod`

### Database Connection Pool Exhausted
- Check Postgres connections: `kubectl exec -n banking-prod postgres-0 -- psql -U banking_user -d banking -c "SELECT count(*) as connections FROM pg_stat_activity;"`
- Increase connection pool in Flask: `SQLALCHEMY_ENGINE_OPTIONS = {'pool_size': 20, 'pool_recycle': 3600}`
- Restart services to apply changes

### Upstream Service Down
- Check fraud service: `kubectl get pods -n banking-prod fraud-detection-service-*`
- Check logs: `kubectl logs -n banking-prod -l app=fraud-detection-service`
- Restart if needed: `kubectl rollout restart deployment/fraud-detection-service -n banking-prod`

---

## 4. Disk Space Exhaustion

**Symptoms**: Postgres won't start, Elasticsearch indexing fails

**Diagnosis**:
\`\`\`bash
# Check disk usage
kubectl exec -n banking-prod postgres-0 -- df -h
kubectl exec -n logging elasticsearch-0 -- df -h

# Check PVC usage
kubectl get pvc -n banking-prod
kubectl get pvc -n logging
\`\`\`

**Fix**:

1. **Expand PVC**:
\`\`\`bash
kubectl patch pvc pgdata-postgres-0 -n banking-prod -p '{"spec":{"resources":{"requests":{"storage":"50Gi"}}}}'
\`\`\`

2. **Clean old logs**:
\`\`\`bash
# Delete old indices in Elasticsearch
curl -X DELETE "localhost:9200/banking-$(date -d '30 days ago' +%Y.%m.%d)" 2>/dev/null
\`\`\`

---

## 5. Vault Unsealing (after outage)

**Steps**:
\`\`\`bash
# Check status
vault status

# If sealed, unseal with 3 of 5 keys
vault operator unseal <key1>
vault operator unseal <key2>
vault operator unseal <key3>

# Verify
vault status

# Verify services reconnect
kubectl get pods -n banking-prod
\`\`\`

---

## 6. Database Backup & Recovery

**Backup**:
\`\`\`bash
kubectl exec -n banking-prod postgres-0 -- pg_dump -U banking_user banking > backup-$(date +%Y%m%d).sql
\`\`\`

**Restore**:
\`\`\`bash
kubectl exec -i -n banking-prod postgres-0 -- psql -U banking_user banking < backup-20260511.sql
\`\`\`

---

## 7. Deployment Rollback

**If a deployment is broken**:
\`\`\`bash
# Check rollout history
kubectl rollout history deployment/transaction-service -n banking-prod

# Rollback to previous version
kubectl rollout undo deployment/transaction-service -n banking-prod

# Verify
kubectl get deployment -n banking-prod
kubectl logs -n banking-prod -l app=transaction-service --tail=50
\`\`\`

---

## Escalation Contacts

- **On-call Engineer**: alerts@company.com
- **Database DBA**: database-team@company.com
- **Infrastructure**: infra-team@company.com

## Incident Post-Mortem Template

See `docs/INCIDENT-TEMPLATE.md`
```

**7b. Create incident response template**

Create `docs/INCIDENT-TEMPLATE.md`:

```markdown
# Incident Post-Mortem

**Date**: YYYY-MM-DD
**Duration**: HH:MM
**Severity**: SEV-1 (Critical) / SEV-2 (High) / SEV-3 (Medium) / SEV-4 (Low)

## Summary
[Brief description of what happened]

## Impact
- **Affected Users**: [Number and description]
- **Data Loss**: Yes/No [Details]
- **Services Down**: [List of services]
- **Duration**: [Start time] - [End time]

## Root Cause
[What ultimately caused the incident]

## Timeline
- **HH:MM** - [Event]
- **HH:MM** - [Detection]
- **HH:MM** - [Response initiated]
- **HH:MM** - [Resolution]

## Response Actions Taken
1. [Action]
2. [Action]

## Lessons Learned
- [What went well]
- [What could be improved]

## Action Items
| Item | Owner | Due Date |
|------|-------|----------|
| [Implement fix] | [Name] | [Date] |
| [Add monitoring] | [Name] | [Date] |

## Follow-up
- [ ] Monitoring improved
- [ ] Documentation updated
- [ ] Team trained
```

**7c. Create deployment checklist**

Create `docs/DEPLOYMENT-CHECKLIST.md`:

```markdown
# Production Deployment Checklist

## Pre-Deployment
- [ ] All tests passing in CI
- [ ] Code review approved
- [ ] Security scan (Trivy) passed
- [ ] Database migrations tested
- [ ] Rollback plan documented
- [ ] Communication sent to team

## Deployment
- [ ] Take backup of Postgres
- [ ] Apply manifests: `kubectl apply -k k8s/overlays/production`
- [ ] Monitor rollout: `kubectl rollout status deployment/* -n banking-prod --timeout=10m`
- [ ] Verify all pods running: `kubectl get pods -n banking-prod`
- [ ] Run smoke tests
- [ ] Verify Prometheus metrics being collected
- [ ] Check Kibana for errors

## Post-Deployment
- [ ] Monitor error rates for 1 hour
- [ ] Verify database consistency
- [ ] Check customer reports / monitoring dashboards
- [ ] Document deployment in changelog
- [ ] Update deployment runbook if needed

## Rollback Criteria
Execute immediate rollback if:
- [ ] Error rate > 5%
- [ ] Latency p95 > 2 seconds
- [ ] Database connection failures
- [ ] Data integrity issues
- [ ] Critical security alert

## Rollback Steps
\`\`\`bash
kubectl rollout undo deployment/transaction-service -n banking-prod
kubectl rollout undo deployment/fraud-detection-service -n banking-prod
kubectl rollout undo deployment/notification-service -n banking-prod
kubectl rollout undo deployment/frontend -n banking-prod
\`\`\`
```

**7d. Create a status page template**

Create `docs/STATUS-PAGE.md`:

```markdown
# Banking System Status

**Last Updated**: [Auto-update from Prometheus]

| Component | Status | Latency | Error Rate |
|-----------|--------|---------|------------|
| Transaction Service | 🟢 Healthy | 150ms | 0.1% |
| Fraud Detection | 🟢 Healthy | 50ms | 0.0% |
| Notification Service | 🟢 Healthy | 100ms | 0.2% |
| Frontend | 🟢 Healthy | 300ms | 0.0% |
| PostgreSQL | 🟢 Healthy | - | - |
| Vault | 🟢 Healthy | - | - |

## Ongoing Incidents
None

## Scheduled Maintenance
- **May 15, 2026** - Database maintenance window, 2:00-3:00 AM UTC
```

---

## Deployment Orchestration: All Steps Together

Create a single command to deploy production:

```bash
#!/bin/bash
set -e

echo "=== Banking System Production Deployment ==="

# 1. Build and push images
echo "Step 1: Building and pushing images..."
docker build -t your-registry.com/banking/transaction-service:v1.0.0 transaction-service/
docker build -t your-registry.com/banking/fraud-detection-service:v1.0.0 fraud-detection-service/
# ... etc

# 2. Deploy Vault
echo "Step 2: Deploying production Vault..."
helm install vault hashicorp/vault -n vault --create-namespace -f vault-values.yaml

# 3. Deploy monitoring
echo "Step 3: Deploying Prometheus + Grafana..."
helm install prometheus prometheus-community/kube-prometheus-stack -n monitoring --create-namespace -f prometheus-values.yaml

# 4. Deploy logging
echo "Step 4: Deploying ELK stack..."
helm install elasticsearch elastic/elasticsearch -n logging --create-namespace -f elasticsearch-values.yaml
helm install logstash elastic/logstash -n logging -f logstash-values.yaml
helm install kibana elastic/kibana -n logging -f kibana-values.yaml

# 5. Deploy banking services
echo "Step 5: Deploying banking services..."
kubectl apply -k k8s/overlays/production

# 6. Verify deployment
echo "Step 6: Verifying deployment..."
kubectl rollout status deployment/transaction-service -n banking-prod --timeout=10m
kubectl rollout status deployment/fraud-detection-service -n banking-prod --timeout=10m
kubectl rollout status deployment/notification-service -n banking-prod --timeout=10m
kubectl rollout status deployment/frontend -n banking-prod --timeout=10m

echo "=== Deployment Complete ==="
echo "Access endpoints:"
echo "  - Kibana: kubectl port-forward -n logging svc/kibana 5601:5601"
echo "  - Grafana: kubectl port-forward -n monitoring svc/prometheus-grafana 3000:80"
echo "  - Frontend: kubectl port-forward -n banking-prod svc/frontend 3000:80"
```

---

## Summary

**Follow this order:**

1. **Registry + Image Tags** → Push to your registry (Docker Hub, ECR, GCR)
2. **Vault Production** → Set up HA Vault with policies and K8s auth
3. **Resource Limits** → Define requests/limits and enable HPA
4. **Monitoring** → Deploy Prometheus + Grafana for metrics and alerting
5. **Log Aggregation** → Deploy ELK for centralized logging
6. **HA & Security** → Apply PDBs and NetworkPolicies
7. **Documentation** → Create runbooks and incident procedures

Each step builds on the previous one and integrates into the `k8s/overlays/production` structure.
