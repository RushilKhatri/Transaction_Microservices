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
        sh '''
          set -e
          . .venv-ci/bin/activate
          pip install safety

          safety check -r transaction-service/requirements.txt --full-report > reports/safety-transaction.txt
          safety check -r fraud-detection-service/requirements.txt --full-report > reports/safety-fraud.txt
          safety check -r notification-service/requirements.txt --full-report > reports/safety-notification.txt

          cd frontend
          npm ci --silent
          npm audit --audit-level=high
        '''
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
          COMPOSE_CMD="docker compose -p $SMOKE_PROJECT --env-file .env.docker"

          $COMPOSE_CMD down -v --remove-orphans || true

          $COMPOSE_CMD up -d vault postgres
          bash infra/vault/seed-dev.sh
          transaction_container_id="$($COMPOSE_CMD run -d --no-deps transaction-service)"

          wait_for_health() {
            container_id="$1"
            label="$2"
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

          wait_for_health "$transaction_container_id" transaction-service
          fraud_container_id="$($COMPOSE_CMD run -d --no-deps fraud-detection-service)"
          wait_for_health "$fraud_container_id" fraud-detection-service
          notification_container_id="$($COMPOSE_CMD run -d --no-deps notification-service)"
          wait_for_health "$notification_container_id" notification-service
          $COMPOSE_CMD run -d --no-deps frontend

          docker exec -i "$transaction_container_id" python - <<'PY'
import json
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
