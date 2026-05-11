# Kubernetes Scaffold

This folder is the next deployment stage after Docker Compose.

## What is included

- `postgres` StatefulSet with persistent storage and the existing `infra/postgres/init.sql`
- `vault` Deployment in dev mode for local/teaching use
- `transaction-service`, `fraud-detection-service`, and `notification-service` Deployments + Services
- `frontend` Deployment + Service
- `Ingress` rules for browser access and service routing
- Shared ConfigMap and Secret examples for app configuration

## What is still left before this becomes production-ready

- Replace the placeholder image names with registry tags from CI/CD
- Decide whether Vault stays in dev mode or moves to a production Vault cluster
- Provision real secrets instead of the example Secret values
- Build the frontend image with the ingress-based API URLs for your cluster
- Set up DNS or a local hosts entry for `banking.local`
- Add optional production hardening: resource limits, PodDisruptionBudgets, NetworkPolicies, and autoscaling

## Apply locally

```bash
kubectl apply -k k8s/
```

If you use NGINX Ingress, make sure the ingress controller is installed first and that `banking.local` resolves to the ingress IP.