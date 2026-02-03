import json
import queue
import threading
import time
from typing import Any, Dict

from flasgger import Swagger, swag_from
from flask import Flask, jsonify, request, g
from flask_cors import CORS
from werkzeug.exceptions import HTTPException

from app.config import load_config
from app.orchestrator import Orchestrator
from app.services.eureka import eureka_register
from app.tools.plugins import load_skill_plugins
from app.tools.registry import ToolRegistry
from app.utils.formatting import format_recommendations_text
from app.utils.logging import REQUEST_ID_HEADER, get_logger
from app.clients.mcp import MCPClient


CONFIG = load_config()
logger = get_logger()


def mask_key(value: str) -> str:
    if not value:
        return "missing"
    if len(value) <= 8:
        return value[0] + "***"
    return value[:6] + "..." + value[-4:]


def create_app() -> Flask:
    app = Flask(__name__)
    CORS(app)

    Swagger(
        app,
        template={
            "info": {
                "title": "Agent Service API",
                "description": "Multi-agent trip recommendation service",
                "version": "2.0.0",
            },
            "basePath": "/",
            "schemes": ["http", "https"],
        },
    )

    @app.before_request
    def assign_request_id() -> None:
        g.request_id = request.headers.get(REQUEST_ID_HEADER) or str(time.time_ns())

    @app.after_request
    def add_request_id_header(response):  # type: ignore[no-untyped-def]
        response.headers[REQUEST_ID_HEADER] = g.request_id or ""
        return response

    @app.errorhandler(Exception)
    def handle_exception(error):  # type: ignore[no-untyped-def]
        if isinstance(error, HTTPException):
            return error
        logger.exception("unhandled error: %s", error)
        return jsonify({"error": "internal_error", "request_id": g.request_id}), 500

    registry = ToolRegistry()
    def chrome_mcp_browse(url: str, instructions: str = "") -> Dict[str, Any]:
        if not CONFIG.chrome_mcp_url:
            return {"status": "not_configured", "message": "CHROME_MCP_URL is not set", "url": url}
        client = MCPClient(CONFIG.chrome_mcp_url)
        page = client.call_tool("new_page", {"url": url})
        page_result = page.get("result") if isinstance(page, dict) else {}
        page_id = page_result.get("pageId") if isinstance(page_result, dict) else None
        if page_id is not None:
            client.call_tool("select_page", {"pageId": page_id, "bringToFront": False})
            client.call_tool("wait_for", {"text": "Vietnam", "timeout": 8000})

        eval_result = client.call_tool(
            "evaluate_script",
            {
                "function": """() => {
  const titles = Array.from(document.querySelectorAll('h3')).map((el) => el.innerText).filter(Boolean);
  const anchors = Array.from(document.querySelectorAll('a')).map((el) => el.innerText).filter(Boolean);
  const bodyText = document.body && document.body.innerText ? document.body.innerText : '';
  return {
    titles: titles.slice(0, 15),
    anchors: anchors.slice(0, 20),
    bodyText: bodyText.slice(0, 20000),
  };
}""",
            },
        )
        eval_payload = {}
        if isinstance(eval_result, dict):
            eval_payload = eval_result.get("result") or {}
        eval_text = ""
        eval_titles = []
        if isinstance(eval_payload, dict):
            eval_text = str(eval_payload.get("bodyText") or "")
            eval_titles = eval_payload.get("titles") or []

        snapshot = client.call_tool("take_snapshot", {"verbose": True})
        snapshot_result = snapshot.get("result") if isinstance(snapshot, dict) else snapshot
        snapshot_text = ""
        if isinstance(snapshot_result, dict):
            snapshot_text = str(snapshot_result.get("content") or snapshot_result.get("snapshot") or "")
        return {
            "status": "ok",
            "page": page,
            "eval_text": eval_text,
            "eval_titles": eval_titles,
            "snapshot": snapshot,
            "snapshot_text": snapshot_text,
            "instructions": instructions,
        }

    registry.register_simple(
        name="chrome_mcp_browse",
        description="Use Chrome MCP to browse a page (if configured)",
        schema={"url": "string", "instructions": "string"},
        handler=chrome_mcp_browse,
    )

    skills_dir = "app/skills"
    loaded_skills = load_skill_plugins(registry, skills_dir)
    orchestrator = Orchestrator(CONFIG, registry)

    logger.info(
        "agent-service config providers: agent1=%s agent2=%s agent3=%s",
        CONFIG.agent_providers.get("agent1"),
        CONFIG.agent_providers.get("agent2"),
        CONFIG.agent_providers.get("agent3"),
    )
    logger.info(
        "agent-service api keys: agent1=%s agent2=%s agent3=%s",
        mask_key(CONFIG.agent_keys.get("agent1", "")),
        mask_key(CONFIG.agent_keys.get("agent2", "")),
        mask_key(CONFIG.agent_keys.get("agent3", "")),
    )

    @app.route("/")
    def root() -> Any:
        return jsonify(
            {
                "service": "agent-service",
                "status": "running",
                "endpoints": ["/health", "/recommendations", "/plan", "/openapi.json"],
                "skills_loaded": loaded_skills,
            }
        )

    @app.route("/health")
    def health() -> Any:
        return jsonify({"status": "ok"})

    @app.route("/recommendations", methods=["POST"])
    @swag_from(
        {
            "tags": ["Agent"],
            "summary": "Generate trip recommendations",
            "parameters": [
                {
                    "name": "body",
                    "in": "body",
                    "required": True,
                    "schema": {
                        "type": "object",
                        "properties": {
                            "days": {"type": "integer"},
                            "budget": {"type": "number"},
                            "budget_scope": {"type": "string"},
                            "people": {"type": "integer"},
                            "group_type": {"type": "string"},
                            "interests": {"type": "array", "items": {"type": "string"}},
                            "origin": {"type": "string"},
                            "season": {"type": "string"},
                        },
                    },
                }
            ],
            "responses": {
                200: {"description": "Recommendations generated"},
                400: {"description": "Invalid request"},
            },
        }
    )
    def recommendations() -> Any:
        payload = request.get_json(silent=True)
        if payload is None:
            payload = {}
        if not isinstance(payload, dict):
            return jsonify({"error": "payload must be a JSON object"}), 400
        result = orchestrator.run(payload)
        result["answer"] = format_recommendations_text(result)
        return jsonify(result)

    def stream_recommendations(payload: Dict[str, Any]):
        q: "queue.Queue[Dict[str, Any]]" = queue.Queue()

        def emit(event: str, data: Dict[str, Any]):
            q.put({"event": event, "data": data})

        def worker():
            try:
                result = orchestrator.run_with_stream(payload, emit)
                message = format_recommendations_text(result)
                result["answer"] = message
                for token in message.split():
                    emit("token", {"text": token + " "})
                    time.sleep(0.02)
                emit("final", result)
            except Exception as exc:
                emit("error", {"message": str(exc)})
            finally:
                emit("done", {})

        threading.Thread(target=worker, daemon=True).start()

        while True:
            item = q.get()
            event = item.get("event", "message")
            data = json.dumps(item.get("data", {}))
            yield f"event: {event}\ndata: {data}\n\n"
            if event == "done":
                break

    @app.route("/recommendations/stream", methods=["POST"])
    def recommendations_stream() -> Any:
        payload = request.get_json(silent=True)
        if payload is None:
            payload = {}
        if not isinstance(payload, dict):
            return jsonify({"error": "payload must be a JSON object"}), 400

        return app.response_class(
            stream_recommendations(payload),
            mimetype="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    @app.route("/plan", methods=["POST"])
    def plan() -> Any:
        payload = request.get_json(silent=True)
        if payload is None:
            payload = {}
        if not isinstance(payload, dict):
            return jsonify({"error": "payload must be a JSON object"}), 400
        result = orchestrator.run(payload)
        return jsonify(result)

    @app.route("/openapi.json")
    def openapi_spec() -> Any:
        return jsonify(app.extensions["swagger"].get_apispecs())

    return app


app = create_app()


if __name__ == "__main__":
    threading.Thread(target=eureka_register, args=(CONFIG,), daemon=True).start()
    app.run(host="0.0.0.0", port=CONFIG.port)

