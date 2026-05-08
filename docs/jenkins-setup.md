# Jenkins setup runbook (Phase 3)

This runbook is for running the root [Jenkinsfile](../Jenkinsfile) exactly as-is on an Ubuntu host.

## 1) Install Jenkins + required runtime tools

Install and start Jenkins:

- Install Java 17
- Install Jenkins LTS
- Start Jenkins service and complete initial admin setup

Install tools required by pipeline stages:

- Docker Engine
- Docker Compose plugin (`docker compose`)
- Python 3 + `venv`
- Node.js + npm

Add `jenkins` user to Docker group and restart Jenkins:

- `sudo usermod -aG docker jenkins`
- `sudo systemctl restart jenkins`

## 2) Jenkins plugins (minimum)

Install these plugins from **Manage Jenkins → Plugins**:

- Pipeline
- Git
- GitHub
- Credentials
- Credentials Binding
- JUnit
- ANSI Color
- Timestamper

## 3) Credentials

Create Docker Hub credential (needed only if `PUSH_IMAGES=true`):

- Type: Username with password
- ID: `dockerhub-creds`
- Username: Docker Hub username
- Password: Docker Hub access token

## 4) Create pipeline job

1. New Item → **Pipeline**
2. Definition: **Pipeline script from SCM**
3. SCM: **Git**
4. Repository URL: your repo URL
5. Branch: your working branch (for example `*/main`)
6. Script path: `Jenkinsfile`
7. Save

## 5) Build parameters to use

The pipeline exposes:

- `PUSH_IMAGES` (default `false`)
- `RUN_DEPLOY` (default `false`)
- `DOCKERHUB_NAMESPACE` (default placeholder)

Recommended first run:

- `PUSH_IMAGES=false`
- `RUN_DEPLOY=false`

## 6) GitHub webhook (automatic builds)

In Jenkins job configuration:

- Enable **GitHub hook trigger for GITScm polling**

In GitHub repo settings:

- Add webhook URL: `http://<jenkins-host>:8080/github-webhook/`
- Content type: `application/json`
- Events: Just the push event

If Jenkins is not public, use one of:

- Reverse proxy + HTTPS
- VPN/private network
- Temporary tunnel for demo

## 7) What a successful run should show

Stages expected to pass:

1. Checkout
2. Unit Tests
3. SAST Scan (Bandit)
4. Dependency Audit (Safety + npm audit)
5. Docker Build
6. Image Scan (Trivy)
7. Compose Smoke Test (Vault seed + health + end-to-end transaction)

Artifacts expected:

- JUnit XML files in `reports/*.xml`
- Security reports under `reports/`

## 8) Common issues and fixes

### Jenkins cannot run Docker

Symptom: permission denied on Docker socket.

Fix:

- Ensure `jenkins` is in Docker group.
- Restart Jenkins service.

### Trivy image pull/rate limits

Fix:

- Pre-pull Trivy image on Jenkins node.
- Configure registry credentials if needed.

### npm audit fails build

Fix options:

- Upgrade vulnerable frontend dependencies.
- Temporarily lower strictness only if explicitly approved.

### Safety/Bandit fail build

Fix:

- Treat as intended gate.
- Patch dependency or source issue and rerun.

## 9) Optional next hardening

- Use dedicated Jenkins agent node for builds
- Add branch protections and PR checks
- Add signed image provenance/SBOM stage
- Replace demo deploy stage with actual Ansible/K8s deploy logic
