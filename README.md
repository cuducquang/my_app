# Local MLOps Platform with Kubernetes (Kind)

A comprehensive MLOps platform running on Kubernetes (Kind) with service discovery, API gateway, and infrastructure components for machine learning workflows.

## 🏗 Architecture Stack

* **Cluster Orchestration:** Kubernetes (using [Kind](https://kind.sigs.k8s.io/))
* **Service Discovery:** Spring Cloud Eureka (Netflix Eureka Server)
* **API Gateway:** Go-based gateway with Eureka integration
* **Backend:** Python Flask API
* **Workflow Automation:** [n8n](https://n8n.io/)
* **Experiment Tracking:** [Weights & Biases (WandB)](https://wandb.ai/) (Self-hosted)
* **Vector Database:** [ChromaDB](https://www.trychroma.com/)
* **GitOps/Deployment:** [ArgoCD](https://argo-cd.readthedocs.io/)
* **Infrastructure as Code:** Kubernetes YAML manifests
* **CI/CD:** GitHub Actions with Docker Hub integration

---

## 🚀 Prerequisites (Requirements)

Before starting, please ensure your computer has downloaded:

1.  [Docker Desktop](https://www.docker.com/products/docker-desktop/) (at least 8GB RAM).
2.  [Kind](https://kind.sigs.k8s.io/docs/user/quick-start/) (`go install sigs.k8s.io/kind@v0.20.0`).
3.  [Kubectl](https://kubernetes.io/docs/tasks/tools/).
4.  (Recommend) [Lens](https://k8slens.dev/) to have UI k8s.

---

## 🛠️ Step-by-Step Setup Guide

### 1. Create Kubernetes Cluster
Create one k8s cluster by kind:

```bash
kind create cluster --name kind
```

Check if kind cluster running:

```bash
kubectl cluster-info
kubectl get nodes
```

### 2. Setup Secrets

Create required secrets (e.g., WandB API key):

```bash
kubectl create secret generic wandb-secret \
  --from-literal=api-key=your-wandb-api-key
```

### 3. Deploy Application Services

The platform consists of three main application services:

1. **Discovery Server (Eureka)**: Service registry for microservices
2. **API Gateway**: Entry point that routes requests to backend services
3. **Flask Backend**: Python API with endpoints for infrastructure testing

#### Option A: Using Docker Hub Images (Recommended for CI/CD)

If you're using images from Docker Hub (built via GitHub Actions):

```bash
# Apply all application services
kubectl apply -f k8s/apps/discovery-server.yaml
kubectl apply -f k8s/apps/flask-deployment.yaml
kubectl apply -f k8s/apps/api-gateway.yaml

# Wait for pods to be ready
kubectl wait --for=condition=ready pod -l app=discovery-server --timeout=120s
kubectl wait --for=condition=ready pod -l app=flask-backend --timeout=120s
kubectl wait --for=condition=ready pod -l app=api-gateway --timeout=120s
```

#### Option B: Using Local Images (For Development)

If you're building images locally:

```bash
# Build Docker images
docker build -t cdquang/my-app:discovery-server-latest ./discovery-server
docker build -t cdquang/my-app:flask-api-latest ./test
docker build -t cdquang/my-app:api-gateway-latest ./api-gateway

# Load images into kind cluster
kind load docker-image cdquang/my-app:discovery-server-latest --name kind
kind load docker-image cdquang/my-app:flask-api-latest --name kind
kind load docker-image cdquang/my-app:api-gateway-latest --name kind

# Apply manifests
kubectl apply -f k8s/apps/discovery-server.yaml
kubectl apply -f k8s/apps/flask-deployment.yaml
kubectl apply -f k8s/apps/api-gateway.yaml
```

#### Verify Services are Running

```bash
# Check pod status
kubectl get pods

# Check services
kubectl get services

# View Eureka dashboard (after port-forwarding, see below)
# You should see both FLASK-SERVICE and API-GATEWAY registered
```

### 4. Accessing Services

#### Understanding Kubernetes Networking

In Kubernetes, each pod gets its own IP address (e.g., `10.244.0.20`) within the cluster's private network. Services are exposed via `ClusterIP` by default, which means:

- **Pod IPs** (like `10.244.0.20:5000`) are only accessible from **inside the cluster**
- **Service names** (like `flask-service:80`) resolve to ClusterIPs and are also only accessible from within the cluster
- To access services from your **localhost**, you need to use `kubectl port-forward` or expose services via `NodePort`/`LoadBalancer`

#### Port Forwarding Services

**Option 1: Access via API Gateway (Recommended)**

The API Gateway is the main entry point. Forward port 80 to access all backend services:

```bash
# Forward API Gateway service
kubectl port-forward service/api-gateway 8080:80

# Now access:
# - http://localhost:8080/health - Gateway health check
# - http://localhost:8080/flask - Proxy to Flask GET /
# - http://localhost:8080/flask/test-infrastructure - Proxy to Flask POST /test-infrastructure
```

**Option 2: Direct Service Access (For Debugging)**

If you need direct access to individual services:

```bash
# Eureka Dashboard
kubectl port-forward service/discovery-server 8761:8761
# Access: http://localhost:8761

# Flask Backend (direct)
kubectl port-forward service/flask-service 5000:80
# Access: http://localhost:5000
```

**Note**: The port-forward command maps `local-port:service-port`. For example:
- `kubectl port-forward service/flask-service 5000:80` maps localhost:5000 → flask-service:80
- The service port 80 routes to container port 5000 (as defined in the Service manifest)

### 5. Setup Infrastructure

Deploy infrastructure components:

**ArgoCD** (GitOps)

```bash
kubectl create namespace argocd
kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml
```

**WandB** (Experiment Tracking)

```bash
docker pull wandb/local:latest
kind load docker-image wandb/local:latest --name kind
kubectl apply -f k8s/infrastructure/wandb-deployment.yaml
kubectl apply -f k8s/secrets/wandb-secret.yaml
```

**n8n and ChromaDB**

```bash
kubectl apply -f k8s/infrastructure/n8n-deployment.yaml
kubectl apply -f k8s/infrastructure/chromadb-deployment.yaml
```

---

## 🔄 CI/CD Pipeline

This project includes a GitHub Actions workflow (`.github/workflows/docker-ci.yml`) that:

1. Builds Docker images for `api-gateway`, `discovery-server`, and `flask-api`
2. Pushes images to Docker Hub (`cdquang/my-app`) with tags:
   - `{service}-latest` (e.g., `api-gateway-latest`)
   - `{service}-{commit-sha}` (e.g., `api-gateway-cacc7511...`)

**Setup GitHub Secrets:**

1. Go to your GitHub repository → Settings → Secrets and variables → Actions
2. Add:
   - `DOCKERHUB_USERNAME`: Your Docker Hub username
   - `DOCKERHUB_TOKEN`: Your Docker Hub access token

**Trigger:** The workflow runs automatically on push to `main` branch.

**Update Kubernetes to use latest images:**

After CI/CD builds new images, restart deployments to pull the latest:

```bash
kubectl rollout restart deployment/discovery-server
kubectl rollout restart deployment/flask-backend
kubectl rollout restart deployment/api-gateway
```

With `imagePullPolicy: Always`, Kubernetes will pull the latest images from Docker Hub.

---

## 📚 Service Discovery Flow

1. **Discovery Server (Eureka)** runs on port 8761 and maintains a registry of all services
2. **Flask Backend** registers itself as `FLASK-SERVICE` with Eureka on startup
3. **API Gateway** registers itself as `API-GATEWAY` with Eureka on startup
4. **API Gateway** queries Eureka to discover Flask instances when routing requests
5. If Eureka is unavailable, API Gateway falls back to `FLASK_BASE_URL` (http://flask-service)

**View registered services:**

```bash
# Port-forward Eureka dashboard
kubectl port-forward service/discovery-server 8761:8761

# Open browser: http://localhost:8761
# You should see both FLASK-SERVICE and API-GATEWAY registered
```

---

## 📖 API Documentation (Swagger)

The platform uses **Swagger/OpenAPI** for API documentation with an **aggregation pattern** for microservices:

### Architecture

1. **Each Service Exposes OpenAPI Spec**: Every microservice exposes its OpenAPI specification at `/openapi.json`
   - **Flask Service**: `/openapi.json` (generated by flasgger)
   - **API Gateway**: `/openapi.json` (manual OpenAPI 3.0 spec)

2. **API Gateway Aggregation**: The API Gateway collects specs from all registered services via `/api-docs/aggregate`
   - Queries Eureka to discover services
   - Fetches `/openapi.json` from each service
   - Returns aggregated list of all service specs

3. **Centralized Swagger UI**: Single Swagger UI endpoint at `/swagger-ui` in API Gateway
   - Displays all service APIs in one interface
   - Automatically loads specs from aggregated endpoint
   - No need to port-forward individual services

### Accessing Swagger UI

**Option 1: Via API Gateway (Recommended)**

```bash
# Port-forward API Gateway
kubectl port-forward service/api-gateway 8080:80

# Open browser: http://localhost:8080/swagger-ui
# You'll see all services' APIs in one Swagger UI
```

**Option 2: Direct Service Access (For Debugging)**

```bash
# Flask service Swagger (if you need direct access)
kubectl port-forward service/flask-service 5000:80
# Access: http://localhost:5000/apidocs (flasgger UI)
```

### API Endpoints

- **Swagger UI**: `http://localhost:8080/swagger-ui` - Centralized documentation
- **Aggregated Specs**: `http://localhost:8080/api-docs/aggregate` - JSON with all service specs
- **API Gateway Spec**: `http://localhost:8080/openapi.json` - Gateway's own OpenAPI spec
- **Flask Service Spec**: `http://localhost:5000/openapi.json` - Flask's OpenAPI spec (direct)

### Benefits of This Approach

✅ **Single Entry Point**: One Swagger UI for all services  
✅ **Service Discovery**: Automatically discovers services via Eureka  
✅ **Scalable**: Adding new services automatically includes them in Swagger UI  
✅ **No Manual Port-Forwarding**: Access all APIs through API Gateway  
✅ **Enterprise-Ready**: Follows microservices best practices

---

## 🧪 Local Testing (Before Commit)

**Important**: Always test services locally before committing to avoid breaking deployments.

### Recommended: Docker Compose (Mimics Production)

```bash
# Build and start all services
docker-compose -f docker-compose.local.yml up --build

# Test endpoints
curl http://localhost:8080/health
curl http://localhost:8080/flask

# View Eureka dashboard
# Open: http://localhost:8761

# Stop services
docker-compose -f docker-compose.local.yml down
```

**Why Docker Compose?**
- ✅ Uses same Dockerfiles as production
- ✅ Mimics Kubernetes environment
- ✅ Isolated and reproducible
- ✅ Fast to start/stop

### Alternative: Run Services Natively
**Quick Start (Native)**:

```bash
# Terminal 1: Start Eureka
cd discovery-server
mvn spring-boot:run

# Terminal 2: Start Flask
cd test
export EUREKA_SERVER_URL=http://localhost:8761
python app.py

# Terminal 3: Start API Gateway
cd api-gateway
export EUREKA_SERVER_URL=http://localhost:8761/eureka
export FLASK_BASE_URL=http://localhost:5000
go run main.go

# Test: http://localhost:8080/health
```

---

## 🧪 Testing the API (In Kubernetes)

Once services are running and port-forwarded:

```bash
# Health check
curl http://localhost:8080/health

# Flask endpoint (via API Gateway)
curl http://localhost:8080/flask

# Flask test-infrastructure endpoint
curl -X POST http://localhost:8080/flask/test-infrastructure \
  -H "Content-Type: application/json" \
  -d '{}'
```

---

## 🛠️ Troubleshooting

**Services not appearing in Eureka:**

1. Check pod logs:
   ```bash
   kubectl logs -l app=flask-backend
   kubectl logs -l app=api-gateway
   ```

2. Verify Eureka is accessible:
   ```bash
   kubectl exec -it <discovery-server-pod> -- curl http://localhost:8761
   ```

3. Check service connectivity:
   ```bash
   kubectl exec -it <api-gateway-pod> -- wget -O- http://discovery-server:8761/eureka
   ```

**Port-forward not working:**

- Ensure the service exists: `kubectl get services`
- Check if pods are running: `kubectl get pods`
- Try a different local port if the current one is in use

**Images not pulling:**

- For local development: Use `kind load docker-image` after building
- For Docker Hub: Ensure `imagePullPolicy: Always` and images are pushed to Docker Hub
- Check image tags match in manifests and Docker Hub

