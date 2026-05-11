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
    booleanParam(name: 'PUSH_IMAGES', defaultValue: false, description: 'Push built images to Docker Hub')
    booleanParam(name: 'RUN_DEPLOY', defaultValue: false, description: 'Run deployment step after image push')
    booleanParam(name: 'FAIL_ON_IMAGE_SCAN', defaultValue: false, description: 'Fail pipeline on Trivy HIGH/CRITICAL findings')
    string(name: 'DOCKERHUB_NAMESPACE', defaultValue: 'your-dockerhub-username', description: 'Docker Hub namespace/user')
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
          docker compose --env-file .env.docker down -v || true

          docker compose --env-file .env.docker up -d vault postgres
          bash infra/vault/seed-dev.sh
          docker compose --env-file .env.docker up -d transaction-service

          # wait for health
          timeout 120 sh -c 'until [ "$(docker inspect --format="{{.State.Health.Status}}" banking-transaction 2>/dev/null)" = "healthy" ]; do sleep 2; done'

          docker compose --env-file .env.docker up -d notification-service fraud-detection-service frontend

          timeout 120 sh -c 'until [ "$(docker inspect --format="{{.State.Health.Status}}" banking-fraud 2>/dev/null)" = "healthy" ]; do sleep 2; done'
          timeout 120 sh -c 'until [ "$(docker inspect --format="{{.State.Health.Status}}" banking-notification 2>/dev/null)" = "healthy" ]; do sleep 2; done'

          curl -fsS http://localhost:5001/health > /dev/null
          curl -fsS http://localhost:5002/health > /dev/null
          curl -fsS http://localhost:5003/health > /dev/null
          curl -fsS http://localhost:3000 > /dev/null

          TOKEN=$(curl -fsS -X POST http://localhost:5001/auth/token \
            -H 'Content-Type: application/json' \
            -d '{"username":"admin","password":"admin123"}' \
            | python3 -c 'import sys,json; print(json.load(sys.stdin)["access_token"])')

          A1=$(curl -fsS -X POST http://localhost:5001/account/create \
            -H "Authorization: Bearer $TOKEN" \
            -H 'Content-Type: application/json' \
            -d '{"owner_name":"Jenkins A","balance":120000}' \
            | python3 -c 'import sys,json; print(json.load(sys.stdin)["id"])')

          A2=$(curl -fsS -X POST http://localhost:5001/account/create \
            -H "Authorization: Bearer $TOKEN" \
            -H 'Content-Type: application/json' \
            -d '{"owner_name":"Jenkins B","balance":1000}' \
            | python3 -c 'import sys,json; print(json.load(sys.stdin)["id"])')

          SUCCESS=0
          for i in $(seq 1 10); do
            curl -sS -X POST http://localhost:5001/transaction -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d "{\"from_account_id\":\"$A1\",\"to_account_id\":\"$A2\",\"amount\":60000,\"transaction_type\":\"debit\"}" > tx.json 2>&1
            HTTP_CODE=$?
            
            if [ "$HTTP_CODE" -eq 0 ]; then
              python3 -c "import json; d=json.load(open('tx.json')); assert d.get('fraud_flagged') is True; print(d['id'])" && SUCCESS=1 && break
            fi
            
            echo "Transaction attempt $i failed"
            cat tx.json || true
            sleep 2
          done

          [ "$SUCCESS" = "1" ]
        '''
      }
    }

    stage('Push to Docker Hub') {
      when {
        expression { return params.PUSH_IMAGES }
      }
      steps {
        withCredentials([usernamePassword(credentialsId: 'dockerhub-creds', usernameVariable: 'DOCKER_USER', passwordVariable: 'DOCKER_PASS')]) {
          sh '''
            set -e
            echo "$DOCKER_PASS" | docker login -u "$DOCKER_USER" --password-stdin

            docker tag banking-devsecops-transaction-service:latest "$DOCKERHUB_NAMESPACE/transaction-service:${BUILD_NUMBER}"
            docker tag banking-devsecops-fraud-detection-service:latest "$DOCKERHUB_NAMESPACE/fraud-detection-service:${BUILD_NUMBER}"
            docker tag banking-devsecops-notification-service:latest "$DOCKERHUB_NAMESPACE/notification-service:${BUILD_NUMBER}"
            docker tag banking-devsecops-frontend:latest "$DOCKERHUB_NAMESPACE/frontend:${BUILD_NUMBER}"

            docker push "$DOCKERHUB_NAMESPACE/transaction-service:${BUILD_NUMBER}"
            docker push "$DOCKERHUB_NAMESPACE/fraud-detection-service:${BUILD_NUMBER}"
            docker push "$DOCKERHUB_NAMESPACE/notification-service:${BUILD_NUMBER}"
            docker push "$DOCKERHUB_NAMESPACE/frontend:${BUILD_NUMBER}"
          '''
        }
      }
    }

    stage('Deploy (Optional)') {
      when {
        allOf {
          expression { return params.RUN_DEPLOY }
          expression { return params.PUSH_IMAGES }
        }
      }
      steps {
        sh '''
          set -e
          if [ -f ansible/playbook.yml ]; then
            ansible-playbook ansible/playbook.yml
          else
            echo "No ansible/playbook.yml found; skipping deploy."
          fi
        '''
      }
    }
  }

  post {
    always {
      junit testResults: 'reports/*.xml', allowEmptyResults: true
      archiveArtifacts artifacts: 'reports/*', allowEmptyArchive: true
      sh 'docker compose --env-file .env.docker down -v || true'
    }
  }
}
