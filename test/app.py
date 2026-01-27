import os
from flask import Flask, jsonify, request
from flask_cors import CORS
import chromadb
import wandb
import random
import requests
import socket
import threading
import time

app = Flask(__name__)
CORS(app)

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

    try:
        r = requests.post(register_url, data=xml, headers={"Content-Type": "application/xml"}, timeout=5)
        if r.status_code >= 200 and r.status_code <= 299:
            print(f"[eureka] registered {app_name} ({instance_id})")
        else:
            print(f"[eureka] register failed: {r.status_code} {r.text}")
            return
    except Exception as e:
        print(f"[eureka] register error: {e}")
        return

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
    # Optional: self-register to Eureka if EUREKA_SERVER_URL is set
    threading.Thread(target=_eureka_register, daemon=True).start()
    app.run(host='0.0.0.0', port=SERVICE_PORT)