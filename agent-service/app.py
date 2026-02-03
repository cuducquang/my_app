import os
from flask import Flask, jsonify, request
from flask_cors import CORS
from flasgger import Swagger, swag_from
import chromadb
import mlflow
import random
import requests
import socket
import threading
import time

app = Flask(__name__)
CORS(app)

# Global variables for caching
chroma_client = None
collection = None

# --- PRE-LOAD CHROMA MODEL ---
print("⏳ Initializing ChromaDB Client & Loading Models...")
try:
    if _check_connection(CHROMA_HOST, CHROMA_PORT, timeout=3):
        chroma_client = chromadb.HttpClient(host=CHROMA_HOST, port=int(CHROMA_PORT))
        
        # Create/Get collection to trigger model loading
        collection = chroma_client.get_or_create_collection(name="test_collection")
        
        # Trigger model load into RAM with a dummy query
        collection.query(query_texts=["Hello world"], n_results=1)
        
        print("✅ Model loaded successfully! Ready to serve.")
    else:
        print(f"⚠️ Warning: Could not connect to ChromaDB at {CHROMA_HOST}:{CHROMA_PORT}")

except Exception as e:
    print(f"⚠️ Warning: Could not pre-load Chroma: {e}")


# Initialize Swagger
swagger = Swagger(app, template={
    "info": {
        "title": "Flask Backend API",
        "description": "MLOps Platform Flask Backend API for infrastructure testing",
        "version": "1.0.0"
    },
    "basePath": "/",
    "schemes": ["http", "https"]
})

CHROMA_HOST = os.getenv("CHROMA_HOST", "localhost")
CHROMA_PORT = os.getenv("CHROMA_PORT", "8000")
MLFLOW_TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI")
EUREKA_SERVER_URL = os.getenv("EUREKA_SERVER_URL", "").rstrip("/")
EUREKA_APP_NAME = os.getenv("EUREKA_APP_NAME", "FLASK-SERVICE")
EUREKA_INSTANCE_ID = os.getenv("EUREKA_INSTANCE_ID", "")
PREFER_IP = os.getenv("PREFER_IP", "true").lower() == "true"
SERVICE_PORT = int(os.getenv("PORT", "5000"))


def _local_ip():
    try:
        # best-effort: resolve hostname -> IP
        return socket.gethostbyname(socket.gethostname())
    except Exception:
        return "127.0.0.1"


def _check_connection(host, port, timeout=2):
    """Check if a TCP port is open"""
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return True
    except (socket.timeout, ConnectionRefusedError, OSError):
        return False



def _eureka_register():
    if not EUREKA_SERVER_URL:
        return

    ip = _local_ip()
    instance_id = EUREKA_INSTANCE_ID or f"{EUREKA_APP_NAME.lower()}:{ip}:{SERVICE_PORT}"
    app_name = EUREKA_APP_NAME.upper()
    base = EUREKA_SERVER_URL
    if not base.endswith("/eureka"):
        base = base + "/eureka"

    register_url = f"{base}/apps/{app_name}"
    home = f"http://{ip}:{SERVICE_PORT}/"
    health = f"http://{ip}:{SERVICE_PORT}/"

    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<instance>
  <instanceId>{instance_id}</instanceId>
  <hostName>{ip}</hostName>
  <app>{app_name}</app>
  <ipAddr>{ip}</ipAddr>
  <status>UP</status>
  <port enabled="true">{SERVICE_PORT}</port>
  <securePort enabled="false">443</securePort>
  <homePageUrl>{home}</homePageUrl>
  <statusPageUrl>{health}</statusPageUrl>
  <healthCheckUrl>{health}</healthCheckUrl>
  <dataCenterInfo class="com.netflix.appinfo.InstanceInfo$DefaultDataCenterInfo">
    <name>MyOwn</name>
  </dataCenterInfo>
