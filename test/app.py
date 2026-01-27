import os
from flask import Flask, jsonify, request
from flask_cors import CORS
import chromadb
import wandb
import random

app = Flask(__name__)
CORS(app)

CHROMA_HOST = os.getenv("CHROMA_HOST", "localhost")
CHROMA_PORT = os.getenv("CHROMA_PORT", "8000")
WANDB_URL = os.getenv("WANDB_BASE_URL", "")

@app.route('/')
def hello():
    return jsonify({"message": "Flask API is running inside Kubernetes! 🚀"})

@app.route('/test-infrastructure', methods=['POST'])
def test_infra():
    logs = {}
    
    try:
        chroma_client = chromadb.HttpClient(host=CHROMA_HOST, port=int(CHROMA_PORT))
        
        collection = chroma_client.get_or_create_collection(name="test_collection")
        
        collection.add(
            documents=["This is a test document from Flask"],
            metadatas=[{"source": "flask_api"}],
            ids=["id1"]
        )
        logs['chromadb'] = "Success: Connected and inserted vector data."
    except Exception as e:
        logs['chromadb'] = f"Error: {str(e)}"

    # 2. Test WandB Connection
    try:
        if WANDB_URL:
            run = wandb.init(project="k8s-local-test", name=f"api-test-{random.randint(1,1000)}")
            wandb.log({"accuracy": random.random(), "loss": random.random()})
            run.finish()
            logs['wandb'] = f"Success: Logged metrics to {WANDB_URL}"
        else:
            logs['wandb'] = "Skipped: WANDB_BASE_URL not set."
            
    except Exception as e:
        logs['wandb'] = f"Error: {str(e)}"

    return jsonify(logs)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)