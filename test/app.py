import os
from flask import Flask, jsonify, request
from flask_cors import CORS
from flasgger import Swagger, swag_from
import chromadb
import wandb
import random
import requests
import socket
import threading
import time

app = Flask(__name__)
CORS(app)

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
WANDB_URL = os.getenv("WANDB_BASE_URL", "")
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
    try:
        if _check_connection(CHROMA_HOST, CHROMA_PORT, timeout=3):
            chroma_client = chromadb.HttpClient(host=CHROMA_HOST, port=int(CHROMA_PORT))
            
            collection = chroma_client.get_or_create_collection(name="test_collection")
            
            collection.add(
                documents=["This is a test document from Flask"],
                metadatas=[{"source": "flask_api"}],
                ids=[f"id_{random.randint(1, 1000)}"]
            )
            logs['chromadb'] = f"Success: Connected to {CHROMA_HOST}:{CHROMA_PORT} and inserted vector data."
        else:
             logs['chromadb'] = f"Failed: Could not connect to {CHROMA_HOST}:{CHROMA_PORT} (Connection refused or timeout)"
    except Exception as e:
        logs['chromadb'] = f"Error: {str(e)}"

    # 2. Test WandB Connection
    try:
        if WANDB_URL:
            # Parse host/port from WANDB_URL for check
            # Assumes format http://host:port
            try:
                from urllib.parse import urlparse
                parsed = urlparse(WANDB_URL)
                host = parsed.hostname
                port = parsed.port or 80
                
                if _check_connection(host, port, timeout=3):
                    run = wandb.init(project="k8s-local-test", name=f"api-test-{random.randint(1,1000)}", reinit=True)
                    wandb.log({"accuracy": random.random(), "loss": random.random()})
                    run.finish()
                    logs['wandb'] = f"Success: Logged metrics to {WANDB_URL}"
                else:
                    logs['wandb'] = f"Failed: Could not connect to WandB at {host}:{port}"
            except Exception as parse_err:
                 logs['wandb'] = f"Error parsing WANDB_URL: {str(parse_err)}"
        else:
            logs['wandb'] = "Skipped: WANDB_BASE_URL not set."
            
    except Exception as e:
        logs['wandb'] = f"Error: {str(e)}"

    return jsonify(logs)

@app.route('/openapi.json')
def openapi_spec():
    """OpenAPI specification endpoint for service discovery"""
    return jsonify(swagger.get_apispecs())

if __name__ == '__main__':
    # Optional: self-register to Eureka if EUREKA_SERVER_URL is set
    threading.Thread(target=_eureka_register, daemon=True).start()
    app.run(host='0.0.0.0', port=SERVICE_PORT)