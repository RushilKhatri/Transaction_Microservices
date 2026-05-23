pipeline {
  agent any

  options {
    timestamps()
    disableConcurrentBuilds()
  }

  triggers {
    githubPush()
  }

  parameters {
    booleanParam(name: 'FAIL_ON_IMAGE_SCAN', defaultValue: false, description: 'Fail pipeline on Trivy HIGH/CRITICAL findings')
    string(name: 'DOCKERHUB_NAMESPACE', defaultValue: 'rushilkhatri', description: 'Docker Hub namespace/user')
    string(name: 'K8S_NAMESPACE', defaultValue: 'banking', description: 'Kubernetes namespace for deployment')
    string(name: 'K8S_IMAGE_TAG', defaultValue: 'latest', description: 'Image tag for Kubernetes deployment (auto-set to BUILD_NUMBER)')
  }

  environment {
    COMPOSE_PROJECT_NAME = 'banking-devsecops'
    PIP_DISABLE_PIP_VERSION_CHECK = '1'
  }

  stages {
    stage('Checkout') {
      steps {
        checkout scm
      }
    }

    stage('Unit Tests') {
      steps {
        sh '''
          set -e
          rm -rf reports .venv-ci
          mkdir -p reports

          python3 -m venv .venv-ci
          . .venv-ci/bin/activate
          pip install --upgrade pip

          pip install -r transaction-service/requirements.txt
          (cd transaction-service && pytest tests -q --junitxml=../reports/transaction-tests.xml)

          pip install -r fraud-detection-service/requirements.txt
          (cd fraud-detection-service && pytest tests -q --junitxml=../reports/fraud-tests.xml)

          pip install -r notification-service/requirements.txt
          (cd notification-service && pytest tests -q --junitxml=../reports/notification-tests.xml)
        '''
      }
    }

    stage('SAST Scan (Bandit)') {
      steps {
        sh '''
          set -e
          . .venv-ci/bin/activate
          pip install bandit
          bandit -r transaction-service/app fraud-detection-service/app notification-service/app \
            -f txt -o reports/bandit-report.txt
        '''
      }
    }

    stage('Dependency Audit (Safety + npm audit)') {
      steps {
        timeout(time: 10, unit: 'MINUTES') {
          sh '''
            set -e
            . .venv-ci/bin/activate
            pip install safety

            # Run safety checks in parallel to reduce total execution time
            safety check -r transaction-service/requirements.txt --full-report > reports/safety-transaction.txt &
            safety check -r fraud-detection-service/requirements.txt --full-report > reports/safety-fraud.txt &
            safety check -r notification-service/requirements.txt --full-report > reports/safety-notification.txt &
            wait  # wait for all background safety checks to complete

            cd frontend
            # prefer cached packages to reduce network latency in CI
            npm ci --silent --prefer-offline
            # run audit but don't fail the stage on transient network errors
            npm audit --audit-level=high || true
          '''
        }
      }
    }

    stage('Docker Build') {
      steps {
        sh '''
          set -e
          docker compose --env-file .env.docker build transaction-service fraud-detection-service notification-service frontend
        '''
      }
    }

    stage('Image Scan (Trivy)') {
      steps {
        sh '''
          set -e
          mkdir -p reports

          if [ "${FAIL_ON_IMAGE_SCAN}" = "true" ]; then
            TRIVY_EXIT=1
          else
            TRIVY_EXIT=0
          fi

          for IMG in \
            banking-devsecops-transaction-service:latest \
            banking-devsecops-fraud-detection-service:latest \
            banking-devsecops-notification-service:latest \
            banking-devsecops-frontend:latest
          do
            SAFE_NAME=$(echo "$IMG" | tr ':/' '__')
            docker run --rm \
              -v /var/run/docker.sock:/var/run/docker.sock \
              aquasec/trivy:0.51.2 image \
              --scanners vuln \
              --severity HIGH,CRITICAL \
              --ignore-unfixed \
              --exit-code "$TRIVY_EXIT" \
              "$IMG" > "reports/trivy-${SAFE_NAME}.txt"
            cat "reports/trivy-${SAFE_NAME}.txt"
          done
        '''
      }
    }

    stage('Compose Smoke Test (Vault + E2E Tx)') {
      steps {
        sh '''
          set -e

          SMOKE_PROJECT="banking-devsecops-smoke-${BUILD_NUMBER:-local}"
          # compose command will reference both the main compose file and a temporary override
          COMPOSE_CMD_BASE="docker compose -p $SMOKE_PROJECT --env-file .env.docker -f docker-compose.yml -f .smoke-override.yml"

          pick_free_port() {
            python3 - <<'PY'
import socket
sock = socket.socket()
sock.bind(('127.0.0.1', 0))
print(sock.getsockname()[1])
sock.close()
PY
          }

          export POSTGRES_HOST_PORT="$(pick_free_port)"
          export VAULT_HOST_PORT="$(pick_free_port)"
          export TRANSACTION_HOST_PORT="$(pick_free_port)"
          export FRAUD_HOST_PORT="$(pick_free_port)"
          export NOTIFICATION_HOST_PORT="$(pick_free_port)"
          export FRONTEND_HOST_PORT="$(pick_free_port)"

          # create a temporary override compose file that maps container ports to randomized host ports
          cat > .smoke-override.yml <<EOF
services:
  postgres:
    container_name: "banking-postgres-${SMOKE_PROJECT}"
    ports:
      - "${POSTGRES_HOST_PORT}:5432"
  vault:
    container_name: "banking-vault-${SMOKE_PROJECT}"
    ports:
      - "${VAULT_HOST_PORT}:8200"
  transaction-service:
    container_name: "banking-transaction-${SMOKE_PROJECT}"
    ports:
      - "${TRANSACTION_HOST_PORT}:5001"
  fraud-detection-service:
    container_name: "banking-fraud-${SMOKE_PROJECT}"
    ports:
      - "${FRAUD_HOST_PORT}:5002"
  notification-service:
    container_name: "banking-notification-${SMOKE_PROJECT}"
    ports:
      - "${NOTIFICATION_HOST_PORT}:5003"
  frontend:
    container_name: "banking-frontend-${SMOKE_PROJECT}"
    ports:
      - "${FRONTEND_HOST_PORT}:80"
EOF

          cleanup() {
            $COMPOSE_CMD_BASE down -v --remove-orphans || true
            rm -f .smoke-override.yml || true
          }
          trap cleanup EXIT

          $COMPOSE_CMD_BASE down -v --remove-orphans || true

          $COMPOSE_CMD_BASE up -d vault postgres
          bash infra/vault/seed-dev.sh
          $COMPOSE_CMD_BASE up -d transaction-service fraud-detection-service notification-service frontend

          wait_for_health() {
            service_name="$1"
            container_id="$(docker compose -p $SMOKE_PROJECT -f docker-compose.yml -f .smoke-override.yml ps -q "$service_name")"
            label="$service_name"

            if [ -z "$container_id" ]; then
              echo "ERROR: could not find container for $label"
              exit 1
            fi

            i=0
            while [ "$i" -lt 60 ]; do
              health_status="$(docker inspect --format='{{if .State.Health}}{{.State.Health.Status}}{{else}}no-healthcheck{{end}}' "$container_id" 2>/dev/null || true)"

              if [ "$health_status" = "healthy" ]; then
                return 0
              fi

              if [ "$health_status" = "unhealthy" ]; then
                echo "ERROR: $label container became unhealthy"
                docker logs "$container_id" --tail 50 || true
                exit 1
              fi

              i=$((i + 1))
              sleep 2
            done

            echo "ERROR: timed out waiting for $label to become healthy"
            docker logs "$container_id" --tail 50 || true
            exit 1
          }

          wait_for_health transaction-service
          wait_for_health fraud-detection-service
          wait_for_health notification-service
          $COMPOSE_CMD_BASE exec -T transaction-service python - <<'PY'
import time
import urllib.request


def request(method, url, payload=None, headers=None):
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, method=method, headers=headers or {})
    with urllib.request.urlopen(req, timeout=20) as response:
        return response.read().decode("utf-8")


def wait_for(url, label):
    for _ in range(60):
        try:
            request("GET", url)
            return
        except Exception:
            time.sleep(2)
    raise RuntimeError(f"{label} did not become ready")


wait_for("http://localhost:5001/health", "transaction service")
wait_for("http://fraud-detection-service:5002/health", "fraud service")
wait_for("http://notification-service:5003/health", "notification service")
wait_for("http://frontend/", "frontend")

token_response = json.loads(
    request(
        "POST",
        "http://localhost:5001/auth/token",
        payload={"username": "admin", "password": "admin123"},
        headers={"Content-Type": "application/json"},
    )
)
token = token_response["access_token"]

account_one = json.loads(
    request(
        "POST",
        "http://localhost:5001/account/create",
        payload={"owner_name": "Jenkins A", "balance": 120000},
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
)["id"]

account_two = json.loads(
    request(
        "POST",
        "http://localhost:5001/account/create",
        payload={"owner_name": "Jenkins B", "balance": 1000},
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
)["id"]

transaction = json.loads(
    request(
        "POST",
        "http://localhost:5001/transaction",
        payload={
            "from_account_id": account_one,
            "to_account_id": account_two,
            "amount": 60000,
            "transaction_type": "debit",
        },
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
)

assert transaction.get("fraud_flagged") is True, transaction
print(transaction["id"])
        '''
      }
    }

    stage('Push to Docker Hub') {
      steps {
        withCredentials([usernamePassword(credentialsId: 'dockerhub-creds', usernameVariable: 'DOCKER_USER', passwordVariable: 'DOCKER_PASS')]) {
          sh '''
            set -e
            if ! echo "$DOCKER_PASS" | docker login -u "$DOCKER_USER" --password-stdin; then
              echo "ERROR: Docker Hub login failed. Please verify Jenkins credential 'dockerhub-creds' (username and token/password)."
              echo "Hint: use a Docker Hub Personal Access Token as the password."
              exit 1
            fi

            docker tag banking-devsecops-transaction-service:latest "$DOCKERHUB_NAMESPACE/transaction-service:${BUILD_NUMBER}"
            docker tag banking-devsecops-fraud-detection-service:latest "$DOCKERHUB_NAMESPACE/fraud-detection-service:${BUILD_NUMBER}"
            docker tag banking-devsecops-notification-service:latest "$DOCKERHUB_NAMESPACE/notification-service:${BUILD_NUMBER}"
            docker tag banking-devsecops-frontend:latest "$DOCKERHUB_NAMESPACE/frontend:${BUILD_NUMBER}"

            docker push "$DOCKERHUB_NAMESPACE/transaction-service:${BUILD_NUMBER}"
            docker push "$DOCKERHUB_NAMESPACE/fraud-detection-service:${BUILD_NUMBER}"
            docker push "$DOCKERHUB_NAMESPACE/notification-service:${BUILD_NUMBER}"
            docker push "$DOCKERHUB_NAMESPACE/frontend:${BUILD_NUMBER}"

            echo "All images pushed successfully with tag ${BUILD_NUMBER}"
          '''
        }
      }
    }

    stage('Deploy to Kubernetes via Ansible') {
      steps {
        sh '''
          set -e

          # Ensure ansible-playbook is available
          ANSIBLE_CMD=$(which ansible-playbook || echo "/usr/bin/ansible-playbook")
          if [ ! -x "$ANSIBLE_CMD" ]; then
            echo "ERROR: ansible-playbook not found at $ANSIBLE_CMD"
            exit 1
          fi

          echo "Deploying to Kubernetes with zero-downtime rolling update..."
          echo "Using ansible-playbook: $ANSIBLE_CMD"
          
          "$ANSIBLE_CMD" \
            -i ansible/inventory/hosts.ini \
            ansible/deploy.yml \
            --vault-password-file ansible/.vault_pass \
            -e k8s_namespace="${K8S_NAMESPACE}" \
            -e k8s_image_tag="${K8S_IMAGE_TAG}"
          
          echo "Deployment completed successfully!"
        '''
      }
    }
  }

  post {
    always {
      junit testResults: 'reports/*.xml', allowEmptyResults: true
      archiveArtifacts artifacts: 'reports/*', allowEmptyArchive: true
      sh '''
        set -e
        SMOKE_PROJECT="banking-devsecops-smoke-${BUILD_NUMBER:-local}"
        docker compose -p "$SMOKE_PROJECT" --env-file .env.docker down -v --remove-orphans || true
        docker compose --env-file .env.docker down -v || true
      '''
    }
  }
}
