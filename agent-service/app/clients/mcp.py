from typing import Any, Dict
import uuid

import requests


class MCPClient:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    def _post(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        res = requests.post(self.base_url, json=payload, timeout=20)
        if res.status_code >= 400:
            return {"error": f"HTTP {res.status_code}", "details": res.text}
        return res.json()

    def list_tools(self) -> Dict[str, Any]:
        payload = {"jsonrpc": "2.0", "id": str(uuid.uuid4()), "method": "tools/list"}
        return self._post(payload)

    def call_tool(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        payload = {
            "jsonrpc": "2.0",
            "id": str(uuid.uuid4()),
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        }
        return self._post(payload)

