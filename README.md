# Local MLOps Platform with Kubernetes (Kind)

Description .......

## 🏗 Architecture Stack

* **Cluster Orchestration:** Kubernetes (sử dụng [Kind](https://kind.sigs.k8s.io/))
* **Workflow Automation:** [n8n](https://n8n.io/)
* **Experiment Tracking:** [Weights & Biases (WandB)](https://wandb.ai/) (Self-hosted)
* **Vector Database:** [ChromaDB](https://www.trychroma.com/)
* **GitOps/Deployment:** [ArgoCD](https://argo-cd.readthedocs.io/)
* **Backend:** Python Flask
* **Infrastructure as Code:** Kubernetes YAML manifests

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

### 3. Setup Infrastructure
AgroCD

``` bash
kubectl create namespace argocd
kubectl apply -n argocd -f [https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml](https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml)
```

WandB

``` bash
docker pull wandb/local:latest
kind load docker-image wandb/local:latest
kubectl apply -f k8s/infrastructure/wandb.yaml
```

n8n and chromadb

``` bash
kubectl apply -f k8s/infrastructure/n8n.yaml
kubectl apply -f k8s/infrastructure/chromadb.yaml
```