</instance>"""

    # Registration retry loop
    while True:
        try:
            r = requests.post(register_url, data=xml, headers={"Content-Type": "application/xml"}, timeout=5)
            if 200 <= r.status_code <= 299:
                print(f"[eureka] registered {app_name} ({instance_id})")
                break
            else:
                print(f"[eureka] register failed: {r.status_code} {r.text}")
        except Exception as e:
            print(f"[eureka] register error: {e}")
        
        print("[eureka] retrying registration in 5s...")
        time.sleep(5)

    # heartbeat loop
    hb_url = f"{base}/apps/{app_name}/{instance_id}"
    while True:
        try:
            r = requests.put(hb_url, timeout=5)
            if r.status_code < 200 or r.status_code > 299:
                print(f"[eureka] heartbeat failed: {r.status_code} {r.text}")
        except Exception as e:
            print(f"[eureka] heartbeat error: {e}")
        time.sleep(30)

@app.route('/')
@swag_from({
    'tags': ['Health'],
    'summary': 'Health check endpoint',
    'responses': {
        200: {
            'description': 'Service is running',
            'schema': {
                'type': 'object',
                'properties': {
                    'message': {'type': 'string'}
                }
            }
        }
    }
})
def hello():
    """Health check endpoint
    ---
    """
    return jsonify({"message": "Flask API is running inside Kubernetes! 🚀"})

@app.route('/test-infrastructure', methods=['POST'])
@swag_from({
    'tags': ['Infrastructure'],
    'summary': 'Test infrastructure connections',
    'description': 'Tests connections to ChromaDB and WandB infrastructure',
    'consumes': ['application/json'],
    'produces': ['application/json'],
    'parameters': [
        {
            'name': 'body',
            'in': 'body',
            'required': False,
            'schema': {
                'type': 'object'
            }
        }
    ],
    'responses': {
        200: {
            'description': 'Test results',
            'schema': {
                'type': 'object',
                'properties': {
                    'chromadb': {'type': 'string'},
                    'wandb': {'type': 'string'}
                }
            }
        }
    }
})
def test_infra():
    """Test infrastructure connections
    ---
    """
    logs = {}
    
    # 1. Test ChromaDB Connection
    logs = {}
    
    # 1. Test ChromaDB Connection
    global collection, chroma_client
    try:
        # Use cached collection if available, else try to re-init
        if collection is None:
             if _check_connection(CHROMA_HOST, CHROMA_PORT, timeout=3):
                chroma_client = chromadb.HttpClient(host=CHROMA_HOST, port=int(CHROMA_PORT))
                collection = chroma_client.get_or_create_collection(name="test_collection")
             else:
                logs['chromadb'] = f"Failed: Could not connect to {CHROMA_HOST}:{CHROMA_PORT}"
        
        if collection:
            collection.add(
                documents=["This is a test document from Flask"],
                metadatas=[{"source": "flask_api"}],
                ids=[f"id_{random.randint(1, 1000)}"]
            )
            logs['chromadb'] = f"Success: Connected to {CHROMA_HOST}:{CHROMA_PORT} and inserted vector data (Cached)."
        elif 'chromadb' not in logs:
             logs['chromadb'] = "Error: ChromaDB not initialized."
             
    except Exception as e:
        logs['chromadb'] = f"Error: {str(e)}"
        # Reset cache on error to force retry next time
        collection = None

    # 2. Test MLflow Connection
    try:
        mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
        mlflow.set_experiment("k8s-local-test")
        
        with mlflow.start_run(run_name=f"api-test-{random.randint(1,1000)}"):
            mlflow.log_metric("accuracy", random.random())
            mlflow.log_metric("loss", random.random())
            mlflow.log_param("source", "flask-api")
            
        logs['mlflow'] = f"Success: Logged to {MLFLOW_TRACKING_URI}"
            
    except Exception as e:
        logs['mlflow'] = f"Error: {str(e)}"

    return jsonify(logs)

@app.route('/openapi.json')
def openapi_spec():
    """OpenAPI specification endpoint for service discovery"""
    return jsonify(swagger.get_apispecs())

if __name__ == '__main__':
    # Optional: self-register to Eureka if EUREKA_SERVER_URL is set
    threading.Thread(target=_eureka_register, daemon=True).start()
    app.run(host='0.0.0.0', port=SERVICE_PORT)