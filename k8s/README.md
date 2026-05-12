# Kubernetes Scaffold

This folder is the Kubernetes deployment stage after Docker Compose. In the submission flow, Jenkins hands off to Ansible, and Ansible applies these manifests through Kustomize.

## What is included

- `postgres` StatefulSet with persistent storage and the existing `infra/postgres/init.sql`
- `vault` Deployment in dev mode for local/teaching use
- `transaction-service`, `fraud-detection-service`, and `notification-service` Deployments + Services
- `frontend` Deployment + Service
- `Ingress` rules for browser access and service routing
- Shared ConfigMap and a generated Secret for app configuration
- Horizontal Pod Autoscalers for the service workloads

## What is still left before this becomes production-ready

- Replace the placeholder image names with registry tags from CI/CD
- Decide whether Vault stays in dev mode or moves to a production Vault cluster
- Ensure the Ansible vault password is supplied securely in CI/CD
- Build the frontend image with the ingress-based API URLs for your cluster
- Set up DNS or a local hosts entry for `banking.local`
- Metrics Server is installed automatically by the Ansible deployment if it is missing

## Apply locally

```bash
ansible-playbook -i ansible/inventory/hosts.ini ansible/deploy.yml --vault-password-file ansible/.vault_pass
```

If you use NGINX Ingress, make sure the ingress controller is installed first and that `banking.local` resolves to the ingress IP.

## Why this setup is useful

- The secret values live in Ansible Vault instead of plain YAML, so the same playbook can be reused across environments.
- Jenkins stays thin: it builds and tests, then hands Kubernetes rollout to Ansible.
- HPA and resource limits make the deployment closer to a real production submission rather than a static demo.